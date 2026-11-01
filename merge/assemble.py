"""组包：配对结果 → 管理系统的 POST /api/spheroidization 请求体。

三段最容易出错的地方，都在这个文件里一次解决：

1. **时长格式**：vpmin 的 actual_spheroidization_time 是 "HH:MM:SS.ss"，
   后端要的是浮点秒。优先用起止时间算，格式串只当兜底。
2. **分段换算**：vpmin 给的是墙钟毫秒串（start/end + duration_sec/gap_before_sec），
   后端要的是"相对亮光起点的秒"。而且**只有多段时这个键才存在**。
3. **异常三态**：0 正常 / 6 未判定 / 3、4、5 异常。
   未判定要传 None，不能传 0——传 0 等于替机器宣布"正常"。

PLC 的四个字段原样搬，**不做任何补偿**（采集脚本已经减过 24 秒）。
"""

import json
import re
from typing import Optional

from .pair import Pair, parse_time

HMS_RE = re.compile(r"^(\d+):(\d+):(\d+(?:\.\d+)?)$")

# 未判定：机器没给出结论。后端三态里对应 NULL。
TYPE_UNJUDGED = 6
TYPE_NORMAL = 0


def hms_to_seconds(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 3)
    match = HMS_RE.match(str(value).strip())
    if not match:
        return None
    h, m, s = match.groups()
    return round(int(h) * 3600 + int(m) * 60 + float(s), 3)


def abnormal_flag(abnormal_type: Optional[int]) -> Optional[int]:
    """0 正常 / 1 异常 / None 未知。

    2026-11-01 老板定：**未判定（类型 6）算异常**——
    机器没判出来本身就是质量问题，不能放进"正常"里混过去。
    只有上游压根没给类型（None）时才留空，那是"没这个字段"，两回事。
    """
    if abnormal_type is None:
        return None
    return 0 if int(abnormal_type) == TYPE_NORMAL else 1


def abnormal_reason(record: dict) -> Optional[str]:
    """异常原因。未判定统一写"未判定"，不带 vpmin 那串技术细节。"""
    abnormal_type = record.get("abnormal_type")
    if abnormal_type is not None and int(abnormal_type) == TYPE_UNJUDGED:
        return "未判定"
    return record.get("abnormal_reason") or None


def span_seconds(start, end) -> Optional[float]:
    s, e = parse_time(start), parse_time(end)
    if s is None or e is None:
        return None
    return round((e - s).total_seconds(), 3)


def segments_from_record(record: dict, light_start: str) -> list[dict]:
    """vpmin 的墙钟分段 → 后端要的相对秒。

    vpmin 只在 len(segments) > 1 时输出 spheroidization_segments，
    单段炉子没有这个键，返回空列表（后端允许 0 段）。
    """
    raw = record.get("spheroidization_segments") or []
    if not raw:
        return []

    t0 = parse_time(raw[0].get("start")) or parse_time(light_start)
    if t0 is None:
        return []

    out: list[dict] = []
    for index, seg in enumerate(raw, start=1):
        start = parse_time(seg.get("start"))
        end = parse_time(seg.get("end"))
        if start is None or end is None:
            return []          # 有一条坏就整条不传分段，宁可少数据不要脏数据
        start_offset = round((start - t0).total_seconds(), 3)
        end_offset = round((end - t0).total_seconds(), 3)
        duration = seg.get("duration_sec")
        duration = (
            round(float(duration), 3)
            if isinstance(duration, (int, float))
            else round(end_offset - start_offset, 3)
        )
        gap = seg.get("gap_before_sec")
        gap = round(float(gap), 3) if isinstance(gap, (int, float)) else None
        out.append(
            {
                "seg_index": index,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "gap_before": gap,
                "duration": duration,
            }
        )
    return out


class AssembleError(Exception):
    """组包失败（缺必填字段等）。走死信，不重试。"""


def build_payload(pair: Pair, temperature: Optional[dict], device_id: str) -> dict:
    record = pair.light["record"]
    plc = pair.plc["record"]

    start = record.get("spheroidization_start_time") or pair.light.get("start")
    end = record.get("spheroidization_end_time") or pair.light.get("end")
    duration = span_seconds(start, end)
    if duration is None:
        duration = hms_to_seconds(record.get("actual_spheroidization_time"))
    if duration is None:
        raise AssembleError("亮光起止时间缺失，算不出球化时长")

    # PLC 四字段：后端都是 NOT NULL，缺一个就写不进去
    feed_start = plc.get("spheroidization_wire_entry_start_time")
    feed_end = plc.get("spheroidization_wire_entry_end_time")
    feed_duration = plc.get("spheroidization_wire_entry_total_duration")
    weight = plc.get("spheroidization_weight")
    missing = [
        name
        for name, value in (
            ("进线开始", feed_start),
            ("进线结束", feed_end),
            ("进线时长", feed_duration),
            ("重量", weight),
        )
        if value is None
    ]
    if missing:
        raise AssembleError("PLC 缺字段：" + "、".join(missing))

    abnormal_type = record.get("abnormal_type")
    external_id = str(record.get("reaction_count") or "").strip()
    if not external_id:
        raise AssembleError("vpmin 记录缺 reaction_count，无法生成幂等键")

    payload = {
        "device_id": device_id,
        "external_id": external_id,
        "detection_time": pair.anchor,
        "plc_button_time": pair.anchor if pair.anchor_kind == "button" else None,
        "spheroidization_start_time": start,
        "spheroidization_end_time": end,
        "actual_spheroidization_time": duration,
        "spheroidization_abnormal": abnormal_flag(abnormal_type),
        "abnormal_type": abnormal_type,
        "abnormal_reason": abnormal_reason(record),
        "segments": segments_from_record(record, start),
        # 🔴 原样搬，不补偿
        "spheroidization_wire_entry_start_time": feed_start,
        "spheroidization_wire_entry_end_time": feed_end,
        "spheroidization_wire_entry_total_duration": feed_duration,
        "spheroidization_weight": weight,
    }

    image = record.get("spheroidization_image")
    if image:
        payload["spheroidization_image"] = _strip_data_uri(image)

    if temperature:
        payload["temperature"] = temperature["value"]
        # 后端温度表只认到秒，毫秒要去掉
        payload["temperature_time"] = re.sub(
            r"\.\d+$", "", str(temperature["measured_at"])
        )
        payload["gun_no"] = int(temperature["gun_no"])

    return payload


def _strip_data_uri(value) -> str:
    text = str(value)
    if text.startswith("data:") and ";base64," in text:
        return text.split(";base64,", 1)[1]
    return text


def plc_skew(payload: dict) -> Optional[float]:
    """进线时长 vs 起止差。用来发现"采集侧补偿常量漂了"，不自动改数据。"""
    span = span_seconds(
        payload.get("spheroidization_wire_entry_start_time"),
        payload.get("spheroidization_wire_entry_end_time"),
    )
    total = payload.get("spheroidization_wire_entry_total_duration")
    if span is None or total is None:
        return None
    return round(float(total) - span, 3)


def body_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
