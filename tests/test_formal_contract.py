"""正式版契约测试（2026-10-31）。

为什么单开一个文件：这批断言锁的是**前后端接口契约**，不是业务规则。
两份开发成果（后端包 / 前端包）之前各写各的，登录结构、用户字段名、
切换标准的入参名、切换日志的返回形状全对不上，85 个测试全绿但前端一接就崩。
这些用例就是防止再跑偏的钉子。

对应前端实现：
- frontend/src/auth.ts（读 data.user、user.permission_keys）
- frontend/src/views/Users.vue（读 user.permission_keys）
- frontend/src/views/Standard.vue（读 data.items + summary）
- frontend/src/api/index.ts（switchStandard 发 standard_id）
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Container, get_container
from app.infrastructure.database.connection import create_tables, verify_schema
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app


def _standard_payload(**overrides):
    payload = {
        "standard_spheroidization_time": 70.0,
        "weighing_standard": 1500.0,
        "remark": "契约测试",
    }
    payload.update(overrides)
    return payload


def _record_payload(**overrides):
    payload = {
        "detection_time": "2026-10-31 09:00:00",
        "spheroidization_wire_entry_start_time": "2026-10-31 08:59:00",
        "spheroidization_wire_entry_end_time": "2026-10-31 09:01:00",
        "spheroidization_wire_entry_total_duration": 120.0,
        "spheroidization_weight": 1500.0,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def env(tmp_path):
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
        yield client, container

    app.dependency_overrides.clear()
    conn.close()


def _login(client, username="root", password="pass1234"):
    body = client.post(
        "/api/users/login", json={"username": username, "password": password}
    ).json()
    return body, {"Authorization": f"Bearer {body['data']['token']}"}


def test_登录返回嵌套_user_且带_permission_keys(env):
    client, _ = env
    body, _headers = _login(client)

    data = body["data"]
    assert data["user"]["username"] == "root"
    assert data["user"]["is_admin"] is True
    # 前端 auth.ts 读的就是这个字段
    assert "permission_keys" in data["user"]
    assert "page:users" in data["user"]["permission_keys"]


def test_用户列表每项都有_permission_keys(env):
    client, container = env
    _body, headers = _login(client)
    user = container.create_user().execute("worker", "pass1234", False, "root")
    container.user_permission().replace(user.user_id, ["page:records"])

    items = client.get("/api/users", headers=headers).json()["data"]
    worker = next(item for item in items if item["username"] == "worker")

    # Users.vue: [...user.permission_keys] / user.permission_keys.length
    assert worker["permission_keys"] == ["page:records"]
    # 兼容字段保留一版
    assert worker["permissions"] == ["page:records"]


def test_me_带_permission_keys(env):
    client, _ = env
    _body, headers = _login(client)
    data = client.get("/api/users/me", headers=headers).json()["data"]
    assert "permission_keys" in data
    assert data["is_admin"] is True


def test_切换标准接受前端字段名_standard_id(env):
    client, container = env
    _body, headers = _login(client)
    first = client.post(
        "/api/standards", json=_standard_payload(), headers=headers
    ).json()["data"]
    second = client.post(
        "/api/standards",
        json=_standard_payload(standard_spheroidization_time=80.0),
        headers=headers,
    ).json()["data"]
    assert second["id"] != first["id"]

    # frontend/src/api/index.ts: switchStandard({standard_id, reason})
    body = client.post(
        "/api/standards/switch",
        json={"standard_id": first["id"], "reason": "契约定稿回切"},
        headers=headers,
    ).json()
    assert body["code"] == 200
    assert body["data"]["id"] == first["id"]

    current = client.get("/api/standards/current").json()["data"]
    assert current["id"] == first["id"]


def test_切换日志返回分页对象且字段对得上前端(env):
    client, _ = env
    _body, headers = _login(client)
    std = client.post(
        "/api/standards", json=_standard_payload(), headers=headers
    ).json()["data"]
    client.post(
        "/api/standards/switch",
        json={"standard_id": std["id"], "reason": "首次应用"},
        headers=headers,
    )

    data = client.get("/api/standards/switch-logs", headers=headers).json()["data"]

    # Standard.vue 读 data.items
    assert isinstance(data, dict) and "items" in data
    log = data["items"][0]
    # Standard.vue 优先显示 summary，其次用 from_standard_id / to_value
    assert log["summary"]
    assert log["to_standard_id"] == std["id"]
    assert log["to_value"] == 70.0
    assert "from_standard_id" in log


def test_异常类型接受1到6_超出仍是422(env):
    client, _ = env
    _body, headers = _login(client)
    client.post("/api/standards", json=_standard_payload(), headers=headers)

    ok_body = client.post(
        "/api/spheroidization", json=_record_payload(abnormal_type=5)
    ).json()
    assert ok_body["code"] == 200
    assert ok_body["data"]["abnormal_type"] == 5

    bad = client.post(
        "/api/spheroidization", json=_record_payload(abnormal_type=7)
    ).json()
    assert bad["code"] == 422


def test_人工补录可随记录带温度(env):
    client, container = env
    _body, headers = _login(client)
    client.post("/api/standards", json=_standard_payload(), headers=headers)

    body = client.post(
        "/api/spheroidization",
        json=_record_payload(
            temperature=1523.4,
            temperature_time="2026-10-31 09:00:30",
        ),
    ).json()
    assert body["code"] == 200
    record_id = body["data"]["id"]
    # 创建响应里的温度来自关联的测温记录
    assert body["data"]["temperature"] == 1523.4

    rows = container.temperature_repo.list_by_record_ids([record_id])
    assert len(rows) == 1
    assert rows[0].gun_no == 0  # 0 = 人工补录
    assert rows[0].temperature == 1523.4


def test_老库缺表时启动自检直接报错(env):
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE SpheroidizationRecord (spheroidization_record_id INTEGER)"
    )
    with pytest.raises(RuntimeError) as excinfo:
        verify_schema(conn)
    assert "migrate_db.py" in str(excinfo.value)
    conn.close()
