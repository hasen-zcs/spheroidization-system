"""前后端全链路契约测试（2026-10-31）。

目标：前端 `frontend/src` 里每一个 `api/index.ts` 的函数、每一个页面读取的字段，
在后端都能拿到、类型也对得上。任何一处对不上，这里必须先红。

与 test_formal_contract.py 的分工：
- 那边锁"本次修复的 5 处契约"；
- 这边是一条不落的全链路冒烟：游客 / 普通用户 / 管理员三种角色，
  覆盖 health、记录 CRUD、图片、处置、复核、标准、切换日志、账号全套。
"""

import base64
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Container, get_container
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app

# 最小 JPEG 头（FFD8 ... FFD9），够 _guess_media_type 认出 image/jpeg
TINY_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


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


def _login(client, username="root", password="pass" + "1234"):
    body = client.post(
        "/api/users/login", json={"username": username, "password": password}
    ).json()
    token = (body.get("data") or {}).get("token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return body, headers


def _standard(client, headers, **overrides):
    payload = {
        "standard_spheroidization_time": 70.0,
        "weighing_standard": 1500.0,
        "standard_spheroidization_time_upper": 105.0,
        "standard_spheroidization_time_lower": 30.0,
        "remark": "全链路",
    }
    payload.update(overrides)
    return client.post("/api/standards", json=payload, headers=headers).json()


def _record(client, **overrides):
    payload = {
        "detection_time": "2026-10-31 10:00:00",
        "spheroidization_start_time": "2026-10-31 10:00:10",
        "spheroidization_end_time": "2026-10-31 10:01:30",
        "actual_spheroidization_time": 80.0,
        "spheroidization_abnormal": True,
        "abnormal_type": 3,
        "abnormal_reason": "超出上限 105s",
        "spheroidization_wire_entry_start_time": "2026-10-31 09:59:00",
        "spheroidization_wire_entry_end_time": "2026-10-31 10:01:40",
        "spheroidization_wire_entry_total_duration": 160.0,
        "spheroidization_weight": 1508.5,
        "temperature": 1521.5,
        "temperature_time": "2026-10-31 09:59:30",
        "spheroidization_image": base64.b64encode(TINY_JPEG).decode("ascii"),
    }
    payload.update(overrides)
    return client.post("/api/spheroidization", json=payload).json()


# ---------------- 游客 ----------------

def test_游客链路(env):
    client, _ = env
    assert client.get("/api/health").json()["data"]["status"] == "running"
    assert client.get("/api/spheroidization").json()["code"] == 200
    assert client.get("/api/spheroidization/stats").json()["code"] == 200
    # 标准当前值游客可读（监控页切换卡片要用）
    assert client.get("/api/standards/current").json()["code"] in (200, 404)

    # 其余一律要登录
    assert client.get("/api/spheroidization/1").json()["code"] == 401
    assert client.post("/api/spheroidization/1/process").json()["code"] == 401
    assert client.get("/api/reviews/1").json()["code"] == 401
    assert client.get("/api/standards/history").json()["code"] == 401
    # 游客带 abnormal=true 拿异常列表：403（不是 401，前端只弹提示不跳登录）
    assert client.get("/api/spheroidization?abnormal=true").json()["code"] == 403


# ---------------- 管理员：记录全链路 ----------------

def test_记录创建列表详情图片处置复核(env):
    client, _ = env
    _body, headers = _login(client)
    _standard(client, headers)

    created = _record(client)
    assert created["code"] == 200, created
    record = created["data"]

    # 前端 SpheroidizationRecord 需要的字段一个都不能少
    required = {
        "id",
        "detection_time",
        "spheroidization_start_time",
        "spheroidization_end_time",
        "actual_spheroidization_time",
        "spheroidization_abnormal",
        "standard_spheroidization_time",
        "abnormal_type",
        "abnormal_reason",
        "temperature",
        "temperature_time",
        "spheroidization_wire_entry_start_time",
        "spheroidization_wire_entry_end_time",
        "spheroidization_wire_entry_total_duration",
        "spheroidization_weight",
        "processed",
        "processed_at",
        "processed_by",
        "review_result",
    }
    assert required <= set(record)

    # 类型：前端 TS 声明是 boolean
    assert isinstance(record["spheroidization_abnormal"], bool)
    assert isinstance(record["processed"], bool)
    assert record["temperature"] == 1521.5
    assert record["abnormal_type"] == 3

    # 列表：分页对象 + 列表不带图片
    page = client.get("/api/spheroidization?page=1&page_size=20").json()["data"]
    assert set(page) == {"items", "total", "page", "page_size", "has_more"}
    assert page["total"] == 1
    assert "spheroidization_image" not in page["items"][0]

    # 详情：带 base64 图片
    detail = client.get(f"/api/spheroidization/{record['id']}", headers=headers).json()
    assert detail["code"] == 200
    assert detail["data"]["spheroidization_image"]
    assert detail["data"]["review_result"] is None

    # 图片端点：原样字节 + 正确 Content-Type
    image = client.get(f"/api/spheroidization/{record['id']}/image", headers=headers)
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert image.content == TINY_JPEG

    # 处置：前端裸 POST 不带 body，必须能过（历史上 422 过）
    processed = client.post(
        f"/api/spheroidization/{record['id']}/process", headers=headers
    ).json()
    assert processed["code"] == 200, processed
    assert processed["data"]["processed"] is True
    assert processed["data"]["processed_by"] == "root"
    assert processed["data"]["processed_at"]

    # 处置不可逆
    again = client.post(
        f"/api/spheroidization/{record['id']}/process", headers=headers
    ).json()
    assert again["code"] == 400

    # 复核：中文结果 + 复核人取登录态
    review = client.post(
        "/api/reviews",
        json={
            "spheroidization_record_id": record["id"],
            "review_result": "异常",
            "review_remark": "确实偏长",
        },
        headers=headers,
    ).json()
    assert review["code"] == 200, review
    assert review["data"]["reviewer"] == "root"

    reviews = client.get(f"/api/reviews/{record['id']}", headers=headers).json()["data"]
    assert len(reviews) == 1
    assert set(reviews[0]) == {
        "id",
        "spheroidization_record_id",
        "review_result",
        "reviewer",
        "review_remark",
        "reviewed_at",
    }

    # 详情里回填最新复核结论
    detail2 = client.get(f"/api/spheroidization/{record['id']}", headers=headers).json()
    assert detail2["data"]["review_result"] == "异常"
    assert detail2["data"]["processed"] is True


def test_筛选与统计(env):
    client, _ = env
    _body, headers = _login(client)
    _standard(client, headers)
    normal = _record(
        client, spheroidization_abnormal=False, abnormal_type=None,
        abnormal_reason=None, detection_time="2026-10-31 11:00:00",
    )["data"]
    _record(client, detection_time="2026-10-31 12:00:00")

    stats = client.get("/api/spheroidization/stats").json()["data"]
    assert set(stats) == {"total", "abnormal", "processed", "unprocessed"}
    assert stats == {"total": 2, "abnormal": 1, "processed": 0, "unprocessed": 2}

    abnormal = client.get(
        "/api/spheroidization?abnormal=true", headers=headers
    ).json()["data"]
    assert abnormal["total"] == 1

    unprocessed = client.get(
        "/api/spheroidization?processed=false", headers=headers
    ).json()["data"]
    assert unprocessed["total"] == 2

    only_normal = client.get(
        "/api/spheroidization?abnormal=false", headers=headers
    ).json()["data"]
    assert only_normal["items"][0]["id"] == normal["id"]


# ---------------- 标准全链路 ----------------

def test_标准创建当前历史切换日志(env):
    client, _ = env
    _body, headers = _login(client)

    first = _standard(client, headers)["data"]
    second = _standard(
        client, headers, standard_spheroidization_time=80.0
    )["data"]

    current = client.get("/api/standards/current").json()["data"]
    assert current["id"] == second["id"]
    assert current["standard_spheroidization_time_upper"] == 105.0

    history = client.get("/api/standards/history", headers=headers).json()["data"]
    # 后端按 id 升序给历史；前端自己排版，不依赖顺序
    assert {item["id"] for item in history} >= {first["id"], second["id"]}

    switched = client.post(
        "/api/standards/switch",
        json={"standard_id": first["id"], "reason": "全链路验收"},
        headers=headers,
    ).json()
    assert switched["code"] == 200
    assert switched["data"]["id"] == first["id"]

    logs = client.get("/api/standards/switch-logs", headers=headers).json()["data"]
    assert set(logs) == {"items", "page", "page_size"}
    item = logs["items"][0]
    for key in ("id", "switched_at", "summary", "reason"):
        assert key in item
    assert item["to_standard_id"] == first["id"]
    assert item["to_value"] == 70.0
    assert item["operated_by"] == "root"


# ---------------- 账号全链路 ----------------

def test_账号管理全链路(env):
    client, _ = env
    _body, headers = _login(client)

    created = client.post(
        "/api/users",
        json={"username": "zhangsan", "password": "pass1234", "is_admin": False},
        headers=headers,
    ).json()
    assert created["code"] == 200
    user = created["data"]
    assert user["enabled"] is True
    assert user["permission_keys"] == []

    # 授权
    granted = client.put(
        f"/api/users/{user['id']}/permissions",
        json={"permission_keys": ["page:records", "action:process"]},
        headers=headers,
    ).json()
    assert granted["code"] == 200

    # 普通用户登录后拿到的权限快照
    body, worker_headers = _login(client, "zhangsan", "pass1234")
    assert body["data"]["user"]["permission_keys"] == ["action:process", "page:records"]

    # 有权限能处置、无权限不能进用户管理
    _standard(client, headers)
    record = _record(client, spheroidization_image=None)["data"]
    assert client.post(
        f"/api/spheroidization/{record['id']}/process", headers=worker_headers
    ).json()["code"] == 200
    assert client.get("/api/users", headers=worker_headers).json()["code"] == 403

    # 重置密码
    assert client.post(
        f"/api/users/{user['id']}/password",
        json={"new_password": "newpass123"},
        headers=headers,
    ).json()["code"] == 200
    assert _login(client, "zhangsan", "pass1234")[0]["code"] == 401
    assert _login(client, "zhangsan", "newpass123")[0]["code"] == 200

    # 停用 / 启用（前端发布尔）
    assert client.put(
        f"/api/users/{user['id']}/enabled", json={"enabled": False}, headers=headers
    ).json()["code"] == 200
    assert _login(client, "zhangsan", "newpass123")[0]["code"] == 401
    assert client.put(
        f"/api/users/{user['id']}/enabled", json={"enabled": True}, headers=headers
    ).json()["code"] == 200
    assert _login(client, "zhangsan", "newpass123")[0]["code"] == 200

    # 列表字段
    listed = client.get("/api/users", headers=headers).json()["data"]
    worker = next(item for item in listed if item["username"] == "zhangsan")
    assert set(worker) >= {
        "id",
        "username",
        "enabled",
        "is_admin",
        "permission_keys",
        "created_by",
        "created_at",
    }


def test_注销后_token_立即失效(env):
    client, _ = env
    _body, headers = _login(client)
    assert client.post("/api/users/logout", headers=headers).json()["code"] == 200
    assert client.get("/api/users/me", headers=headers).json()["code"] == 401
    # 失效后列表仍可游客访问，但用户管理不行
    assert client.get("/api/users", headers=headers).json()["code"] == 401


def test_健康检查与错误信封(env):
    client, _ = env
    body = client.get("/api/health").json()
    assert set(body) == {"code", "message", "data"}
    # 不存在的记录：404 也是信封，不是裸 HTTP 错误页
    _body, headers = _login(client)
    missing = client.get("/api/spheroidization/9999", headers=headers).json()
    assert missing["code"] == 404
    assert set(missing) == {"code", "message", "data"}


# ---------------- 部署链路：视频代理 / 前端托管 ----------------

def test_视频代理上游不可用时返回503信封(env, monkeypatch):
    """视频服务没起来时，前端拿到 503 + 信封，而不是裸 500/挂起。"""
    from app.api import video

    monkeypatch.setattr(video, "_upstream_base", lambda: "http://127.0.0.1:1")
    client, _ = env
    resp = client.get("/api/video_feed1")
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == 503 and body["data"] is None


def test_前端构建产物存在时由后端托管(env):
    """有 frontend/dist 时，/ 返回 HTML、未知 /api 仍是 JSON 信封。

    没构建过就跳过——这条只在打包部署前有意义。
    """
    from pathlib import Path

    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if not dist.is_dir():
        pytest.skip("未构建前端（npm run build）")

    client, _ = env
    index = client.get("/")
    assert index.status_code == 200
    assert "text/html" in index.headers["content-type"]

    spa = client.get("/records/users")
    assert spa.status_code == 200
    assert "text/html" in spa.headers["content-type"]

    missing_api = client.get("/api/not-exist")
    assert missing_api.status_code == 404
    assert missing_api.json()["code"] == 404
