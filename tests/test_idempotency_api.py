"""幂等 + 分段的接口层验收（v3 第一刀）。

单元测试能证明库里的行对了，但这个文件要证明**线上那条路**也对：
JSON 契约、422 信封、详情返回分段的形状——合并层就是照这些字段拼请求的。

请求体刻意跟合并层实际要发的一致（相对秒 + device_id/external_id），
以后合并层对不上，这里先红。
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Container, get_container
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app

STANDARD = {
    "standard_spheroidization_time": 75.0,
    "standard_spheroidization_time_upper": 90.0,
    "standard_spheroidization_time_lower": 60.0,
    "weighing_standard": 1500.0,
    "remark": "v3 接口测试",
}

RECORD = {
    "device_id": "casting-1",
    "external_id": "2042",
    "detection_time": "2026-11-01 09:12:27.900",
    "plc_button_time": "2026-11-01 09:12:27.900",
    "spheroidization_start_time": "2026-11-01 09:12:31.400",
    "spheroidization_end_time": "2026-11-01 09:14:06.855",
    "actual_spheroidization_time": 95.455,
    "spheroidization_abnormal": 1,
    "abnormal_type": 5,
    "abnormal_reason": "球化过程中间亮光停顿：第 2 段前停顿 15.2s",
    "spheroidization_wire_entry_start_time": "2026-11-01 09:12:31.000",
    "spheroidization_wire_entry_end_time": "2026-11-01 09:17:31.000",
    "spheroidization_wire_entry_total_duration": 300.0,
    "spheroidization_weight": 1608.0,
    "segments": [
        {"seg_index": 1, "start_offset": 0.0, "end_offset": 40.0,
         "gap_before": None, "duration": 40.0},
        {"seg_index": 2, "start_offset": 55.2, "end_offset": 95.455,
         "gap_before": 15.2, "duration": 40.255},
    ],
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


def _post(client, **overrides):
    payload = dict(RECORD)
    payload["segments"] = [dict(s) for s in RECORD["segments"]]
    payload.update(overrides)
    return client.post("/api/spheroidization", json=payload).json()


def test_重复上传只建一条并返回_existing(env):
    client, container, _ = env
    first = _post(client)
    second = _post(client)

    assert first["code"] == 200 and first["data"]["existing"] is False
    assert second["code"] == 200 and second["data"]["existing"] is True
    assert first["data"]["id"] == second["data"]["id"]
    assert container.conn.execute(
        "SELECT COUNT(*) FROM SpheroidizationRecord"
    ).fetchone()[0] == 1


def test_同键不同内容返回409且不入库(env):
    client, container, _ = env
    _post(client)
    conflict = _post(client, spheroidization_weight=9999.0)

    assert conflict["code"] == 409
    assert "拒绝覆盖" in conflict["message"]
    assert container.conn.execute(
        "SELECT COUNT(*) FROM SpheroidizationRecord"
    ).fetchone()[0] == 1


def test_详情返回分段明细(env):
    client, _, headers = env
    record_id = _post(client)["data"]["id"]

    body = client.get(f"/api/spheroidization/{record_id}", headers=headers).json()
    assert body["code"] == 200
    segs = body["data"]["segments"]
    assert [s["seg_index"] for s in segs] == [1, 2]
    assert segs[0]["gap_before"] is None
    assert segs[1]["gap_before"] == 15.2
    assert segs[1]["end_offset"] == 95.455


def test_列表接口不带分段(env):
    client, _, headers = env
    _post(client)
    body = client.get("/api/spheroidization", headers=headers).json()
    assert body["code"] == 200
    assert "segments" not in body["data"]["items"][0]


def test_脏分段被422挡住(env):
    client, container, _ = env
    bad = [
        {"seg_index": 1, "start_offset": 0.0, "end_offset": 40.0,
         "gap_before": None, "duration": 40.0},
        {"seg_index": 3, "start_offset": 55.2, "end_offset": 95.455,
         "gap_before": 15.2, "duration": 40.255},
    ]
    body = _post(client, segments=bad)
    assert body["code"] == 422
    assert container.conn.execute(
        "SELECT COUNT(*) FROM SpheroidizationRecord"
    ).fetchone()[0] == 0


def test_老调用不带幂等键仍然能建且无分段(env):
    client, _, headers = env
    payload = dict(RECORD)
    payload.pop("device_id")
    payload.pop("external_id")
    payload.pop("segments")
    payload["abnormal_type"] = 0
    payload["spheroidization_abnormal"] = 0

    body = client.post("/api/spheroidization", json=payload).json()
    assert body["code"] == 200
    assert body["data"]["existing"] is False

    detail = client.get(
        f"/api/spheroidization/{body['data']['id']}", headers=headers
    ).json()
    assert detail["data"]["segments"] == []


def test_幂等命中不再补第二条温度(env):
    """重放时温度不能重复落库：同一条记录挂两条一模一样的读数就是脏数据。"""
    client, container, _ = env
    payload = dict(RECORD)
    payload["segments"] = [dict(s) for s in RECORD["segments"]]
    payload["temperature"] = 1523.5
    payload["temperature_time"] = "2026-11-01 09:09:00"
    payload["gun_no"] = 4

    first = client.post("/api/spheroidization", json=payload).json()
    second = client.post("/api/spheroidization", json=payload).json()

    assert first["data"]["existing"] is False
    assert second["data"]["existing"] is True
    count = container.conn.execute(
        "SELECT COUNT(*) FROM TemperatureRecord WHERE spheroidization_record_id = ?",
        (first["data"]["id"],),
    ).fetchone()[0]
    assert count == 1
