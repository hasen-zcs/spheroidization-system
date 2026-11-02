"""heat 路径配 reaction 图 v2：纯时间窗（非对称）匹配。

背景：
- heat_records.jsonl 不带亮光分析图，图在 vpmin 的 reactions.jsonl 里
- reaction_count 在 heat 与 reactions 是**两套不同步计数器**（实测 rc 相等命中 0），不能当匹配键
- 实测 delta=亮光起点−炉锚点：51~476s（中位 53s），相邻炉锚点最小间隔 531s
  → 窗口 [-before, +after]（默认 -30/+300）取最近一条，消费制，不会串炉
"""

import json

from merge.assemble import build_payload_from_heat
from merge.config import Config
from merge.pair import parse_time
from merge.service import MergeService
from merge.state import MergeState

DEVICE = "test-device"
IMG_URI = "data:image/jpeg;base64,QUJD"  # base64 内容 "ABC"
IMG_B64 = "QUJD"

ANCHOR = "2026-11-02 10:00:00.000"


def _light_line(rc: int, start: str, with_image: bool = True) -> str:
    d = {
        "reaction_count": rc,
        "detection_time": start,
        "spheroidization_start_time": start,
        "spheroidization_end_time": start,
        "actual_spheroidization_time": 10.0,
        "spheroidization_abnormal": 0,
    }
    if with_image:
        d["spheroidization_image"] = IMG_URI
    return json.dumps(d, ensure_ascii=False)


def _heat_line(rc: int, anchor: str = ANCHOR, **over) -> str:
    rec = {
        "reaction_count": rc,
        "detection_time": anchor,
        "spheroidization_start_time": anchor,
        "spheroidization_end_time": anchor,
        "actual_spheroidization_time": 10.0,
        "spheroidization_abnormal": 0,
        "abnormal_type": 0,
        "spheroidization_wire_entry_start_time": anchor,
        "spheroidization_wire_entry_end_time": anchor,
        "spheroidization_wire_entry_total_duration": 10.0,
        "spheroidization_weight": 1800.0,
        "plc_button_time": anchor,
        "plc_anchor": "button",
    }
    rec.update(over)
    return json.dumps(rec, ensure_ascii=False)


def _service(tmp_path, monkeypatch, vpmin_lines=(), heat_lines=()):
    vpmin = tmp_path / "reactions.jsonl"
    heat = tmp_path / "heat_records.jsonl"
    vpmin.write_text("\n".join(vpmin_lines) + ("\n" if vpmin_lines else ""), encoding="utf-8")
    heat.write_text("\n".join(heat_lines) + ("\n" if heat_lines else ""), encoding="utf-8")

    monkeypatch.setenv("MERGE_HEAT_FILE", str(heat))
    monkeypatch.setenv("MERGE_VPMIN_FILE", str(vpmin))
    monkeypatch.setenv("MERGE_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("MERGE_DRYRUN_OUT", str(tmp_path / "dryrun.jsonl"))
    monkeypatch.setenv("MERGE_TEMP_ALL", str(tmp_path / "no_temp.jsonl"))
    monkeypatch.setenv("MERGE_TEMP_DIR", str(tmp_path / "no_temp_dir"))
    monkeypatch.setenv("MERGE_SOURCE", "heat")
    monkeypatch.setenv("MERGE_DEVICE_ID", DEVICE)

    cfg = Config()
    state = MergeState(cfg.state_db)
    return cfg, state, MergeService(cfg, state=state)


def _pending_bodies(state):
    return [json.loads(r["body"]) for r in state.conn.execute("SELECT body FROM pending_upload").fetchall()]


def _add_light(state, fp, start, rc=1, with_image=True):
    payload = {"reaction_count": rc}
    if with_image:
        payload["spheroidization_image"] = IMG_URI
    return state.add_light(fp, json.dumps(payload), start, start, 10.0, rc)


# ---------------- state 层：窗口语义 ----------------

def test_find_light_picks_nearest_in_window(tmp_path, monkeypatch):
    """窗口内多条 → 取时间最近；窗口默认 -30/+300。"""
    cfg, state, _ = _service(tmp_path, monkeypatch)
    with state:
        _add_light(state, "f1", "2026-11-02 09:59:00.000")  # -60s，窗外（before=30）
        _add_light(state, "f2", "2026-11-02 10:00:40.000")  # +40s
        _add_light(state, "f3", "2026-11-02 10:00:53.000")  # +53s（现场典型）
    found = state.find_light_for_heat(
        parse_time(ANCHOR), cfg.image_match_before, cfg.image_match_after
    )
    assert found is not None
    assert found[1] == "f2"  # +40s 比 +53s 更近
    payload, fp = found
    assert payload["spheroidization_image"] == IMG_URI


def test_before_boundary(tmp_path, monkeypatch):
    """before 侧：-31s 不配，-29s 配。"""
    cfg, state, _ = _service(tmp_path, monkeypatch)
    anchor = parse_time(ANCHOR)
    with state:
        _add_light(state, "far", "2026-11-02 09:59:29.000")  # -31s
    assert state.find_light_for_heat(anchor, 30.0, 300.0) is None
    with state:
        state.delete_light("far")
        _add_light(state, "near", "2026-11-02 09:59:31.000")  # -29s
    assert state.find_light_for_heat(anchor, 30.0, 300.0)[1] == "near"


def test_after_boundary(tmp_path, monkeypatch):
    """after 侧：+301s 不配，+299s 配。"""
    cfg, state, _ = _service(tmp_path, monkeypatch)
    anchor = parse_time(ANCHOR)
    with state:
        _add_light(state, "far", "2026-11-02 10:05:01.000")  # +301s
    assert state.find_light_for_heat(anchor, 30.0, 300.0) is None
    with state:
        state.delete_light("far")
        _add_light(state, "near", "2026-11-02 10:04:59.000")  # +299s
    assert state.find_light_for_heat(anchor, 30.0, 300.0)[1] == "near"


def test_consume_on_match_keeps_unmatched(tmp_path, monkeypatch):
    """消费制：配上的删掉，没配上的保留。"""
    cfg, state, service = _service(tmp_path, monkeypatch)
    with state:
        _add_light(state, "hit", "2026-11-02 10:00:53.000")
        _add_light(state, "miss", "2026-11-02 12:00:00.000")
    assert state.find_light_for_heat(parse_time(ANCHOR), 30.0, 300.0)[1] == "hit"
    state.delete_light("hit")
    rows = [r[0] for r in state.conn.execute("SELECT fp FROM light_event")]
    assert rows == ["miss"]


# ---------------- assemble 层 ----------------

def test_build_payload_image_param_priority():
    rec = json.loads(_heat_line(1))
    rec["spheroidization_image"] = "data:image/jpeg;base64,OWN"
    p = build_payload_from_heat(rec, None, DEVICE, image=IMG_B64)
    assert p["spheroidization_image"] == "OWN"  # record 自带图优先
    del rec["spheroidization_image"]
    assert build_payload_from_heat(rec, None, DEVICE, image=IMG_B64)["spheroidization_image"] == IMG_B64
    assert "spheroidization_image" not in build_payload_from_heat(rec, None, DEVICE)
    # data URI 前缀会被剥掉
    assert build_payload_from_heat(rec, None, DEVICE, image=IMG_URI)["spheroidization_image"] == IMG_B64


# ---------------- service 层：真实 _ingest 全流程 ----------------

def test_ingest_heat_attaches_image_rc_mismatch(tmp_path, monkeypatch):
    """v2 核心：rc 完全不同（heat=1 / reaction=400）也能按时间窗配上图。"""
    cfg, state, service = _service(
        tmp_path, monkeypatch,
        vpmin_lines=[_light_line(400, "2026-11-02 10:00:53.000")],  # +53s，现场典型 delta
        heat_lines=[_heat_line(1)],
    )
    service._ingest({"lights": 0, "temps": 0, "heat": 0, "existing": 0})
    bodies = _pending_bodies(state)
    assert len(bodies) == 1
    assert bodies[0]["spheroidization_image"] == IMG_B64  # 已剥 data: 前缀
    assert state.conn.execute("SELECT count(*) FROM light_event").fetchone()[0] == 0  # 消费掉


def test_ingest_heat_no_match_no_image(tmp_path, monkeypatch):
    """窗户外的亮光不配，炉子无图；亮光行保留等 TTL。"""
    cfg, state, service = _service(
        tmp_path, monkeypatch,
        vpmin_lines=[_light_line(400, "2026-11-02 12:00:00.000")],  # 距锚点 2h
        heat_lines=[_heat_line(1)],
    )
    service._ingest({"lights": 0, "temps": 0, "heat": 0, "existing": 0})
    bodies = _pending_bodies(state)
    assert len(bodies) == 1
    assert "spheroidization_image" not in bodies[0]
    assert state.conn.execute("SELECT count(*) FROM light_event").fetchone()[0] == 1


def test_ingest_heat_reaction_without_image_deletes_row(tmp_path, monkeypatch):
    """配上了但 reaction 无图 → 无图字段，行照样删（防反复匹配）。"""
    cfg, state, service = _service(
        tmp_path, monkeypatch,
        vpmin_lines=[_light_line(400, "2026-11-02 10:00:53.000", with_image=False)],
        heat_lines=[_heat_line(1)],
    )
    service._ingest({"lights": 0, "temps": 0, "heat": 0, "existing": 0})
    bodies = _pending_bodies(state)
    assert "spheroidization_image" not in bodies[0]
    assert state.conn.execute("SELECT count(*) FROM light_event").fetchone()[0] == 0


def test_ingest_idempotent_reread(tmp_path, monkeypatch):
    """游标清零重读 → pending 仍 1 条，图不重复不丢。"""
    cfg, state, service = _service(
        tmp_path, monkeypatch,
        vpmin_lines=[_light_line(400, "2026-11-02 10:00:53.000")],
        heat_lines=[_heat_line(1)],
    )
    service._ingest({"lights": 0, "temps": 0, "heat": 0, "existing": 0})
    state.conn.execute("UPDATE cursor SET offset = 0")
    state.conn.commit()
    service._ingest({"lights": 0, "temps": 0, "heat": 0, "existing": 0})
    bodies = _pending_bodies(state)
    assert len(bodies) == 1
    assert bodies[0]["spheroidization_image"] == IMG_B64
