"""vpmin 的 reactions.jsonl（追加写、不轮转）。

一行就是一炉：7 个老字段 + abnormal_type / abnormal_reason /
spheroidization_segments（仅多段时才有）。

**注意**：`spheroidization_segments` 这个键只在 len(segments) > 1 时出现，
正常炉/超标准炉根本没有。所以这里一律用 .get()，缺键当"没有分段"。
"""

import json
from pathlib import Path

from .base import fingerprint, tail_lines


def read_new(path: Path, cursor):
    """:return: (事件列表, inode, 新 offset)"""
    raw, inode, offset = tail_lines(path, cursor)
    events = []
    for obj in raw:
        if "__bad_line__" in obj:
            events.append({"kind": "bad", "raw": obj["__bad_line__"]})
            continue
        start = obj.get("spheroidization_start_time") or obj.get("detection_time")
        end = obj.get("spheroidization_end_time")
        duration = _duration(obj)
        events.append(
            {
                "kind": "light",
                "fp": fingerprint(
                    {
                        "count": obj.get("reaction_count"),
                        "start": start,
                        "end": end,
                        "duration": duration,
                    }
                ),
                "record": obj,
                "start": start,
                "end": end,
                "duration": duration,
                "reaction_count": obj.get("reaction_count"),
            }
        )
    return events, inode, offset


def _duration(obj: dict) -> float | None:
    """优先用亮光起止算，实在没有才解析 HH:MM:SS.ss。"""
    value = obj.get("actual_spheroidization_time")
    if isinstance(value, (int, float)):
        return round(float(value), 3)
    return None


def encode(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
