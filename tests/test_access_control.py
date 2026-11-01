"""账号权限与本次改表的验收断言。

对应改动清单第九节"验收断言（改完自测用）"，以及第 57~59 条
（首个管理员、复核人、游客封锁）的落地检查。

和 test_smoke.py 的分工：那边测业务规则，这里测"谁能做什么"和库表结构。
"""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Container, get_container
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app


def _record_payload(**overrides):
    payload = {
        "detection_time": "2026-10-29 09:00:00",
        "spheroidization_wire_entry_start_time": "2026-10-29 08:59:00",
        "spheroidization_wire_entry_end_time": "2026-10-29 09:01:00",
        "spheroidization_wire_entry_total_duration": 120.0,
        "spheroidization_weight": 1500.0,
    }
    payload.update(overrides)
    return payload


def _standard_payload(**overrides):
    payload = {
        "standard_spheroidization_time": 70.0,
        "weighing_standard": 1500.0,
        "remark": "验收",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def env(tmp_path):
    """空库 + 容器 + TestClient，并建好一个超管。"""
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
        container.create_user().execute("root", "pass1234", True, "system")
        yield client, container, state_path

    app.dependency_overrides.clear()
    conn.close()


def _login(client, username, password="pass1234"):
    token = client.post(
        "/api/users/login",
        json={"username": username, "password": password},
    ).json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _make_user(container, username, permissions, is_admin=False):
    """建号并授权，返回登录头。"""
    user = container.create_user().execute(username, "pass1234", is_admin, "root")
    if permissions:
        container.user_permission().replace(user.user_id, permissions)
    return user


def test_建表后七张表和触发器都在(env):
    _, container, _ = env
    tables = {
        row["name"]
        for row in container.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert tables == {
        "StandardRecord",
        "SpheroidizationRecord",
        "ReviewRecord",
        "TemperatureRecord",
        "StandardSwitchLogs",
        "UserAccount",
        "UserPermission",
        # v3（2026-11-01）：幂等台账 + 分段明细
        "UploadLedger",
        "FlashSegment",
    }

    triggers = {
        row["name"]
        for row in container.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )
    }
    assert {"standard_sync_sequence", "spheroidization_sync_sequence",
            "review_sync_sequence"} <= triggers


def test_进站未球化可以只填检测时间(env):
    client, container, _ = env
    headers = _login(client, "root")
    client.post("/api/standards", json=_standard_payload(), headers=headers)

    body = client.post(
        "/api/spheroidization",
        json=_record_payload(
            spheroidization_abnormal=True,
            abnormal_type=1,
            abnormal_reason="进站未球化",
        ),
    ).json()

    assert body["code"] == 200
    data = body["data"]
    # 三个时间都没传，库里就是 NULL，不是 0 也不是空串
    assert data["spheroidization_start_time"] is None
    assert data["spheroidization_end_time"] is None
    assert data["actual_spheroidization_time"] is None
    assert data["abnormal_type"] == 1
    assert data["abnormal_reason"] == "进站未球化"


def test_异常类型超出1到4是422不是500(env):
    client, _, _ = env
    headers = _login(client, "root")
    client.post("/api/standards", json=_standard_payload(), headers=headers)

    response = client.post(
        "/api/spheroidization",
        json=_record_payload(abnormal_type=9),
    )

    assert response.status_code == 200
    assert response.json()["code"] == 422


def test_游客看得到列表但处理记录要登录(env):
    client, _, _ = env
    headers = _login(client, "root")
    client.post("/api/standards", json=_standard_payload(), headers=headers)
    client.post("/api/spheroidization", json=_record_payload())

    guest_list = client.get("/api/spheroidization").json()
    assert guest_list["code"] == 200
    assert len(guest_list["data"]["items"]) == 1

    guest_process = client.post("/api/spheroidization/1/process", json={}).json()
    assert guest_process["code"] == 401

    ok_process = client.post(
        "/api/spheroidization/1/process", json={}, headers=headers
    ).json()
    assert ok_process["code"] == 200
    # 处理人来自登录态
    assert ok_process["data"]["processed_by"] == "root"


def test_没有切换权限的人切标准被403(env):
    client, container, _ = env
    root_headers = _login(client, "root")
    first = client.post(
        "/api/standards", json=_standard_payload(), headers=root_headers
    ).json()["data"]

    _make_user(container, "worker", ["page:records"])
    worker_headers = _login(client, "worker")

    denied = client.post(
        "/api/standards/switch",
        json={"to_standard_record_id": first["id"], "reason": "想切"},
        headers=worker_headers,
    ).json()
    assert denied["code"] == 403


def test_有权限的人切换后日志和状态文件都对得上(env):
    client, container, state_path = env
    root_headers = _login(client, "root")
    first = client.post(
        "/api/standards", json=_standard_payload(), headers=root_headers
    ).json()["data"]
    second = client.post(
        "/api/standards",
        json=_standard_payload(standard_spheroidization_time=80.0),
        headers=root_headers,
    ).json()["data"]

    _make_user(container, "caster", ["action:switch_standard"])
    caster_headers = _login(client, "caster")

    switched = client.post(
        "/api/standards/switch",
        json={"to_standard_record_id": first["id"], "reason": "浇筑工判定"},
        headers=caster_headers,
    ).json()
    assert switched["code"] == 200

    row = container.conn.execute(
        "SELECT * FROM StandardSwitchLogs ORDER BY switch_log_id DESC LIMIT 1"
    ).fetchone()
    assert row["from_standard_record_id"] == second["id"]
    assert row["to_standard_record_id"] == first["id"]
    assert row["operated_by"] == "caster"
    assert row["reason"] == "浇筑工判定"

    # 状态文件指向新标准
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["standard_record_id"] == first["id"]


def test_温度上报免登录并随列表返回(env):
    client, _, _ = env
    headers = _login(client, "root")
    client.post("/api/standards", json=_standard_payload(), headers=headers)
    record = client.post("/api/spheroidization", json=_record_payload()).json()["data"]

    reported = client.post(
        "/api/temperature",
        json={
            "gun_no": 1,
            "temperature": 1405.0,
            "measured_at": "2026-10-29 08:59:30",
            "spheroidization_record_id": record["id"],
        },
    ).json()
    assert reported["code"] == 200
    assert reported["data"]["spheroidization_record_id"] == record["id"]

    item = client.get("/api/spheroidization").json()["data"]["items"][0]
    assert item["temperature"] == 1405.0


def test_温度关联不存在的记录被拒(env):
    client, _, _ = env

    body = client.post(
        "/api/temperature",
        json={
            "gun_no": 1,
            "temperature": 1405.0,
            "measured_at": "2026-10-29 08:59:30",
            "spheroidization_record_id": 9999,
        },
    ).json()

    assert body["code"] == 400


def test_普通用户碰不到用户管理接口(env):
    client, container, _ = env
    _make_user(container, "worker", ["page:records"])
    worker_headers = _login(client, "worker")

    assert client.get("/api/users", headers=worker_headers).json()["code"] == 403
    assert (
        client.post(
            "/api/users",
            json={"username": "x", "password": "pass1234"},
            headers=worker_headers,
        ).json()["code"]
        == 403
    )


def test_管理员建号授权和改密码都能走通(env):
    client, container, _ = env
    root_headers = _login(client, "root")

    created = client.post(
        "/api/users",
        json={"username": "newbie", "password": "pass1234", "is_admin": False},
        headers=root_headers,
    ).json()
    assert created["code"] == 200
    user_id = created["data"]["id"]

    granted = client.put(
        f"/api/users/{user_id}/permissions",
        json={"permission_keys": ["page:records", "action:review"]},
        headers=root_headers,
    ).json()
    assert granted["code"] == 200
    assert set(granted["data"]) == {"page:records", "action:review"}

    reset = client.post(
        f"/api/users/{user_id}/password",
        json={"new_password": "another1234"},
        headers=root_headers,
    ).json()
    assert reset["code"] == 200

    # 旧密码失效、新密码可用
    assert (
        client.post(
            "/api/users/login",
            json={"username": "newbie", "password": "pass1234"},
        ).json()["code"]
        == 401
    )
    assert (
        client.post(
            "/api/users/login",
            json={"username": "newbie", "password": "another1234"},
        ).json()["code"]
        == 200
    )


def test_停用账号不能登录(env):
    """2026-10-31 改口径：停用账号必须真的进不来。

    原用例是把"停用但能登录"钉住（老板 10-28 说不考虑禁用用户）。
    正式版补上了拦截，这条随之改成断言 401，并加了"重新启用可登录"的回归。
    """
    client, container, _ = env
    root_headers = _login(client, "root")
    user = _make_user(container, "worker", [])

    disabled = client.put(
        f"/api/users/{user.user_id}/enabled",
        json={"enabled": False},
        headers=root_headers,
    ).json()
    assert disabled["code"] == 200

    login = client.post(
        "/api/users/login",
        json={"username": "worker", "password": "pass1234"},
    ).json()
    assert login["code"] == 401

    # 重新启用后恢复登录，证明拦的是 enabled 而不是账号被写坏
    client.put(
        f"/api/users/{user.user_id}/enabled",
        json={"enabled": True},
        headers=root_headers,
    )
    again = client.post(
        "/api/users/login",
        json={"username": "worker", "password": "pass1234"},
    ).json()
    assert again["code"] == 200
