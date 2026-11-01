"""T-004c：现场真实温度字段的宽容解析（device_name / spheroidization_temperature*）。

真实数据在 ~/spheroidization-delivery/dataset/temperature.jsonl（现场 60 炉导出）。
核心坑：device_name 带日期前缀（"2026-11-01 测温枪4"），枪号必须剥日期后取，
绝不能吃成 2026。
"""

import json
from pathlib import Path

from merge.sources.temp import parse_event, parse_gun

DATASET = Path.home() / "spheroidization-delivery" / "dataset" / "temperature.jsonl"


def _real_lines():
    return [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_real_fields_last_line():
    """现场最后一行：枪4、1467、16:50:29（任务书指定的关键指标行）。"""
    obj = _real_lines()[-1]
    assert obj["device_name"] == "2026-11-01 测温枪4"
    event = parse_event(obj)
    assert event is not None
    assert event["gun_no"] == 4
    assert event["value"] == 1467.0
    assert event["measured_at"] == "2026-11-01 16:50:29"


def test_real_fields_first_three_lines():
    """真实前 3 行（都是枪4、1419）：时间各不相同，枪号绝不能取成 2026。"""
    expected = [
        ("2026-11-01 09:15:38", 1419.0),
        ("2026-11-01 09:15:42", 1419.0),
        ("2026-11-01 09:15:48", 1419.0),
    ]
    for obj, (measured_at, value) in zip(_real_lines()[:3], expected):
        event = parse_event(obj)
        assert event is not None
        assert event["gun_no"] == 4, f"枪号取成 {event['gun_no']}（多半吃到了日期）"
        assert event["value"] == value
        assert event["measured_at"] == measured_at


def test_device_name_other_guns_not_date():
    """文件里混有测温枪2/枪1：剥日期后应取 2 / 1，过滤留给上层。"""
    by_gun = {}
    for obj in _real_lines():
        gun = parse_gun(obj)
        if gun is not None:
            by_gun.setdefault(gun, obj)
    assert parse_gun(by_gun[2]) == 2
    assert parse_gun(by_gun[1]) == 1
    assert 2026 not in by_gun


def test_legacy_format_regression():
    """旧格式（gun_no/temperature/measured_at）仍然能解析。"""
    event = parse_event(
        {"gun_no": 4, "temperature": "1450", "measured_at": "2026-10-01 08:00:00"}
    )
    assert event is not None
    assert event["gun_no"] == 4
    assert event["value"] == 1450.0
    assert event["measured_at"] == "2026-10-01 08:00:00"


def test_gun_name_without_device_name_unchanged():
    """无 device_name 但有 gun_name：行为与旧逻辑一致。"""
    event = parse_event(
        {"gun_name": "测温枪4", "temperature": 1400, "measured_at": "2026-10-01 09:00:00"}
    )
    assert event is not None
    assert event["gun_no"] == 4
    assert event["value"] == 1400.0


def test_unparseable_skipped():
    """缺字段/取不出枪号：跳过，不猜。"""
    assert parse_event({"device_name": "2026-11-01 测温枪", "spheroidization_temperature": "1467"}) is None
    assert parse_event({"device_name": "未知设备", "spheroidization_temperature": "1467",
                        "spheroidization_temperature_time": "2026-11-01 16:50:29"}) is None
