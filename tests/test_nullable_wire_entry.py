"""TASK-4：进线结束时间 / 进线总时长放宽为可空。

两层验收：
1. 接口层：这两字段给 null（或不传）→ 200 入库，详情原样返回 null，
   abnormal 语义不受影响（数据缺口不是工艺异常）。
2. 迁移 v5：已迁到 v4（列齐全、两列仍 NOT NULL）的老库，
   跑 migrate 走既有重建路径放开两列；数据不丢、行数对得上、二次运行幂等。
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Container, get_container
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app
from scripts.migrate_db import (
    _is_migrated,
    _main_table_ddl,
    _needs_nullable_relax,
    _schema_statements,
    migrate,
)

STANDARD = {
    "standard_spheroidization_time": 75.0,
    "weighing_standard": 1500.0,
    "remark": "TASK-4 接口测试",
}

# 正常炉：亮光齐、进线开始/重量齐，唯独进线结束/总时长为 null（PLC 没采到）
NULL_WIRE_RECORD = {
    "detection_time": "2026-11-03 09:12:27.900",
    "spheroidization_start_time": "2026-11-03 09:12:31.400",
    "spheroidization_end_time": "2026-11-03 09:14:06.855",
    "actual_spheroidization_time": 95.455,
    "spheroidization_abnormal": 0,
    "abnormal_type": 0,
    "spheroidization_wire_entry_start_time": "2026-11-03 09:12:31.000",
    "spheroidization_wire_entry_end_time": None,
    "spheroidization_wire_entry_total_duration": None,
    "spheroidization_weight": 1608.0,
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SPHEROIDIZATION_DB", str(tmp_path / "test.db"))
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_tables(conn)
    container = Container(
        conn=conn,
        standard_application_state=JsonStandardApplicationState(
            tmp_path / "active_standard.json"
        ),
    )
    app.dependency_overrides[get_container] = lambda: container

    with TestClient(app) as client:
        container.create_user().execute("root", "pass1234", True, "system")
        body = client.post(
            "/api/users/login", json={"username": "root", "password": "pass1234"}
        ).json()
        headers = {"Authorization": f"Bearer {body['data']['token']}"}
        client.post("/api/standards", json=STANDARD, headers=headers)
        yield client, container, headers

    app.dependency_overrides.clear()
    conn.close()


def test_进线结束和时长为null也入库且详情原样返回null(env):
    client, container, headers = env
    payload = dict(NULL_WIRE_RECORD)

    body = client.post("/api/spheroidization", json=payload).json()
    assert body["code"] == 200, body
    record_id = body["data"]["id"]

    detail = client.get(f"/api/spheroidization/{record_id}", headers=headers).json()
    assert detail["code"] == 200
    data = detail["data"]
    # 缺的就是空，原样返回 null，不许填占位值
    assert data["spheroidization_wire_entry_end_time"] is None
    assert data["spheroidization_wire_entry_total_duration"] is None
    # 其余物性字段不受影响
    assert data["spheroidization_wire_entry_start_time"] == "2026-11-03 09:12:31.000"
    assert data["spheroidization_weight"] == 1608.0
    # 数据缺口不是工艺异常：abnormal 保持给进来的 0，不许被置 1
    assert data["spheroidization_abnormal"] is False
    assert data["abnormal_type"] == 0
    assert data["abnormal_reason"] is None

    # 库里这两列是真 NULL，不是空串/0
    row = container.conn.execute(
        "SELECT spheroidization_wire_entry_end_time, spheroidization_wire_entry_total_duration"
        " FROM SpheroidizationRecord WHERE spheroidization_record_id = ?",
        (record_id,),
    ).fetchone()
    assert row[0] is None and row[1] is None


def test_幂等路径同样接受null且重放命中(env):
    client, container, _ = env
    payload = dict(NULL_WIRE_RECORD)
    # 合并层 heat 路径的口径：带幂等键，且直接不传这两字段（默认 None）
    payload["device_id"] = "casting-1"
    payload["external_id"] = "9001"
    payload.pop("spheroidization_wire_entry_end_time")
    payload.pop("spheroidization_wire_entry_total_duration")

    first = client.post("/api/spheroidization", json=payload).json()
    assert first["code"] == 200, first
    assert first["data"]["existing"] is False

    second = client.post("/api/spheroidization", json=payload).json()
    assert second["code"] == 200
    assert second["data"]["existing"] is True
    assert second["data"]["id"] == first["data"]["id"]
    assert container.conn.execute(
        "SELECT COUNT(*) FROM SpheroidizationRecord"
    ).fetchone()[0] == 1


# ---------------- 迁移 v5 ----------------


def _old_main_table_ddl() -> str:
    """v4 时代的主表 DDL：列齐全，但进线两列仍是 NOT NULL。

    直接取当前 schema.sql 的主表 DDL 再给这两列加回 NOT NULL，
    保证除了这两列的约束、和当前正式版逐字一致。
    """
    ddl = _main_table_ddl()
    ddl = ddl.replace(
        "spheroidization_wire_entry_end_time TEXT,",
        "spheroidization_wire_entry_end_time TEXT NOT NULL,",
    )
    ddl = ddl.replace(
        "spheroidization_wire_entry_total_duration REAL,",
        "spheroidization_wire_entry_total_duration REAL NOT NULL,",
    )
    assert "spheroidization_wire_entry_end_time TEXT NOT NULL" in ddl
    assert "spheroidization_wire_entry_total_duration REAL NOT NULL" in ddl
    return ddl


def _build_v4_era_db(db_path: Path) -> None:
    """造一个已迁到 v4 的老库：主表列齐全（两列 NOT NULL）+ v3/v4 表都在，
    并插 2 行进线两列非空的记录。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # 老库当时已有的表：标准表 + 主表 + v3/v4 的三张表
        wanted = {"StandardRecord", "UploadLedger", "FlashSegment", "AuditLog"}
        for name, stmt in _schema_statements():
            if name in wanted:
                conn.execute(stmt)
        conn.execute(_old_main_table_ddl())

        conn.execute(
            "INSERT INTO StandardRecord"
            " (standard_spheroidization_time, standard_spheroidization_time_upper,"
            "  standard_spheroidization_time_lower, weighing_standard,"
            "   created_at, created_by)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (75.0, 90.0, 60.0, 1500.0, "2026-09-01 08:00:00", "张三"),
        )
        rows = [
            ("2026-10-20 08:30:15", "2026-10-20 08:30:20", "2026-10-20 08:31:25",
             65.0, 65.0, 0, 0, None, None, 0, None, None,
             "2026-10-20 08:30:40", "2026-10-20 08:32:00", 80.0, 1608.0),
            ("2026-10-20 09:15:32", "2026-10-20 09:15:40", "2026-10-20 09:17:05",
             85.0, 65.0, 1, 3, "球化超时", None, 0, None, None,
             "2026-10-20 09:15:50", "2026-10-20 09:18:30", 160.0, 1580.0),
        ]
        for (det, st, et, act, snap, abn, atype, areason, btn,
             proc, pat, pby, ws, we, wd, wt) in rows:
            conn.execute(
                "INSERT INTO SpheroidizationRecord"
                " (standard_record_id, detection_time, spheroidization_start_time,"
                "  spheroidization_end_time, actual_spheroidization_time,"
                "  standard_spheroidization_time, spheroidization_abnormal,"
                "  abnormal_type, abnormal_reason, plc_button_time,"
                "  processed, processed_at, processed_by,"
                "  spheroidization_wire_entry_start_time,"
                "  spheroidization_wire_entry_end_time,"
                "  spheroidization_wire_entry_total_duration, spheroidization_weight)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, det, st, et, act, snap, abn, atype, areason, btn,
                 proc, pat, pby, ws, we, wd, wt),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def v4_era_db(tmp_path, monkeypatch):
    """一个「列齐全但进线两列还 NOT NULL」的老库 + 备份目录指到临时区。"""
    db_path = tmp_path / "v4-era.db"
    _build_v4_era_db(db_path)
    # 迁移会往 data/backups/ 写备份，测试里不能污染仓库
    monkeypatch.setattr(
        "scripts.migrate_db.BACKUP_DIR", tmp_path / "backups"
    )
    return db_path


def test_v5判定_老库识别为新库不识别(v4_era_db):
    conn = sqlite3.connect(v4_era_db)
    conn.row_factory = sqlite3.Row
    try:
        assert _needs_nullable_relax(conn) is True
        # 列齐全 + v3/v4 表都在，但 NOT NULL 没放开 → 不算已迁移
        assert _is_migrated(conn) is False
    finally:
        conn.close()

    fresh = sqlite3.connect(":memory:")
    fresh.row_factory = sqlite3.Row
    create_tables(fresh)
    try:
        assert _needs_nullable_relax(fresh) is False
        assert _is_migrated(fresh) is True
    finally:
        fresh.close()


def test_迁移v5_放开两列且数据不丢(v4_era_db):
    before = sqlite3.connect(v4_era_db)
    before.row_factory = sqlite3.Row
    try:
        original = before.execute(
            "SELECT spheroidization_record_id, detection_time,"
            " spheroidization_wire_entry_end_time,"
            " spheroidization_wire_entry_total_duration,"
            " spheroidization_weight"
            " FROM SpheroidizationRecord ORDER BY spheroidization_record_id"
        ).fetchall()
        row_count = before.execute(
            "SELECT COUNT(*) FROM SpheroidizationRecord"
        ).fetchone()[0]
    finally:
        before.close()

    assert migrate(v4_era_db) == 0

    conn = sqlite3.connect(v4_era_db)
    conn.row_factory = sqlite3.Row
    try:
        # ① 两列不再带 NOT NULL：能直接插一行这两列为 NULL 的记录
        assert _needs_nullable_relax(conn) is False
        assert _is_migrated(conn) is True
        conn.execute(
            "INSERT INTO SpheroidizationRecord"
            " (standard_record_id, detection_time, standard_spheroidization_time,"
            "  spheroidization_wire_entry_start_time, spheroidization_weight)"
            " VALUES (?, ?, ?, ?, ?)",
            (1, "2026-11-03 10:00:00", 75.0, "2026-11-03 10:00:10", 1600.0),
        )
        # ② 原有行数不丢、数据原样
        assert conn.execute(
            "SELECT COUNT(*) FROM SpheroidizationRecord"
        ).fetchone()[0] == row_count + 1
        after = conn.execute(
            "SELECT spheroidization_record_id, detection_time,"
            " spheroidization_wire_entry_end_time,"
            " spheroidization_wire_entry_total_duration,"
            " spheroidization_weight"
            " FROM SpheroidizationRecord ORDER BY spheroidization_record_id"
        ).fetchall()
        assert [tuple(r) for r in after[: len(original)]] == [
            tuple(r) for r in original
        ]
    finally:
        conn.close()


def test_迁移v5_二次运行幂等不重建(v4_era_db, capsys):
    assert migrate(v4_era_db) == 0
    conn = sqlite3.connect(v4_era_db)
    conn.row_factory = sqlite3.Row
    try:
        ddl_before = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table'"
            " AND name='SpheroidizationRecord'"
        ).fetchone()[0]
        count_before = conn.execute(
            "SELECT COUNT(*) FROM SpheroidizationRecord"
        ).fetchone()[0]
    finally:
        conn.close()

    rc = migrate(v4_era_db)
    out = capsys.readouterr().out
    assert rc == 0
    # 幂等：第二次直接判「已迁移」提前返回——
    # 输出以这句结尾，说明没有再走备份/建表/重建那一段
    assert out.strip().endswith("已经是正式版结构，无需迁移。")

    conn = sqlite3.connect(v4_era_db)
    conn.row_factory = sqlite3.Row
    try:
        ddl_after = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table'"
            " AND name='SpheroidizationRecord'"
        ).fetchone()[0]
        count_after = conn.execute(
            "SELECT COUNT(*) FROM SpheroidizationRecord"
        ).fetchone()[0]
    finally:
        conn.close()
    assert ddl_after == ddl_before
    assert count_after == count_before
