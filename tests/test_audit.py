"""T-011a 审计日志验收测试。

覆盖任务书要求的最小集：
- 标准创建 / 切换 → 各有 1 条审计，action/actor/target 正确
- 处置 / 复核 → 各有审计
- 建用户 / 改密 / 授权 → 各有审计，且 detail 里不含密码明文
- 过滤（actor / action / 日期区间）生效
- 游客 401、非管理员 403
- 审计写入失败不影响主业务（明确策略，见 domain/audit/service.py）
"""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Container, get_container
from app.domain.audit.entities import AuditAction, AuditLog, AuditTarget
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app

# 复用 conftest 里的两个构造函数，保持建数据写法一致
from tests.conftest import create_record, create_standard  # noqa: E402


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


def _audit_rows(container):
    """直接读库里的全部审计行，按 created_at、audit_id 正序。"""
    rows = container.conn.execute(
        "SELECT * FROM AuditLog ORDER BY created_at, audit_id"
    ).fetchall()
    return [dict(r) for r in rows]


def _audit_api(client, headers, **params):
    resp = client.get("/api/audit", headers=headers, params=params)
    body = resp.json()
    assert body["code"] == 200, body
    return body["data"]


# ============================================================
# 各写操作的埋点
# ============================================================

def test_create_standard_writes_audit(env):
    client, container, _ = env
    headers = _login(client, "root")
    resp = client.post(
        "/api/standards",
        headers=headers,
        json={"standard_spheroidization_time": 72.0, "weighing_standard": 1500.0},
    )
    body = resp.json()
    assert body["code"] == 200, body
    # 前端契约里主键叫 id（见 schemas/standard.py 的 to_response）
    standard_id = body["data"]["id"]

    rows = _audit_rows(container)
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "root"
    assert row["action"] == AuditAction.CREATE_STANDARD
    assert row["target_type"] == AuditTarget.STANDARD
    assert row["target_id"] == str(standard_id)
    detail = json.loads(row["detail"])
    assert detail["standard_spheroidization_time"] == 72.0
    assert detail["weighing_standard"] == 1500.0


def test_switch_standard_writes_audit(env):
    client, container, _ = env
    headers = _login(client, "root")
    # 先建两套标准
    first = client.post(
        "/api/standards",
        headers=headers,
        json={"standard_spheroidization_time": 65.0, "weighing_standard": 1500.0},
    ).json()["data"]
    second = client.post(
        "/api/standards",
        headers=headers,
        json={"standard_spheroidization_time": 70.0, "weighing_standard": 1500.0},
    ).json()["data"]

    resp = client.post(
        "/api/standards/switch",
        headers=headers,
        json={"to_standard_record_id": first["id"],
              "reason": "回退验证"},
    )
    assert resp.json()["code"] == 200

    switch_rows = [
        r for r in _audit_rows(container)
        if r["action"] == AuditAction.SWITCH_STANDARD
    ]
    assert len(switch_rows) == 1
    row = switch_rows[0]
    assert row["actor"] == "root"
    assert row["target_type"] == AuditTarget.STANDARD
    assert row["target_id"] == str(first["id"])
    detail = json.loads(row["detail"])
    assert detail["reason"] == "回退验证"
    # 创建动作的两条也都在
    assert sum(
        1 for r in _audit_rows(container)
        if r["action"] == AuditAction.CREATE_STANDARD
    ) == 2


def test_process_record_writes_audit(env):
    client, container, _ = env
    _login(client, "root")  # 先让库里有数据的前提不依赖登录
    create_standard(container, 65.0, "root")
    record = create_record(container, "2026-11-01 08:00:00", 65.0, abnormal=1)

    worker = container.create_user().execute("worker", "pass1234", False, "root")
    container.user_permission().replace(
        worker.user_id, ["action:process"]
    )
    headers = _login(client, "worker")

    resp = client.post(f"/api/spheroidization/{record.spheroidization_record_id}/process", headers=headers)
    assert resp.json()["code"] == 200

    rows = [r for r in _audit_rows(container) if r["action"] == AuditAction.PROCESS_RECORD]
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "worker"
    assert row["target_type"] == AuditTarget.SPHEROIDIZATION_RECORD
    assert row["target_id"] == str(record.spheroidization_record_id)
    detail = json.loads(row["detail"])
    assert detail["processed_by"] == "worker"
    assert detail["processed_at"]


def test_review_writes_audit(env):
    client, container, _ = env
    create_standard(container, 65.0, "root")
    record = create_record(container, "2026-11-01 09:00:00", 75.0, abnormal=1)

    reviewer = container.create_user().execute("reviewer", "pass1234", False, "root")
    container.user_permission().replace(reviewer.user_id, ["action:review"])
    headers = _login(client, "reviewer")

    resp = client.post(
        "/api/reviews",
        headers=headers,
        json={
            "spheroidization_record_id": record.spheroidization_record_id,
            # 前端契约是中文枚举（"正常" / "异常"），库里的 0/1 由后端转
            "review_result": "异常",
            "review_remark": "确认异常",
        },
    )
    assert resp.json()["code"] == 200
    review_id = resp.json()["data"]["id"]

    rows = [r for r in _audit_rows(container) if r["action"] == AuditAction.REVIEW_RECORD]
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "reviewer"
    assert row["target_type"] == AuditTarget.REVIEW
    assert row["target_id"] == str(review_id)
    detail = json.loads(row["detail"])
    assert detail["spheroidization_record_id"] == record.spheroidization_record_id
    assert detail["review_result"] == 1


def test_create_user_writes_audit_without_password(env):
    client, container, _ = env
    headers = _login(client, "root")
    resp = client.post(
        "/api/users",
        headers=headers,
        json={"username": "newguy", "password": "S3cretPass!", "is_admin": False},
    )
    assert resp.json()["code"] == 200

    rows = [r for r in _audit_rows(container) if r["action"] == AuditAction.CREATE_USER]
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "root"
    assert row["target_type"] == AuditTarget.USER
    detail = json.loads(row["detail"])
    assert detail["username"] == "newguy"
    # 密码明文不得出现在审计里的任何字段
    for value in row.values():
        assert value is None or "S3cretPass!" not in str(value)


def test_change_password_writes_audit_without_plaintext(env):
    client, container, _ = env
    headers = _login(client, "root")
    target = container.create_user().execute("victim", "pass1234", False, "root")

    resp = client.post(
        f"/api/users/{target.user_id}/password",
        headers=headers,
        json={"new_password": "BrandNew999"},
    )
    assert resp.json()["code"] == 200

    rows = [r for r in _audit_rows(container) if r["action"] == AuditAction.CHANGE_PASSWORD]
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "root"
    assert row["target_type"] == AuditTarget.USER
    assert row["target_id"] == str(target.user_id)
    # detail 不允许出现新密码，也不允许出现旧密码
    for value in row.values():
        assert value is None or "BrandNew999" not in str(value)
        assert value is None or "pass1234" not in str(value)
    # 改完之后新密码真的生效了（业务本身没被审计拖累）
    login = client.post(
        "/api/users/login",
        json={"username": "victim", "password": "BrandNew999"},
    ).json()
    assert login["code"] == 200


def test_grant_permission_writes_audit(env):
    client, container, _ = env
    headers = _login(client, "root")
    target = container.create_user().execute("grantme", "pass1234", False, "root")

    resp = client.put(
        f"/api/users/{target.user_id}/permissions",
        headers=headers,
        json={"permission_keys": ["page:records", "action:review"]},
    )
    assert resp.json()["code"] == 200

    rows = [r for r in _audit_rows(container) if r["action"] == AuditAction.GRANT_PERMISSION]
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "root"
    assert row["target_id"] == str(target.user_id)
    detail = json.loads(row["detail"])
    assert detail["permission_keys"] == ["action:review", "page:records"]


# ============================================================
# 查询接口：过滤 + 权限
# ============================================================

def _seed(container, actor, action, created_at, target_id="1"):
    """直接往库里插审计行，用来测过滤（业务路径测不过来这么多条）。"""
    container.audit_repo.add(
        AuditLog(
            audit_id=None,
            actor=actor,
            action=action,
            target_type=AuditTarget.USER,
            target_id=target_id,
            detail=None,
            ip=None,
            created_at=created_at,
        )
    )


def test_filter_by_actor_action_and_date(env):
    client, container, _ = env
    admin_headers = _login(client, "root")
    _seed(container, "root", "create_user", "2026-10-01 08:00:00", "1")
    _seed(container, "root", "change_password", "2026-10-15 09:30:00", "2")
    _seed(container, "worker", "create_user", "2026-11-01 10:00:00", "3")

    # 按 actor
    data = _audit_api(client, admin_headers, actor="root")
    assert data["total"] == 2
    assert all(item["actor"] == "root" for item in data["items"])

    # 按 action
    data = _audit_api(client, admin_headers, action="change_password")
    assert data["total"] == 1
    assert data["items"][0]["target_id"] == "2"

    # 日期区间（闭区间）
    data = _audit_api(
        client, admin_headers, start="2026-10-15 00:00:00", end="2026-10-31 23:59:59"
    )
    assert data["total"] == 1
    assert data["items"][0]["action"] == "change_password"

    # 组合：actor + 日期
    data = _audit_api(
        client, admin_headers,
        actor="worker", start="2026-10-01 00:00:00", end="2026-12-31 23:59:59",
    )
    assert data["total"] == 1
    assert data["items"][0]["actor"] == "worker"

    # 最新在前
    data = _audit_api(client, admin_headers)
    assert data["total"] == 3
    assert data["items"][0]["created_at"] == "2026-11-01 10:00:00"

    # 分页
    data = _audit_api(client, admin_headers, page=2, page_size=2)
    assert data["total"] == 3
    assert len(data["items"]) == 1
    assert data["items"][0]["created_at"] == "2026-10-01 08:00:00"


def test_guest_gets_401(env):
    client, _, _ = env
    resp = client.get("/api/audit")
    body = resp.json()
    assert resp.status_code == 200  # 统一信封，HTTP 恒 200
    assert body["code"] == 401


def test_non_admin_gets_403(env):
    client, container, _ = env
    # 有登录态但零权限
    container.create_user().execute("nobody", "pass1234", False, "root")
    headers = _login(client, "nobody")
    body = client.get("/api/audit", headers=headers).json()
    assert body["code"] == 403

    # 有别的权限但没有 manage_users 也一样 403
    worker = container.create_user().execute("worker", "pass1234", False, "root")
    container.user_permission().replace(worker.user_id, ["action:process"])
    headers = _login(client, "worker")
    body = client.get("/api/audit", headers=headers).json()
    assert body["code"] == 403


def test_admin_can_read(env):
    client, container, _ = env
    headers = _login(client, "root")
    _seed(container, "root", "create_user", "2026-11-01 08:00:00")
    data = _audit_api(client, headers)
    assert data["total"] == 1
    item = data["items"][0]
    for key in ("audit_id", "actor", "action", "target_type", "target_id",
                "detail", "ip", "created_at"):
        assert key in item


# ============================================================
# 策略：审计写入失败不影响主业务
# ============================================================

def test_audit_failure_does_not_break_business(env, monkeypatch):
    client, container, _ = env
    headers = _login(client, "root")

    def _boom(self, audit):
        raise RuntimeError("audit table on fire")

    monkeypatch.setattr(
        "app.infrastructure.database.audit_repo.SqliteAuditRepository.add", _boom
    )

    # 建标准：审计炸了，业务照常成功
    resp = client.post(
        "/api/standards",
        headers=headers,
        json={"standard_spheroidization_time": 66.0, "weighing_standard": 1500.0},
    )
    body = resp.json()
    assert body["code"] == 200, body
    assert body["data"]["id"]

    # 建用户：同样不受影响
    resp = client.post(
        "/api/users",
        headers=headers,
        json={"username": "stillworks", "password": "pass1234", "is_admin": False},
    )
    assert resp.json()["code"] == 200

    # 库里一条审计都没有（写全失败），但业务数据都在
    assert _audit_rows(container) == []
    assert container.conn.execute(
        "SELECT COUNT(*) FROM StandardRecord"
    ).fetchone()[0] == 1
    assert container.conn.execute(
        "SELECT COUNT(*) FROM UserAccount WHERE username = 'stillworks'"
    ).fetchone()[0] == 1
