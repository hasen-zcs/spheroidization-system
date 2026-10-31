"""
SQLite 版仓储实现，对应 domain 层的抽象接口。

    SpheroidizationRepository    -> SqliteSpheroidizationRepository
    StandardRepository           -> SqliteStandardRepository
    ReviewRepository             -> SqliteReviewRepository
    TemperatureRepository        -> SqliteTemperatureRepository
    StandardSwitchLogRepository  -> SqliteStandardSwitchLogRepository
    UserAccountRepository        -> SqliteUserRepository
    UserPermissionRepository     -> SqliteUserPermissionRepository

UseCase 只认抽象接口，调它们的写法跟内存实现对得上。

连接由调用方通过构造函数注入，本文件不建连接也不建表，
只管"给我连接，我做增改查"。

实体字段名和列名一一对应，所以查询结果可以直接 XxxRecord(**dict(row)) 转实体。
类型上不做任何转换：时间是 "2026-09-05 08:30:15" 字符串，是否直接存 0 / 1 整数。

主键由数据库自增分配（三张表都是 INTEGER PRIMARY KEY AUTOINCREMENT），
所以插入语句里不写主键列，插完读 cursor.lastrowid 回填到实体上。
"""

import sqlite3
from datetime import datetime
from typing import Iterable, List, Optional

from app.core.exceptions import BusinessException
from app.domain.review.entities import ReviewRecord
from app.domain.review.repositories import ReviewRepository
from app.domain.spheroidization.entities import SpheroidizationRecord
from app.domain.spheroidization.repositories import SpheroidizationRepository
from app.domain.standard.entities import StandardRecord
from app.domain.standard.repositories import StandardRepository
from app.domain.standard.switchlog_entities import StandardSwitchLog
from app.domain.standard.switchlog_repositories import StandardSwitchLogRepository
from app.domain.temperature.entities import TemperatureRecord
from app.domain.temperature.repositories import TemperatureRepository
from app.domain.user.entities import UserAccount
from app.domain.user.repositories import UserAccountRepository, UserPermissionRepository


def _now() -> str:
    """当前时间，格式 "2026-09-05 08:30:15"，跟实体字段类型保持一致。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SqliteSpheroidizationRepository(SpheroidizationRepository):
    """球化检测记录仓储实现，对应表 SpheroidizationRecord。"""

    _table_name = "SpheroidizationRecord"
    _pk_column = "spheroidization_record_id"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def _to_entity(row: sqlite3.Row) -> SpheroidizationRecord:
        """
        查询结果一行转实体。

        能直接 **dict(row) 是因为列名和字段名完全一致。
        表上加了新列而实体没跟上时，这里会立刻 TypeError 报出来，不会被静默忽略。
        """
        return SpheroidizationRecord(**dict(row))

    @staticmethod
    def _where_clause(
        abnormal: bool | None = None,
        processed: bool | None = None,
    ) -> tuple[str, list[int]]:
        conditions: list[str] = []
        params: list[int] = []
        if abnormal is not None:
            if abnormal:
                conditions.append("spheroidization_abnormal = 1")
            else:
                conditions.append(
                    "(spheroidization_abnormal = 0 "
                    "OR spheroidization_abnormal IS NULL)"
                )
        if processed is not None:
            conditions.append("processed = ?")
            params.append(1 if processed else 0)
        if not conditions:
            return "", params
        return " WHERE " + " AND ".join(conditions), params

    def _reload_by_id(self, record_id: int) -> SpheroidizationRecord:
        """按主键从库里读回一条。"""
        row = self._conn.execute(
            f"SELECT * FROM {self._table_name} WHERE {self._pk_column} = ?",
            (record_id,),
        ).fetchone()
        return self._to_entity(row)

    def save(self, record: SpheroidizationRecord) -> SpheroidizationRecord:
        """新增一条记录，读回数据库分配的主键后返回。"""
        with self._conn:
            # 主键列不写进 INSERT，交给数据库自增分配
            cursor = self._conn.execute(
                f"""
                INSERT INTO {self._table_name} (
                    standard_record_id,
                    detection_time, 
                    spheroidization_start_time,
                    spheroidization_end_time, 
                    actual_spheroidization_time,
                    standard_spheroidization_time, 
                    spheroidization_abnormal,
                    abnormal_type, 
                    abnormal_reason,
                    processed, processed_at, 
                    processed_by,
                    spheroidization_wire_entry_start_time,
                    spheroidization_wire_entry_end_time,
                    spheroidization_wire_entry_total_duration,
                    spheroidization_weight, 
                    spheroidization_image
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.standard_record_id,
                    record.detection_time,
                    record.spheroidization_start_time,
                    record.spheroidization_end_time,
                    record.actual_spheroidization_time,
                    record.standard_spheroidization_time,
                    record.spheroidization_abnormal,
                    record.abnormal_type,
                    record.abnormal_reason,
                    record.processed,
                    record.processed_at,
                    record.processed_by,
                    record.spheroidization_wire_entry_start_time,
                    record.spheroidization_wire_entry_end_time,
                    record.spheroidization_wire_entry_total_duration,
                    record.spheroidization_weight,
                    record.spheroidization_image,
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
                UPDATE {self._table_name}
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
                 WHERE {self._pk_column} = :record_id
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
                    f"{self._pk_column}={record.spheroidization_record_id}"
                )

            # 读回返回，因为 processed_at 是库里算出来的，
            # 调用方手上那条实体的这个字段还是空的。
            return self._reload_by_id(record.spheroidization_record_id)

    def get_by_id(self, record_id: int) -> Optional[SpheroidizationRecord]:
        """按主键查单条，查不到返回 None。"""
        row = self._conn.execute(
            f"SELECT * FROM {self._table_name} WHERE {self._pk_column} = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return self._to_entity(row)

    def list_all(self) -> List[SpheroidizationRecord]:
        """查全部记录，无数据返回空列表。"""
        rows = self._conn.execute(
            f"SELECT * FROM {self._table_name} ORDER BY {self._pk_column}"
        ).fetchall()
        return [self._to_entity(row) for row in rows]

    def list_abnormal(self) -> List[SpheroidizationRecord]:
        """查异常记录（spheroidization_abnormal = 1），无数据返回空列表。

        该字段可为空，SQL 里 NULL = 1 不成立，空值自然被排除，
        正好符合"没判定过就不算异常"，不用额外写 IS NOT NULL。
        """
        rows = self._conn.execute(
            f"""
            SELECT * FROM {self._table_name}
             WHERE spheroidization_abnormal = 1
             ORDER BY {self._pk_column}
            """
        ).fetchall()
        return [self._to_entity(row) for row in rows]

    def list_page(
        self,
        offset: int,
        limit: int,
        abnormal: bool | None = None,
        processed: bool | None = None,
    ) -> List[SpheroidizationRecord]:
        where, params = self._where_clause(abnormal, processed)
        rows = self._conn.execute(
            f"""
            SELECT * FROM {self._table_name}{where}
            ORDER BY {self._pk_column} DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
        return [self._to_entity(row) for row in rows]

    def count(
        self,
        abnormal: bool | None = None,
        processed: bool | None = None,
    ) -> int:
        where, params = self._where_clause(abnormal, processed)
        row = self._conn.execute(
            f"SELECT COUNT(*) FROM {self._table_name}{where}",
            params,
        ).fetchone()
        return int(row[0])


class SqliteStandardRepository(StandardRepository):
    """
    检测标准仓储实现，对应表 StandardRecord。

    没有 update / delete：标准表纯追加，
    新标准创建后自动成为当前标准，旧标准一律不动。
    """

    _table_name = "StandardRecord"
    _pk_column = "standard_record_id"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def _to_entity(row: sqlite3.Row) -> StandardRecord:
        """查询结果一行转实体。"""
        return StandardRecord(**dict(row))

    def save(self, standard: StandardRecord) -> StandardRecord:
        """新增一条标准，读回主键并生成创建时间后返回。只增不改。"""
        with self._conn:
            standard.created_at = _now()
            # 主键列不写进 INSERT，交给数据库自增分配
            cursor = self._conn.execute(
                f"""
                INSERT INTO {self._table_name} (
                    standard_spheroidization_time,
                    standard_spheroidization_time_upper,
                    standard_spheroidization_time_lower,
                    weighing_standard,
                    created_at, created_by, remark
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    standard.standard_spheroidization_time,
                    standard.standard_spheroidization_time_upper,
                    standard.standard_spheroidization_time_lower,
                    standard.weighing_standard,
                    standard.created_at,
                    standard.created_by,
                    standard.remark,
                ),
            )
            standard.standard_record_id = cursor.lastrowid
        return standard

    def get_by_id(self, standard_id: int) -> Optional[StandardRecord]:
        row = self._conn.execute(
            f"SELECT * FROM {self._table_name} WHERE {self._pk_column} = ?",
            (standard_id,),
        ).fetchone()
        if row is None:
            return None
        return self._to_entity(row)

    def get_current(self) -> Optional[StandardRecord]:
        """查回退标准 = 主键最大的那条，一条都没有时返回 None。

        新标准主键一定比旧的大，所以倒序取第一条就是最新的。
        标准表纯追加从不回头改，这个前提永远成立，
        应用层优先读取 active_standard.json；只有文件缺失或无效时才使用本条回退。
        """
        row = self._conn.execute(
            f"SELECT * FROM {self._table_name} ORDER BY {self._pk_column} DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return self._to_entity(row)

    def get_history(self) -> List[StandardRecord]:
        """查全部标准，含当前和历史，无数据返回空列表。"""
        rows = self._conn.execute(
            f"SELECT * FROM {self._table_name} ORDER BY {self._pk_column}"
        ).fetchall()
        return [self._to_entity(row) for row in rows]


class SqliteReviewRepository(ReviewRepository):
    """
    人工复核记录仓储实现，对应表 ReviewRecord。

    没有 update / delete：复核记录纯追加。
    """

    _table_name = "ReviewRecord"
    _pk_column = "review_record_id"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def _to_entity(row: sqlite3.Row) -> ReviewRecord:
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
                INSERT INTO {self._table_name} (
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
            SELECT * FROM {self._table_name}
             WHERE spheroidization_record_id = ?
             ORDER BY {self._pk_column}
            """,
            (spheroid_id,),
        ).fetchall()
        return [self._to_entity(row) for row in rows]

    def get_latest_results(self, spheroid_ids: list[int]) -> dict[int, int]:
        if not spheroid_ids:
            return {}

        placeholders = ", ".join("?" for _ in spheroid_ids)
        rows = self._conn.execute(
            f"""
            SELECT review.spheroidization_record_id, review.review_result
              FROM {self._table_name} AS review
              JOIN (
                    SELECT spheroidization_record_id,
                           MAX(review_record_id) AS latest_review_id
                      FROM {self._table_name}
                     WHERE spheroidization_record_id IN ({placeholders})
                     GROUP BY spheroidization_record_id
              ) AS latest
                ON review.review_record_id = latest.latest_review_id
            """,
            spheroid_ids,
        ).fetchall()
        return {
            int(row["spheroidization_record_id"]): int(row["review_result"])
            for row in rows
        }


class SqliteTemperatureRepository(TemperatureRepository):
    """
    测温枪读数仓储实现，对应表 TemperatureRecord。

    没有 update / delete：温度是测量事实，不改不删。
    attach_to_record() 是唯一会写已有行的入口，它动的只是关联列。
    """

    _table_name = "TemperatureRecord"
    _pk_column = "temperature_record_id"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def _to_entity(row: sqlite3.Row) -> TemperatureRecord:
        """查询结果一行转实体。列名和字段名必须完全一致。"""
        return TemperatureRecord(**dict(row))

    def save(self, record: TemperatureRecord) -> TemperatureRecord:
        """新增一条测温读数，读回主键并生成入库时间后返回。"""
        with self._conn:
            if record.created_at is None:
                record.created_at = _now()
            cursor = self._conn.execute(
                f"""
                INSERT INTO {self._table_name} (
                    gun_no, 
                    temperature, 
                    measured_at,
                    spheroidization_record_id, 
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.gun_no,
                    record.temperature,
                    record.measured_at,
                    record.spheroidization_record_id,
                    record.created_at,
                ),
            )
            record.temperature_record_id = cursor.lastrowid
        return record

    def get_by_id(self, record_id: int) -> Optional[TemperatureRecord]:
        row = self._conn.execute(
            f"SELECT * FROM {self._table_name} WHERE {self._pk_column} = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return self._to_entity(row)

    def list_by_record_ids(self, ids: list[int]) -> List[TemperatureRecord]:
        """一次查出挂在这几条球化记录上的全部温度。

        空列表直接返回：空集拼出来的 IN () 是语法错误，
        这个边界交给实现方挡掉，调用方不用写判断。
        """
        if not ids:
            return []

        placeholders = ", ".join("?" for _ in ids)
        # 按测温时刻正序：调用方用字典推导收结果，同一记录有多条时
        # 后写进去的覆盖先写进去的，于是最终留下的是最新那条。
        # 主键做第二排序键，保证同一时刻的两条顺序稳定、结果可复现。
        rows = self._conn.execute(
            f"""
            SELECT * FROM {self._table_name}
             WHERE spheroidization_record_id IN ({placeholders})
             ORDER BY measured_at ASC, {self._pk_column} ASC
            """,
            ids,
        ).fetchall()
        return [self._to_entity(row) for row in rows]

    def attach_to_record(
        self,
        temperature_id: int,
        spheroidization_record_id: int,
    ) -> None:
        """把一条温度读数挂到指定球化记录上。

        影响 0 行说明温度记录不存在，报错而不是装作挂上了——
        否则调用方会以为关联成功，页面上了还是查不到。
        """
        with self._conn:
            cursor = self._conn.execute(
                f"""
                UPDATE {self._table_name}
                   SET spheroidization_record_id = ?
                 WHERE {self._pk_column} = ?
                """,
                (spheroidization_record_id, temperature_id),
            )
            if cursor.rowcount == 0:
                raise BusinessException(
                    f"要挂接的温度记录不存在：{self._pk_column}={temperature_id}"
                )


class SqliteStandardSwitchLogRepository(StandardSwitchLogRepository):
    """标准切换日志仓储实现，对应表 StandardSwitchLogs（表名是复数）。"""

    _table_name = "StandardSwitchLogs"
    _pk_column = "switch_log_id"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def _to_entity(row: sqlite3.Row) -> StandardSwitchLog:
        """查询结果一行转实体。"""
        return StandardSwitchLog(**dict(row))

    def save(self, log: StandardSwitchLog) -> StandardSwitchLog:
        """新增一条切换日志，读回主键后返回。

        switched_at / operated_by / reason 都由应用层填好再传进来：
        这三个值要和"这次操作"绑定，不能让仓储自己取当前时间。
        """
        with self._conn:
            cursor = self._conn.execute(
                f"""
                INSERT INTO {self._table_name} (
                    switched_at, from_standard_record_id,
                    to_standard_record_id, operated_by, reason
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    log.switched_at,
                    log.from_standard_record_id,
                    log.to_standard_record_id,
                    log.operated_by,
                    log.reason,
                ),
            )
            log.switch_log_id = cursor.lastrowid
        return log

    def list_all(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> List[StandardSwitchLog]:
        """分页查切换日志，倒序返回，最新的在最前面。"""
        rows = self._conn.execute(
            f"""
            SELECT * FROM {self._table_name}
             ORDER BY {self._pk_column} DESC
             LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [self._to_entity(row) for row in rows]


class SqliteUserRepository(UserAccountRepository):
    """登录账号仓储实现，对应表 UserAccount。

    不提供删除：账号只停用不删，否则历史记录里的操作人就断链了。
    """

    _table_name = "UserAccount"
    _pk_column = "user_id"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def _to_entity(row: sqlite3.Row) -> UserAccount:
        """查询结果一行转实体。"""
        return UserAccount(**dict(row))

    class SqliteUserRepository(UserAccountRepository):
     _table_name = "UserAccount"

    def save(self, user: UserAccount) -> UserAccount:
        if user.created_at is None:
            user.created_at = _now()

        try:
            with self._conn:
                cursor = self._conn.execute(
                    f"""
                    INSERT INTO {self._table_name} (
                        username,
                        password_hash,
                        enabled,
                        is_admin,
                        created_by,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user.username,
                        user.password_hash,
                        user.enabled,
                        user.is_admin,
                        user.created_by,
                        user.created_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if (
                getattr(exc, "sqlite_errorname", None)
                == "SQLITE_CONSTRAINT_UNIQUE"
                and str(exc)
                == f"UNIQUE constraint failed: {self._table_name}.username"
            ):
                raise BusinessException("用户名已存在") from exc

            raise

        user.user_id = cursor.lastrowid
        return user

    def get_by_username(self, username: str) -> Optional[UserAccount]:
        """按登录名查账号，查不到返回 None。

        用户名有 UNIQUE 约束，理论上最多一条；这里按规范只取一条，
        不写 fetchall，查不到和查出多条都不该在这一层分叉。
        """
        row = self._conn.execute(
            f"SELECT * FROM {self._table_name} WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return self._to_entity(row)

    def get_by_id(self, user_id: int) -> Optional[UserAccount]:
        row = self._conn.execute(
            f"SELECT * FROM {self._table_name} WHERE {self._pk_column} = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return self._to_entity(row)

    def list_all(self) -> List[UserAccount]:
        """查全部账号。用户量小，不分页。"""
        rows = self._conn.execute(
            f"SELECT * FROM {self._table_name} ORDER BY {self._pk_column}"
        ).fetchall()
        return [self._to_entity(row) for row in rows]

    def set_enabled(self, user_id: int, enabled: int) -> None:
        """启用 / 停用账号。影响 0 行说明账号不存在，报错。"""
        with self._conn:
            cursor = self._conn.execute(
                f"UPDATE {self._table_name} SET enabled = ? WHERE {self._pk_column} = ?",
                (enabled, user_id),
            )
            if cursor.rowcount == 0:
                raise BusinessException(f"要修改的账号不存在：{self._pk_column}={user_id}")

    def update_password(self, user_id: int, password_hash: str) -> None:
        """改密码。传进来的已经是哈希，这里不再哈希一遍。"""
        with self._conn:
            cursor = self._conn.execute(
                f"""
                UPDATE {self._table_name}
                   SET password_hash = ?
                 WHERE {self._pk_column} = ?
                """,
                (password_hash, user_id),
            )
            if cursor.rowcount == 0:
                raise BusinessException(f"要改密码的账号不存在：{self._pk_column}={user_id}")


class SqliteUserPermissionRepository(UserPermissionRepository):
    """用户权限仓储实现，对应表 UserPermission。

    一行一个权限点，(user_id, permission_key) 是联合主键，
    所以同一用户同一权限天然只有一条，grant 用 INSERT OR IGNORE 就够。
    """

    _table_name = "UserPermission"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list_keys_by_user(self, user_id: int) -> set[str]:
        rows = self._conn.execute(
            f"SELECT permission_key FROM {self._table_name} WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {row["permission_key"] for row in rows}

    def grant(self, user_id: int, permission_key: str) -> None:
        """加一个权限点。已经有了就忽略，不报错。

        用户管理页每次保存都是整组提交，里面必然混着已有的权限点，
        这里报错的话调用方还得先查一遍哪些已经有了。
        """
        with self._conn:
            self._conn.execute(
                f"""
                INSERT OR IGNORE INTO {self._table_name}
                    (user_id, permission_key)
                VALUES (?, ?)
                """,
                (user_id, permission_key),
            )

    def revoke(self, user_id: int, permission_key: str) -> None:
        """去掉一个权限点。本来就没有时什么也不做。"""
        with self._conn:
            self._conn.execute(
                f"""
                DELETE FROM {self._table_name}
                 WHERE user_id = ? AND permission_key = ?
                """,
                (user_id, permission_key),
            )

    def replace_all(
        self,
        user_id: int,
        permission_keys: Iterable[str],
    ) -> None:
        """整体覆盖某个用户的权限：先删干净再插新的。

        删和插必须在同一个事务里（with self._conn: 已经保证了），
        中途插失败会整体回滚。分开提交的话，一旦插入失败就会留下
        "权限被删光、新的没插上"的空权限状态，等于把这人的权限清零了。
        """
        keys = list(permission_keys)
        with self._conn:
            self._conn.execute(
                f"DELETE FROM {self._table_name} WHERE user_id = ?",
                (user_id,),
            )
            self._conn.executemany(
                f"""
                INSERT INTO {self._table_name} (user_id, permission_key)
                VALUES (?, ?)
                """,
                [(user_id, key) for key in keys],
            )
