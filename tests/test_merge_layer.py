"""合并层（第一刀第二步）的单元测试。

重点测三类东西，都是这套代码最容易出错、错了还看不出来的地方：

1. **不二次补偿**：PLC 采集侧已经减了 24 秒，合并层再减就全错
2. **滚动文件**：plc.jsonl 是原地重写的，按 offset 追尾必丢（10-10 事故）
3. **崩溃恢复**：进程被杀时，已组包没上传的必须还在
"""

import json
from datetime import datetime, timedelta

import pytest

from merge.assemble import (
    AssembleError,
    abnormal_flag,
    build_payload,
    hms_to_seconds,
    plc_skew,
    segments_from_record,
)
from merge.config import Config
from merge.pair import pair_events, parse_time
from merge.service import MergeService
from merge.sources.base import tail_lines
from merge.state import MergeState
from merge.upload import TransportError


# ==========================================================
# 夹具
# ==========================================================

@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.vpmin_file = tmp_path / "reactions.jsonl"
    c.plc_all_file = tmp_path / "all_plc.jsonl"
    c.plc_rolling_file = tmp_path / "plc.jsonl"
    c.temp_all_file = tmp_path / "all_temperature.jsonl"
    c.temp_rolling_dir = tmp_path / "temper" / "temperature_guns"
    c.button_file = tmp_path / "button.jsonl"
    c.state_db = tmp_path / "merge_state.db"
    c.dry_run_out = tmp_path / "dryrun.jsonl"
    c.poll_interval = 0
    return c


VPMIN_LINE = {
    "reaction_count": 2042,
    "detection_time": "2026-11-01 09:12:31.400",
    "spheroidization_start_time": "2026-11-01 09:12:31.400",
    "spheroidization_end_time": "2026-11-01 09:14:06.855",
    "actual_spheroidization_time": "00:01:35.46",
    "spheroidization_abnormal": "",
    "spheroidization_image": "data:image/jpeg;base64,AAAA",
    "abnormal_type": 5,
    "abnormal_reason": "球化过程中间亮光停顿：第 2 段前停顿 15.2s",
    "spheroidization_segments": [
        {"seq": 1, "start": "2026-11-01 09:12:31.400",
         "end": "2026-11-01 09:13:11.400",
         "duration_sec": 40.0, "gap_before_sec": None},
        {"seq": 2, "start": "2026-11-01 09:13:26.600",
         "end": "2026-11-01 09:14:06.855",
         "duration_sec": 40.255, "gap_before_sec": 15.2},
    ],
}

PLC_LINE = {
    "spheroidization_wire_entry_start_time": "2026-11-01 09:12:05.000",
    "spheroidization_wire_entry_end_time": "2026-11-01 09:17:05.000",
    "spheroidization_wire_entry_total_duration": 300.0,
    "spheroidization_weight": 1608.5,
}


def write_lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


class FakeTransport:
    """可编排的假后端。每调用一次消费一个响应；异常用 Exception 实例表示。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, body):
        self.calls.append(json.loads(body))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def svc(cfg, transport=None, log=None):
    from merge.upload import Uploader

    uploader = Uploader(cfg, transport=transport) if transport else None
    return MergeService(cfg, state=MergeState(cfg.state_db), uploader=uploader,
                        log=log.append if log is not None else (lambda m: None))


# ==========================================================
# 一、换算与组包
# ==========================================================

def test_分段墙钟转相对秒():
    segs = segments_from_record(VPMIN_LINE, VPMIN_LINE["spheroidization_start_time"])
    assert [s["seg_index"] for s in segs] == [1, 2]
    assert segs[0]["start_offset"] == 0.0
    assert segs[0]["end_offset"] == 40.0
    # 55.2 = 09:13:26.600 - 09:12:31.400
    assert segs[1]["start_offset"] == 55.2
    assert segs[1]["gap_before"] == 15.2
    assert segs[1]["duration"] == 40.255


def test_单段没有segments键时为空():
    line = dict(VPMIN_LINE)
    line.pop("spheroidization_segments")
    assert segments_from_record(line, line["spheroidization_start_time"]) == []


def test_hms解析():
    assert hms_to_seconds("00:01:35.46") == 95.46
    assert hms_to_seconds("01:00:00") == 3600.0
    assert hms_to_seconds(95.5) == 95.5
    assert hms_to_seconds(None) is None


def test_异常三态():
    assert abnormal_flag(0) == 0
    assert abnormal_flag(6) is None      # 未判定不能冒充正常
    assert abnormal_flag(None) is None
    assert abnormal_flag(3) == 1


def test_组包不做二次补偿():
    pair = pair_events(
        [{"fp": "l1", "start": VPMIN_LINE["spheroidization_start_time"],
          "end": VPMIN_LINE["spheroidization_end_time"],
          "duration": 95.455, "record": VPMIN_LINE}],
        [{"fp": "p1", "start": PLC_LINE["spheroidization_wire_entry_start_time"],
          "end": PLC_LINE["spheroidization_wire_entry_end_time"], "record": PLC_LINE}],
        [],
        Config(),
    )[0]
    payload = build_payload(pair, None, "casting-1")

    # 🔴 原样搬：文件里 09:17:05，payload 里也必须 09:17:05
    assert payload["spheroidization_wire_entry_end_time"] == "2026-11-01 09:17:05.000"
    assert payload["spheroidization_wire_entry_total_duration"] == 300.0
    assert plc_skew(payload) == 0.0
    assert payload["actual_spheroidization_time"] == 95.455
    assert payload["spheroidization_abnormal"] == 1
    assert payload["segments"][1]["start_offset"] == 55.2
    # 图片 data URI 前缀必须去掉，后端只收裸 base64
    assert payload["spheroidization_image"] == "AAAA"


def test_组包缺重量直接报错():
    bad_plc = dict(PLC_LINE)
    bad_plc.pop("spheroidization_weight")
    pair = pair_events(
        [{"fp": "l1", "start": VPMIN_LINE["spheroidization_start_time"],
          "end": VPMIN_LINE["spheroidization_end_time"],
          "duration": 95.455, "record": VPMIN_LINE}],
        [{"fp": "p1", "start": PLC_LINE["spheroidization_wire_entry_start_time"],
          "end": PLC_LINE["spheroidization_wire_entry_end_time"], "record": bad_plc}],
        [],
        Config(),
    )[0]
    with pytest.raises(AssembleError, match="重量"):
        build_payload(pair, None, "casting-1")


# ==========================================================
# 二、文件读取
# ==========================================================

def test_半行留到下一轮(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_text('{"a":1}\n{"b":2}\n{"c":', encoding="utf-8")
    objs, inode, offset = tail_lines(path, None)
    assert objs == [{"a": 1}, {"b": 2}]

    with open(path, "a", encoding="utf-8") as fh:
        fh.write("3}\n")
    objs2, _, _ = tail_lines(path, (inode, offset))
    assert objs2 == [{"c": 3}]


def test_文件变短从头读(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    objs, inode, offset = tail_lines(path, None)
    assert len(objs) == 2

    path.write_text('{"a":9}\n', encoding="utf-8")     # 原地重写、变短
    objs2, _, _ = tail_lines(path, (inode, offset))
    assert objs2 == [{"a": 9}]


def test_PLC滚动文件每轮全量读但不重复入队(cfg):
    # 没有 all_plc.jsonl，只有滚动 plc.jsonl
    write_lines(cfg.plc_rolling_file, [PLC_LINE])
    service = svc(cfg)
    service.run_once()
    service.run_once()
    service.run_once()

    rows = service.state.conn.execute("SELECT COUNT(*) FROM plc_event").fetchone()[0]
    assert rows == 1


def test_vpmin游标续读(cfg):
    write_lines(cfg.vpmin_file, [VPMIN_LINE])
    service = svc(cfg)
    service.run_once()
    first = service.state.conn.execute("SELECT COUNT(*) FROM light_event").fetchone()[0]

    second_line = dict(VPMIN_LINE, reaction_count=2043,
                       spheroidization_start_time="2026-11-01 10:00:00.000",
                       spheroidization_end_time="2026-11-01 10:01:30.000")
    write_lines(cfg.vpmin_file, [second_line])
    service.run_once()

    rows = service.state.conn.execute("SELECT COUNT(*) FROM light_event").fetchone()[0]
    assert first == 1 and rows == 2


# ==========================================================
# 三、配对
# ==========================================================

def test_按钮定锚点(cfg):
    lights = [{"fp": "l1", "start": "2026-11-01 09:12:31.400",
               "end": "2026-11-01 09:14:06.855", "duration": 95.455,
               "record": VPMIN_LINE}]
    plcs = [{"fp": "p1", "start": "2026-11-01 09:12:05.000",
             "end": "2026-11-01 09:17:05.000", "record": PLC_LINE}]
    buttons = [{"pressed_at": "2026-11-01 09:11:52"}]

    pair = pair_events(lights, plcs, buttons, cfg)[0]
    assert pair.anchor_kind == "button"
    assert pair.anchor == "2026-11-01 09:11:52"


def test_没按钮回退亮光起点(cfg):
    lights = [{"fp": "l1", "start": "2026-11-01 09:12:31.400",
               "end": "2026-11-01 09:14:06.855", "duration": 95.455,
               "record": VPMIN_LINE}]
    plcs = [{"fp": "p1", "start": "2026-11-01 09:12:05.000",
             "end": "2026-11-01 09:17:05.000", "record": PLC_LINE}]

    pair = pair_events(lights, plcs, [], cfg)[0]
    assert pair.anchor_kind == "light"
    assert pair.anchor == "2026-11-01 09:12:31.400"


def test_同一条进线多条亮光取最长(cfg):
    plcs = [{"fp": "p1", "start": "2026-11-01 09:12:05.000",
             "end": "2026-11-01 09:17:05.000", "record": PLC_LINE}]
    lights = [
        {"fp": "short", "start": "2026-11-01 09:12:40.000",
         "end": "2026-11-01 09:12:50.000", "duration": 10.0, "record": {}},
        {"fp": "long", "start": "2026-11-01 09:12:31.400",
         "end": "2026-11-01 09:14:06.855", "duration": 95.455, "record": {}},
    ]
    pair = pair_events(lights, plcs, [], cfg)[0]
    assert pair.light["fp"] == "long"


def test_亮光不在进线窗口内不配对(cfg):
    plcs = [{"fp": "p1", "start": "2026-11-01 09:12:05.000",
             "end": "2026-11-01 09:17:05.000", "record": PLC_LINE}]
    lights = [{"fp": "far", "start": "2026-11-01 20:00:00.000",
               "end": "2026-11-01 20:01:00.000", "duration": 60.0, "record": {}}]
    assert pair_events(lights, plcs, [], cfg) == []


# ==========================================================
# 四、温度
# ==========================================================

def _run_full(cfg, transport, temp_lines=None):
    write_lines(cfg.button_file, [{"button_confirm_time": "2026-11-01 09:11:52"}])
    write_lines(cfg.plc_rolling_file, [PLC_LINE])
    write_lines(cfg.vpmin_file, [VPMIN_LINE])
    if temp_lines is not None:
        write_lines(cfg.temp_all_file, temp_lines)
    service = svc(cfg, transport=transport)
    return service, service.run_once()


def test_温度必须早于锚点且在窗口内(cfg):
    ok = {"gun_no": 4, "temperature": 1523.5, "measured_at": "2026-11-01 09:09:00"}
    too_old = {"gun_no": 4, "temperature": 1400.0,
               "measured_at": "2026-11-01 08:30:00"}
    wrong_gun = {"gun_no": 1, "temperature": 1300.0,
                 "measured_at": "2026-11-01 09:10:00"}
    late = {"gun_no": 4, "temperature": 1500.0, "measured_at": "2026-11-01 09:20:00"}

    transport = FakeTransport([(200, {"code": 200, "data": {"id": 7}})])
    service, _ = _run_full(cfg, transport, [too_old, wrong_gun, ok, late])
    sent = transport.calls[0]
    assert sent["temperature"] == 1523.5
    assert sent["gun_no"] == 4
    # 温度时间要去掉毫秒（后端温度表只到秒）
    assert sent["temperature_time"] == "2026-11-01 09:09:00"


def test_一条温度只能挂一炉(cfg):
    temp = {"gun_no": 4, "temperature": 1523.5, "measured_at": "2026-11-01 09:09:00"}
    second = dict(VPMIN_LINE, reaction_count=2043,
                  spheroidization_start_time="2026-11-01 09:20:31.400",
                  spheroidization_end_time="2026-11-01 09:22:06.855")
    second_plc = {
        "spheroidization_wire_entry_start_time": "2026-11-01 09:20:05.000",
        "spheroidization_wire_entry_end_time": "2026-11-01 09:25:05.000",
        "spheroidization_wire_entry_total_duration": 300.0,
        "spheroidization_weight": 1609.0,
    }
    write_lines(cfg.button_file, [{"button_confirm_time": "2026-11-01 09:11:52"}])
    write_lines(cfg.plc_rolling_file, [PLC_LINE, second_plc])
    write_lines(cfg.vpmin_file, [VPMIN_LINE, second])
    write_lines(cfg.temp_all_file, [temp])

    transport = FakeTransport([(200, {"code": 200, "data": {"id": 1}})] * 2)
    service = svc(cfg, transport=transport)
    service.run_once()

    assert len(transport.calls) == 2
    assert "temperature" in transport.calls[0]
    assert "temperature" not in transport.calls[1]     # 同一条温度不能复用


# ==========================================================
# 五、上传与恢复
# ==========================================================

def test_上传成功后落delivered(cfg):
    transport = FakeTransport([(200, {"code": 200, "data": {"id": 11, "existing": False}})])
    service, stats = _run_full(cfg, transport)
    assert stats["uploaded"] == 1
    assert service.state.pending_count() == 0
    assert service.state.is_delivered("casting-1", "2042")


def test_幂等命中计入existing(cfg):
    transport = FakeTransport([(200, {"code": 200, "data": {"id": 11, "existing": True}})])
    _, stats = _run_full(cfg, transport)
    assert stats["existing"] == 1


def test_网络失败留队_重启后补传(cfg):
    service, stats = _run_full(cfg, FakeTransport([TransportError("断网")]))
    assert stats["failed"] == 1
    assert service.state.pending_count() == 1

    # 进程"重启"：新建 state 和 service，指同一个状态库
    service2 = svc(cfg, transport=FakeTransport([(200, {"code": 200, "data": {"id": 11}})]))
    # 让重试时间到点
    service2.state.conn.execute("UPDATE pending_upload SET next_at = '2000-01-01 00:00:00'")
    service2.state.commit()
    service2.run_once()
    assert service2.state.pending_count() == 0
    assert service2.state.is_delivered("casting-1", "2042")


def test_4xx进死信不重试(cfg):
    transport = FakeTransport([(200, {"code": 422, "message": "分段不合法"})])
    service, stats = _run_full(cfg, transport)
    assert stats["dead"] == 1
    assert service.state.pending_count() == 0
    rows = service.state.dead_letter_rows()
    assert rows and "422" in rows[0]["error"]


def test_409进死信(cfg):
    transport = FakeTransport([(200, {"code": 409, "message": "幂等键冲突"})])
    service, stats = _run_full(cfg, transport)
    assert stats["dead"] == 1
    assert service.state.pending_count() == 0


def test_dry_run只写预览不调接口(cfg):
    cfg.dry_run = True
    service, stats = _run_full(cfg, FakeTransport([]))
    assert stats["pairs"] == 1
    assert service.state.pending_count() == 0
    lines = cfg.dry_run_out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    preview = json.loads(lines[0])
    assert preview["external_id"] == "2042"
    assert preview["_anchor"] == "button"
    assert preview["_image_bytes"] == 4


def test_连续无进线触发告警(cfg):
    logs = []
    for count in (1, 2, 3):
        line = dict(VPMIN_LINE, reaction_count=3000 + count,
                    spheroidization_start_time=f"2026-11-01 10:0{count}:00.000",
                    spheroidization_end_time=f"2026-11-01 10:0{count}:30.000")
        write_lines(cfg.vpmin_file, [line])

    service = svc(cfg, log=logs)
    stats = service.run_once()
    assert stats["no_plc_streak"] == 3
    assert any("PLC 采集中断" in message for message in logs)
