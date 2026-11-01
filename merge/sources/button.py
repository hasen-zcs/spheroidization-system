"""按钮时刻（DB200.128.0 的上升沿，2 秒去抖）。

文件是追加写的 JSONL，一行一个 `{"button_confirm_time": "YYYY-MM-DD HH:MM:SS"}`。
**只有秒**，没有毫秒——按钮只用来定锚点（画图/记录的起点），
秒级精度够用；真正的时间口径还是亮光起止。
"""

import json
from pathlib import Path

from .base import fingerprint, tail_lines


def read_new(path: Path, cursor):
    raw, inode, offset = tail_lines(path, cursor)
    events = []
    for obj in raw:
        if "__bad_line__" in obj:
            continue
        pressed = obj.get("button_confirm_time") or obj.get("pressed_at")
        if not pressed:
            continue
        events.append(
            {
                "kind": "button",
                "fp": fingerprint({"at": pressed}),
                "pressed_at": str(pressed),
            }
        )
    return events, inode, offset


def encode(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
