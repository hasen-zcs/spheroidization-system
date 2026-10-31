"""前后端 API 契约测试。

这些用例直接经过 FastAPI，而不是只调用 UseCase。目的是锁住前端依赖的
请求字段、响应字段、分页结构、统计字段和最新复核结果。
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
        "created_by": "测试员",
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
        "spheroidization_temperature": 1520.0,
        "spheroidization_temperature_time": "2026-09-26 08:00:10",
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
        yield client, container

    app.dependency_overrides.clear()
    conn.close()


def _post_standard(client, **overrides):
    response = client.post("/api/standards", json=_standard_payload(**overrides))
    assert response.status_code == 200
    assert response.json()["code"] == 200
    return response.json()["data"]


def _post_record(client, **overrides):
    response = client.post("/api/spheroidization", json=_record_payload(**overrides))
    assert response.status_code == 200
    assert response.json()["code"] == 200
    return response.json()["data"]


def test_球化记录请求必须包含前端表单的新字段(api_client):
    client, _ = api_client
    _post_standard(client)

    response = client.post(
        "/api/spheroidization",
        json={
            "detection_time": "2026-09-26 08:00:00",
            "spheroidization_start_time": "2026-09-26 08:00:05",
            "spheroidization_end_time": "2026-09-26 08:01:10",
            "actual_spheroidization_time": 65.0,
            "spheroidization_abnormal": False,
        },
    )

    body = response.json()
    assert body["code"] == 422
    assert "spheroidization_temperature" in body["message"]
    assert "spheroidization_weight" in body["message"]


def test_标准旧字段被拒绝而不是静默忽略(api_client):
    client, _ = api_client
    payload = _standard_payload()
    payload["standard_entry_length"] = 130

    body = client.post("/api/standards", json=payload).json()

    assert body["code"] == 422
    assert "standard_entry_length" in body["message"]


def test_标准球化时间必须大于零(api_client):
    client, _ = api_client

    body = client.post(
        "/api/standards",
        json=_standard_payload(standard_spheroidization_time=0),
    ).json()

    assert body["code"] == 422
    assert "standard_spheroidization_time" in body["message"]


def test_应用历史标准后当前标准持久变化(api_client):
    client, _ = api_client
    first = _post_standard(client, standard_spheroidization_time=65.0)
    _post_standard(client, standard_spheroidization_time=70.0)

    applied = client.post(
        f"/api/standards/{first['id']}/apply"
    ).json()
    assert applied["code"] == 200
    assert applied["data"]["id"] == first["id"]

    current = client.get("/api/standards/current").json()
    assert current["data"]["id"] == first["id"]

    history = client.get("/api/standards/history").json()
    assert [item["id"] for item in history["data"]] == [
        first["id"],
        first["id"] + 1,
    ]


def test_记录响应用新字段并包含空复核结果(api_client):
    client, _ = api_client
    _post_standard(client)

    record = _post_record(client)

    assert record["spheroidization_temperature"] == 1520.0
    assert record["spheroidization_weight"] == 1600.0
    assert record["spheroidization_wire_entry_total_duration"] == 70.0
    assert record["review_result"] is None
    assert "temperature" not in record
    assert "weight" not in record


def test_列表分页筛选和统计使用新契约(api_client):
    client, _ = api_client
    _post_standard(client)
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
    ).json()
    assert abnormal["data"]["total"] == 1

    stats = client.get("/api/spheroidization/stats").json()
    assert stats["data"] == {
        "total": 3,
        "abnormal": 1,
        "processed": 0,
        "unprocessed": 3,
    }


def test_JPG图片按Base64入库并以BLOB原样读回(api_client):
    client, container = api_client
    _post_standard(client)
    jpeg = b"\xff\xd8\xff\xe0" + b"contract-test-image-data" + b"\xff\xd9"
    encoded = base64.b64encode(jpeg).decode("ascii")

    record = _post_record(client, spheroidization_image=encoded)

    row = container.conn.execute(
        "SELECT spheroidization_image FROM SpheroidizationRecord WHERE "
        "spheroidization_record_id = ?",
        (record["id"],),
    ).fetchone()
    assert bytes(row["spheroidization_image"]) == jpeg

    detail = client.get(f"/api/spheroidization/{record['id']}").json()
    assert detail["data"]["spheroidization_image"] == encoded

    image_response = client.get(
        f"/api/spheroidization/{record['id']}/image"
    )
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/jpeg"
    assert image_response.content == jpeg


def test_列表和详情返回最新一条复核结果(api_client):
    client, _ = api_client
    _post_standard(client)
    record = _post_record(client)

    first = client.post(
        "/api/reviews",
        json={
            "spheroidization_record_id": record["id"],
            "review_result": "正常",
            "review_remark": "首次复核",
            "reviewer": "张三",
        },
    ).json()
    assert first["code"] == 200

    second = client.post(
        "/api/reviews",
        json={
            "spheroidization_record_id": record["id"],
            "review_result": "异常",
            "review_remark": "二次复核",
            "reviewer": "李四",
        },
    ).json()
    assert second["code"] == 200

    page = client.get("/api/spheroidization").json()
    assert page["data"]["items"][0]["review_result"] == "异常"

    detail = client.get(f"/api/spheroidization/{record['id']}").json()
    assert detail["data"]["review_result"] == "异常"
    assert detail["data"]["spheroidization_image"] is None

