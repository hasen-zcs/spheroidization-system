"""TASK-5：heat 组包后进线结束/时长为 null → 标记为类型 2 异常。

背景：PLC 采不到喂丝结束（进线结束/时长为 null，回捞后仍缺）的炉次，
老板拍板直接当异常——归入类型 2（进线线异常），不加新类型、不动 schema。
标记发生在 build_payload_from_heat 组包之后（合并层才知道"回捞过仍缺失"）。
"""

from merge.assemble import build_payload_from_heat

DEVICE = "test-device"

MISSING_NOTE = "进线结束时间缺失（PLC 未采集到喂丝结束）"


def _heat_record(**overrides) -> dict:
    """一炉 heat 记录：进线结束/时长为 null（回捞后仍缺的形态）。"""
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
        "spheroidization_wire_entry_end_time": None,
        "spheroidization_wire_entry_total_duration": None,
        "spheroidization_weight": 1600.0,
    }
    rec.update(overrides)
    return rec


def test_进线结束null且原type为0_改成type2异常():
    """① null + 原 abnormal_type=0 → type 变 2、abnormal=1、reason 含缺失说明。"""
    payload = build_payload_from_heat(_heat_record(abnormal_type=0), None, DEVICE)
    assert payload["abnormal_type"] == 2
    assert payload["spheroidization_abnormal"] == 1
    assert MISSING_NOTE in payload["abnormal_reason"]
    # 原本没有别的原因，reason 就是这一句
    assert payload["abnormal_reason"] == MISSING_NOTE
    # null 原样保留（后端已接受 null，只补异常标记）
    assert payload["spheroidization_wire_entry_end_time"] is None
    assert payload["spheroidization_wire_entry_total_duration"] is None


def test_进线结束null且原type非0_保持type追加reason():
    """② null + 原 abnormal_type=5（带原 reason）→ type 保持 5、abnormal=1、reason = 原 reason + 分隔 + 缺失说明。"""
    payload = build_payload_from_heat(
        _heat_record(abnormal_type=5, spheroidization_abnormal=1, abnormal_reason="中间停顿"),
        None,
        DEVICE,
    )
    assert payload["abnormal_type"] == 5
    assert payload["spheroidization_abnormal"] == 1
    assert payload["abnormal_reason"] == "中间停顿；" + MISSING_NOTE


def test_进线结束非null_行为与原有一致回归():
    """③ 进线结束/时长非 null → payload 与原行为完全一致（回归）。"""
    rec = _heat_record(
        abnormal_type=0,
        spheroidization_wire_entry_end_time="2026-11-03 09:05:25.000",
        spheroidization_wire_entry_total_duration=300.0,
    )
    payload = build_payload_from_heat(rec, None, DEVICE)
    expected = {
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
        "spheroidization_wire_entry_end_time": "2026-11-03 09:05:25.000",
        "spheroidization_wire_entry_total_duration": 300.0,
        "spheroidization_weight": 1600.0,
    }
    assert payload == expected
