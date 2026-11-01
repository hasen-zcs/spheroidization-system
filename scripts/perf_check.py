"""性能检查（T-012）：对目标库跑真实链路压测，打印 P50/P95/max。

覆盖项（每项默认 ≥20 次）：
- 列表分页：第 1 页 / 第 500 页 / 最后一页，page_size=20 与 200
  （走 QuerySpheroidizationUseCase.list_page，含 count）
- 详情（含分段）：get_by_id + 最新复核 + 温度 + 分段（与详情接口同口径）
- 报表 summary（90 天区间）
- 导出 CSV 1 万条（流式，统计总耗时与首块耗时）

验收线：列表 P95 < 300ms、详情 P95 < 100ms、报表 P95 < 1500ms、
导出 1 万条总耗时 < 30s 且首字节 < 1s、库体积 < 500MB。

用法：
    python scripts/perf_check.py --db /tmp/perf/spheroidization.db [--runs 20]
退出码：全部达标 0，任一不达标 1。
"""

import argparse
import math
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.application.reports.service import ReportsService
from app.application.reports.stats import iter_csv_chunks
from app.application.spheroidization.query import QuerySpheroidizationUseCase
from app.infrastructure.database.connection import init_database
from app.infrastructure.database.flash_repo import SqliteFlashSegmentRepository
from app.infrastructure.database.sqlite import (
    SqliteReviewRepository,
    SqliteSpheroidizationRepository,
    SqliteTemperatureRepository,
)
from app.schemas.reports import CSV_HEADER


def percentile(values: list[float], pct: float) -> float:
    """最近秩法：P95 取排序后第 ceil(pct*n) 个。"""
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, math.ceil(pct * len(ordered)) - 1))
    return ordered[k]


class Bench:
    def __init__(self, label: str, target_ms: float | None):
        self.label = label
        self.target_ms = target_ms
        self.samples: list[float] = []

    def run(self, fn, n: int):
        for _ in range(n):
            t0 = time.perf_counter()
            fn()
            self.samples.append((time.perf_counter() - t0) * 1000.0)

    @property
    def p50(self):
        return percentile(self.samples, 0.50)

    @property
    def p95(self):
        return percentile(self.samples, 0.95)

    @property
    def mx(self):
        return max(self.samples)

    @property
    def ok(self) -> bool:
        if self.target_ms is None:
            return True
        return self.p95 < self.target_ms

    def line(self) -> str:
        verdict = ""
        if self.target_ms is not None:
            verdict = f"  目标P95<{self.target_ms:.0f}ms → {'✅ PASS' if self.ok else '❌ FAIL'}"
        return (
            f"{self.label:<28} n={len(self.samples):>3}  "
            f"P50={self.p50:8.1f}ms  P95={self.p95:8.1f}ms  max={self.mx:8.1f}ms{verdict}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="性能检查")
    parser.add_argument("--db", default="/tmp/perf/spheroidization.db")
    parser.add_argument("--runs", type=int, default=20, help="每项采样次数（≥20）")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.runs < 20:
        print(f"错误：每项至少 20 次，当前 --runs={args.runs}")
        return 1

    db_path = Path(args.db)
    conn = init_database(db_path)
    rng = random.Random(args.seed)

    total = conn.execute("SELECT COUNT(*) FROM SpheroidizationRecord").fetchone()[0]
    if total == 0:
        print("库里没有数据，先跑 scripts/gen_perf_data.py")
        return 1
    print(f"目标库：{db_path}（{total} 条记录，库体积 {db_path.stat().st_size / 1024 / 1024:.1f} MB）")

    spheroid_repo = SqliteSpheroidizationRepository(conn)
    review_repo = SqliteReviewRepository(conn)
    temp_repo = SqliteTemperatureRepository(conn)
    segment_repo = SqliteFlashSegmentRepository(conn)
    uc = QuerySpheroidizationUseCase(spheroid_repo, review_repo, temp_repo, segment_repo)
    reports = ReportsService(conn)

    results: list[Bench] = []

    # ---- 列表分页：第 1 页 / 第 500 页 / 最后一页 × page_size 20 / 200 ----
    for size in (20, 200):
        last_page = math.ceil(total / size)
        for page, tag in ((1, "第1页"), (500, "第500页"), (last_page, f"最后一页({last_page})")):
            bench = Bench(f"列表{tag} size={size}", 300.0)
            bench.run(lambda p=page, s=size: uc.list_page(p, s), args.runs)
            results.append(bench)

    # ---- 详情（含分段）：随机 ID 池，含若干类型 5（有分段）记录 ----
    seg_ids = [
        r[0]
        for r in conn.execute(
            "SELECT spheroidization_record_id FROM SpheroidizationRecord "
            "WHERE abnormal_type = 5 ORDER BY RANDOM() LIMIT 20"
        )
    ]
    pool = rng.sample(range(1, total + 1), 200)
    pool = list(dict.fromkeys(pool + seg_ids))

    def detail_once():
        rid = rng.choice(pool)
        record = uc.get_by_id(rid)
        if record is None:
            raise SystemExit(f"样本记录 {rid} 不存在？")
        reviews = uc.latest_review_results([record])
        temps = uc.temperatures_for([record])
        segments = uc.segments_for(rid)
        _ = (record, reviews, temps, segments)

    bench = Bench("详情(含分段)", 100.0)
    bench.run(detail_once, args.runs)
    results.append(bench)

    # ---- 报表 summary（90 天区间）----
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

    bench = Bench(f"报表summary({start}~{end})", 1500.0)
    bench.run(lambda: reports.summary(start, end), args.runs)
    results.append(bench)

    # ---- 导出 CSV 1 万条（流式，按 detection_time 倒序第 1 万条的时刻做下界）----
    cutoff = conn.execute(
        "SELECT detection_time FROM SpheroidizationRecord "
        "ORDER BY detection_time DESC LIMIT 1 OFFSET 9999"
    ).fetchone()[0]
    out_file = db_path.with_name(db_path.name + ".export.csv")

    def export_once():
        t0 = time.perf_counter()
        first_chunk_ms = None
        n_rows = 0
        with open(out_file, "w", encoding="utf-8") as fh:
            for chunk in iter_csv_chunks(CSV_HEADER, reports.iter_export_rows(cutoff, end)):
                if first_chunk_ms is None:
                    first_chunk_ms = (time.perf_counter() - t0) * 1000.0
                fh.write(chunk)
        total_ms = (time.perf_counter() - t0) * 1000.0
        n_rows = sum(1 for _ in open(out_file, encoding="utf-8")) - 1  # 扣掉表头
        return total_ms, first_chunk_ms, n_rows

    first_probe = export_once()
    if not (10000 <= first_probe[2] <= 10500):
        print(f"错误：导出样本应约为 10000 行（允许同秒并列小幅超出），实际 {first_probe[2]} 行")
        return 1
    export_n = first_probe[2]

    exp_total: list[float] = []
    exp_first: list[float] = []
    for _ in range(max(0, args.runs - 1)):
        t, f, _ = export_once()
        exp_total.append(t)
        exp_first.append(f)
    exp_total.append(first_probe[0])
    exp_first.append(first_probe[1])

    exp_ok = percentile(exp_total, 0.95) < 30_000.0 and percentile(exp_first, 0.95) < 1_000.0
    results.append(None)  # 占位，导出单独打印
    export_line = (
        f"{'导出CSV 1万条(流式)':<28} n={len(exp_total):>3}  "
        f"实际{export_n}行 | 总耗时 P50={percentile(exp_total, 0.5):8.1f}ms P95={percentile(exp_total, 0.95):8.1f}ms "
        f"max={max(exp_total):8.1f}ms | "
        f"首字节 P50={percentile(exp_first, 0.5):7.1f}ms P95={percentile(exp_first, 0.95):7.1f}ms "
        f"max={max(exp_first):7.1f}ms  "
        f"目标总<30s/首字节<1s → {'✅ PASS' if exp_ok else '❌ FAIL'}"
    )

    # ---- 汇总 ----
    print()
    for r in results:
        if r is not None:
            print(r.line())
    print(export_line)

    size_mb = db_path.stat().st_size / 1024 / 1024
    size_ok = size_mb < 500
    print(f"{'库体积':<30} {size_mb:10.1f} MB   目标<500MB → {'✅ PASS' if size_ok else '❌ FAIL'}")

    # 索引清单（报告用）
    indexes = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
        )
    ]
    print("\n库内现有索引：")
    for name, sql in indexes:
        print(f"  {sql}")
    if not indexes:
        print("  （无二级索引）")

    conn.close()
    out_file.unlink(missing_ok=True)

    all_ok = all(r.ok for r in results if r is not None) and exp_ok and size_ok
    print(f"\n总体结论：{'✅ 全部达标' if all_ok else '❌ 存在不达标项'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
