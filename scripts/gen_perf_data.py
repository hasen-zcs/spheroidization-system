"""生成性能压测用的真实分布测试数据（T-012）。

只走真实仓储/ORM（app.infrastructure.database），不写裸 SQL 插数据，
保证索引、约束、外键与生产一致。

分布（--seed 固定后可复现）：
- abnormal_type：0 正常占 90%，1/3/4/5/6 各少量
  （1 4%、3 3%、4 1.5%、5 1%、6 0.5%）
- 30% 的记录带一条测温读数（TemperatureRecord，枪号 1~3）
- 类型 5（分段多次球化）的记录带 2~3 条分段明细（FlashSegment 证据链）
- 检测时间均匀分布在过去 90 天
- 约 60% 的异常记录已被人工处置（processed=1）
- 不生成图片（BLOB 列留空）：库体积指标本就不含图片

用法：
    python scripts/gen_perf_data.py --db /tmp/perf/spheroidization.db --rows 50000 --seed 42

注意：目标库已存在时直接删掉重建（压测库就该是一次性的）。
"""

import argparse
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.flash.entities import FlashSegment
from app.domain.review.entities import ReviewRecord
from app.domain.spheroidization.entities import SpheroidizationRecord
from app.domain.standard.entities import StandardRecord
from app.domain.temperature.entities import TemperatureRecord
from app.infrastructure.database.connection import init_database

# 类型分布：0 占 90%，其余各少量（合计 10%）
TYPE_WEIGHTS = [(0, 0.90), (1, 0.04), (3, 0.03), (4, 0.015), (5, 0.01), (6, 0.005)]
TYPE_REASONS = {
    1: "进站未球化，反应炉入口信号缺失",
    3: "实际球化时长超过标准上限",
    4: "实际球化时长低于标准下限",
    5: "球化过程中出现中间亮光停顿",
}
OPERATORS = ["张三", "李四", "王五"]
REVIEWERS = ["赵一", "钱二"]


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _r3(value: float) -> float:
    return round(value, 3)


def _make_segments(rng: random.Random):
    """类型 5 的分段证据链：2~3 段亮光，中间有正数停顿。"""
    n = rng.randint(2, 3)
    segs = []
    t = 0.0
    for i in range(1, n + 1):
        dur = rng.uniform(5.0, 30.0)
        gap = None if i == 1 else rng.uniform(1.5, 8.0)
        if gap:
            t += gap
        end = t + dur
        segs.append(
            FlashSegment(
                seg_index=i,
                start_offset=_r3(t),
                end_offset=_r3(end),
                gap_before=_r3(gap) if gap else None,
                duration=_r3(end - t),
            )
        )
        t = end
    return segs


def generate(db_path: Path, rows: int, seed: int) -> None:
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        stale = db_path.with_name(db_path.name + suffix)
        if stale.exists():
            stale.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    conn = init_database(db_path)
    # 压测数据生成提速：WAL + 降低同步强度（只影响这个临时库的写入节奏，
    # 不改任何表结构/索引）。
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # 仓储全部复用同一条连接（与 Container 装配的是同一套实现）
    from app.infrastructure.database.sqlite import (
        SqliteReviewRepository,
        SqliteSpheroidizationRepository,
        SqliteStandardRepository,
        SqliteTemperatureRepository,
    )
    from app.infrastructure.database.flash_repo import SqliteFlashSegmentRepository

    spheroid_repo = SqliteSpheroidizationRepository(conn)
    standard_repo = SqliteStandardRepository(conn)
    review_repo = SqliteReviewRepository(conn)
    temp_repo = SqliteTemperatureRepository(conn)
    segment_repo = SqliteFlashSegmentRepository(conn)

    std1 = standard_repo.save(
        StandardRecord(
            standard_spheroidization_time=65.0,
            weighing_standard=1500.0,
            created_by="张三",
            remark="初始标准",
        )
    )
    std2 = standard_repo.save(
        StandardRecord(
            standard_spheroidization_time=70.0,
            weighing_standard=1500.0,
            standard_spheroidization_time_upper=80.0,
            standard_spheroidization_time_lower=60.0,
            created_by="李四",
            remark="调整",
        )
    )
    standard_ids = [std1.standard_record_id, std2.standard_record_id]

    rng = random.Random(seed)
    now = datetime.now()
    span = timedelta(days=90)
    types = [t for t, _ in TYPE_WEIGHTS]
    weights = [w for _, w in TYPE_WEIGHTS]

    type_counts = {t: 0 for t in types}
    temp_count = 0
    seg_count = 0
    review_count = 0
    processed_count = 0

    BATCH = 1000
    done = 0
    while done < rows:
        batch = rows - done
        with conn:  # 一整批一个事务，5 万条不至于 5 万次 fsync
            for _ in range(batch):
                # ---- 时间轴：90 天均匀分布 ----
                detection = now - timedelta(seconds=rng.random() * span.total_seconds())
                std_id = rng.choice(standard_ids)
                type_ = rng.choices(types, weights=weights, k=1)[0]
                type_counts[type_] += 1

                actual = max(20.0, min(180.0, rng.gauss(65.0, 10.0)))
                start = detection + timedelta(seconds=rng.uniform(1.0, 5.0))
                end = start + timedelta(seconds=actual)
                wire_start = detection + timedelta(seconds=rng.uniform(10.0, 30.0))
                wire_dur = max(20.0, min(200.0, rng.gauss(80.0, 15.0)))
                wire_end = wire_start + timedelta(seconds=wire_dur)

                abnormal = 0 if type_ == 0 else (None if type_ == 6 else 1)
                reason = TYPE_REASONS.get(type_)
                processed = 0
                processed_at = None
                processed_by = None
                if type_ != 0 and type_ != 6 and rng.random() < 0.6:
                    processed = 1
                    processed_at = _fmt(detection + timedelta(hours=rng.uniform(1, 48)))
                    processed_by = rng.choice(OPERATORS)
                    processed_count += 1

                record = spheroid_repo.save_no_commit(
                    SpheroidizationRecord(
                        standard_record_id=std_id,
                        detection_time=_fmt(detection),
                        spheroidization_start_time=_fmt(start),
                        spheroidization_end_time=_fmt(end),
                        actual_spheroidization_time=round(actual, 1),
                        standard_spheroidization_time=float(std2.standard_spheroidization_time),
                        spheroidization_abnormal=abnormal,
                        abnormal_type=type_,
                        abnormal_reason=reason,
                        plc_button_time=_fmt(detection - timedelta(seconds=5)) if rng.random() < 0.8 else None,
                        spheroidization_wire_entry_start_time=_fmt(wire_start),
                        spheroidization_wire_entry_end_time=_fmt(wire_end),
                        spheroidization_wire_entry_total_duration=round(wire_dur, 1),
                        spheroidization_weight=round(max(1200.0, rng.gauss(1600.0, 60.0)), 1),
                        processed=processed,
                        processed_at=processed_at,
                        processed_by=processed_by,
                    )
                )
                rid = record.spheroidization_record_id

                # 30% 带温度
                if rng.random() < 0.3:
                    temp_repo.save(
                        TemperatureRecord(
                            gun_no=rng.randint(1, 3),
                            temperature=round(max(800.0, rng.gauss(1450.0, 60.0)), 1),
                            measured_at=_fmt(start + timedelta(seconds=rng.uniform(40.0, 90.0))),
                            spheroidization_record_id=rid,
                        )
                    )
                    temp_count += 1

                # 类型 5 带分段证据链
                if type_ == 5:
                    segs = _make_segments(rng)
                    segment_repo.save_many_no_commit(rid, segs)
                    seg_count += len(segs)

                # 异常记录约 50% 有人工复核
                if type_ != 0 and type_ != 6 and rng.random() < 0.5:
                    review_repo.save(
                        ReviewRecord(
                            spheroidization_record_id=rid,
                            review_result=0 if rng.random() < 0.8 else 1,
                            reviewer=rng.choice(REVIEWERS),
                        )
                    )
                    review_count += 1
        done += batch
        if done % 10000 == 0:
            print(f"  已生成 {done}/{rows}")

    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()

    elapsed = time.monotonic() - t0
    size_mb = db_path.stat().st_size / 1024 / 1024
    print(f"生成完成：{rows} 条记录，用时 {elapsed:.1f}s，库体积 {size_mb:.1f} MB（不含图片）")
    dist = "、".join(f"类型{t}:{type_counts[t]}" for t in sorted(type_counts))
    print(f"  分布：{dist}")
    print(f"  温度记录：{temp_count}（{temp_count / rows:.1%}），分段：{seg_count}，复核：{review_count}，已处置：{processed_count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成性能压测数据")
    parser.add_argument("--db", default="/tmp/perf/spheroidization.db", help="目标 SQLite 库路径")
    parser.add_argument("--rows", type=int, default=50000, help="生成记录条数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()
    if args.rows <= 0:
        print("rows 必须为正数")
        return 1
    generate(Path(args.db), args.rows, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
