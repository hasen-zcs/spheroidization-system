"""回归：切换记录接口不能因关联标准被软删/缺失而 500（2026-11-14 线上事故）。

事故链：生产 4 条切换日志的目标标准全被软删（工艺部清理测试标准）→
list_logs 里 get_by_id 查不到返回 None → 路由 to_value 没判空 →
AttributeError → GET /api/standards/switch-logs 500 → 前端整张「切换记录」显示空。

两层修复各钉一个用例：
1. switch.py list_logs 改用 get_by_id_including_deleted：
   软删的标准在历史记录里照常显示（历史账本不丢信息）。
2. 路由 to_value 判 None：极端情况（整行物理不存在）也不 500，给 null。
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Container, get_container
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app

from tests.conftest import create_standard, create_user


@pytest.fixture
def env(tmp_path):
    """空库 + 容器 + TestClient：超管 + 两条标准（id=1 老标准、id=2 当前生效）。"""
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
        create_standard(container, 65.0, "root", remark="A")
        create_standard(container, 70.0, "root", remark="B")
        yield client, container
    app.dependency_overrides.clear()
    conn.close()


def _login(client, username, password="pass1234"):
    token = client.post(
        "/api/users/login",
        json={"username": username, "password": password},
    ).json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _switch(client, headers, to_id):
    resp = client.post(
        "/api/standards/switch",
        json={"to_standard_record_id": to_id, "reason": "回归测试切换"},
        headers=headers,
    ).json()
    assert resp["code"] == 200, resp


def test_切换目标标准被软删后列表照常返回(env):
    """事故复现：切到标准 1 后，再建新标准把当前移走，把标准 1 软删，switch-logs 必须 200 且值都在。"""
    client, container = env
    headers = _login(client, "root")

    _switch(client, headers, to_id=1)  # 当前(2) -> 1，现在 1 是当前标准

    # 再建一条标准，当前生效移到 3，标准 1 变成非当前才能作废
    create_standard(container, 75.0, "root", remark="C")

    resp = client.request(
        "DELETE",
        "/api/standards/1",
        json={"reason": "清理测试标准"},
        headers=headers,
    ).json()
    assert resp["code"] == 200, resp

    body = client.get("/api/standards/switch-logs", headers=headers).json()
    assert body["code"] == 200, body
    items = body["data"]["items"]
    assert len(items) == 1
    entry = items[0]
    assert entry["to_standard_record_id"] == 1
    # 软删不丢值：目标标准 65s 要能显示出来
    assert entry["to_value"] == 65.0
    assert entry["to_standard"] is not None
    assert entry["to_standard"]["id"] == 1
    assert entry["to_standard"]["deleted_at"] is not None
    # 来源标准（当前标准 2）正常
    assert entry["from_standard"]["id"] == 2
    assert entry["from_value"] == 70.0
    # 文案不能出现字面 "None"
    assert "None" not in entry["summary"]
    assert "标准1" in entry["summary"] and "标准2" in entry["summary"]


def test_标准整行不存在时接口不500返回null(env):
    """极端情况：日志指向的物理行不在（比如误删库行），接口仍 200，值给 null。"""
    client, container = env
    headers = _login(client, "root")

    # 手工塞一条指向不存在标准 99 的切换日志（绕过业务层）；
    # 目标行物理不存在必然违反外键，先临时关掉该连接的 FK 检查再塞
    container.conn.execute("PRAGMA foreign_keys = OFF")
    container.conn.execute(
        "INSERT INTO StandardSwitchLogs"
        " (switched_at, from_standard_record_id, to_standard_record_id,"
        "  operated_by, reason)"
        " VALUES ('2026-11-14 00:00:00', 98, 99, 'root', '极端用例')",
    )
    container.conn.commit()
    container.conn.execute("PRAGMA foreign_keys = ON")

    body = client.get("/api/standards/switch-logs", headers=headers).json()
    assert body["code"] == 200, body
    items = body["data"]["items"]
    assert len(items) == 1
    entry = items[0]
    assert entry["from_value"] is None
    assert entry["to_value"] is None
    assert entry["from_standard"] is None
    assert entry["to_standard"] is None
    assert "None" not in entry["summary"]
    assert "（无）" in entry["summary"]
