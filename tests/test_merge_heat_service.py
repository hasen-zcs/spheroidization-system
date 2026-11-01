"""heat 主源合并路径测试：三类 payload / 双读幂等 / 稳定幂等键。

样本取自 /home/hasen/spheroidization-delivery/dataset/heat_probe.txt：
类型 0 / 类型 1 各抽一条（probe 里本来就没类型 2 样本，按 heat schema 造一条）。
"""

import json
from pathlib import Path

from merge.assemble import build_payload_from_heat
from merge.config import Config
from merge.pair import parse_time
from merge.service import MergeService
from merge.state import MergeState

DATASET = Path("/home/hasen/spheroidization-delivery/dataset/heat_probe.txt")
DEVICE = "test-device"

PLC_KEYS = (
    "spheroidization_wire_entry_start_time",
    "spheroidization_wire_entry_end_time",
    "spheroidization_wire_entry_total_duration",
    "spheroidization_weight",
)


def _probe_records() -> list[dict]:
    """heat_probe.txt 是探查文档：只取 JSON 记录行。"""
    out = []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith('{"reaction_count"'):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _record_by_type(abnormal_type: int) -> dict:
    for rec in _probe_records():
        if rec.get("abnormal_type") == abnormal_type:
            return rec
    raise AssertionError(f"dataset 里没有 abnormal_type={abnormal_type} 的样本")


def _type2_record() -> dict:
    # 样本集没有类型 2：按 heat schema 造一条（start/end 缺失，同类型 1 形态）
    return {
        "reaction_count": 9001,
        "detection_time": "2026-10-29 23:00:00.123",
        "spheroidization_start_time": None,
        "spheroidization_end_time": None,
        "actual_spheroidization_time": None,
        "spheroidization_abnormal": 1,
        "abnormal_type": 2,
        "abnormal_reason": "造样本：类型 2",
        "spheroidization_wire_entry_start_time": "2026-10-29 23:00:40.500",
        "spheroidization_wire_entry_end_time": "2026-10-29 23:02:10.500",
        "spheroidization_wire_entry_total_duration": 90.0,
        "spheroidization_weight": 1800.0,
        "plc_button_time": "2026-10-29 23:00:00.123",
        "plc_arrival_time": None,
        "plc_anchor": "button",
    }


def test_payloads_three_types():
    """三类 payload：abnormal_type 分别为 0/1/2；类型 1/2 的 start/end 为 None 不报错。"""
    samples = (
        (0, _record_by_type(0)),
        (1, _record_by_type(1)),
        (2, _type2_record()),
    )
    for expected_type, rec in samples:
        payload = build_payload_from_heat(rec, None, DEVICE)
        assert payload["abnormal_type"] == expected_type
        assert payload["device_id"] == DEVICE
        assert payload["external_id"].startswith("heat:")
        # 稳定：同一条记录组两次包，幂等键不变
        assert build_payload_from_heat(rec, None, DEVICE)["external_id"] == payload["external_id"]
        # PLC 四字段原样取自 record（heat 记录已融合）
        for key in PLC_KEYS:
            assert payload[key] == rec.get(key)
        if expected_type in (1, 2):
            assert payload["spheroidization_start_time"] is None
            assert payload["spheroidization_end_time"] is None
            assert payload["actual_spheroidization_time"] is None


def test_payload_segments_mapping():
    """类型 0 样本：seq/start/end/duration_sec/gap_before_sec → 现有 segments 结构。

    probe 里唯一的分段记录（count 218）在探查文件里被截断、不是完整 JSON，
    所以拿 parse 得到的类型 0 样本附上按 schema 造的分段数组。

    T-004d 后：start/end 必须换算成"相对球化起点的秒"（float, ≥0），
    不能再把墙钟串原样塞进 start_offset/end_offset（后端 422 的根因）。
    """
    rec = dict(_record_by_type(0))
    rec["spheroidization_segments"] = [
        {
            "seq": 1,
            "start": rec["spheroidization_start_time"],
            "end": "2026-11-01 16:42:10.000",
            "duration_sec": 29.933,
            "gap_before_sec": None,
        },
        {
            "seq": 2,
            "start": "2026-11-01 16:42:40.000",
            "end": rec["spheroidization_end_time"],
            "duration_sec": 59.925,
            "gap_before_sec": 29.999,
        },
    ]
    payload = build_payload_from_heat(rec, None, DEVICE)
    segs = payload["segments"]
    assert len(segs) == 2
    t0 = parse_time(rec["spheroidization_start_time"])
    for src, dst in zip(rec["spheroidization_segments"], segs):
        assert dst["seg_index"] == src.get("seq")
        assert dst["start_offset"] == round(
            (parse_time(src["start"]) - t0).total_seconds(), 3
        )
        assert dst["end_offset"] == round(
            (parse_time(src["end"]) - t0).total_seconds(), 3
        )
        assert dst["gap_before"] == src.get("gap_before_sec")
        assert dst["duration"] == src.get("duration_sec")


def test_payload_temperature_rule():
    """温度同现规则：有就填（秒级），无则不填，绝不造假。"""
    rec = _record_by_type(0)
    no_temp = build_payload_from_heat(rec, None, DEVICE)
    assert "temperature" not in no_temp
    assert "temperature_time" not in no_temp
    assert "gun_no" not in no_temp

    payload = build_payload_from_heat(
        rec, {"gun_no": 4, "value": 38.5, "measured_at": "2026-11-01 16:42:10.789"}, DEVICE
    )
    assert payload["temperature"] == 38.5
    assert payload["temperature_time"] == "2026-11-01 16:42:10"  # 毫秒去掉
    assert payload["gun_no"] == 4


def test_double_ingest_single_pending(tmp_path, monkeypatch):
    """同一条 heat 记录读两轮（含游标重置全量重读）→ pending_upload 只有 1 条。"""
    heat_file = tmp_path / "heat_records.jsonl"
    heat_file.write_text(
        json.dumps(_record_by_type(1), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("MERGE_HEAT_FILE", str(heat_file))
    monkeypatch.setenv("MERGE_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("MERGE_DRYRUN_OUT", str(tmp_path / "dryrun.jsonl"))
    monkeypatch.setenv("MERGE_TEMP_ALL", str(tmp_path / "no_temp.jsonl"))  # 不存在 → 空
    monkeypatch.setenv("MERGE_TEMP_DIR", str(tmp_path / "no_temp_dir"))   # 兜底目录也不存在
    monkeypatch.setenv("MERGE_SOURCE", "heat")
    monkeypatch.setenv("MERGE_DEVICE_ID", DEVICE)

    cfg = Config()
    cfg.dry_run = False
    state = MergeState(cfg.state_db)
    service = MergeService(cfg, state=state)

    def pending():
        return state.conn.execute("SELECT * FROM pending_upload").fetchall()

    def ingest():
        service._ingest({"temps": 0, "heat": 0, "existing": 0})

    ingest()  # 第一遍
    rows = pending()
    assert len(rows) == 1
    assert rows[0]["external_id"].startswith("heat:")
    assert rows[0]["device_id"] == DEVICE

    ingest()  # 第二遍（游标已推进，没有新内容）
    assert len(pending()) == 1

    # 游标清零强制全量重读：stable sha（sha256(external_id)[:16]）去重，还是 1 条
    state.conn.execute("UPDATE cursor SET offset = 0")
    state.conn.commit()
    ingest()
    assert len(pending()) == 1
