"""T-011b 自查改密 POST /api/users/me/password 的验收测试。

覆盖：旧密码校验、强度策略（短 / 纯数字 / 纯字母）、新旧相同、
改后所有旧 token 立即 401、新密码可登录、管理员重置同套策略、审计留痕。

沿用 test_access_control.py 的 env 装配方式：内存库 + 容器 + TestClient，
与 API 层走同一条链路。
"""

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Container, get_container
from app.domain.audit.entities import AuditAction, AuditTarget
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app


@pytest.fixture
def env(tmp_path):
    """空库 + 容器 + TestClient，建一个超管 root 和一个普通用户 worker。"""
    import sqlite3

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
        worker = container.create_user().execute("worker", "pass1234", False, "root")
        yield client, container, worker.user_id

    app.dependency_overrides.clear()
    conn.close()


def _login(client, username, password="pass1234"):
    body = client.post(
        "/api/users/login",
        json={"username": username, "password": password},
    ).json()
    assert body["code"] == 200, body
    return {"Authorization": f"Bearer {body['data']['token']}"}


def _headers_for(token):
    return {"Authorization": f"Bearer {token}"}


def _change(client, headers, old_password, new_password):
    return client.post(
        "/api/users/me/password",
        json={"old_password": old_password, "new_password": new_password},
        headers=headers,
    ).json()


def test_未登录_401(env):
    client, _, _ = env
    resp = client.post(
        "/api/users/me/password",
        json={"old_password": "pass1234", "new_password": "NewPass5678"},
    )
    assert resp.json()["code"] == 401


def test_旧密码错误_400_且密码未被改动(env):
    client, _, _ = env
    headers = _login(client, "worker")
    resp = _change(client, headers, "wrongpass1", "NewPass5678")
    assert resp["code"] == 400
    # 密码没被改：旧密码照样能登录
    assert _login(client, "worker", "pass1234") is not None
    assert (
        client.post(
            "/api/users/login",
            json={"username": "worker", "password": "NewPass5678"},
        ).json()["code"]
        == 401
    )


@pytest.mark.parametrize(
    "weak, missing_hint",
    [
        ("ab1", "长度"),           # 太短
        ("12345678", "字母"),      # 纯数字
        ("abcdefgh", "数字"),      # 纯字母
    ],
)
def test_弱密码_422_并说明缺什么(env, weak, missing_hint):
    client, _, _ = env
    headers = _login(client, "worker")
    resp = _change(client, headers, "pass1234", weak)
    assert resp["code"] == 422
    assert missing_hint in resp["message"]
    # 弱密码没被接受：旧密码仍可登录
    _login(client, "worker", "pass1234")


def test_新旧密码相同_422(env):
    client, _, _ = env
    headers = _login(client, "worker")
    resp = _change(client, headers, "pass1234", "pass1234")
    assert resp["code"] == 422
    _login(client, "worker", "pass1234")


def test_改密成功_旧token立即401_新密码可登录(env):
    client, _, _ = env
    # 同一用户两个并发会话：两个旧 token 都得废
    headers_a = _login(client, "worker")
    body_b = client.post(
        "/api/users/login",
        json={"username": "worker", "password": "pass1234"},
    ).json()
    headers_b = _headers_for(body_b["data"]["token"])

    token_a = headers_a["Authorization"].split(" ", 1)[1]

    resp = _change(client, headers_a, "pass1234", "NewPass5678")
    assert resp["code"] == 200, resp

    # 旧 token（A 和 B）再请求 → 401（统一信封：HTTP 200 + body.code 401）
    for token in (token_a, headers_b["Authorization"].split(" ", 1)[1]):
        me = client.get("/api/users/me", headers=_headers_for(token)).json()
        assert me["code"] == 401, me

    # 新密码能登录
    _login(client, "worker", "NewPass5678")
    # 旧密码登录已失效
    assert (
        client.post(
            "/api/users/login",
            json={"username": "worker", "password": "pass1234"},
        ).json()["code"]
        == 401
    )


def test_管理员重置弱密码_422(env):
    client, container, worker_id = env
    headers = _login(client, "root")
    resp = client.post(
        f"/api/users/{worker_id}/password",
        json={"new_password": "12345678"},
        headers=headers,
    ).json()
    assert resp["code"] == 422
    # 弱密码没被静默接受
    _login(client, "worker", "pass1234")


def test_改密后审计有记录且detail不含密码(env):
    client, container, worker_id = env
    headers = _login(client, "worker")
    resp = _change(client, headers, "pass1234", "NewPass5678")
    assert resp["code"] == 200

    rows = [
        r
        for r in (
            dict(r)
            for r in container.conn.execute(
                "SELECT * FROM AuditLog ORDER BY created_at, audit_id"
            ).fetchall()
        )
        if r["action"] == AuditAction.CHANGE_PASSWORD
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "worker"
    assert row["target_type"] == AuditTarget.USER
    assert row["target_id"] == str(worker_id)
    # detail=None：改密审计不落任何字段
    assert row["detail"] is None
    # 新旧密码明文不得出现在审计任何列
    for value in row.values():
        assert value is None or "pass1234" not in str(value)
        assert value is None or "NewPass5678" not in str(value)


def test_响应与日志不泄露密码(env, capsys):
    client, _, _ = env
    headers = _login(client, "worker")
    resp = client.post(
        "/api/users/me/password",
        json={"old_password": "pass1234", "new_password": "NewPass5678"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.text
    assert "pass1234" not in body
    assert "NewPass5678" not in body
