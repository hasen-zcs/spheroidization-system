# -*- coding: utf-8 -*-
"""临时演示脚本：用 public/reaction_curve.png 创建一条带曲线的演示记录（截图用，之后删除）。"""
import base64
import io
import json
import urllib.request

from PIL import Image

PNG_PATH = r"D:\项目组学习\项目工作\东贝生产线\系统架构\1.2\球化监测系统 (1)\spheroidization-system\frontend\public\reaction_curve.png"
API = "http://127.0.0.1:8000/api/spheroidization"

img = Image.open(PNG_PATH).convert("RGB")
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=88)
b64 = base64.b64encode(buf.getvalue()).decode("ascii")

payload = {
    "detection_time": "2026-09-06 18:00:00",
    "spheroidization_start_time": "2026-09-06 18:00:10",
    "spheroidization_end_time": "2026-09-06 18:01:15",
    "actual_spheroidization_time": 65,
    "spheroidization_abnormal": True,
    "spheroidization_temperature": 1520,
    "spheroidization_temperature_time": "2026-09-06 18:00:20",
    "spheroidization_wire_entry_start_time": "2026-09-06 18:00:30",
    "spheroidization_wire_entry_end_time": "2026-09-06 18:01:40",
    "spheroidization_wire_entry_total_duration": 70,
    "spheroidization_weight": 1600,
    "spheroidization_image": b64,
}

req = urllib.request.Request(
    API,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=10) as resp:
    body = json.loads(resp.read().decode("utf-8"))

print("code:", body.get("code"))
print("message:", body.get("message"))
if body.get("data"):
    print("new_record_id:", body["data"].get("id"))
