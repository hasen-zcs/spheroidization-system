"""报表服务：summary 统计 + CSV 导出行生成器。

数据源唯一准绳是管理库（D-007）：全部直查 SQLite 表
（SpheroidizationRecord / ReviewRecord / TemperatureRecord），
不读任何前端算出来的数、不碰采集侧的 jsonl。

口径说明
--------
- "类型" 一律指 abnormal_type（0 正常 / 1 进站未球化 / 2 进线中断 /
  3 超过标准 / 4 低于标准 / 5 分段多次球化 / 6 未判定）。
  该列可空（机器没给判定），口径里 NULL 归入 0（正常）。
- abnormal_count = 类型 ≠ 0 的记录数（未判定 type=6 也算在内，
  它单列一个 unjudged_count 方便看，但不从异常里剔除）。
- 日期过滤按 detection_time 文本区间，含头含尾。
- 一条记录最多展示"最新"一条复核 / 一条温度，
  与现有列表接口的取法一致（按时间倒序取第一条）。

导出 SELECT 刻意不取 spheroidization_image（BLOB，几十 KB 一张，
1 万条会把内存和带宽全吃光）。
"""

import sqlite3
from typing import Iterator, Sequence

from app.application.reports.stats import (
    build_by_type,
    duration_stats,
    normalize_range,
    rate,
)
from app.core.exceptions import BusinessException

# 导出的记录列表每页取多少条。页内还要带复核和温度两趟查询，
# 1000 条一页在 sqlite 上毫秒级，1 万条就是 10 趟，远够快。
_PAGE_SIZE = 1000

# 主表要导出的列。顺序就是 CSV 里它们的顺序（中间夹着关联出来的列），
# 不要随手加 spheroidization_image。
_EXPORT_COLUMNS = (
    "spheroidization_record_id",
    "detection_time",
    "spheroidization_start_time",
    "spheroidization_end_time",
    "actual_spheroidization_time",
    "abnormal_type",
    "abnormal_reason",
    "processed",
    "spheroidization_wire_entry_start_time",
    "spheroidization_wire_entry_end_time",
    "spheroidization_weight",
)


def _row_tuple(row: sqlite3.Row) -> dict:
    return dict(row)


class ReportsService:
    """报表查询。构造时注入连接（和 Container 里其它仓储同一条）。"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # summary
    # ------------------------------------------------------------------

    def summary(self, start: str | None = None, end: str | None = None) -> dict:
        start_bound, end_bound = self._bounds(start, end)
        where, params = self._where(start_bound, end_bound)

        # 总量 + 异常数 + 未判定数，一条 SQL 出
        row = self._conn.execute(
            f"""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN COALESCE(abnormal_type, 0) <> 0 THEN 1 ELSE 0 END), 0) AS abnormal_count,
                   COALESCE(SUM(CASE WHEN abnormal_type = 6 THEN 1 ELSE 0 END), 0) AS unjudged_count
            FROM SpheroidizationRecord{where}
            """,
            params,
        ).fetchone()
        total, abnormal_count, unjudged_count = int(row["total"]), int(row["abnormal_count"]), int(row["unjudged_count"])

        # 类型分布 0..6
        by_type = build_by_type(
            self._conn.execute(
                f"""
                SELECT COALESCE(abnormal_type, 0) AS type, COUNT(*) AS n
                FROM SpheroidizationRecord{where}
                GROUP BY type
                """,
                params,
            ).fetchall()
        )

        # 球化时长：只取非空，交给纯函数算
        durations = [
            float(value)
            for (value,) in self._conn.execute(
                f"""
                SELECT actual_spheroidization_time
                FROM SpheroidizationRecord
                WHERE actual_spheroidization_time IS NOT NULL{self._tail(where)}
                """,
                params,
            )
        ]

        # 温度覆盖：区间内"至少有一条关联测温记录"的记录数
        covered = int(
            self._conn.execute(
                f"""
                SELECT COUNT(DISTINCT t.spheroidization_record_id)
                FROM TemperatureRecord t
                WHERE t.spheroidization_record_id IN (
                    SELECT spheroidization_record_id FROM SpheroidizationRecord{where}
                )
                """,
                params,
            ).fetchone()[0]
        )
        by_gun = {}
        for gun_row in self._conn.execute(
            f"""
            SELECT t.gun_no, COUNT(*) AS n, AVG(t.temperature) AS avg_t
            FROM TemperatureRecord t
            WHERE t.spheroidization_record_id IN (
                SELECT spheroidization_record_id FROM SpheroidizationRecord{where}
            )
            GROUP BY t.gun_no
            ORDER BY t.gun_no
            """,
            params,
        ):
            by_gun[str(gun_row["gun_no"])] = {
                "count": int(gun_row["n"]),
                "avg": round(float(gun_row["avg_t"]), 2) if gun_row["avg_t"] is not None else None,
            }

        # 按天分布
        by_day = [
            {
                "date": r["day"],
                "total": int(r["total"]),
                "abnormal": int(r["abnormal"]),
            }
            for r in self._conn.execute(
                f"""
                SELECT substr(detection_time, 1, 10) AS day,
                       COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN COALESCE(abnormal_type, 0) <> 0 THEN 1 ELSE 0 END), 0) AS abnormal
                FROM SpheroidizationRecord{where}
                GROUP BY day
                ORDER BY day
                """,
                params,
            )
        ]

        return {
            "total": total,
            "by_type": by_type,
            "abnormal_count": abnormal_count,
            "abnormal_rate": rate(abnormal_count, total),
            "unjudged_count": unjudged_count,
            "duration": duration_stats(durations),
            "temperature": {
                "covered": covered,
                "total": total,
                "coverage_rate": rate(covered, total),
                "by_gun": by_gun,
            },
            "by_day": by_day,
        }

    # ------------------------------------------------------------------
    # export
    # ------------------------------------------------------------------

    def iter_export_rows(
        self,
        start: str | None = None,
        end: str | None = None,
        abnormal_type: int | None = None,
    ) -> Iterator[Sequence[object]]:
        """逐条产出 CSV 行（不含表头，文本化的字段值）。

        生成器：调用方一边拉一边发，1 万条不用整表进内存。
        """
        start_bound, end_bound = self._bounds(start, end)
        where, params = self._where(start_bound, end_bound, abnormal_type)

        columns = ", ".join(_EXPORT_COLUMNS)
        last_id = 0
        while True:
            page = self._conn.execute(
                f"""
                SELECT {columns}
                FROM SpheroidizationRecord
                WHERE spheroidization_record_id > ?{self._tail(where, extra_le=last_id)}
                ORDER BY spheroidization_record_id
                LIMIT ?
                """,
                [last_id, *params, _PAGE_SIZE],
            ).fetchall()
            if not page:
                return
            records = [_row_tuple(row) for row in page]
            reviews = self._latest_reviews([r["spheroidization_record_id"] for r in records])
            temperatures = self._latest_temperatures([r["spheroidization_record_id"] for r in records])
            for record in records:
                yield self._export_row(record, reviews, temperatures)
            last_id = records[-1]["spheroidization_record_id"]
            if len(page) < _PAGE_SIZE:
                return

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _bounds(start: str | None, end: str | None) -> tuple[str | None, str | None]:
        try:
            return normalize_range(start, end)
        except ValueError as exc:
            # 日期写错 / 头尾倒置是参数问题，走统一信封 400，不是 500
            raise BusinessException(str(exc), 400) from exc

    @staticmethod
    def _where(
        start_bound: str | None, end_bound: str | None, type_: int | None = None
    ) -> tuple[str, list]:
        conditions: list[str] = []
        params: list = []
        if start_bound:
            conditions.append("detection_time >= ?")
            params.append(start_bound)
        if end_bound:
            conditions.append("detection_time <= ?")
            params.append(end_bound)
        if type_ is not None:
            conditions.append("COALESCE(abnormal_type, 0) = ?")
            params.append(type_)
        if not conditions:
            return "", params
        return " WHERE " + " AND ".join(conditions), params

    @staticmethod
    def _tail(where: str, extra_le: int | None = None) -> str:
        """把 " WHERE a AND b" 挪到子查询后面用，必要时追加 id 上界。

        keyset 分页里 where 条件要跟在 "id > ?" 之后，
        单独抽出来避免手写第二份拼接逻辑。
        """
        if not where:
            return ""
        return " AND " + where[len(" WHERE "):]

    def _latest_reviews(self, record_ids: list[int]) -> dict[int, int]:
        """这批记录各自的最新复核结果（0/1）。没复核过的不在结果里。

        按复核时间倒序、同时间按主键倒序，Python 侧"先到先得"，
        每条记录留下的就是最新那条——和列表接口的口径一致。
        """
        if not record_ids:
            return {}
        placeholders = ",".join("?" for _ in record_ids)
        rows = self._conn.execute(
            f"""
            SELECT spheroidization_record_id, review_result
            FROM ReviewRecord
            WHERE spheroidization_record_id IN ({placeholders})
            ORDER BY reviewed_at DESC, review_record_id DESC
            """,
            record_ids,
        ).fetchall()
        latest: dict[int, int] = {}
        for row in rows:
            latest.setdefault(row["spheroidization_record_id"], row["review_result"])
        return latest

    def _latest_temperatures(self, record_ids: list[int]) -> dict[int, tuple[float, int]]:
        """这批记录各自的最新一条温度（temperature, gun_no）。"""
        if not record_ids:
            return {}
        placeholders = ",".join("?" for _ in record_ids)
        rows = self._conn.execute(
            f"""
            SELECT spheroidization_record_id, temperature, gun_no
            FROM TemperatureRecord
            WHERE spheroidization_record_id IN ({placeholders})
            ORDER BY measured_at DESC, temperature_record_id DESC
            """,
            record_ids,
        ).fetchall()
        latest: dict[int, tuple[float, int]] = {}
        for row in rows:
            latest.setdefault(
                row["spheroidization_record_id"],
                (row["temperature"], row["gun_no"]),
            )
        return latest

    def _export_row(
        self,
        record: dict,
        reviews: dict[int, int],
        temperatures: dict[int, tuple[float, int]],
    ) -> Sequence[object]:
        """一条记录转成 CSV 一行。None 一律给空串，Excel 里看着干净。"""
        from app.schemas.reports import (
            ABNORMAL_TYPE_LABELS,
            REVIEW_RESULT_LABELS,
        )

        record_id = record["spheroidization_record_id"]
        type_ = record["abnormal_type"] if record["abnormal_type"] is not None else 0
        review_result = reviews.get(record_id)
        temperature = temperatures.get(record_id)
        return [
            record_id,
            record["detection_time"],
            record["spheroidization_start_time"] or "",
            record["spheroidization_end_time"] or "",
            record["actual_spheroidization_time"] if record["actual_spheroidization_time"] is not None else "",
            ABNORMAL_TYPE_LABELS.get(type_, f"未知类型({type_})"),
            record["abnormal_reason"] or "",
            REVIEW_RESULT_LABELS.get(review_result, "") if review_result is not None else "",
            "已处理" if record["processed"] else "未处理",
            record["spheroidization_wire_entry_start_time"] or "",
            record["spheroidization_wire_entry_end_time"] or "",
            record["spheroidization_weight"] if record["spheroidization_weight"] is not None else "",
            temperature[0] if temperature is not None else "",
            temperature[1] if temperature is not None else "",
        ]
