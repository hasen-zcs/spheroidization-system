"""heat_records.jsonl 数据源（追加写、不轮转），风格与 vpmin.py 一致。

一行一炉：反应次数 + 进丝起止 + PLC 锚点 + 球化判定字段。

**已知冲突**：`spheroidization_abnormal` 在 heat_records 通道里是 int（0/1），
但检测侧另一条通道可能写成字符串（"成功"/"失败"/"未判定"）。这里统一归一化：
"成功"→0（正常）、"失败"→1（异常）、"未判定"→None，int 原样保留，其它值 → None。

`abnormal_type` 同样按 int 处理；`spheroidization_segments` 单段时缺键，一律 .get()。
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
        events.append(
            {
                "kind": "heat",
                "fp": fingerprint(
                    {
                        "count": obj.get("reaction_count"),
                        "anchor": obj.get("plc_anchor"),
                        "entry_start": obj.get("spheroidization_wire_entry_start_time"),
                    }
                ),
                "record": obj,
                "reaction_count": obj.get("reaction_count"),
                "abnormal_type": _abnormal_type(obj.get("abnormal_type")),
                "spheroidization_abnormal": _abnormal(obj.get("spheroidization_abnormal")),
                "anchor": obj.get("plc_anchor"),
            }
        )
    return events, inode, offset


def _abnormal(value):
    """归一化球化判定：0/1 原样；"成功"→0（正常）、"失败"→1（异常）、"未判定"→None。

    见模块头注释——检测侧两条通道类型不一致（int vs 中文字符串），
    这是已知冲突，合并层兜底统一。
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value if value in (0, 1) else None
    if isinstance(value, str):
        return {"成功": 0, "失败": 1, "未判定": None}.get(value)
    return None


def encode(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _abnormal_type(value):
    """abnormal_type 归一化为 int；非法/缺失 → 0（正常，未知不臆断为异常）。"""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0
