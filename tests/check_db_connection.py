"""
看看"后端到底连没连上数据库"。

先起服务：

    .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

再另开一个窗口跑本脚本：

    .venv/Scripts/python.exe tests/check_db_connection.py

它会打印「建之前几条 → 通过 HTTP 建一条 → 建之后几条」。
多出来的那一行，就是后端真的写进数据库的证据。
"""

import json
import sqlite3
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

数据库路径 = Path(__file__).resolve().parents[1] / "data" / "spheroidization.db"
表 = ["StandardRecord", "SpheroidizationRecord", "ReviewRecord"]


def 看库(标题):
    """打印三张表各几行，球化记录连内容一起列出来。"""
    print(f"\n--- {标题} ---")
    if not 数据库路径.exists():
        print(f"  数据库文件还不存在：{数据库路径}")
        return {}
    conn = sqlite3.connect(数据库路径)
    conn.row_factory = sqlite3.Row
    条数 = {}
    for t in 表:
        条数[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:24} {条数[t]} 行")
    print("  库里现有的球化记录：")
    for r in conn.execute(
        "SELECT spheroidization_record_id, detection_time, processed, processed_by "
        "FROM SpheroidizationRecord ORDER BY spheroidization_record_id"
    ):
        r = dict(r)
        状态 = f"已处理({r['processed_by']})" if r["processed"] else "未处理"
        print(f"    #{r['spheroidization_record_id']}  {r['detection_time']}  {状态}")
    conn.close()
    return 条数


def 请求(path, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:8000{path}",
        data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"\n  请求失败：{e}")
        print("  服务起了吗？先跑：.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000")
        return None


def 建标准():
    return 请求("/api/standards", {
        "standard_spheroidization_time": 70,
        "standard_entry_length": 130,
        "weighing_standard": 1500,
        "created_by": "查看连接",
        "remark": "自动补的标准",
    })


def 建记录(检测时间):
    """通过 HTTP 接口建一条球化记录。"""
    return 请求("/api/spheroidization", {
        "detection_time": 检测时间,
        "spheroidization_start_time": "2026-01-01 00:00:20",
        "spheroidization_end_time": "2026-01-01 00:01:25",
        "actual_spheroidization_time": 65.0,
        "spheroidization_abnormal": False,
    })


def main():
    检测时间 = datetime.now().strftime("2026-01-01 %H:%M:%S")

    print("=" * 56)
    print("后端 <-> 数据库，连上没有？")
    print("=" * 56)
    print(f"\n数据库文件：{数据库路径}")
    if 数据库路径.exists():
        print(f"文件大小：{数据库路径.stat().st_size} 字节")
    else:
        print("（文件还不存在，服务第一次启动时会自动建）")

    之前 = 看库("第 1 步：现在库里有什么")

    # 业务规则：没有生效标准就不让建记录（UseCase 里的规则，已生效）。
    # 所以库里是空的时候，先补一条标准。
    if 之前 and 之前["StandardRecord"] == 0:
        print("\n--- 库里没有生效标准，先通过接口补一条 ---")
        r = 建标准()
        if r is None:
            return 1
        print(f"  建标准返回 code={r['code']}，id={r['data']['id']}")

    print(f"\n--- 第 2 步：通过 HTTP 接口建一条球化记录（检测时间 {检测时间}）---")
    r = 建记录(检测时间)
    if r is None:
        return 1
    if r.get("code") != 200:
        print(f"  接口返回失败：{r}")
        return 1
    print(f"  接口返回 code={r['code']}，新记录的 id={r['data']['id']}")

    之后 = 看库("第 3 步：再看库里有什么")

    print("\n" + "=" * 56)
    if 之前 and 之后:
        涨了 = 之后["SpheroidizationRecord"] - 之前["SpheroidizationRecord"]
        if 涨了 == 1:
            print("多出来 1 行 —— 后端真的写进数据库了，连上了。")
        else:
            print(f"球化记录条数变化：{涨了}（预期 +1）")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main())
