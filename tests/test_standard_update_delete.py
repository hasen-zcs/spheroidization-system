"""TASK-12A 检测标准 修改/删除 验收测试。

覆盖任务书 C 节最小集：
- 无 action:create_standard 权限的普通账号 PUT/DELETE → 403
- PUT 成功：5 字段全改、GET /current 反映新值、created_at/created_by 不变
- PUT 非法值（time=0 / upper=-1 / 多传字段）→ 422
- PUT 不存在的 id / 已软删的 id → 404「标准不存在」
- DELETE 当前生效标准 → 400（message 含「当前生效」），当前标准不受影响
- DELETE 非当前标准 → 标准列表不再包含；重复 DELETE 幂等 200、不新增审计
- DELETE 空白原因 → 422
- 审计：修改/删除各 1 条，actor/target 正确，detail 不含图片 BLOB
"""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core import permissions as P
from app.dependencies import Container, get_container
from app.domain.audit.entities import AuditAction, AuditTarget
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app

from tests.conftest import create_standard, create_user


@pytest.fixture
def env(tmp_path):
    """空库 + 容器 + TestClient：超管 + 两条标准（第 2 条当前生效）。"""
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
        yield client, container

    app.dependency_overrides.clear()
    conn.close()


def _delete(client, url, payload, headers):
    """httpx 的 TestClient.delete() 不收 json 参数，统一走 request()。"""
    return client.request("DELETE", url, json=payload, headers=headers)


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


def _update_payload(**overrides):
    payload = {
        "standard_spheroidization_time": 72.5,
        "standard_spheroidization_time_upper": 80.0,
        "standard_spheroidization_time_lower": 60.0,
        "weighing_standard": 1600.0,
        "remark": "工艺调整",
    }
    payload.update(overrides)
    return payload


def _current_id(client, headers):
    return client.get("/api/standards/current", headers=headers).json()["data"]["id"]


def _non_current_id(client, headers):
    current = _current_id(client, headers)
    ids = [
        s["id"]
        for s in client.get("/api/standards/history", headers=headers).json()["data"]
    ]
    return next(i for i in ids if i != current)


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


# ============================================================
# 权限
# ============================================================

def test_无权限账号修改和删除都403(env):
    client, container = env
    _make_user(container, "noperm", [])
    headers = _login(client, "noperm")
    current = _current_id(client, headers)

    resp = client.put(
        f"/api/standards/{current}", json=_update_payload(), headers=headers
    ).json()
    assert resp["code"] == 403

    resp = _delete(client, f"/api/standards/{current}", {"reason": "删"}, headers).json()
    assert resp["code"] == 403


def test_非管理员有检测标准管理权限也能修改(env):
    client, container = env
    _make_user(container, "mgr", [P.ACTION_CREATE_STANDARD])
    headers = _login(client, "mgr")
    current = _current_id(client, headers)

    resp = client.put(
        f"/api/standards/{current}",
        json=_update_payload(remark="有权限的普通账号改"),
        headers=headers,
    ).json()
    assert resp["code"] == 200
    assert resp["data"]["remark"] == "有权限的普通账号改"

    rows = _audit_rows(container, action=AuditAction.UPDATE_STANDARD)
    assert len(rows) == 1
    assert rows[0]["actor"] == "mgr"
    assert rows[0]["target_type"] == AuditTarget.STANDARD


# ============================================================
# 修改（PUT）
# ============================================================

def test_PUT成功5字段全改且当前标准反映且创建信息不动(env):
    client, container = env
    headers = _login(client, "root")
    current = _current_id(client, headers)

    before = next(
        s
        for s in client.get("/api/standards/history", headers=headers).json()["data"]
        if s["id"] == current
    )

    resp = client.put(
        f"/api/standards/{current}", json=_update_payload(), headers=headers
    ).json()
    assert resp["code"] == 200
    assert resp["message"] == "标准修改成功"

    data = resp["data"]
    assert data["id"] == current
    assert data["standard_spheroidization_time"] == 72.5
    assert data["standard_spheroidization_time_upper"] == 80.0
    assert data["standard_spheroidization_time_lower"] == 60.0
    assert data["weighing_standard"] == 1600.0
    assert data["remark"] == "工艺调整"
    # 创建信息一律不动
    assert data["created_by"] == before["created_by"] == "root"
    assert data["created_at"] == before["created_at"]

    # 当前标准反映新值（修订是同一行，指向不变）
    current_now = client.get("/api/standards/current", headers=headers).json()["data"]
    assert current_now["id"] == current
    assert current_now["standard_spheroidization_time"] == 72.5
    assert current_now["weighing_standard"] == 1600.0

    # 审计 1 条：action/target/actor 正确，detail 是 5 个字段的 JSON
    rows = _audit_rows(container, action=AuditAction.UPDATE_STANDARD)
    assert len(rows) == 1
    assert rows[0]["actor"] == "root"
    assert rows[0]["target_type"] == AuditTarget.STANDARD
    assert str(rows[0]["target_id"]) == str(current)
    detail = json.loads(rows[0]["detail"])
    assert detail["standard_spheroidization_time"] == 72.5
    assert detail["weighing_standard"] == 1600.0
    assert "spheroidization_image" not in rows[0]["detail"]


def test_PUT非法值422(env):
    client, container = env
    headers = _login(client, "root")
    current = _current_id(client, headers)

    # 球化时间必须 > 0
    resp = client.put(
        f"/api/standards/{current}",
        json=_update_payload(standard_spheroidization_time=0),
        headers=headers,
    ).json()
    assert resp["code"] == 422

    # 上限必须 > 0
    resp = client.put(
        f"/api/standards/{current}",
        json=_update_payload(standard_spheroidization_time_upper=-1),
        headers=headers,
    ).json()
    assert resp["code"] == 422

    # extra="forbid"：多传字段 422
    resp = client.put(
        f"/api/standards/{current}",
        json=_update_payload(created_by="root"),
        headers=headers,
    ).json()
    assert resp["code"] == 422

    # 值没被改
    assert _current_id(client, headers) == current
    assert (
        client.get("/api/standards/current", headers=headers).json()["data"][
            "standard_spheroidization_time"
        ]
        == 70.0
    )


def test_PUT不存在的id404(env):
    client, container = env
    headers = _login(client, "root")

    resp = client.put(
        "/api/standards/9999", json=_update_payload(), headers=headers
    ).json()
    assert resp["code"] == 404
    assert resp["message"] == "标准不存在"
    assert _audit_rows(container, action=AuditAction.UPDATE_STANDARD) == []


def test_PUT已软删的标准404(env):
    client, container = env
    headers = _login(client, "root")
    non_current = _non_current_id(client, headers)

    resp = _delete(client, f"/api/standards/{non_current}", {"reason": "作废"}, headers).json()
    assert resp["code"] == 200

    resp = client.put(
        f"/api/standards/{non_current}", json=_update_payload(), headers=headers
    ).json()
    assert resp["code"] == 404
    assert resp["message"] == "标准不存在"


# ============================================================
# 删除（DELETE，软删除）
# ============================================================

def test_DELETE当前标准被拒(env):
    client, container = env
    headers = _login(client, "root")
    current = _current_id(client, headers)

    resp = _delete(client, f"/api/standards/{current}", {"reason": "删当前"}, headers).json()
    assert resp["code"] == 400
    assert "当前生效" in resp["message"]

    # 当前标准原封不动，也没留删除审计
    assert _current_id(client, headers) == current
    assert _audit_rows(container, action=AuditAction.DELETE_STANDARD) == []
    row = container.conn.execute(
        "SELECT deleted_at FROM StandardRecord WHERE standard_record_id=?",
        (current,),
    ).fetchone()
    assert row["deleted_at"] is None


def test_DELETE非当前标准后列表消失且重复删除幂等(env):
    client, container = env
    headers = _login(client, "root")
    current = _current_id(client, headers)
    non_current = _non_current_id(client, headers)

    resp = _delete(client, f"/api/standards/{non_current}", {"reason": "标准过期"}, headers).json()
    assert resp["code"] == 200
    assert resp["message"] == "标准已删除"

    # 标准列表（默认不含已删）不再包含它
    ids = [
        s["id"]
        for s in client.get("/api/standards/history", headers=headers).json()["data"]
    ]
    assert non_current not in ids
    assert current in ids

    # 库里没物理删，软删三列在位
    row = container.conn.execute(
        "SELECT deleted_at, deleted_by, delete_reason FROM StandardRecord"
        " WHERE standard_record_id=?",
        (non_current,),
    ).fetchone()
    assert row["deleted_at"] is not None
    assert row["deleted_by"] == "root"
    assert row["delete_reason"] == "标准过期"

    # 审计 1 条：before/after 快照，detail 不含图片 BLOB
    rows = _audit_rows(container, action=AuditAction.DELETE_STANDARD)
    assert len(rows) == 1
    assert rows[0]["actor"] == "root"
    assert rows[0]["target_type"] == AuditTarget.STANDARD
    assert str(rows[0]["target_id"]) == str(non_current)
    detail = json.loads(rows[0]["detail"])
    assert detail["before"]["deleted_at"] is None
    assert detail["after"]["deleted_at"] is not None
    assert "spheroidization_image" not in rows[0]["detail"]

    # 重复删除幂等：200 + 提示文案，不新增审计
    resp2 = _delete(client, f"/api/standards/{non_current}", {"reason": "再删一次"}, headers).json()
    assert resp2["code"] == 200
    assert "已删除" in resp2["message"]
    assert len(_audit_rows(container, action=AuditAction.DELETE_STANDARD)) == 1

    # 当前标准不受影响
    assert _current_id(client, headers) == current


def test_DELETE不存在的id404(env):
    client, container = env
    headers = _login(client, "root")

    resp = _delete(client, "/api/standards/9999", {"reason": "删"}, headers).json()
    assert resp["code"] == 404
    assert resp["message"] == "目标不存在"
    assert _audit_rows(container, action=AuditAction.DELETE_STANDARD) == []


def test_DELETE空白原因422(env):
    client, container = env
    headers = _login(client, "root")
    non_current = _non_current_id(client, headers)

    resp = _delete(client, f"/api/standards/{non_current}", {"reason": "   "}, headers).json()
    assert resp["code"] == 422

    # 没删成
    ids = [
        s["id"]
        for s in client.get("/api/standards/history", headers=headers).json()["data"]
    ]
    assert non_current in ids
    assert _audit_rows(container, action=AuditAction.DELETE_STANDARD) == []
