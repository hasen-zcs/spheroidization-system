"""测温数据（只认枪 4，但文件里有什么都读，过滤交给上层）。

两个文件：
- `all_temperature.jsonl`：追加写、全量 → offset 追尾（**首选**）
- `temperture_guns/temperature_gunN.jsonl`：**裁到 50 条的滚动文件** →
  只能全量读 + 指纹去重。设计里写"offset 追尾"就是重演 10-10 的丢数事故。

字段名现场不止一套（bridge 的写法、老脚本的写法），所以这里做宽容解析：
枪号认 gun_no / gun / gun_name / temperature_gun / device_name / "枪4" 这类，
时间认 measured_at / spheroidization_temperature_time / temperature_time / measured_time / time，
数值认 temperature / spheroidization_temperature / value / temp。解析不出来就跳过，不猜。
"""

import json
import re
from pathlib import Path

from .base import file_exists, fingerprint, read_all_lines, tail_lines

GUN_KEYS = ("gun_no", "gun", "gun_name", "temperature_gun", "gun_id",
            "device_name")
TIME_KEYS = ("measured_at", "spheroidization_temperature_time",
             "temperature_time", "measured_time", "time")
VALUE_KEYS = ("temperature", "spheroidization_temperature", "value", "temp")

_GUN_RE = re.compile(r"(\d+)")
# device_name 会带日期前缀（如 "2026-11-01 测温枪4"），先剥掉日期再取枪号，
# 否则会命中 2026
_DATE_RE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}")
_GUN_WORD_RE = re.compile(r"枪\s*(\d+)")
_TAIL_NUM_RE = re.compile(r"(\d+)\s*$")


def _gun_from_device_name(text: str) -> int | None:
    """从 device_name 取枪号：剥日期 → 优先「枪N」→ 末尾数字。取不到返回 None。"""
    text = _DATE_RE.sub("", text)
    match = _GUN_WORD_RE.search(text)
    if not match:
        match = _TAIL_NUM_RE.search(text)
    return int(match.group(1)) if match else None


def parse_gun(obj: dict, from_filename: int | None = None) -> int | None:
    for key in GUN_KEYS:
        if key in obj and obj[key] not in (None, ""):
            value = obj[key]
            if isinstance(value, (int, float)):
                return int(value)
            if key == "device_name":
                gun = _gun_from_device_name(str(value))
                if gun is not None:
                    return gun
                continue
            match = _GUN_RE.search(str(value))
            if match:
                return int(match.group(1))
    return from_filename


def parse_event(obj: dict, from_filename: int | None = None) -> dict | None:
    gun = parse_gun(obj, from_filename)
    measured = next((obj[k] for k in TIME_KEYS if obj.get(k)), None)
    value = next((obj[k] for k in VALUE_KEYS if obj.get(k) is not None), None)
    if gun is None or measured is None or value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return {
        "kind": "temp",
        "fp": fingerprint({"gun": gun, "at": measured, "value": round(value, 3)}),
        "gun_no": gun,
        "value": value,
        "measured_at": str(measured),
    }


def read_new(path_all: Path, rolling_dir: Path, cursor):
    """:return: (事件列表, inode, 新 offset)"""
    if file_exists(path_all):
        raw, inode, offset = tail_lines(path_all, cursor)
        events = [
            e for e in (parse_event(o) for o in raw if "__bad_line__" not in o) if e
        ]
        return events, inode, offset

    # 兜底：滚动目录下每把枪一个文件，文件名带枪号
    events: list[dict] = []
    if rolling_dir.exists():
        for path in sorted(rolling_dir.glob("temperature_gun*.jsonl")):
            match = _GUN_RE.search(path.stem)
            gun = int(match.group(1)) if match else None
            for obj in read_all_lines(path):
                event = parse_event(obj, gun)
                if event:
                    events.append(event)
    return events, 0, 0


def encode(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
