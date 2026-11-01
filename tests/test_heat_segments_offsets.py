"""T-004d：heat 分段必须换算成"相对球化起点的秒"（float, ≥0）。

后端 422 的根因：heat_segments 曾把墙钟串原样塞进 start_offset/end_offset。
验收基准用 ~/spheroidization-delivery/dataset/heat_types_125.jsonl 里的真实记录：
- 类型 5（多段炉）：段数 ≥2、首段 start_offset=0.0、偏移严格递增、末段与总时长差 ≤1s
- 类型 1（无亮光）：没有相对基准，必须返回 []，不能报错
- 单段记录：1 段，gap_before 为 None
"""

import json
from pathlib import Path

import pytest

from merge.assemble import heat_segments
from merge.pair import parse_time

DATASET = Path.home() / "spheroidization-delivery" / "dataset" / "heat_types_125.jsonl"


def _records():
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


@pytest.fixture(scope="module")
def type5_records():
    return [r for r in _records() if r["abnormal_type"] == 5]


@pytest.fixture(scope="module")
def type1_records():
    return [r for r in _records() if r["abnormal_type"] == 1]


def test_dataset_has_both_types(type5_records, type1_records):
    assert len(type5_records) >= 2
    assert len(type1_records) >= 1


@pytest.mark.parametrize("idx", [0, 1], ids=["heat8", "heat19"])
def test_type5_real_record_offsets(type5_records, idx):
    rec = type5_records[idx]
    segs = heat_segments(rec)

    # 段数 ≥2
    assert len(segs) >= 2

    # 偏移必须是数字，不是墙钟串
    for seg in segs:
        assert isinstance(seg["start_offset"], float)
        assert isinstance(seg["end_offset"], float)
        assert seg["start_offset"] >= 0.0
        assert seg["end_offset"] > seg["start_offset"]

    # 首段 start_offset ≈ 0（真实数据里首段起点与 spheroidization_start_time 有 1ms 级抖动）
    assert segs[0]["start_offset"] == pytest.approx(0.0, abs=0.01)

    # 偏移严格递增
    for prev, cur in zip(segs, segs[1:]):
        assert cur["start_offset"] > prev["start_offset"]
        assert cur["end_offset"] > prev["end_offset"]

    # 末段 end_offset 与总时长差 ≤1s
    total = (
        parse_time(rec["spheroidization_end_time"])
        - parse_time(rec["spheroidization_start_time"])
    ).total_seconds()
    assert abs(segs[-1]["end_offset"] - total) <= 1.0

    # 顺序按 seq，seg_index 就是 seq
    assert [s["seg_index"] for s in segs] == [1, 2, 3]

    # 首段 gap_before 必须 None
    assert segs[0]["gap_before"] is None

    # 换算值与记录里的 duration_sec/gap_before_sec 一致（round 3 位）
    assert segs[0]["duration"] == rec["spheroidization_segments"][0]["duration_sec"]
    assert segs[1]["gap_before"] == rec["spheroidization_segments"][1]["gap_before_sec"]


def test_type1_no_light_start_returns_empty(type1_records):
    for rec in type1_records:
        assert rec["spheroidization_start_time"] is None
        assert heat_segments(rec) == []


def test_missing_light_start_even_with_segments_returns_empty():
    # 有分段但没有亮光起点（类型 1/2 的形态）→ 无相对基准 → []，不报错
    rec = {
        "spheroidization_start_time": None,
        "spheroidization_segments": [
            {"seq": 1, "start": "2026-10-30 11:45:26.785",
             "end": "2026-10-30 11:45:31.382",
             "duration_sec": 4.597, "gap_before_sec": None},
        ],
    }
    assert heat_segments(rec) == []


def test_single_segment_one_gap_none():
    rec = {
        "spheroidization_start_time": "2026-10-30 11:45:26.785",
        "spheroidization_segments": [
            {"seq": 1, "start": "2026-10-30 11:45:26.785",
             "end": "2026-10-30 11:45:54.856",
             "duration_sec": 28.071, "gap_before_sec": 2.007},
        ],
    }
    segs = heat_segments(rec)
    assert len(segs) == 1
    seg = segs[0]
    assert seg["seg_index"] == 1
    assert seg["start_offset"] == 0.0
    assert seg["end_offset"] == pytest.approx(28.071)
    assert seg["duration"] == 28.071
    assert seg["gap_before"] is None


def test_missing_duration_falls_back_to_end_minus_start():
    rec = {
        "spheroidization_start_time": "2026-10-30 11:45:26.785",
        "spheroidization_segments": [
            {"seq": 1, "start": "2026-10-30 11:45:26.785",
             "end": "2026-10-30 11:45:30.0", "duration_sec": None},
        ],
    }
    segs = heat_segments(rec)
    assert segs[0]["duration"] == pytest.approx(3.215)


def test_no_segments_key_returns_empty():
    assert heat_segments({"spheroidization_start_time": "2026-10-30 11:45:26.785"}) == []
    assert heat_segments({}) == []
