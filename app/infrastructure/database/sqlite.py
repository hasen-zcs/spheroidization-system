"""
SQLite 版仓储实现，对应 domain 层的三个抽象接口。

    SpheroidizationRepository -> SqliteSpheroidizationRepository
    StandardRepository        -> SqliteStandardRepository
    ReviewRepository          -> SqliteReviewRepository

跟 memory.py 是同一组接口的两个实现，UseCase 调它们的写法一样。

连接由调用方通过构造函数注入，本文件不建连接也不建表，
只管"给我连接，我做增改查"。

实体字段名和列名一一对应，所以查询结果可以直接 XxxRecord(**dict(row)) 转实体。
类型上不做任何转换：时间是 "2026-09-05 08:30:15" 字符串，是否直接存 0 / 1 整数。

主键由数据库自增分配（三张表都是 INTEGER PRIMARY KEY AUTOINCREMENT），
所以插入语句里不写主键列，插完读 cursor.lastrowid 回填到实体上。
"""

import sqlite3
from datetime import datetime
from typing import List, Optional

from app.core.exceptions import BusinessException
from app.domain.review.entities import ReviewRecord
from app.domain.review.repositories import ReviewRepository
from app.domain.spheroidization.entities import SpheroidizationRecord
from app.domain.spheroidization.repositories import SpheroidizationRepository
from app.domain.standard.entities import StandardRecord
from app.domain.standard.repositories import StandardRepository


def _now() -> str:
    """当前时间，格式 "2026-09-05 08:30:15"，跟实体字段类型保持一致。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SqliteSpheroidizationRepository(SpheroidizationRepository):
    """球化检测记录仓储实现，对应表 SpheroidizationRecord。"""

    _表名 = "SpheroidizationRecord"
    _主键列 = "spheroidization_record_id"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def _转实体(row: sqlite3.Row) -> SpheroidizationRecord:
        """
        查询结果一行转实体。

        能直接 **dict(row) 是因为列名和字段名完全一致。
        表上加了新列而实体没跟上时，这里会立刻 TypeError 报出来，不会被静默忽略。
        """
        return SpheroidizationRecord(**dict(row))

    def _按主键读回(self, record_id: int) -> SpheroidizationRecord:
        """按主键从库里读回一条。"""
        row = self._conn.execute(
            f"SELECT * FROM {self._表名} WHERE {self._主键列} = ?",
            (record_id,),
        ).fetchone()
        return self._转实体(row)

    def save(self, record: SpheroidizationRecord) -> SpheroidizationRecord:
        """新增一条记录，读回数据库分配的主键后返回。"""
        with self._conn:
            # 主键列不写进 INSERT，交给数据库自增分配
            cursor = self._conn.execute(
                f"""
                INSERT INTO {self._表名} (
                    standard_record_id,
                    detection_time, spheroidization_start_time,
                    spheroidization_end_time, actual_spheroidization_time,
                    standard_spheroidization_time, spheroidization_abnormal,
                    processed, processed_at, processed_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.standard_record_id,
                    record.detection_time,
                    record.spheroidization_start_time,
                    record.spheroidization_end_time,
                    record.actual_spheroidization_time,
                    record.standard_spheroidization_time,
                    record.spheroidization_abnormal,
                    record.processed,
                    record.processed_at,
                    record.processed_by,
                ),
            )
            # lastrowid 就是刚插进去那行的主键
            record.spheroidization_record_id = cursor.lastrowid
        return record

    def update(self, record: SpheroidizationRecord) -> SpheroidizationRecord:
        """
        更新人工处理状态，对应 UPDATE。

        只更新 processed / processed_by / processed_at 三个字段。
        机器检测事实连 SET 子句都没进，想改也改不了。
        """
        with self._conn:
            cursor = self._conn.execute(
                f"""
                UPDATE {self._表名}
                   SET processed    = :processed,
                       processed_by = :processed_by,
                       -- 处理时间由实现方生成：只在"未处理 -> 已处理"时写，
                       -- 已经是已处理就保留原值。
                       -- 写成 CASE 是为了让判断和写入在同一条语句里完成，
                       -- 不会被别的操作插进来，也不用先查一次再写一次。
                       processed_at = CASE
                                        WHEN processed = 0 AND :processed = 1
                                            THEN :now
                                        ELSE processed_at
                                      END
                 WHERE {self._主键列} = :record_id
                """,
                {
                    "processed": record.processed,
                    "processed_by": record.processed_by,
                    "now": _now(),
                    "record_id": record.spheroidization_record_id,
                },
            )

            # 影响 0 行说明记录不存在，报错而不是装作更新成功
            if cursor.rowcount == 0:
                raise BusinessException(
                    f"要更新的球化检测记录不存在："
                    f"{self._主键列}={record.spheroidization_record_id}"
                )

            # 读回返回，因为 processed_at 是库里算出来的，
            # 调用方手上那条实体的这个字段还是空的。
            return self._按主键读回(record.spheroidization_record_id)

    def get_by_id(self, record_id: int) -> Optional[SpheroidizationRecord]:
        """按主键查单条，查不到返回 None。"""
        row = self._conn.execute(
            f"SELECT * FROM {self._表名} WHERE {self._主键列} = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return self._转实体(row)

    def list_all(self) -> List[SpheroidizationRecord]:
        """查全部记录，无数据返回空列表。"""
        rows = self._conn.execute(
            f"SELECT * FROM {self._表名} ORDER BY {self._主键列}"
        ).fetchall()
        return [self._转实体(row) for row in rows]

    def list_abnormal(self) -> List[SpheroidizationRecord]:
        """查异常记录（spheroidization_abnormal = 1），无数据返回空列表。

        该字段可为空，SQL 里 NULL = 1 不成立，空值自然被排除，
        正好符合"没判定过就不算异常"，不用额外写 IS NOT NULL。
        """
        rows = self._conn.execute(
            f"""
            SELECT * FROM {self._表名}
             WHERE spheroidization_abnormal = 1
             ORDER BY {self._主键列}
            """
        ).fetchall()
        return [self._转实体(row) for row in rows]


class SqliteStandardRepository(StandardRepository):
    """
    检测标准仓储实现，对应表 StandardRecord。

    没有 update / delete：标准表纯追加，
    新标准创建后自动成为当前标准，旧标准一律不动。
    """

    _表名 = "StandardRecord"
    _主键列 = "standard_record_id"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def _转实体(row: sqlite3.Row) -> StandardRecord:
        """查询结果一行转实体。"""
        return StandardRecord(**dict(row))

    def save(self, standard: StandardRecord) -> StandardRecord:
        """新增一条标准，读回主键并生成创建时间后返回。只增不改。"""
        with self._conn:
            standard.created_at = _now()
            # 主键列不写进 INSERT，交给数据库自增分配
            cursor = self._conn.execute(
                f"""
                INSERT INTO {self._表名} (
                    standard_spheroidization_time,
                    standard_entry_length, weighing_standard,
                    created_at, created_by, remark
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    standard.standard_spheroidization_time,
                    standard.standard_entry_length,
                    standard.weighing_standard,
                    standard.created_at,
                    standard.created_by,
                    standard.remark,
                ),
            )
            standard.standard_record_id = cursor.lastrowid
        return standard

    def get_current(self) -> Optional[StandardRecord]:
        """查当前有效标准 = 主键最大的那条，一条都没有时返回 None。

        新标准主键一定比旧的大，所以倒序取第一条就是最新的。
        标准表纯追加从不回头改，这个前提永远成立，
        不需要额外的"是否生效"标记字段。
        """
        row = self._conn.execute(
            f"SELECT * FROM {self._表名} ORDER BY {self._主键列} DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return self._转实体(row)

    def get_history(self) -> List[StandardRecord]:
        """查全部标准，含当前和历史，无数据返回空列表。"""
        rows = self._conn.execute(
            f"SELECT * FROM {self._表名} ORDER BY {self._主键列}"
        ).fetchall()
        return [self._转实体(row) for row in rows]


class SqliteReviewRepository(ReviewRepository):
    """
    人工复核记录仓储实现，对应表 ReviewRecord。

    没有 update / delete：复核记录纯追加。
    """

    _表名 = "ReviewRecord"
    _主键列 = "review_record_id"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def _转实体(row: sqlite3.Row) -> ReviewRecord:
        """查询结果一行转实体。"""
        return ReviewRecord(**dict(row))

    def save(self, review: ReviewRecord) -> ReviewRecord:
        """新增一条复核记录，读回主键并生成复核时间后返回。

        review_result 直接存 0 / 1 整数，不做字符串转换，
        表上的 CHECK 会拒绝其他值。
        """
        with self._conn:
            review.reviewed_at = _now()
            # 主键列不写进 INSERT，交给数据库自增分配
            cursor = self._conn.execute(
                f"""
                INSERT INTO {self._表名} (
                    spheroidization_record_id,
                    review_result, review_remark, reviewer, reviewed_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    review.spheroidization_record_id,
                    review.review_result,
                    review.review_remark,
                    review.reviewer,
                    review.reviewed_at,
                ),
            )
            review.review_record_id = cursor.lastrowid
        return review

    def list_by_spheroid_id(self, spheroid_id: int) -> List[ReviewRecord]:
        """查某条球化记录的全部复核历史，无记录返回空列表。

        按主键排序就是复核先后顺序。
        """
        rows = self._conn.execute(
            f"""
            SELECT * FROM {self._表名}
             WHERE spheroidization_record_id = ?
             ORDER BY {self._主键列}
            """,
            (spheroid_id,),
        ).fetchall()
        return [self._转实体(row) for row in rows]
