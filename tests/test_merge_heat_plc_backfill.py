"""T-004e：heat 链路进线结束/时长 null → 从 all_plc.jsonl 按进线开始时间回捞。

样本取自影子干跑（T-G4）实例：heat:11 start=2026-10-30 16:59:24.950（heat 带毫秒），
all_plc.jsonl rc=1453 行 start=2026-10-30 16:59:24（不带毫秒）end=17:10:51 dur=686.63。
"""

import json
from pathlib import Path

from merge.assemble import backfill_plc_from_all_plc, match_plc_row
from merge.config import Config
from merge.service import MergeService
from merge.state import MergeState

DEVICE = "test-device"

PLC_START = "2026-10-30 16:59:24.950"      # heat 侧：带毫秒
PLC_ALL_START = "2026-10-30 16:59:24"      # all_plc 侧：不带毫秒
PLC_END = "2026-10-30 17:10:51"
PLC_DURATION = 686.63
PLC_WEIGHT = 1528.0


def _heat_record(**overrides) -> dict:
    """一炉 heat 记录：进线结束/时长为 null（T-G4 影子干跑的问题形态）。"""
    rec = {
        "reaction_count": 11,
        "detection_time": "2026-10-30 16:59:24.950",
        "spheroidization_start_time": "2026-10-30 16:59:55.000",
        "spheroidization_end_time": "2026-10-30 17:11:20.000",
        "actual_spheroidization_time": None,
        "spheroidization_abnormal": 0,
        "abnormal_type": 0,
        "abnormal_reason": None,
        "spheroidization_wire_entry_start_time": PLC_START,
        "spheroidization_wire_entry_end_time": None,
        "spheroidization_wire_entry_total_duration": None,
        "spheroidization_weight": 1528.0,
        "plc_button_time": "2026-10-30 16:58:44.950",
        "plc_anchor": "button",
    }
    rec.update(overrides)
    return rec


def _plc_all_row(**overrides) -> dict:
    row = {
        "reaction_count": 1453,
        "spheroidization_wire_entry_start_time": PLC_ALL_START,
        "spheroidization_wire_entry_end_time": PLC_END,
        "spheroidization_wire_entry_total_duration": PLC_DURATION,
        "spheroidization_weight": PLC_WEIGHT,
    }
    row.update(overrides)
    return row


def _setup(tmp_path: Path, monkeypatch, heat_records: list[dict],
           plc_all_rows: list[dict] | None = None) -> MergeService:
    """heat 源 + all_plc 回捞环境。plc_all_rows=None → all_plc 文件不存在。"""
    heat_file = tmp_path / "heat_records.jsonl"
    heat_file.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in heat_records) + "\n",
        encoding="utf-8",
    )
    env = {
        "MERGE_HEAT_FILE": str(heat_file),
        "MERGE_STATE_DB": str(tmp_path / "state.db"),
        "MERGE_TEMP_ALL": str(tmp_path / "no_temp.jsonl"),
        "MERGE_TEMP_DIR": str(tmp_path / "no_temp_dir"),
        "MERGE_SOURCE": "heat",
        "MERGE_DEVICE_ID": DEVICE,
    }
    if plc_all_rows is None:
        env["MERGE_PLC_ALL"] = str(tmp_path / "no_such_all_plc.jsonl")
    else:
        plc_all = tmp_path / "all_plc.jsonl"
        plc_all.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in plc_all_rows) + "\n",
            encoding="utf-8",
        )
        env["MERGE_PLC_ALL"] = str(plc_all)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    cfg = Config()
    state = MergeState(cfg.state_db)
    return MergeService(cfg, state=state, log=lambda message: None)


def _pending_bodies(state: MergeState) -> list[dict]:
    rows = state.conn.execute("SELECT body FROM pending_upload").fetchall()
    return [json.loads(row["body"]) for row in rows]


class _FakeUploader:
    """按脚本返回固定响应的假 uploader（不碰网络、不碰 8000/8021 等端口）。"""

    def __init__(self, responses):
        self.responses = list(responses)

    def send(self, body: str):
        return self.responses.pop(0)

    def backoff(self, attempts: int) -> float:
        return 1.0


def test_backfill_null_end_duration_from_all_plc(tmp_path, monkeypatch):
    """① end/duration null + all_plc 有对应行（heat 带毫秒、all_plc 不带）→ 回填成功且值与 all_plc 一致。"""
    service = _setup(
        tmp_path, monkeypatch,
        heat_records=[_heat_record()],
        plc_all_rows=[_plc_all_row()],
    )
    state = service.state

    service._ingest({"temps": 0, "heat": 0, "existing": 0})

    bodies = _pending_bodies(state)
    assert len(bodies) == 1
    body = bodies[0]
    assert body["spheroidization_wire_entry_start_time"] == PLC_START  # heat 原值，未被动
    assert body["spheroidization_wire_entry_end_time"] == PLC_END
    assert body["spheroidization_wire_entry_total_duration"] == PLC_DURATION
    # 非 null 字段保持 heat 原值（这里 heat 的 weight 与 all_plc 恰好同值，用②的断言覆盖"不覆盖"）


def test_backfill_does_not_override_non_null(tmp_path, monkeypatch):
    """② heat 字段非空 → 不被 all_plc 覆盖（heat 为准），即使 all_plc 有另一套值。"""
    heat_rec = _heat_record(
        spheroidization_wire_entry_end_time="2026-10-30 17:00:00.000",
        spheroidization_wire_entry_total_duration=123.456,
    )
    service = _setup(
        tmp_path, monkeypatch,
        heat_records=[heat_rec],
        plc_all_rows=[_plc_all_row()],  # 同一进线开始时间，但结束/时长完全不同
    )
    state = service.state

    service._ingest({"temps": 0, "heat": 0, "existing": 0})

    (body,) = _pending_bodies(state)
    assert body["spheroidization_wire_entry_end_time"] == "2026-10-30 17:00:00.000"
    assert body["spheroidization_wire_entry_total_duration"] == 123.456
    # 半 null 场景：只有 duration 为 null → 只回填 duration，end 保持 heat 值
    half = _heat_record(
        spheroidization_wire_entry_end_time="2026-10-30 17:05:00.000",
        spheroidization_wire_entry_total_duration=None,
    )
    row = backfill_plc_from_all_plc(half, service.cfg.plc_all_file)
    assert row is not None
    assert half["spheroidization_wire_entry_end_time"] == "2026-10-30 17:05:00.000"
    assert half["spheroidization_wire_entry_total_duration"] == PLC_DURATION


def test_no_matching_row_dead_letter_note(tmp_path, monkeypatch):
    """③ all_plc 无对应行 → 维持现状（422 死信），且死信 error 含「无法回捞」。"""
    service = _setup(
        tmp_path, monkeypatch,
        heat_records=[_heat_record()],
        plc_all_rows=[_plc_all_row(spheroidization_wire_entry_start_time="2026-10-30 15:00:00")],
    )
    service.uploader = _FakeUploader(
        [(200, {"code": 422, "message": "进线结束时间缺失"})]
    )
    state = service.state

    service._ingest({"temps": 0, "heat": 0, "existing": 0})
    # 回捞失败：body 里 end/duration 仍是 null
    (body,) = _pending_bodies(state)
    assert body["spheroidization_wire_entry_end_time"] is None
    assert body["spheroidization_wire_entry_total_duration"] is None

    stats = {"failed": 0, "dead": 0, "uploaded": 0, "existing": 0}
    service._flush_uploads(stats)

    assert stats["dead"] == 1
    rows = state.dead_letter_rows()
    assert len(rows) == 1
    assert "422" in rows[0]["error"]
    assert "无法回捞" in rows[0]["error"]


def test_missing_all_plc_file_is_silent(tmp_path, monkeypatch):
    """all_plc 文件不存在 → 静默跳过回捞：不报错、正常组包入库（值保持 null）。"""
    service = _setup(
        tmp_path, monkeypatch,
        heat_records=[_heat_record()],
        plc_all_rows=None,  # MERGE_PLC_ALL 指向不存在的文件
    )
    state = service.state

    service._ingest({"temps": 0, "heat": 0, "existing": 0})  # 不应抛异常

    (body,) = _pending_bodies(state)
    assert body["spheroidization_wire_entry_end_time"] is None
    assert body["spheroidization_wire_entry_total_duration"] is None


def test_match_window_boundary():
    """匹配规则：秒级截断后相等 / 相差 ≤2s 命中；>2s 不命中。"""
    rows = [
        _plc_all_row(spheroidization_wire_entry_start_time="2026-10-30 16:59:24"),   # 差 0.95s
        _plc_all_row(spheroidization_wire_entry_start_time="2026-10-30 16:59:27"),   # 差 2.05s → 窗口外
        _plc_all_row(spheroidization_wire_entry_start_time="2026-10-30 17:00:00"),   # 窗口外
    ]
    # 0.95s：秒级截断后不相等（24 vs 24 的 .950）但 ≤2s → 命中最近的一行
    hit = match_plc_row("2026-10-30 16:59:24.950", rows)
    assert hit is not None
    assert hit["spheroidization_wire_entry_start_time"] == "2026-10-30 16:59:24"
    # 恰好 2.000s：边界包含（≤2s）
    edge_rows = [_plc_all_row(spheroidization_wire_entry_start_time="2026-10-30 16:59:28")]
    assert match_plc_row("2026-10-30 16:59:26", edge_rows) is not None
    # 2.5s → 窗口外
    assert match_plc_row("2026-10-30 16:59:26", [
        _plc_all_row(spheroidization_wire_entry_start_time="2026-10-30 16:59:28.5")
    ]) is None
    # 无开始时间 / 空列表 → None
    assert match_plc_row(None, rows) is None
    assert match_plc_row("2026-10-30 16:59:24.950", []) is None
