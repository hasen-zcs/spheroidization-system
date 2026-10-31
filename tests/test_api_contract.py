"""前后端 API 契约测试。

这些用例直接经过 FastAPI，而不是只调用 UseCase。目的是锁住前端依赖的
请求字段、响应字段、分页结构、统计字段和最新复核结果。

2026-10 起多数写接口要求登录，夹具里先建一个超管并登录，
把 Authorization 头一起交给用例。游客能看的接口另外单独测。
"""

import base64
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Container, get_container
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app


def _standard_payload(**overrides):
    payload = {
        "standard_spheroidization_time": 70.0,
        "standard_spheroidization_time_upper": 75.0,
        "standard_spheroidization_time_lower": 65.0,
        "weighing_standard": 1500.0,
        "remark": "契约测试",
    }
    payload.update(overrides)
    return payload


def _record_payload(**overrides):
    payload = {
        "detection_time": "2026-09-26 08:00:00",
        "spheroidization_start_time": "2026-09-26 08:00:05",
        "spheroidization_end_time": "2026-09-26 08:01:10",
        "actual_spheroidization_time": 65.0,
        "spheroidization_abnormal": False,
        "spheroidization_wire_entry_start_time": "2026-09-26 08:00:20",
        "spheroidization_wire_entry_end_time": "2026-09-26 08:01:30",
        "spheroidization_wire_entry_total_duration": 70.0,
        "spheroidization_weight": 1600.0,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def api_client(tmp_path):
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
        # 超管拥有全部权限，用它测正常路径；游客路径的用例自己不带这个头
        container.create_user().execute("admin", "pass1234", True, "system")
        token = container.login().execute("admin", "pass1234")["token"]
        headers = {"Authorization": f"Bearer {token}"}
        yield client, container, headers

    app.dependency_overrides.clear()
    conn.close()


@pytest.fixture
def guest_client(api_client):
    """只拿 client，不带登录头。"""
    client, _, _ = api_client
    return client


def _post_standard(client, headers, **overrides):
    response = client.post(
        "/api/standards",
        json=_standard_payload(**overrides),
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["code"] == 200
    return response.json()["data"]


def _post_record(client, **overrides):
    # 这个接口是给上游检测程序用的，不要求登录
    response = client.post("/api/spheroidization", json=_record_payload(**overrides))
    assert response.status_code == 200
    assert response.json()["code"] == 200
    return response.json()["data"]


def test_球化记录缺必填字段是422(guest_client):
    client = guest_client

    response = client.post(
        "/api/spheroidization",
        json={
            "detection_time": "2026-09-26 08:00:00",
            "spheroidization_abnormal": False,
        },
    )

    body = response.json()
    assert body["code"] == 422
    # 进线和重量仍然是必填，缺失要指名道姓
    assert "spheroidization_weight" in body["message"]


def test_已经删掉的温度字段现在会被拒绝(guest_client):
    """上游如果还在发温度字段，这里要立刻 422，而不是静默丢数据。"""
    client = guest_client

    body = client.post(
        "/api/spheroidization",
        json=_record_payload(spheroidization_temperature=1520.0),
    ).json()

    assert body["code"] == 422
    assert "spheroidization_temperature" in body["message"]


def test_标准旧字段被拒绝而不是静默忽略(api_client):
    client, _, headers = api_client
    payload = _standard_payload()
    payload["standard_entry_length"] = 130

    body = client.post("/api/standards", json=payload, headers=headers).json()

    assert body["code"] == 422
    assert "standard_entry_length" in body["message"]


def test_标准创建人不再由前端传(api_client):
    """前端多传 created_by 会被 extra="forbid" 打回来。"""
    client, _, headers = api_client

    body = client.post(
        "/api/standards",
        json=_standard_payload(created_by="张三"),
        headers=headers,
    ).json()

    assert body["code"] == 422
    assert "created_by" in body["message"]


def test_标准球化时间必须大于零(api_client):
    client, _, headers = api_client

    body = client.post(
        "/api/standards",
        json=_standard_payload(standard_spheroidization_time=0),
        headers=headers,
    ).json()

    assert body["code"] == 422
    assert "standard_spheroidization_time" in body["message"]


def test_切换标准后当前标准变化并留下日志(api_client):
    client, _, headers = api_client
    first = _post_standard(client, headers, standard_spheroidization_time=65.0)
    _post_standard(client, headers, standard_spheroidization_time=70.0)

    switched = client.post(
        "/api/standards/switch",
        json={"to_standard_record_id": first["id"], "reason": "改用旧标准"},
        headers=headers,
    ).json()
    assert switched["code"] == 200
    assert switched["data"]["id"] == first["id"]

    current = client.get("/api/standards/current").json()
    assert current["data"]["id"] == first["id"]

    history = client.get("/api/standards/history", headers=headers).json()
    assert [item["id"] for item in history["data"]] == [
        first["id"],
        first["id"] + 1,
    ]

    logs = client.get("/api/standards/switch-logs", headers=headers).json()
    assert logs["code"] == 200
    assert len(logs["data"]["items"]) == 1
    entry = logs["data"]["items"][0]
    assert entry["to_standard_record_id"] == first["id"]
    assert entry["operated_by"] == "admin"
    assert "改用旧标准" in entry["summary"]
    # 切之前是第 2 条标准，日志要记下来
    assert entry["from_standard_record_id"] == first["id"] + 1
    assert entry["from_standard"]["id"] == first["id"] + 1


def test_切换标准必须填原因(api_client):
    client, _, headers = api_client
    first = _post_standard(client, headers)

    body = client.post(
        "/api/standards/switch",
        json={"to_standard_record_id": first["id"], "reason": "   "},
        headers=headers,
    ).json()

    assert body["code"] == 422
    assert "reason" in body["message"]


def test_记录响应带异常分类和空温度(api_client):
    client, _, headers = api_client
    _post_standard(client, headers)

    record = _post_record(client, abnormal_type=3, abnormal_reason="超过标准")

    assert record["abnormal_type"] == 3
    assert record["abnormal_reason"] == "超过标准"
    assert record["spheroidization_weight"] == 1600.0
    assert record["spheroidization_wire_entry_total_duration"] == 70.0
    assert record["review_result"] is None
    # 温度拆表后这里返回关联到的那条，没有关联就是 None
    assert record["temperature"] is None
    assert record["temperature_time"] is None
    assert "weight" not in record


def test_温度上报后随记录一起返回(api_client):
    client, _, headers = api_client
    _post_standard(client, headers)
    record = _post_record(client)

    reported = client.post(
        "/api/temperature",
        json={
            "gun_no": 2,
            "temperature": 1402.5,
            "measured_at": "2026-09-26 08:05:00",
            "spheroidization_record_id": record["id"],
        },
    ).json()
    assert reported["code"] == 200
    assert reported["data"]["gun_no"] == 2

    page = client.get("/api/spheroidization").json()
    item = page["data"]["items"][0]
    assert item["temperature"] == 1402.5
    assert item["temperature_time"] == "2026-09-26 08:05:00"


def test_温度上报时间格式不对被拒(guest_client):
    body = guest_client.post(
        "/api/temperature",
        json={
            "gun_no": 1,
            "temperature": 1400.0,
            "measured_at": "2026-9-26 8:05",
        },
    ).json()

    assert body["code"] == 422
    assert "measured_at" in body["message"]


def test_列表分页筛选和统计使用新契约(api_client):
    client, _, headers = api_client
    _post_standard(client, headers)
    _post_record(client, spheroidization_abnormal=False)
    _post_record(client, spheroidization_abnormal=True)
    _post_record(client, spheroidization_abnormal=False)

    first_page = client.get(
        "/api/spheroidization",
        params={"page": 1, "page_size": 2},
    ).json()
    assert first_page["code"] == 200
    assert first_page["data"]["total"] == 3
    assert len(first_page["data"]["items"]) == 2
    assert first_page["data"]["has_more"] is True
    assert [item["id"] for item in first_page["data"]["items"]] == [3, 2]

    abnormal = client.get(
        "/api/spheroidization",
        params={"abnormal": "true", "page_size": 20},
        headers=headers,
    ).json()
    assert abnormal["data"]["total"] == 1

    stats = client.get("/api/spheroidization/stats").json()
    assert stats["data"] == {
        "total": 3,
        "abnormal": 1,
        "processed": 0,
        "unprocessed": 3,
    }


def test_游客带abnormal参数被拒(guest_client):
    """光给 /abnormal 挂权限不够，?abnormal=true 这条路也要堵上。"""
    body = guest_client.get(
        "/api/spheroidization",
        params={"abnormal": "true"},
    ).json()

    assert body["code"] == 403


def test_游客能看正常记录的列表(guest_client):
    body = guest_client.get("/api/spheroidization").json()
    assert body["code"] == 200


def test_详情和图片需要登录(api_client):
    client, _, headers = api_client
    _post_standard(client, headers)
    record = _post_record(client)

    assert client.get(f"/api/spheroidization/{record['id']}").json()["code"] == 401
    assert client.get(f"/api/spheroidization/{record['id']}").json()["code"] == 401
    # 带上登录态就能看
    assert (
        client.get(
            f"/api/spheroidization/{record['id']}", headers=headers
        ).json()["code"]
        == 200
    )


def test_JPG图片按Base64入库并以BLOB原样读回(api_client):
    client, container, headers = api_client
    _post_standard(client, headers)
    jpeg = b"\xff\xd8\xff\xe0" + b"contract-test-image-data" + b"\xff\xd9"
    encoded = base64.b64encode(jpeg).decode("ascii")

    record = _post_record(client, spheroidization_image=encoded)

    row = container.conn.execute(
        "SELECT spheroidization_image FROM SpheroidizationRecord WHERE "
        "spheroidization_record_id = ?",
        (record["id"],),
    ).fetchone()
    assert bytes(row["spheroidization_image"]) == jpeg

    detail = client.get(
        f"/api/spheroidization/{record['id']}", headers=headers
    ).json()
    assert detail["data"]["spheroidization_image"] == encoded

    image_response = client.get(
        f"/api/spheroidization/{record['id']}/image", headers=headers
    )
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/jpeg"
    assert image_response.content == jpeg


def test_列表和详情返回最新一条复核结果(api_client):
    client, _, headers = api_client
    _post_standard(client, headers)
    record = _post_record(client)

    first = client.post(
        "/api/reviews",
        json={
            "spheroidization_record_id": record["id"],
            "review_result": "正常",
            "review_remark": "首次复核",
        },
        headers=headers,
    ).json()
    assert first["code"] == 200
    # 复核人从登录态取，不接受前端传值
    assert first["data"]["reviewer"] == "admin"

    second = client.post(
        "/api/reviews",
        json={
            "spheroidization_record_id": record["id"],
            "review_result": "异常",
            "review_remark": "二次复核",
        },
        headers=headers,
    ).json()
    assert second["code"] == 200

    page = client.get("/api/spheroidization").json()
    assert page["data"]["items"][0]["review_result"] == "异常"

    detail = client.get(
        f"/api/spheroidization/{record['id']}", headers=headers
    ).json()
    assert detail["data"]["review_result"] == "异常"
    assert detail["data"]["spheroidization_image"] is None


def test_复核接口不再接受前端传复核人(api_client):
    client, _, headers = api_client
    _post_standard(client, headers)
    record = _post_record(client)

    body = client.post(
        "/api/reviews",
        json={
            "spheroidization_record_id": record["id"],
            "review_result": "正常",
            "reviewer": "张三",
        },
        headers=headers,
    ).json()

    assert body["code"] == 422
    assert "reviewer" in body["message"]


def test_登录失败提示不区分用户名和密码(api_client):
    client, _, _ = api_client

    no_user = client.post(
        "/api/users/login", json={"username": "nobody", "password": "x"}
    ).json()
    bad_password = client.post(
        "/api/users/login", json={"username": "admin", "password": "wrong"}
    ).json()

    assert no_user["code"] == bad_password["code"] == 401
    assert no_user["message"] == bad_password["message"]


def test_未登录调用户管理被401(guest_client):
    body = guest_client.get("/api/users").json()
    assert body["code"] == 401


def test_用户响应不含密码哈希(api_client):
    client, _, headers = api_client

    body = client.get("/api/users", headers=headers).json()
    assert body["code"] == 200
    assert body["data"][0]["username"] == "admin"
    assert "password_hash" not in body["data"][0]
