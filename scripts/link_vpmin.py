"""vpmin（检测）→ 管理系统（正式版）的联动桥。

检测侧产出 `reactions.jsonl`（7 列 + 扩展字段），管理系统吃
`POST /api/spheroidization` + `POST /api/temperature`。两边格式不是一一对应，
这个脚本负责翻译，也是这轮"联动实验"的被测对象。

字段映射
--------
| vpmin                    | 管理系统                                   |
|--------------------------|--------------------------------------------|
| reaction_count           | 仅日志用（后端不接序号）                   |
| detection_time           | detection_time（优先取按钮时刻 button_time）|
| spheroidization_start_time | 原样                                     |
| spheroidization_end_time | 原样                                       |
| actual_spheroidization_time | "00:01:30.57" → 90.57（浮点秒）          |
| spheroidization_abnormal | "成功"/"失败"/布尔 → true/false             |
| spheroidization_image    | data URI → 纯 base64                       |
| abnormal_type/_reason    | 原样（1~6）                                |
| segs / segments          | 后端暂未落库（只记类型+原因），脚本打警告  |
| temperature / gun_no     | 拆成独立温度上报，拿到记录 id 后回填关联   |

用法
----
    python scripts/link_vpmin.py --file reactions.jsonl \
        --base-url http://127.0.0.1:8000 --dry-run
    python scripts/link_vpmin.py --file reactions.jsonl --base-url http://127.0.0.1:8000
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

TIME_RE = re.compile(r"^(\d+):(\d+):(\d+(?:\.\d+)?)$")


def hms_to_seconds(value):
    """'00:01:30.57' → 90.57；已经是数字就原样返回。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = TIME_RE.match(str(value).strip())
    if not match:
        raise ValueError(f"无法解析时长：{value!r}（应为 HH:MM:SS.ss）")
    h, m, s = match.groups()
    return round(int(h) * 3600 + int(m) * 60 + float(s), 3)


def strip_data_uri(value):
    """'data:image/jpeg;base64,xxxx' → 'xxxx'；后端只收裸 base64。"""
    if not value:
        return None
    text = str(value)
    if text.startswith("data:") and ";base64," in text:
        return text.split(";base64,", 1)[1]
    return text


def normalize_time(value, drop_ms=False):
    """后端温度表只认 'YYYY-MM-DD HH:MM:SS'；球化记录保留毫秒。"""
    if value is None:
        return None
    text = str(value).strip()
    if drop_ms:
        text = re.sub(r"\.\d+$", "", text)
    return text


def to_bool_abnormal(value):
    """'成功'/'失败'/布尔/0/1 → True 表示异常。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip()
    if text in ("失败", "异常", "fail", "failed", "NG"):
        return True
    if text in ("成功", "正常", "pass", "ok", "OK"):
        return False
    # vpmin 的第三态：机器没判出来（类型 6）。后端 abnormal 允许 NULL，
    # 必须映射成 None 而不是 False——false 等于替机器宣布"正常"。
    if text in ("未判定", "unknown", "unknown"):
        return None
    raise ValueError(f"无法识别检测结果：{value!r}")


def build_record(line: dict) -> dict:
    """vpmin 一行 → POST /api/spheroidization 的请求体。"""
    extras = line.get("extras") or {}

    def pick(key, *fallbacks):
        if key in line and line[key] not in (None, ""):
            return line[key]
        for name in fallbacks:
            if name in line and line[name] not in (None, ""):
                return line[name]
            if name in extras and extras[name] not in (None, ""):
                return extras[name]
        return None

    start = pick("spheroidization_start_time")
    end = pick("spheroidization_end_time")
    # 按钮时刻优先；没有按钮就退回亮光起点（会在报告里标成口径缺失）
    detection = normalize_time(pick("button_time", "plc_button_time")) or normalize_time(start)

    payload = {
        "detection_time": detection,
        "spheroidization_start_time": normalize_time(start),
        "spheroidization_end_time": normalize_time(end),
        "actual_spheroidization_time": hms_to_seconds(
            pick("actual_spheroidization_time")
        ),
        "spheroidization_abnormal": to_bool_abnormal(
            pick("spheroidization_abnormal", "status")
        ),
        "abnormal_type": pick("abnormal_type"),
        "abnormal_reason": pick("abnormal_reason"),
        "spheroidization_image": strip_data_uri(pick("spheroidization_image")),
    }

    # PLC 侧三件套：检测模块单机位时给不了，必须由 PLC/合并层提供
    for key in (
        "spheroidization_wire_entry_start_time",
        "spheroidization_wire_entry_end_time",
        "spheroidization_wire_entry_total_duration",
        "spheroidization_weight",
    ):
        value = pick(key)
        if value is not None:
            payload[key] = normalize_time(value) if "time" in key else value

    # 温度随记录一起走（后端会落进 TemperatureRecord，gun_no 默认 0=人工）
    temperature = pick("temperature", "spheroidization_temperature")
    temperature_time = pick("temperature_time", "spheroidization_temperature_time")
    if temperature is not None:
        payload["temperature"] = temperature
        payload["temperature_time"] = normalize_time(temperature_time, drop_ms=True)
        payload["gun_no"] = int(pick("gun_no") or 4)

    return payload


def _post(base_url: str, path: str, payload: dict):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def main() -> int:
    parser = argparse.ArgumentParser(description="vpmin → 管理系统 联动桥")
    parser.add_argument("--file", required=True, help="vpmin reactions.jsonl")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = Path(args.file)
    lines = [json.loads(text) for text in path.read_text(encoding="utf-8").splitlines() if text.strip()]

    ok = failed = 0
    for line in lines:
        try:
            payload = build_record(line)
        except Exception as exc:  # 转换失败要看得见，不要静默丢
            print(f"[转换失败] {line.get('reaction_count')}: {exc}")
            failed += 1
            continue

        if args.dry_run:
            preview = {k: (v[:40] + "…" if isinstance(v, str) and len(v) > 40 else v)
                       for k, v in payload.items()}
            print(f"[dry-run] {line.get('reaction_count')}: {json.dumps(preview, ensure_ascii=False)}")
            if line.get("segments"):
                print(f"          ⚠ 分段明细 {len(line['segments'])} 段，后端无落库位置")
            ok += 1
            continue

        status, body = _post(args.base_url, "/api/spheroidization", payload)
        code = body.get("code")
        if code == 200:
            record_id = body["data"]["id"]
            print(f"[上传] #{line.get('reaction_count')} → 记录 {record_id} "
                  f"类型 {body['data'].get('abnormal_type')} "
                  f"异常 {body['data'].get('spheroidization_abnormal')} "
                  f"温度 {body['data'].get('temperature')}")
            ok += 1
        else:
            print(f"[失败] #{line.get('reaction_count')} HTTP {status} → {body}")
            failed += 1

    print(f"\n完成：成功 {ok}，失败 {failed}，共 {len(lines)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
