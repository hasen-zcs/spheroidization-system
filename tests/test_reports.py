"""报表接口（/api/reports/summary、/api/reports/export）的契约测试。

和 test_api_contract.py 同一个套路：临时内存库 + 覆盖 get_container，
数据直接走 Container 的 UseCase 造（和管理库唯一的写入口一致），
接口走真 FastAPI。
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from conftest import create_record, create_standard, create_temperature, create_user
from app.dependencies import Container, get_container
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app
from app.schemas.reports import CSV_HEADER


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
        create_user(container, "admin", "pass1234", is_admin=True)
        token = container.login().execute("admin", "pass1234")["token"]
        headers = {"Authorization": f"Bearer {token}"}
        yield client, container, headers

    app.dependency_overrides.clear()
    conn.close()


def _guest(client):
    return client  # 不带 Authorization 头就是游客


def _summary(client, headers, **params):
    return client.get("/api/reports/summary", params=params, headers=headers)


def _seed_record(container, idx, detection_time, abnormal_type=None, **overrides):
    """造一条记录。类型 0 对应正常；不传类型则机器没给判定（NULL）。"""
    return create_record(
        container,
        detection_time,
        60.0 + idx,
        abnormal=1 if abnormal_type not in (0, None) else 0,
        abnormal_type=abnormal_type,
        **overrides,
    )


def test_游客访问summary和export都401(api_client):
    client, _, _ = api_client
    assert _summary(client, {}).json()["code"] == 401
    export = client.get("/api/reports/export")
    assert export.json()["code"] == 401


def test_空库summary全零不500(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    body = _summary(client, headers).json()
    assert body["code"] == 200
    data = body["data"]
    assert data["total"] == 0
    assert data["by_type"] == {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0}
    assert data["abnormal_count"] == 0
    assert data["abnormal_rate"] == 0
    assert data["unjudged_count"] == 0
    assert data["duration"] == {"avg": None, "median": None, "min": None, "max": None}
    assert data["temperature"]["covered"] == 0
    assert data["temperature"]["total"] == 0
    assert data["temperature"]["coverage_rate"] == 0
    assert data["temperature"]["by_gun"] == {}
    assert data["by_day"] == []


def test_六种类型分布与异常率(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    for i, type_ in enumerate([0, 1, 2, 3, 4, 6]):
        _seed_record(container, i, f"2026-09-10 08:0{i}:00", abnormal_type=type_)
    data = _summary(client, headers).json()["data"]
    assert data["total"] == 6
    assert data["by_type"] == {"0": 1, "1": 1, "2": 1, "3": 1, "4": 1, "5": 0, "6": 1}
    # 异常 = 类型≠0（未判定 6 也在内），6 里单列 unjudged
    assert data["abnormal_count"] == 5
    assert data["abnormal_rate"] == round(5 / 6, 4)
    assert data["unjudged_count"] == 1


def test_只有部分记录有温度时覆盖率正确(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    ids = [
        _seed_record(container, i, f"2026-09-11 09:0{i}:00")
        for i in range(3)
    ]
    # 只给第 2 条挂温度，测温枪 4 号
    create_temperature(container, 4, 1502.5, "2026-09-11 09:01:05", record_id=ids[1].spheroidization_record_id)
    data = _summary(client, headers).json()["data"]
    temp = data["temperature"]
    assert temp["covered"] == 1
    assert temp["total"] == 3
    assert temp["coverage_rate"] == round(1 / 3, 4)
    assert "4" in temp["by_gun"]
    assert temp["by_gun"]["4"]["count"] == 1


def test_日期过滤含头含尾(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    _seed_record(container, 0, "2026-09-05 08:00:00")
    _seed_record(container, 1, "2026-09-05 23:59:59")  # 当天最后一秒，含尾
    _seed_record(container, 2, "2026-09-06 09:00:00")  # 第二天，不含
    data = _summary(client, headers, start="2026-09-05", end="2026-09-05").json()["data"]
    assert data["total"] == 2
    # 只给头不给尾：当天两条都在
    data = _summary(client, headers, start="2026-09-05").json()["data"]
    assert data["total"] == 3


def test_导出csv行数BOM与字段顺序(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    first = _seed_record(
        container, 0,
        "2026-09-12 10:00:00",
        abnormal_type=3,
        abnormal_reason="超过标准上限",
    )
    second = _seed_record(container, 1, "2026-09-12 10:05:00")
    create_temperature(container, 2, 1488.0, "2026-09-12 10:00:10", record_id=first.spheroidization_record_id)

    response = client.get("/api/reports/export", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "spheroidization_" in response.headers["content-disposition"]

    raw = response.content
    assert raw.startswith(b"\xef\xbb\xbf"), "CSV 首行必须带 UTF-8 BOM"
    text = raw.decode("utf-8-sig")
    lines = text.strip().split("\n")
    # 表头 + 2 条记录
    assert len(lines) == 3
    assert lines[0].split(",") == CSV_HEADER
    # 第一条：类型 3 → 超过标准，带温度 1488.0 / 枪号 2
    row1 = lines[1].split(",")
    assert row1[0] == str(first.spheroidization_record_id)
    assert row1[1] == "2026-09-12 10:00:00"
    assert row1[5] == "超过标准"
    assert row1[6] == "超过标准上限"
    assert row1[8] == "未处理"
    assert row1[12] == "1488.0"
    assert row1[13] == "2"
    # 第二条：正常、无温度（温度和枪号留空）
    row2 = lines[2].split(",")
    assert row2[0] == str(second.spheroidization_record_id)
    assert row2[5] == "正常"
    assert row2[12] == ""
    assert row2[13] == ""


def test_导出支持类型过滤(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    target = _seed_record(container, 0, "2026-09-13 11:00:00", abnormal_type=3)
    other = _seed_record(container, 1, "2026-09-13 11:05:00")
    text = client.get(
        "/api/reports/export", params={"type": 3}, headers=headers
    ).content.decode("utf-8-sig")
    lines = text.strip().split("\n")
    assert len(lines) == 2  # 表头 + 1 条
    assert lines[1].split(",")[0] == str(target.spheroidization_record_id)


def test_导出含复核结果(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    record = _seed_record(container, 0, "2026-09-14 12:00:00", abnormal_type=1)
    container.create_review().execute(
        record.spheroidization_record_id, 0, "王五", "复核没问题"
    )
    text = client.get("/api/reports/export", headers=headers).content.decode("utf-8-sig")
    row = text.strip().split("\n")[1].split(",")
    assert row[7] == "正常"  # 复核结果列


def test_日期参数非法返回422(api_client):
    client, _, headers = api_client
    body = _summary(client, headers, start="2026/09/05").json()
    assert body["code"] == 422


def test_开始晚于结束返回400(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    body = _summary(client, headers, start="2026-09-06", end="2026-09-05").json()
    assert body["code"] == 400
