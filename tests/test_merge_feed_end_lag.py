"""TASK-7：喂丝结束信号迟到容错（heat 组包路径）。

背景：526 炉统计发现 3.3% 的炉子 PLC 喂丝结束位晚于亮光结束几分钟才翻转，
进线时长被记成假的大值。老板拍板：结束位晚于亮光结束 90s 以上才到达 →
判定信号迟到，进线结束/时长按无效处理（NULL + 类型 2 语义），原始值写入原因。

标记发生在 build_payload_from_heat 里、TASK-5 缺失检查之前；
迟到炉的 abnormal_reason 里只该有迟到那句，不能再带「未采集到喂丝结束」。
"""

from merge.assemble import build_payload_from_heat

DEVICE = "test-device"

MISSING_NOTE = "进线结束时间缺失（PLC 未采集到喂丝结束）"


def lag_note(lag: float) -> str:
    return "喂丝结束信号迟到（亮光结束后 +{:.0f}s 才到达，原值弃用）".format(lag)


def _heat_record(**overrides) -> dict:
    """一炉 heat 记录：亮光 09:00:30→09:02:00，进线 09:00:25 起。

    喂丝结束默认 = 亮光结束 +120s（迟到形态），其余关键字覆盖。
    """
    rec = {
        "reaction_count": 77,
        "detection_time": "2026-11-03 09:00:00.123",
        "plc_button_time": "2026-11-03 08:59:30.123",
        "spheroidization_start_time": "2026-11-03 09:00:30.000",
        "spheroidization_end_time": "2026-11-03 09:02:00.000",
        "actual_spheroidization_time": None,
        "spheroidization_abnormal": 0,
        "abnormal_type": 0,
        "abnormal_reason": None,
        "spheroidization_wire_entry_start_time": "2026-11-03 09:00:25.000",
        "spheroidization_wire_entry_end_time": "2026-11-03 09:04:00.000",
        "spheroidization_wire_entry_total_duration": 610.0,
        "spheroidization_weight": 1600.0,
    }
    rec.update(overrides)
    return rec


def test_迟到120s原type0_置null改type2且不重复缺失原因():
    """① 喂丝结束 = 亮光结束 +120s，原 type 0 → 结束/时长置 None、type 2、
    reason 含「+120」且**不含**「未采集到喂丝结束」（迟到句独占 reason）。"""
    payload = build_payload_from_heat(_heat_record(abnormal_type=0), None, DEVICE)
    assert payload["spheroidization_wire_entry_end_time"] is None
    assert payload["spheroidization_wire_entry_total_duration"] is None
    assert payload["abnormal_type"] == 2
    assert payload["spheroidization_abnormal"] == 1
    assert "+120" in payload["abnormal_reason"]
    assert lag_note(120.0) == payload["abnormal_reason"]
    assert "未采集到喂丝结束" not in payload["abnormal_reason"]


def test_迟到且原type5_保持type追加迟到句():
    """② 原 type 5（带原 reason）+ 迟到 → type 保持 5、reason = 原 reason +「；」+ 迟到句。"""
    payload = build_payload_from_heat(
        _heat_record(abnormal_type=5, spheroidization_abnormal=1, abnormal_reason="中间停顿"),
        None,
        DEVICE,
    )
    assert payload["abnormal_type"] == 5
    assert payload["spheroidization_abnormal"] == 1
    assert payload["abnormal_reason"] == "中间停顿；" + lag_note(120.0)
    assert payload["spheroidization_wire_entry_end_time"] is None
    assert payload["spheroidization_wire_entry_total_duration"] is None


def test_lag30s_字段原样不动():
    """③ lag=30s（≤90s）→ 整条 payload 与未改动行为完全一致（回归）。"""
    payload = build_payload_from_heat(
        _heat_record(
            spheroidization_wire_entry_end_time="2026-11-03 09:02:30.000",
            spheroidization_wire_entry_total_duration=125.0,
        ),
        None,
        DEVICE,
    )
    assert payload == {
        "device_id": DEVICE,
        "external_id": "heat:77:2026-11-03 09:00:25.000",
        "detection_time": "2026-11-03 09:00:00.123",
        "plc_button_time": "2026-11-03 08:59:30.123",
        "spheroidization_start_time": "2026-11-03 09:00:30.000",
        "spheroidization_end_time": "2026-11-03 09:02:00.000",
        "actual_spheroidization_time": 90.0,
        "spheroidization_abnormal": 0,
        "abnormal_type": 0,
        "abnormal_reason": None,
        "segments": [],
        "spheroidization_wire_entry_start_time": "2026-11-03 09:00:25.000",
        "spheroidization_wire_entry_end_time": "2026-11-03 09:02:30.000",
        "spheroidization_wire_entry_total_duration": 125.0,
        "spheroidization_weight": 1600.0,
    }


def test_lag恰好90s_不动_严格大于才算迟到():
    """④ 边界：恰好 90.0s → 不判定迟到，字段原样（严格大于 90 才算迟到）。"""
    payload = build_payload_from_heat(
        _heat_record(
            spheroidization_wire_entry_end_time="2026-11-03 09:03:30.000",
            spheroidization_wire_entry_total_duration=185.0,
        ),
        None,
        DEVICE,
    )
    assert payload["spheroidization_wire_entry_end_time"] == "2026-11-03 09:03:30.000"
    assert payload["spheroidization_wire_entry_total_duration"] == 185.0
    assert payload["abnormal_type"] == 0
    assert payload["spheroidization_abnormal"] == 0
    assert payload["abnormal_reason"] is None


def test_亮光结束缺失_走不到迟到判定_不动():
    """⑤ 亮光结束缺失（算不出 lag）+ 喂丝结束存在 → 原样不动。"""
    payload = build_payload_from_heat(
        _heat_record(spheroidization_end_time=None),
        None,
        DEVICE,
    )
    assert payload["spheroidization_end_time"] is None
    assert payload["spheroidization_wire_entry_end_time"] == "2026-11-03 09:04:00.000"
    assert payload["spheroidization_wire_entry_total_duration"] == 610.0
    assert payload["abnormal_type"] == 0
    assert payload["spheroidization_abnormal"] == 0
    assert payload["abnormal_reason"] is None


def test_喂丝结束缺失_原TASK5场景回归():
    """⑥ 喂丝结束缺失（TASK-5 原有场景）→ type 2 + 缺失原因，行为与改动前一致。"""
    payload = build_payload_from_heat(
        _heat_record(
            abnormal_type=0,
            spheroidization_wire_entry_end_time=None,
            spheroidization_wire_entry_total_duration=None,
        ),
        None,
        DEVICE,
    )
    assert payload["abnormal_type"] == 2
    assert payload["spheroidization_abnormal"] == 1
    assert payload["abnormal_reason"] == MISSING_NOTE
