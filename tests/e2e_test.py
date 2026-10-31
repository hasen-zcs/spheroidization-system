"""
端到端测试：走 HTTP，验证接口真的落到数据库。

和 smoke_test.py 的区别：
    smoke_test.py  直接调 UseCase，不经过 FastAPI
    本文件         起真实服务，用 HTTP 请求打进去，最后直查数据库对账

跑之前要先把服务起起来：

    .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

然后另开一个窗口：

    .venv/Scripts/python.exe tests/e2e_test.py

不假设库是空的，每次用时间戳造一批独立的数据，最后按内容核对。

2026-10 起建标准、处置、复核都要登录，所以第一步先登录拿 token。
先建管理员：.venv/Scripts/python.exe scripts/init_admin.py admin
"""

import base64
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

项目根目录 = Path(__file__).resolve().parents[1]
数据库路径 = 项目根目录 / "data" / "spheroidization.db"
BASE = "http://127.0.0.1:8000"

# 2026-10 起处置、复核、建标准都要登录。跑之前先建一个管理员：
#     .venv/Scripts/python.exe scripts/init_admin.py admin
# 账号密码默认 admin / pass1234，可以用环境变量覆盖。
用户名 = os.getenv("E2E_USERNAME", "admin")
密码 = os.getenv("E2E_PASSWORD", "pass1234")
_TOKEN = None

通过 = 0
失败 = 0


def 检查(说明, 实际, 期望):
    global 通过, 失败
    if 实际 == 期望:
        通过 += 1
        print(f"  [OK] {说明}")
    else:
        失败 += 1
        print(f"  [XX] {说明}\n       期望: {期望!r}\n       实际: {实际!r}")


def _鉴权头():
    return {"Authorization": f"Bearer {_TOKEN}"} if _TOKEN else {}


def _请求(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    headers.update(_鉴权头())
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode("utf-8", "replace")}


def _取原始(path):
    """拿原始响应（不解析 JSON），给图片端点用。返回 (HTTP 状态, Content-Type, body 字节)。"""
    req = urllib.request.Request(BASE + path, headers=_鉴权头())
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def main():
    # 每次跑都要和上一次的数据彻底分开，所以标记精确到微秒。
    # 只到秒是不够的：连着跑两次很可能落在同一秒里，两批数据就撞了；
    # 更早的版本甚至连秒都没用上（只取到分），同一分钟内跑多少次都是同一个值。
    时刻 = datetime.now()
    标记 = 时刻.strftime("%H%M%S%f")
    检测时间 = f"2026-01-01 {时刻:%H:%M:%S.%f}"

    print("\n" + "=" * 60)
    print("零、服务在不在")
    print("=" * 60)
    r = _请求("GET", "/api/health")
    if r.get("code") != 200:
        print(f"  服务没起来（{r}）")
        print("  先跑：.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000")
        return 1
    检查("健康检查通", r["code"], 200)

    print("\n" + "=" * 60)
    print("零之二、登录拿 token")
    print("=" * 60)
    global _TOKEN
    r = _请求("POST", "/api/users/login", {"username": 用户名, "password": 密码})
    检查("登录成功", r.get("code"), 200)
    if r.get("code") != 200:
        print(f"  登录失败（{r.get('message')}）")
        print("  先建管理员：.venv/Scripts/python.exe scripts/init_admin.py admin")
        return 1
    _TOKEN = r["data"]["token"]
    检查("拿到 token", isinstance(_TOKEN, str) and len(_TOKEN) > 0, True)

    print("\n" + "=" * 60)
    print("一、建标准")
    print("=" * 60)
    r = _请求("POST", "/api/standards", {
        "standard_spheroidization_time": 72,
        "standard_spheroidization_time_upper": 75,
        "standard_spheroidization_time_lower": 65,
        "weighing_standard": 1501,
        "remark": f"e2e-{标记}",
    })
    检查("返回 code 200", r.get("code"), 200)
    标准 = r["data"]
    检查("响应里有 id（不是 standard_record_id）", "id" in 标准, True)
    检查("创建时间是字符串", isinstance(标准["created_at"], str), True)
    标准id = 标准["id"]

    r = _请求("GET", "/api/standards/current")
    检查("新标准立即成为当前标准", r["data"]["id"], 标准id)

    print("\n" + "=" * 60)
    print("二、建球化记录（快照必须取自当前标准）")
    print("=" * 60)
    # 图片走 base64。用 0x00~0x0F 这 16 个字节就够验编解码了，不用塞几 MB。
    # 前面挂上 JPEG 文件头，是为了同时验图片端点的 Content-Type 嗅探；
    # 后面那 16 个字节仍然覆盖了 0x00，base64 / 编码转换出偏差照样会露馅。
    图片字节 = b"\xff\xd8\xff" + bytes(range(16))
    图片base64 = base64.b64encode(图片字节).decode()

    r = _请求("POST", "/api/spheroidization", {
        "detection_time": 检测时间,
        "spheroidization_start_time": "2026-01-01 00:00:20",
        "spheroidization_end_time": "2026-01-01 00:01:25",
        "actual_spheroidization_time": 65.0,
        "spheroidization_abnormal": True,
        "abnormal_type": 1,
        "abnormal_reason": "超过标准",
        "spheroidization_wire_entry_start_time": "2026-01-01 00:00:40",
        "spheroidization_wire_entry_end_time": "2026-01-01 00:02:00",
        "spheroidization_wire_entry_total_duration": 80.803,
        "spheroidization_weight": 1608.0,
        "spheroidization_image": 图片base64,
    })
    检查("返回 code 200", r.get("code"), 200)
    记录 = r["data"]
    记录id = 记录["id"]
    检查("快照取自刚建的标准", 记录["standard_spheroidization_time"], 72.0)
    检查("processed 是布尔 false", 记录["processed"], False)
    检查("spheroidization_abnormal 是布尔 true", 记录["spheroidization_abnormal"], True)
    检查("异常分类原样回显", 记录["abnormal_type"], 1)
    检查("新增物性字段原样回显", 记录["spheroidization_weight"], 1608.0)
    # 响应里只该有 DDL 里真实存在的列。
    # 注意这里**没有** spheroidization_image：创建响应刻意不回带图片。
    # 温度已经拆表，没关联读数时返回 null，但字段仍在契约里。
    检查("响应字段就是契约里的那几列（创建不回带图片）", sorted(记录), [
        "abnormal_reason", "abnormal_type", "actual_spheroidization_time",
        "detection_time", "id", "processed", "processed_at", "processed_by",
        "review_result", "spheroidization_abnormal", "spheroidization_end_time",
        "spheroidization_start_time", "spheroidization_weight",
        "spheroidization_wire_entry_end_time", "spheroidization_wire_entry_start_time",
        "spheroidization_wire_entry_total_duration", "standard_spheroidization_time",
        "temperature", "temperature_time",
    ])

    r = _请求("GET", f"/api/spheroidization/{记录id}")
    检查("详情接口回带图片，base64 原样",
          r["data"].get("spheroidization_image"), 图片base64)

    全部记录 = _请求("GET", "/api/spheroidization")["data"]["items"]
    检查("列表接口一条都不带图片（否则响应会被整个撑爆）",
         any("spheroidization_image" in x for x in 全部记录), False)

    print("\n" + "-" * 60)
    print("二之二、图片端点（给前端 <img src> 用，响应体不是 JSON）")
    print("-" * 60)
    状态, 类型, 原始 = _取原始(f"/api/spheroidization/{记录id}/image")
    检查("图片端点 HTTP 200", 状态, 200)
    检查("按文件头认出是 JPEG", 类型.split(";")[0], "image/jpeg")
    检查("吐出来的就是原始字节，没有 base64 / 没有 JSON 包装", 原始, 图片字节)

    状态, 类型, _ = _取原始("/api/spheroidization/999999/image")
    检查("记录不存在时回 404 信封", 状态, 200)
    检查("  且 body 是 JSON 不是图片", 类型.split(";")[0], "application/json")

    # 上面那条记录带了图。这条新建的不带图，验「有记录但没图」这条路。
    # 日期用 01-02，跟上面那条分开——两条记录不该共用任何标识。
    r = _请求("POST", "/api/spheroidization", {
        "detection_time": f"2026-01-02 {时刻:%H:%M:%S.%f}",
        "spheroidization_start_time": "2026-01-01 00:00:20",
        "spheroidization_end_time": "2026-01-01 00:01:25",
        "actual_spheroidization_time": 65.0,
        "spheroidization_wire_entry_start_time": "2026-01-01 00:00:40",
        "spheroidization_wire_entry_end_time": "2026-01-01 00:02:00",
        "spheroidization_wire_entry_total_duration": 80.0,
        "spheroidization_weight": 1608.0,
    })
    无图id = r["data"]["id"]
    resp = _请求("GET", f"/api/spheroidization/{无图id}/image")
    检查("有记录但没图，回 code 404", resp.get("code"), 404)

    print("\n" + "-" * 60)
    print("二之三、温度上报（独立接口，免登录）")
    print("-" * 60)
    r = _请求("POST", "/api/temperature", {
        "gun_no": 1,
        "temperature": 1405.5,
        "measured_at": "2026-01-01 00:00:35",
        "spheroidization_record_id": 记录id,
    })
    检查("温度上报 code 200", r.get("code"), 200)
    检查("  关联到了刚建的那条记录", r["data"]["spheroidization_record_id"], 记录id)

    # 直接调温度接口时前端不带 token；这里清空再打一次，验证免登录。
    已保存token = _TOKEN
    _TOKEN = None
    try:
        r = _请求("POST", "/api/temperature", {
            "gun_no": 2,
            "temperature": 1398.0,
            "measured_at": "2026-01-01 00:00:36",
            "spheroidization_record_id": 记录id,
        })
        检查("无 token 也能上报温度", r.get("code"), 200)
    finally:
        _TOKEN = 已保存token

    条目 = next(
        x
        for x in _请求("GET", "/api/spheroidization")["data"]["items"]
        if x["id"] == 记录id
    )
    检查("列表里带出关联的温度（多条取最新那条）", 条目["temperature"], 1398.0)
    检查("  以及测温时刻", 条目["temperature_time"], "2026-01-01 00:00:36")

    print("\n" + "-" * 60)
    print("二之四、漏传必填字段时的响应形状")
    print("-" * 60)
    # 前端是按 body.code 判断成败的，所以校验失败也必须走统一信封，
    # 不能是 FastAPI 默认的 {"detail": [...]}（那样前端读到的是 undefined）
    r = _请求("POST", "/api/spheroidization", {"detection_time": "2026-01-01 00:00:00"})
    检查("漏字段回 code 422", r.get("code"), 422)
    检查("  报错信息里点名了缺哪个字段", "spheroidization_weight" in r.get("message", ""), True)
    检查("  data 是 null", r.get("data"), None)

    print("\n" + "=" * 60)
    print("三、处置（业务规则：不可逆）")
    print("=" * 60)
    r = _请求("POST", f"/api/spheroidization/{记录id}/process", {})
    检查("返回 code 200", r.get("code"), 200)
    检查("处置后 processed 为 true", r["data"]["processed"], True)
    检查("处置人取自登录态", r["data"]["processed_by"], 用户名)

    r = _请求("POST", f"/api/spheroidization/{记录id}/process", {})
    检查("重复处置被拦住（code 400）", r.get("code"), 400)
    检查("提示里带上原处理人", 用户名 in r.get("message", ""), True)

    r = _请求("GET", f"/api/spheroidization/{记录id}")
    检查("被拒绝后处理人没被覆盖", r["data"]["processed_by"], 用户名)

    print("\n" + "=" * 60)
    print("四、复核（中文 -> 0/1 的转换）")
    print("=" * 60)
    r = _请求("POST", "/api/reviews", {
        "spheroidization_record_id": 记录id,
        "review_result": "异常",
        "review_remark": "人工确认异常",
    })
    检查("返回 code 200", r.get("code"), 200)
    检查("回显 review_result 还是中文", r["data"]["review_result"], "异常")
    检查("复核人取自登录态", r["data"]["reviewer"], 用户名)
    检查("响应字段是 id", "id" in r["data"], True)

    r = _请求("POST", "/api/reviews", {
        "spheroidization_record_id": 记录id,
        "review_result": "正常",
        "review_remark": "二次复核",
    })
    检查("同一记录可以有多条复核", r.get("code"), 200)

    # 复核结果是"非异常即正常"的判定，多一个空格就会被存成"正常"。
    # 人工判定被悄悄反过来，事后查不出来，所以必须在门口拦住。
    r = _请求("POST", "/api/reviews", {
        "spheroidization_record_id": 记录id,
        "review_result": "异常 ",
        "review_remark": "手滑多打了个空格",
    })
    检查("复核结果多一个空格被拦（code 422）", r.get("code"), 422)
    检查("  报错里点名了 review_result", "review_result" in r.get("message", ""), True)

    r = _请求("GET", f"/api/reviews/{记录id}")
    检查("复核列表返回数组", isinstance(r["data"], list), True)
    检查("两条复核都在", len(r["data"]), 2)
    检查("且顺序是先异常后正常",
         [x["review_result"] for x in r["data"]], ["异常", "正常"])

    检查("复核不改记录的处置状态",
         _请求("GET", f"/api/spheroidization/{记录id}")["data"]["processed"], True)

    print("\n" + "=" * 60)
    print("五、错误路径")
    print("=" * 60)
    r = _请求("GET", "/api/spheroidization/999999")
    检查("查不存在的记录 code 404", r.get("code"), 404)

    r = _请求("POST", "/api/reviews", {
        "spheroidization_record_id": 999999,
        "review_result": "正常",
        "review_remark": "x",
    })
    检查("给不存在的记录提交复核 code 400", r.get("code"), 400)

    print("\n" + "=" * 60)
    print("六、直查数据库对账（这一步才是关键）")
    print("=" * 60)
    conn = sqlite3.connect(数据库路径)
    conn.row_factory = sqlite3.Row

    # 按主键查，不按 detection_time 查。
    # 按 detection_time 查是 fetchone() 取第一行，库里只要还留着以前跑的同名记录
    # 就会取到旧的那行，"对账"对着对着变成对着上一次的数据，报一堆假失败。
    # 主键来自刚才那个 POST 的响应，按它查才精确。
    row = conn.execute(
        "SELECT * FROM SpheroidizationRecord WHERE spheroidization_record_id = ?",
        (记录id,),
    ).fetchone()
    检查("HTTP 建的球化记录真的在库里", row is not None, True)
    if row is not None:
        row = dict(row)
        检查("  该行主键是数据库分配的", row["spheroidization_record_id"], 记录id)
        检查("  检测时间原样落盘", row["detection_time"], 检测时间)
        检查("  已处理落盘", row["processed"], 1)
        检查("  处理人是登录账号", row["processed_by"], 用户名)
        检查("  处理时间落盘且是字符串", isinstance(row["processed_at"], str), True)
        检查("  异常标记存成了整数 1", row["spheroidization_abnormal"], 1)
        检查("  异常分类落盘", row["abnormal_type"], 1)
        检查("  异常说明落盘", row["abnormal_reason"], "超过标准")
        检查("  快照落盘", row["standard_spheroidization_time"], 72.0)
        检查("  溯源的 standard_record_id 挂上了", row["standard_record_id"], 标准id)
        检查("  新增物性字段落盘", row["spheroidization_weight"], 1608.0)
        检查("  进线总时长落盘且保留小数",
             row["spheroidization_wire_entry_total_duration"], 80.803)
        检查("  图片以 BLOB 落盘（不是 base64 字符串）",
             row["spheroidization_image"], 图片字节)

    # 同样按主键查，理由见上面那条球化记录的注释
    row = dict(conn.execute(
        "SELECT * FROM StandardRecord WHERE standard_record_id = ?", (标准id,)
    ).fetchone())
    检查("HTTP 建的标准真的在库里", row["standard_record_id"], 标准id)
    检查("  remark 原样落盘", row["remark"], f"e2e-{标记}")
    检查("  球化时长上下限落盘",
         (row["standard_spheroidization_time_upper"],
          row["standard_spheroidization_time_lower"]), (75.0, 65.0))

    rows = [dict(x) for x in conn.execute(
        "SELECT * FROM ReviewRecord WHERE spheroidization_record_id = ?", (记录id,)
    )]
    检查("两条复核都在库里", len(rows), 2)
    检查("「异常」存成了整数 1，不是字符串",
         [x["review_result"] for x in rows], [1, 0])
    检查("复核人落盘为登录账号", rows[0]["reviewer"], 用户名)

    rows = [dict(x) for x in conn.execute(
        "SELECT * FROM TemperatureRecord WHERE spheroidization_record_id = ? "
        "ORDER BY measured_at ASC",
        (记录id,),
    )]
    检查("两条温度读数都在库里", len(rows), 2)
    检查("  外键指向那条球化记录", rows[0]["spheroidization_record_id"], 记录id)
    检查("  读数按原值落盘", [x["temperature"] for x in rows], [1405.5, 1398.0])

    print("\n" + "=" * 60)
    合计 = 通过 + 失败
    print(f"结果：{通过}/{合计} 通过" + ("  全部通过" if 失败 == 0 else f"  {失败} 项失败"))
    print("=" * 60)
    return 0 if 失败 == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
