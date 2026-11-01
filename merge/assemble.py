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
from pathlib import Path
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


def heat_segments(record: dict) -> list[dict]:
    """heat 主源的分段 → 后端 segments 结构（相对秒）。

    后端契约要的是"相对球化起点（亮光首段起点）的秒数（float, ≥0）"，
    不是墙钟串。heat 记录里每项是 {seq, start, end, duration_sec, gap_before_sec}：
    - 没有 spheroidization_start_time（类型 1/2）→ 没有相对基准，返回 []
    - 段按 seq 排序，seg_index 直接用 seq
    - 负偏移夹到 0；全部 round(x, 3)；首段 gap_before 必须 None
    - 缺 duration_sec 时用 end-start 算
    """
    raw = record.get("spheroidization_segments") or []
    if not raw:
        return []

    t0 = parse_time(record.get("spheroidization_start_time"))
    if t0 is None:
        return []

    def _num(value) -> Optional[float]:
        return round(float(value), 3) if isinstance(value, (int, float)) else None

    out: list[dict] = []
    for seg in sorted(raw, key=lambda item: item.get("seq") or 0):
        start = parse_time(seg.get("start"))
        end = parse_time(seg.get("end"))
        if start is None or end is None:
            return []          # 有一条坏就整条不传分段，宁可少数据不要脏数据
        start_offset = max(round((start - t0).total_seconds(), 3), 0.0)
        end_offset = max(round((end - t0).total_seconds(), 3), 0.0)
        duration = _num(seg.get("duration_sec"))
        if duration is None:
            duration = round(end_offset - start_offset, 3)
        gap = _num(seg.get("gap_before_sec"))
        out.append(
            {
                "seg_index": seg.get("seq"),
                "start_offset": start_offset,
                "end_offset": end_offset,
                "gap_before": gap,
                "duration": duration,
            }
        )
    # 首段没有"之前的间隙"，必须 None
    if out:
        out[0]["gap_before"] = None
    return out


def build_payload_from_heat(record: dict, temperature: Optional[dict], device_id: str) -> dict:
    """heat 主源组包：一行一炉，记录已融合反应+PLC 字段，不需要配对。

    与 build_payload 的差异：
    - start/end 可为 null（类型 1/2：有球化动作但没检测到亮光），不抛异常
    - 时长算不出就传 null（没有起止 → 退回 hms 串 → 都没有就 null）
    - PLC 四字段直接取 record 里的同名键（heat 记录已融合）
    - 温度同现规则：有就填，无则不填，绝不造假
    """
    start = record.get("spheroidization_start_time") or None
    end = record.get("spheroidization_end_time") or None
    duration = span_seconds(start, end)
    if duration is None:
        duration = hms_to_seconds(record.get("actual_spheroidization_time"))
    # 起止和时长串都缺失 → duration 保持 None，不报错

    abnormal_type = record.get("abnormal_type")
    external_id = "heat:{}:{}".format(
        record.get("reaction_count"),
        record.get("spheroidization_wire_entry_start_time"),
    )

    payload = {
        "device_id": device_id,
        "external_id": external_id,
        "detection_time": record.get("detection_time"),
        "plc_button_time": record.get("plc_button_time"),
        "spheroidization_start_time": start,
        "spheroidization_end_time": end,
        "actual_spheroidization_time": duration,
        "spheroidization_abnormal": abnormal_flag(abnormal_type),
        "abnormal_type": abnormal_type,
        "abnormal_reason": abnormal_reason(record),
        "segments": heat_segments(record),
        # PLC 四字段：heat 记录已融合，直接取同名键
        "spheroidization_wire_entry_start_time": record.get("spheroidization_wire_entry_start_time"),
        "spheroidization_wire_entry_end_time": record.get("spheroidization_wire_entry_end_time"),
        "spheroidization_wire_entry_total_duration": record.get("spheroidization_wire_entry_total_duration"),
        "spheroidization_weight": record.get("spheroidization_weight"),
    }

    if temperature:
        payload["temperature"] = temperature["value"]
        # 后端温度表只认到秒，毫秒要去掉
        payload["temperature_time"] = re.sub(r"\.\d+$", "", str(temperature["measured_at"]))
        payload["gun_no"] = int(temperature["gun_no"])

    return payload


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


# ---------------- heat 链路 PLC 回捞（T-004e） ----------------

# 回捞匹配窗口（秒）：heat 带毫秒、all_plc 不带，
# 秒级截断后相等是 "相差 ≤2s" 的子集，统一按绝对时差 ≤2s 判定。
PLC_BACKFILL_WINDOW = 2.0


def plc_backfill_note(body_text: str) -> Optional[str]:
    """422 死信附注：body 里进线结束/时长为 null → 回捞失败。

    只有 heat 路径可能把 null 放进上传队列（reactions 老路径在组包时就抛
    AssembleError），所以此注记只对 heat 有意义。解析失败返回 None，不影响主流程。
    """
    try:
        payload = json.loads(body_text)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    missing = [
        name
        for name in (
            "spheroidization_wire_entry_end_time",
            "spheroidization_wire_entry_total_duration",
        )
        if payload.get(name) is None
    ]
    if missing:
        return "all_plc 无对应行，无法回捞（缺失：" + "、".join(missing) + "）"
    return None


def _read_plc_all_rows(path: Optional[Path]) -> list[dict]:
    """读 all_plc.jsonl 全量行（仅取有进线开始时间的行）。

    文件不存在 / 不可读 / 行坏 → 静默跳过（返回空列表），
    不影响无 PLC 回捞环境的测试。
    """
    if path is None:
        return []
    try:
        path = Path(path)
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("spheroidization_wire_entry_start_time"):
            rows.append(obj)
    return rows


def match_plc_row(start_time, rows: list[dict]) -> Optional[dict]:
    """按进线开始时间匹配 all_plc 行：|时差| ≤ PLC_BACKFILL_WINDOW 秒。

    多行命中时取时差最小者；平差取文件里靠后的（更接近本炉的写入）。
    """
    target = parse_time(start_time)
    if target is None or not rows:
        return None
    best: Optional[dict] = None
    best_diff: Optional[float] = None
    for row in rows:
        row_time = parse_time(row.get("spheroidization_wire_entry_start_time"))
        if row_time is None:
            continue
        diff = abs((target - row_time).total_seconds())
        if diff > PLC_BACKFILL_WINDOW:
            continue
        if best is None or diff <= best_diff:
            best, best_diff = row, diff
    return best


def backfill_plc_from_all_plc(record: dict, plc_all_file) -> Optional[dict]:
    """heat 记录进线结束/时长为 null 时，从 all_plc.jsonl 回捞（原地回填）。

    - 触发条件：end_time 或 total_duration 为 null；两者都非空直接返回 None
    - 匹配规则：按 spheroidization_wire_entry_start_time，|时差| ≤2s
    - 只回填 null 的字段；heat 已有的非空字段**不被覆盖**（heat 为准）
    - 文件不存在 / 无对应行 / 无开始时间 → 返回 None，record 原样不动

    :return: 命中的 all_plc 行（供日志/诊断）；None = 未回捞。
    """
    has_end = record.get("spheroidization_wire_entry_end_time") is not None
    has_duration = record.get("spheroidization_wire_entry_total_duration") is not None
    if has_end and has_duration:
        return None
    row = match_plc_row(
        record.get("spheroidization_wire_entry_start_time"),
        _read_plc_all_rows(plc_all_file),
    )
    if row is None:
        return None
    if not has_end:
        record["spheroidization_wire_entry_end_time"] = row.get(
            "spheroidization_wire_entry_end_time"
        )
    if not has_duration:
        record["spheroidization_wire_entry_total_duration"] = row.get(
            "spheroidization_wire_entry_total_duration"
        )
    return row
