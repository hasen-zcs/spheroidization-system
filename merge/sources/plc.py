"""PLC 喂丝事件。

两种文件，优先级不同：
- `all_plc.jsonl`：追加写、全量 → 按 offset 追尾（首选，断线久了也能补齐）
- `plc.jsonl`：**只留 10 行、原地重写** → 每轮全量读 + 指纹去重（10-10 丢数据的根因）

🔴 **不在这里做时间补偿**。采集脚本 `Get_PLCInfo.v1.1.py` 已经把喂丝结束
按位延迟回推了 24 秒（TRIGGERS 表里那一列 24）。合并层再减一次，
每炉进线时长就会少 24 秒，速度、长度这些派生值全错。
这里只做一致性校验（见 service 的 plc_skew 日志）。
"""

import json
from pathlib import Path

from .base import file_exists, fingerprint, read_all_lines, tail_lines


def _event(obj: dict) -> dict | None:
    start = obj.get("spheroidization_wire_entry_start_time")
    if not start:
        return None
    end = obj.get("spheroidization_wire_entry_end_time")
    return {
        "kind": "plc",
        "fp": fingerprint({"start": start, "end": end}),
        "record": obj,
        "start": start,
        "end": end,
    }


def read_new(path_all: Path, path_rolling: Path, cursor):
    """:return: (事件列表, inode, 新 offset)"""
    if file_exists(path_all):
        raw, inode, offset = tail_lines(path_all, cursor)
        events = [e for e in (_event(o) for o in raw if "__bad_line__" not in o) if e]
        bad = [
            {"kind": "bad", "raw": o["__bad_line__"]}
            for o in raw
            if "__bad_line__" in o
        ]
        return events + bad, inode, offset

    # 全量文件缺失（现场只在滚动模式时）：每轮全量读，指纹去重
    events = [e for e in (_event(o) for o in read_all_lines(path_rolling)) if e]
    return events, 0, 0


def encode(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
