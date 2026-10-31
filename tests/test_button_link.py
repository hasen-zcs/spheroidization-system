"""按钮接入的单测（2026-11-01）。

被测对象是 `deploy/plc-button/` 下的两个生产补丁：
- Get_PLCInfo.v1.1.py：PLC 采集加按钮位 + 去抖 + stdout 事件
- bridge.v1.1.py：把按钮事件从 plc 通道旁路出去（不占配对序号）

这两边任何一边漏了，按钮链路就断：只写文件下游收不到；只发事件不拦，
plc.jsonl 会被按钮行污染，合并器按序号配对整体错位。
"""

import importlib.util
import json
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy" / "plc-button"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def collector(monkeypatch, tmp_path):
    """注入假 snap7，按临时目录加载采集脚本。"""
    fake = types.ModuleType("snap7")
    fake.client = types.SimpleNamespace(Client=object)
    monkeypatch.setitem(sys.modules, "snap7", fake)
    monkeypatch.setenv("BUTTON_ROLLING_FILE", str(tmp_path / "button.json"))
    monkeypatch.setenv("BUTTON_ALL_FILE", str(tmp_path / "all_button.jsonl"))
    return _load(DEPLOY / "Get_PLCInfo.v1.1.py", "plc_collector_v11")


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    """bridge 的所有路径都挂在 BRIDGE_BASE_DIR 下，测试用临时根。"""
    monkeypatch.setenv("BRIDGE_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("BUTTON_WRITE_IN_BRIDGE", "0")
    module = _load(DEPLOY / "bridge.v1.1.py", "bridge_v11")
    return module


def test_首次采样不产生事件(collector):
    edge = collector.ButtonEdge(debounce_s=2.0)
    assert edge.feed(0, datetime(2026, 11, 1, 0, 0, 0)) is None
    # 一直是 0，不该有事件
    assert edge.feed(0, datetime(2026, 11, 1, 0, 0, 1)) is None


def test_上升沿产生一次事件(collector):
    edge = collector.ButtonEdge(debounce_s=2.0)
    t0 = datetime(2026, 11, 1, 0, 0, 0)
    edge.feed(0, t0)
    event = edge.feed(1, t0 + timedelta(seconds=1))
    assert event == t0 + timedelta(seconds=1)
    assert edge.suppressed == 0


def test_连按在去抖窗口内被吞掉(collector):
    edge = collector.ButtonEdge(debounce_s=2.0)
    t0 = datetime(2026, 11, 1, 0, 0, 0)
    edge.feed(0, t0)
    assert edge.feed(1, t0 + timedelta(seconds=1)) is not None
    edge.feed(0, t0 + timedelta(seconds=1.5))
    # 1.8s 后再次按下：应该被去抖吞掉
    assert edge.feed(1, t0 + timedelta(seconds=1.8)) is None
    assert edge.suppressed == 1
    # 超过窗口后应重新产生
    edge.feed(0, t0 + timedelta(seconds=4))
    assert edge.feed(1, t0 + timedelta(seconds=4.5)) is not None


def test_按钮事件JSON带event字段(collector):
    payload = json.loads(
        collector.button_event_json(datetime(2026, 11, 1, 0, 1, 2))
    )
    assert payload == {
        "event": "button_confirm",
        "button_confirm_time": "2026-11-01 00:01:02",
        "source": "button",
    }


def test_写按钮文件_滚动只留N条(collector, tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "BUTTON_KEEP", 3)
    for minute in range(5):
        collector.append_all_button_confirm(datetime(2026, 11, 1, 0, minute, 0))
        collector.write_button_confirm_rolling(datetime(2026, 11, 1, 0, minute, 0))

    all_lines = (tmp_path / "all_button.jsonl").read_text(encoding="utf-8").splitlines()
    rolling = json.loads((tmp_path / "button.json").read_text(encoding="utf-8"))
    assert len(all_lines) == 5          # 全量不丢
    assert len(rolling) == 3            # 滚动只留 3 条
    assert rolling[-1]["button_confirm_time"] == "2026-11-01 00:04:00"


def test_bridge把按钮事件旁路_不占序号(bridge, tmp_path):
    bridge.emit("plc", {"event": "button_confirm", "button_confirm_time": "2026-11-01 00:00:05"})

    plc_file = tmp_path / "Get_Allinfomation" / "plc.jsonl"
    all_plc = tmp_path / "Get_Allinfomation" / "all_plc.jsonl"
    assert bridge.plc_count == 0
    assert not plc_file.exists() or plc_file.read_text(encoding="utf-8") == ""
    assert not all_plc.exists() or all_plc.read_text(encoding="utf-8") == ""


def test_bridge普通PLC数据仍正常计数(bridge, tmp_path):
    bridge.emit("plc", {"spheroidization_wire_entry_start_time": "2026-11-01 00:00:00"})
    bridge.emit("plc", {"spheroidization_wire_entry_start_time": "2026-11-01 00:02:00"})

    line = (tmp_path / "Get_Allinfomation" / "plc.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    rec = json.loads(line)
    assert bridge.plc_count == 2
    assert rec["reaction_count"] == 2
    assert rec["source"] == "plc"


def test_按钮与进线混流时序号不乱(bridge, tmp_path):
    bridge.emit("plc", {"spheroidization_wire_entry_start_time": "2026-11-01 00:00:00"})
    bridge.emit("plc", {"event": "button_confirm", "button_confirm_time": "2026-11-01 00:00:05"})
    bridge.emit("plc", {"spheroidization_wire_entry_start_time": "2026-11-01 00:02:00"})

    lines = (tmp_path / "Get_Allinfomation" / "plc.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["reaction_count"] for x in lines] == [1, 2]
    assert all("button_confirm_time" not in json.loads(x) for x in lines)
