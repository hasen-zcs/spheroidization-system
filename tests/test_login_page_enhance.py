"""TASK-10 登录页增强：账号下拉列表接口 GET /api/users/accounts。

三条验收：
1. 游客（不带 token）访问 → 200，只含启用中的账号，按用户名排序
2. 停用的账号不出现在列表里
3. 响应体每个元素只有 username 一个字段，密码/权限等字段一概没有
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Container, get_container
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app


@pytest.fixture
def env(tmp_path):
    """空库 + 容器 + TestClient。"""
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
        yield client, container

    app.dependency_overrides.clear()
    conn.close()


def _account_names(client) -> list[str]:
    """游客直接 GET，断言信封 code=200 后取出用户名列表。"""
    body = client.get("/api/users/accounts").json()
    assert body["code"] == 200
    return [item["username"] for item in body["data"]]


def test_游客可拉取启用账号列表(env):
    client, container = env
    container.create_user().execute("zhang", "pass1234", False, "system")
    container.create_user().execute("li", "pass1234", True, "system")

    # 按用户名排序：li 在 zhang 前面
    assert _account_names(client) == ["li", "zhang"]


def test_停用账号不在列表中(env):
    client, container = env
    container.create_user().execute("zhang", "pass1234", False, "system")
    disabled = container.create_user().execute("wang", "pass1234", False, "system")
    container.manage_user().set_enabled(disabled.user_id, 0)

    assert _account_names(client) == ["zhang"]


def test_响应体只有username字段(env):
    client, container = env
    container.create_user().execute("zhang", "pass1234", True, "system")

    body = client.get("/api/users/accounts").json()
    assert body["code"] == 200
    items = body["data"]
    assert len(items) == 1
    assert set(items[0].keys()) == {"username"}
