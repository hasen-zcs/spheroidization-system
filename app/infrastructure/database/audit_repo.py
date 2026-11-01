"""SQLite 版审计日志仓储实现，对应表 AuditLog。"""

import sqlite3
from datetime import datetime

from app.domain.audit.entities import AuditLog
from app.domain.audit.repositories import AuditRepository


def _now() -> str:
    """当前时间，格式 "2026-09-05 08:30:15"，跟库里其他表保持一致。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SqliteAuditRepository(AuditRepository):
    """审计日志仓储实现，对应表 AuditLog。只增不删。"""

    _table_name = "AuditLog"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @staticmethod
    def _to_entity(row: sqlite3.Row) -> AuditLog:
        # 列名和字段名完全一致，直接 **dict(row)；表加列实体没跟上会立刻报错
        return AuditLog(**dict(row))

    def add(self, audit: AuditLog) -> AuditLog:
        """新增一条审计记录，读回数据库分配的主键后返回。自己提交事务。

        审计写入独立于业务事务：业务提交之后才调这里，
        这里失败只影响留痕，不影响已经落库的业务数据。
        """
        with self._conn:
            audit.created_at = audit.created_at or _now()
            # 主键列不写进 INSERT，交给数据库自增分配
            cursor = self._conn.execute(
                f"""
                INSERT INTO {self._table_name} (
                    actor, action, target_type, target_id, detail, ip, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit.actor,
                    audit.action,
                    audit.target_type,
                    audit.target_id,
                    audit.detail,
                    audit.ip,
                    audit.created_at,
                ),
            )
            audit.audit_id = cursor.lastrowid
            return audit

    def list_records(
        self,
        actor: str | None = None,
        action: str | None = None,
        start: str | None = None,
        end: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """按条件分页查。created_at 是固定格式字符串，字典序比较即时间比较。"""
        conditions: list[str] = []
        params: list = []
        if actor is not None:
            conditions.append("actor = ?")
            params.append(actor)
        if action is not None:
            conditions.append("action = ?")
            params.append(action)
        if start is not None:
            conditions.append("created_at >= ?")
            params.append(start)
        if end is not None:
            conditions.append("created_at <= ?")
            params.append(end)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        total = self._conn.execute(
            f"SELECT COUNT(*) FROM {self._table_name}{where}", params
        ).fetchone()[0]

        rows = self._conn.execute(
            f"""
            SELECT * FROM {self._table_name}{where}
            ORDER BY created_at DESC, audit_id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
        return [self._to_entity(row) for row in rows], total
