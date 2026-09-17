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
"""

import json
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


def _请求(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode("utf-8", "replace")}


def main():
    # 每次跑用不同的时间戳，保证能和上一次的数据区分开
    标记 = datetime.now().strftime("%H%M%S")
    检测时间 = f"2026-01-01 00:{标记[:2]}:{标记[2:4]}"

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
    print("一、建标准")
    print("=" * 60)
    r = _请求("POST", "/api/standards", {
        "standard_spheroidization_time": 72,
        "standard_entry_length": 131,
        "weighing_standard": 1501,
        "created_by": "端到端测试",
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
    r = _请求("POST", "/api/spheroidization", {
        "detection_time": 检测时间,
        "spheroidization_start_time": "2026-01-01 00:00:20",
        "spheroidization_end_time": "2026-01-01 00:01:25",
        "actual_spheroidization_time": 65.0,
        "spheroidization_abnormal": True,
    })
    检查("返回 code 200", r.get("code"), 200)
    记录 = r["data"]
    记录id = 记录["id"]
    检查("快照取自刚建的标准", 记录["standard_spheroidization_time"], 72.0)
    检查("processed 是布尔 false", 记录["processed"], False)
    检查("spheroidization_abnormal 是布尔 true", 记录["spheroidization_abnormal"], True)
    # 响应里只该有 DDL 里真实存在的列
    检查("响应字段就是 DDL 里的那几列", sorted(记录), [
        "actual_spheroidization_time", "detection_time", "id", "processed", "processed_at",
        "processed_by", "spheroidization_abnormal", "spheroidization_end_time",
        "spheroidization_start_time", "standard_spheroidization_time",
    ])

    print("\n" + "=" * 60)
    print("三、处置（业务规则：不可逆）")
    print("=" * 60)
    r = _请求("POST", f"/api/spheroidization/{记录id}/process", {"processed_by": "李四"})
    检查("返回 code 200", r.get("code"), 200)
    检查("处置后 processed 为 true", r["data"]["processed"], True)
    检查("处置人正确", r["data"]["processed_by"], "李四")

    r = _请求("POST", f"/api/spheroidization/{记录id}/process", {"processed_by": "王五"})
    检查("重复处置被拦住（code 400）", r.get("code"), 400)
    检查("提示里带上原处理人", "李四" in r.get("message", ""), True)

    r = _请求("GET", f"/api/spheroidization/{记录id}")
    检查("被拒绝后处理人没被覆盖", r["data"]["processed_by"], "李四")

    print("\n" + "=" * 60)
    print("四、复核（中文 -> 0/1 的转换）")
    print("=" * 60)
    r = _请求("POST", "/api/reviews", {
        "spheroidization_record_id": 记录id,
        "review_result": "异常",
        "review_remark": "人工确认异常",
        "reviewer": "王五",
    })
    检查("返回 code 200", r.get("code"), 200)
    检查("回显 review_result 还是中文", r["data"]["review_result"], "异常")
    检查("响应字段是 id", "id" in r["data"], True)

    r = _请求("POST", "/api/reviews", {
        "spheroidization_record_id": 记录id,
        "review_result": "正常",
        "review_remark": "二次复核",
        "reviewer": "赵六",
    })
    检查("同一记录可以有多条复核", r.get("code"), 200)

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
        "reviewer": "y",
    })
    检查("给不存在的记录提交复核 code 400", r.get("code"), 400)

    print("\n" + "=" * 60)
    print("六、直查数据库对账（这一步才是关键）")
    print("=" * 60)
    conn = sqlite3.connect(数据库路径)
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        "SELECT * FROM SpheroidizationRecord WHERE detection_time = ?", (检测时间,)
    ).fetchone()
    检查("HTTP 建的球化记录真的在库里", row is not None, True)
    if row is not None:
        row = dict(row)
        检查("  该行主键是数据库分配的", row["spheroidization_record_id"], 记录id)
        检查("  已处理落盘", row["processed"], 1)
        检查("  处理人落盘", row["processed_by"], "李四")
        检查("  处理时间落盘且是字符串", isinstance(row["processed_at"], str), True)
        检查("  异常标记存成了整数 1", row["spheroidization_abnormal"], 1)
        检查("  快照落盘", row["standard_spheroidization_time"], 72.0)
        检查("  溯源的 standard_record_id 挂上了", row["standard_record_id"], 标准id)

    row = dict(conn.execute(
        "SELECT * FROM StandardRecord WHERE remark = ?", (f"e2e-{标记}",)
    ).fetchone())
    检查("HTTP 建的标准真的在库里", row["standard_record_id"], 标准id)

    rows = [dict(x) for x in conn.execute(
        "SELECT * FROM ReviewRecord WHERE spheroidization_record_id = ?", (记录id,)
    )]
    检查("两条复核都在库里", len(rows), 2)
    检查("「异常」存成了整数 1，不是字符串",
         [x["review_result"] for x in rows], [1, 0])

    print("\n" + "=" * 60)
    合计 = 通过 + 失败
    print(f"结果：{通过}/{合计} 通过" + ("  全部通过" if 失败 == 0 else f"  {失败} 项失败"))
    print("=" * 60)
    return 0 if 失败 == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
