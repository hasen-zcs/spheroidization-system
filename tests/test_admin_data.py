"""TASK-8 管理员数据管理验收测试。

覆盖任务书 F 节最小集：
- 软删后：列表不返回 / count 减 / 报表 summary 减 / 详情 404
- 软删不物理删、不级联（UploadLedger / FlashSegment 行数不变）
- 当前生效标准不许删；非当前标准可删且不影响当前
- 标准/切换日志/复核各自软删后对应列表不含
- 处理状态 0↔1 往返（三字段齐/清空）
- 权限：游客 401、无权限 403、有权限放行
- 审计：每次操作 1 条、actor/action/target_id 正确、detail 不含图片
- 幂等：重复删除/恢复不新增审计行
- 迁移脚本跑两遍幂等、行数不变
"""

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import scripts.migrate_db as m
from app.core import permissions as P
from app.dependencies import Container, get_container
from app.domain.audit.entities import AuditAction, AuditTarget
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app

from tests.conftest import create_record, create_standard, create_user


@pytest.fixture
def env(tmp_path):
    """空库 + 容器 + TestClient：超管 + 两条标准（第 2 条当前生效）+ 一条异常记录。"""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_tables(conn)
    state_path = tmp_path / "active_standard.json"
    container = Container(
        conn=conn,
        standard_application_state=JsonStandardApplicationState(state_path),
    )
    app.dependency_overrides[get_container] = lambda: container

    with TestClient(app) as client:
        create_user(container, "root", is_admin=True)
        create_standard(container, 65.0, "root", remark="初始")
        create_standard(container, 70.0, "root", remark="调整")
        rec = create_record(container, "2026-11-03 08:00:00", 70.0, abnormal=1)
        yield client, container, rec

    app.dependency_overrides.clear()
    conn.close()


def _login(client, username, password="pass1234"):
    token = client.post(
        "/api/users/login",
        json={"username": username, "password": password},
    ).json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _make_user(container, username, permissions, is_admin=False):
    user = create_user(container, username, is_admin=is_admin)
    if permissions:
        container.user_permission().replace(user.user_id, permissions)
    return user


def _audit_rows(container, action=None):
    rows = [
        dict(r)
        for r in container.conn.execute(
            "SELECT * FROM AuditLog ORDER BY audit_id"
        ).fetchall()
    ]
    if action is not None:
        rows = [r for r in rows if r["action"] == action]
    return rows


def _non_current_standard_id(client, headers):
    """取两条标准里"非当前生效"的那条 id。"""
    current = client.get("/api/standards/current").json()["data"]["id"]
    ids = [s["id"] for s in client.get("/api/standards/history", headers=headers).json()["data"]]
    return next(i for i in ids if i != current)


# ============================================================
# 球化记录软删除
# ============================================================

def test_软删记录后列表计数与报表都减(env):
    client, container, rec = env
    headers = _login(client, "root")
    rid = rec.spheroidization_record_id
    before = client.get("/api/spheroidization", headers=headers).json()["data"]["total"]
    report_before = client.get("/api/reports/summary", headers=headers).json()["data"]["total"]
    assert before == 1 and report_before == 1

    resp = client.post(f"/api/admin/records/{rid}/delete", json={"reason": "误录"}, headers=headers).json()
    assert resp["code"] == 200

    after = client.get("/api/spheroidization", headers=headers).json()["data"]
    assert after["total"] == 0
    report_after = client.get("/api/reports/summary", headers=headers).json()["data"]["total"]
    assert report_after == report_before - 1


def test_软删记录后详情404且仓储取不到(env):
    client, container, rec = env
    headers = _login(client, "root")
    rid = rec.spheroidization_record_id
    client.post(f"/api/admin/records/{rid}/delete", json={"reason": "x"}, headers=headers)
    assert client.get(f"/api/spheroidization/{rid}", headers=headers).json()["code"] == 404
    assert container.spheroid_repo.get_by_id(rid) is None


def test_软删记录不物理删不级联(env):
    client, container, rec = env
    headers = _login(client, "root")
    rid = rec.spheroidization_record_id
    conn = container.conn
    # 先给这条记录挂上台账和分段，验证软删不会把它们级联物理删掉
    conn.execute(
        "INSERT INTO UploadLedger (device_id, external_id, record_id, payload_sha, created_at)"
        " VALUES ('casting-1', 'e1', ?, 'sha', '2026-11-03 08:00:00')",
        (rid,),
    )
    conn.execute(
        "INSERT INTO FlashSegment (spheroidization_record_id, seg_index, start_offset, end_offset, duration)"
        " VALUES (?, 1, 0, 2, 2)",
        (rid,),
    )
    conn.commit()

    client.post(f"/api/admin/records/{rid}/delete", json={"reason": "x"}, headers=headers)

    # 主表行数不变（软删不删行，只是置 deleted_at）
    assert conn.execute("SELECT COUNT(*) FROM SpheroidizationRecord").fetchone()[0] == 1
    assert conn.execute("SELECT deleted_at FROM SpheroidizationRecord WHERE spheroidization_record_id=?", (rid,)).fetchone()[0] is not None
    # 关联表行数不变（没有物理 DELETE 触发 CASCADE）
    assert conn.execute("SELECT COUNT(*) FROM UploadLedger WHERE record_id=?", (rid,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM FlashSegment WHERE spheroidization_record_id=?", (rid,)).fetchone()[0] == 1


# ============================================================
# 检测标准软删除
# ============================================================

def test_当前生效标准不许软删(env):
    client, container, rec = env
    headers = _login(client, "root")
    current = client.get("/api/standards/current").json()["data"]["id"]
    resp = client.post(f"/api/admin/standards/{current}/delete", json={"reason": "x"}, headers=headers).json()
    assert resp["code"] == 400
    assert resp["message"] == "该标准当前生效，请先切换标准后再作废"
    assert container.conn.execute(
        "SELECT deleted_at FROM StandardRecord WHERE standard_record_id=?", (current,)
    ).fetchone()[0] is None


def test_非当前标准软删成功且不影响当前(env):
    client, container, rec = env
    headers = _login(client, "root")
    current = client.get("/api/standards/current").json()["data"]["id"]
    other = _non_current_standard_id(client, headers)
    resp = client.post(f"/api/admin/standards/{other}/delete", json={"reason": "作废"}, headers=headers).json()
    assert resp["code"] == 200
    # 当前标准不受影响
    assert client.get("/api/standards/current").json()["data"]["id"] == current


def test_软删标准后历史列表不含(env):
    client, container, rec = env
    headers = _login(client, "root")
    current = client.get("/api/standards/current").json()["data"]["id"]
    other = _non_current_standard_id(client, headers)
    client.post(f"/api/admin/standards/{other}/delete", json={"reason": "作废"}, headers=headers)
    ids = [s["id"] for s in client.get("/api/standards/history", headers=headers).json()["data"]]
    assert other not in ids
    assert current in ids


# ============================================================
# 切换日志 / 复核记录软删除
# ============================================================

def test_软删切换日志后列表不含且标准仍可查(env):
    client, container, rec = env
    headers = _login(client, "root")
    current = client.get("/api/standards/current").json()["data"]["id"]
    other = _non_current_standard_id(client, headers)
    # 切一次，产生一条切换日志
    client.post("/api/standards/switch", json={"to_standard_record_id": other, "reason": "回退"}, headers=headers)
    logs = client.get("/api/standards/switch-logs", headers=headers).json()["data"]["items"]
    assert len(logs) == 1
    log_id = logs[0]["id"]

    client.post(f"/api/admin/switch-logs/{log_id}/delete", json={"reason": "清理"}, headers=headers)

    assert client.get("/api/standards/switch-logs", headers=headers).json()["data"]["items"] == []
    # 标准本身没被动，仍可查
    assert client.get("/api/standards/current").json()["code"] == 200


def test_软删复核记录后该记录复核列表不含(env):
    client, container, rec = env
    headers = _login(client, "root")
    rid = rec.spheroidization_record_id
    rev = client.post(
        "/api/reviews",
        json={"spheroidization_record_id": rid, "review_result": "异常", "review_remark": "确认"},
        headers=headers,
    ).json()
    assert rev["code"] == 200
    rev_id = rev["data"]["id"]
    assert len(client.get(f"/api/reviews/{rid}", headers=headers).json()["data"]) == 1

    client.post(f"/api/admin/reviews/{rev_id}/delete", json={"reason": "复核作废"}, headers=headers)

    assert client.get(f"/api/reviews/{rid}", headers=headers).json()["data"] == []


# ============================================================
# 处理状态往返
# ============================================================

def test_处理状态往返(env):
    client, container, rec = env
    headers = _login(client, "root")
    rid = rec.spheroidization_record_id
    conn = container.conn

    r1 = client.post(f"/api/admin/records/{rid}/processed", json={"processed": 1, "reason": "已处理"}, headers=headers).json()
    assert r1["code"] == 200
    row = conn.execute(
        "SELECT processed, processed_by, processed_at FROM SpheroidizationRecord WHERE spheroidization_record_id=?", (rid,)
    ).fetchone()
    assert row["processed"] == 1 and row["processed_by"] == "root" and row["processed_at"] is not None

    r0 = client.post(f"/api/admin/records/{rid}/processed", json={"processed": 0, "reason": "回退"}, headers=headers).json()
    assert r0["code"] == 200
    row = conn.execute(
        "SELECT processed, processed_by, processed_at FROM SpheroidizationRecord WHERE spheroidization_record_id=?", (rid,)
    ).fetchone()
    assert row["processed"] == 0 and row["processed_by"] is None and row["processed_at"] is None


def test_处理状态原因必填(env):
    client, container, rec = env
    headers = _login(client, "root")
    rid = rec.spheroidization_record_id
    assert (
        client.post(f"/api/admin/records/{rid}/processed", json={"processed": 1, "reason": "   "}, headers=headers).json()["code"]
        == 400
    )
    # 删同理
    assert (
        client.post(f"/api/admin/records/{rid}/delete", json={"reason": "   "}, headers=headers).json()["code"]
        == 400
    )


# ============================================================
# 权限
# ============================================================

def test_权限控制(env):
    client, container, rec = env
    rid = rec.spheroidization_record_id

    # 游客 → 401
    assert client.post(f"/api/admin/records/{rid}/delete", json={"reason": "x"}).json()["code"] == 401

    # 登录但无 action:manage_data → 403
    _make_user(container, "worker", ["page:records"])
    worker = _login(client, "worker")
    assert client.post(f"/api/admin/records/{rid}/delete", json={"reason": "x"}, headers=worker).json()["code"] == 403

    # 有 action:manage_data → 放行
    _make_user(container, "manager", [P.ACTION_MANAGE_DATA])
    manager = _login(client, "manager")
    assert client.post(f"/api/admin/records/{rid}/delete", json={"reason": "x"}, headers=manager).json()["code"] == 200


def test_include_deleted需要管理权限(env):
    client, container, rec = env
    rid = rec.spheroidization_record_id
    root = _login(client, "root")
    client.post(f"/api/admin/records/{rid}/delete", json={"reason": "x"}, headers=root)

    # 有权限：能看到已删除行，且带上 deleted 三字段
    inc = client.get("/api/spheroidization", headers=root, params={"include_deleted": "true"}).json()["data"]
    assert inc["total"] == 1
    assert inc["items"][0]["deleted_at"] is not None
    assert inc["items"][0]["deleted_by"] == "root"
    assert inc["items"][0]["delete_reason"] == "x"

    # 无权限 → 403
    _make_user(container, "worker", ["page:records"])
    worker = _login(client, "worker")
    assert client.get("/api/spheroidization", headers=worker, params={"include_deleted": "true"}).json()["code"] == 403
    # 游客 → 401
    assert client.get("/api/spheroidization", params={"include_deleted": "true"}).json()["code"] == 401


# ============================================================
# 审计 + 幂等
# ============================================================

def test_每次操作写一条审计且不含图片(env):
    client, container, rec = env
    headers = _login(client, "root")
    rid = rec.spheroidization_record_id
    client.post(f"/api/admin/records/{rid}/delete", json={"reason": "误录"}, headers=headers)

    rows = _audit_rows(container, AuditAction.DELETE_RECORD)
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "root"
    assert row["target_type"] == AuditTarget.SPHEROIDIZATION_RECORD
    assert row["target_id"] == str(rid)
    detail = json.loads(row["detail"])
    assert detail["before"]["deleted_at"] is None
    assert detail["after"]["deleted_at"] is not None
    assert detail["after"]["deleted_by"] == "root"
    assert detail["after"]["delete_reason"] == "误录"
    # 图片 BLOB 不进审计
    assert "spheroidization_image" not in row["detail"]


def test_重复删除恢复幂等不新增审计(env):
    client, container, rec = env
    headers = _login(client, "root")
    rid = rec.spheroidization_record_id

    assert client.post(f"/api/admin/records/{rid}/delete", json={"reason": "x"}, headers=headers).json()["code"] == 200
    assert client.post(f"/api/admin/records/{rid}/delete", json={"reason": "x"}, headers=headers).json()["code"] == 200
    assert len(_audit_rows(container, AuditAction.DELETE_RECORD)) == 1

    assert client.post(f"/api/admin/records/{rid}/restore", json={}, headers=headers).json()["code"] == 200
    assert client.post(f"/api/admin/records/{rid}/restore", json={}, headers=headers).json()["code"] == 200
    assert len(_audit_rows(container, AuditAction.RESTORE_RECORD)) == 1
    # 恢复后记录回来了
    assert client.get("/api/spheroidization", headers=headers).json()["data"]["total"] == 1


def test_目标不存在返回404(env):
    client, container, rec = env
    headers = _login(client, "root")
    assert client.post("/api/admin/records/99999/delete", json={"reason": "x"}, headers=headers).json()["code"] == 404
    assert client.post("/api/admin/records/99999/restore", json={}, headers=headers).json()["code"] == 404
    assert client.post("/api/admin/records/99999/processed", json={"processed": 1, "reason": "x"}, headers=headers).json()["code"] == 404


# ============================================================
# 迁移脚本幂等
# ============================================================

def test_迁移脚本跑两遍幂等行数不变(tmp_path, monkeypatch):
    # 备份目录指到临时目录，别污染仓库 data/backups
    monkeypatch.setattr(m, "BACKUP_DIR", tmp_path / "backups")
    db = tmp_path / "old.db"

    # 造一个"pre-v6"库：先按 v6 schema 建表，再把软删除三列 DROP 掉
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    create_tables(conn)
    for table in m.SOFT_DELETE_TABLES:
        for col in m.SOFT_DELETE_COLUMNS:
            conn.execute(f'ALTER TABLE "{table}" DROP COLUMN {col}')
    conn.execute(
        "INSERT INTO StandardRecord (standard_spheroidization_time, weighing_standard, created_at, created_by)"
        " VALUES (70, 1500, '2026-01-01 00:00:00', 'x')"
    )
    conn.execute(
        "INSERT INTO SpheroidizationRecord (standard_record_id, detection_time,"
        " standard_spheroidization_time, spheroidization_wire_entry_start_time, spheroidization_weight)"
        " VALUES (1, '2026-01-01 08:00:00', 70, '2026-01-01 07:59:00', 1600)"
    )
    conn.commit()
    before = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in m.SOFT_DELETE_TABLES}
    conn.close()

    m.migrate(db)
    m.migrate(db)  # 第二遍必须幂等：不报错、不改数据

    c2 = sqlite3.connect(db)
    c2.row_factory = sqlite3.Row
    for table in m.SOFT_DELETE_TABLES:
        assert c2.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == before[table]
        cols = {r[1] for r in c2.execute(f'PRAGMA table_info("{table}")')}
        assert set(m.SOFT_DELETE_COLUMNS) <= cols
        # 老数据 deleted_at 全 NULL
        assert c2.execute(f'SELECT COUNT(*) FROM "{table}" WHERE deleted_at IS NOT NULL').fetchone()[0] == 0
    assert m._is_migrated(c2) is True
    c2.close()
