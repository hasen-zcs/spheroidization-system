"""报表接口（/api/reports/summary、/api/reports/export）的契约测试。

和 test_api_contract.py 同一个套路：临时内存库 + 覆盖 get_container，
数据直接走 Container 的 UseCase 造（和管理库唯一的写入口一致），
接口走真 FastAPI。
"""

import io
import sqlite3

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

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


# ==========================================================
# TASK-2 新增：班次 / 标准 / 趋势 / Excel 导出
# ==========================================================


def test_空库新增三块结构(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    data = _summary(client, headers).json()["data"]
    assert data["shifts"] == [
        {"shift": "白班", "total": 0, "abnormal": 0, "normal": 0, "avg_actual_time": None},
        {"shift": "夜班", "total": 0, "abnormal": 0, "normal": 0, "avg_actual_time": None},
    ]
    assert data["standards"] == []
    assert data["trend"] == []


def test_班次边界归属与均值(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    # 四条边界各一条：07:59 夜班 / 08:00 白班 / 19:59 白班 / 20:00 夜班
    _seed_record(container, 0, "2026-09-20 07:59:00", abnormal_type=0)
    _seed_record(container, 1, "2026-09-20 08:00:00", abnormal_type=1)
    _seed_record(container, 2, "2026-09-20 19:59:00", abnormal_type=2)
    _seed_record(container, 3, "2026-09-20 20:00:00", abnormal_type=3)
    data = _summary(client, headers, start="2026-09-20", end="2026-09-20").json()["data"]
    assert [row["shift"] for row in data["shifts"]] == ["白班", "夜班"]
    day, night = data["shifts"]
    # 白班 = 08:00(类型1) + 19:59(类型2)，都是异常
    assert day["total"] == 2
    assert day["abnormal"] == 2
    assert day["normal"] == 0
    assert day["avg_actual_time"] == round((61.0 + 62.0) / 2, 4)
    # 夜班 = 07:59(类型0 正常) + 20:00(类型3 异常)
    assert night["total"] == 2
    assert night["abnormal"] == 1
    assert night["normal"] == 1
    assert night["avg_actual_time"] == round((60.0 + 63.0) / 2, 4)


def test_班次时长全空时avg为null(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    create_record(container, "2026-09-20 09:00:00", None)
    create_record(container, "2026-09-20 21:00:00", None)
    data = _summary(client, headers, start="2026-09-20", end="2026-09-20").json()["data"]
    assert [row["avg_actual_time"] for row in data["shifts"]] == [None, None]


def test_standards分组与JOIN字段(api_client):
    client, container, headers = api_client
    std_a = create_standard(container, 65.0, "张三")
    _seed_record(container, 0, "2026-09-21 09:00:00", abnormal_type=0)
    _seed_record(container, 1, "2026-09-21 10:00:00", abnormal_type=3)
    # 新建标准立即生效，之后两条归属第二套标准
    std_b = create_standard(container, 75.0, "李四")
    _seed_record(container, 2, "2026-09-21 11:00:00", abnormal_type=0)
    _seed_record(container, 3, "2026-09-21 12:00:00", abnormal_type=6)  # 未判定(6)计入异常
    data = _summary(client, headers, start="2026-09-21", end="2026-09-21").json()["data"]
    assert [row["standard_record_id"] for row in data["standards"]] == [
        std_a.standard_record_id,
        std_b.standard_record_id,
    ]
    a, b = data["standards"]
    # JOIN 出来的标准表字段
    assert a["standard_time"] == 65.0
    assert a["standard_created_by"] == "张三"
    assert a["standard_created_at"]
    assert a["total"] == 2
    assert a["abnormal"] == 1
    assert a["avg_actual_time"] == round((60.0 + 61.0) / 2, 4)
    assert b["standard_time"] == 75.0
    assert b["standard_created_by"] == "李四"
    assert b["total"] == 2
    assert b["abnormal"] == 1
    assert b["avg_actual_time"] == round((62.0 + 63.0) / 2, 4)


def test_trend缺天补齐与异常率(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    # 09-01 两条（1 异常）、09-02 无数据、09-03 两条（1 异常）
    _seed_record(container, 0, "2026-09-01 09:00:00", abnormal_type=0)
    _seed_record(container, 1, "2026-09-01 10:00:00", abnormal_type=1)
    _seed_record(container, 2, "2026-09-03 09:00:00", abnormal_type=0)
    _seed_record(container, 3, "2026-09-03 10:00:00", abnormal_type=2)
    data = _summary(client, headers, start="2026-09-01", end="2026-09-03").json()["data"]
    trend = data["trend"]
    # 序列 3 项，逐日升序，缺天补齐
    assert [row["date"] for row in trend] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert trend[1] == {
        "date": "2026-09-02",
        "total": 0,
        "abnormal": 0,
        "abnormal_rate": 0,
        "avg_actual_time": None,
    }
    assert trend[0]["total"] == 2
    assert trend[0]["abnormal"] == 1
    assert trend[0]["abnormal_rate"] == 0.5
    assert trend[0]["avg_actual_time"] == round((60.0 + 61.0) / 2, 4)
    assert trend[2]["total"] == 2
    assert trend[2]["abnormal"] == 1
    assert trend[2]["abnormal_rate"] == 0.5
    assert trend[2]["avg_actual_time"] == round((62.0 + 63.0) / 2, 4)


def test_导出excel登录200且与CSV同参行数一致(api_client):
    client, container, headers = api_client
    create_standard(container, 70.0, "张三")
    first = _seed_record(container, 0, "2026-09-25 10:00:00", abnormal_type=3)
    _seed_record(container, 1, "2026-09-25 10:05:00")  # 类型 0，被 type=3 过滤掉
    last = _seed_record(container, 2, "2026-09-26 10:00:00", abnormal_type=3)

    params = {"start": "2026-09-25", "end": "2026-09-26", "type": 3}
    csv_lines = client.get(
        "/api/reports/export", params=params, headers=headers
    ).content.decode("utf-8-sig").strip().split("\n")
    assert len(csv_lines) == 3  # 表头 + 2 条

    response = client.get("/api/reports/export/excel", params=params, headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert disposition.endswith('.xlsx"')

    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    # 表头与 CSV 一致（中文列名）
    assert rows[0] == tuple(CSV_HEADER)
    # 行数 = CSV 同参数行数
    assert len(rows) == len(csv_lines)
    # 记录 ID 顺序与内容对齐
    assert [str(row[0]) for row in rows[1:]] == [
        str(first.spheroidization_record_id),
        str(last.spheroidization_record_id),
    ]
    assert rows[1][5] == "超过标准"


def test_导出excel游客401(api_client):
    client, _, _ = api_client
    response = client.get("/api/reports/export/excel")
    assert response.json()["code"] == 401
