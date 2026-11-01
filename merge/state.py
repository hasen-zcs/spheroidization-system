"""合并层自己的状态库（merge_state.db）。

跟管理系统的主库完全分开：这里存的是"流水线走到哪了"，
不是业务数据。丢掉它最坏的结果是重扫一遍文件（靠指纹去重），不会丢业务。

六张表各管一件事：
    cursor        每个追加文件的读取位点（inode + offset）
    light_event   检测出来的亮光，等配进线
    plc_event     喂丝事件，等配亮光
    button_event  按钮时刻，用来定锚点
    temp_event    测温读数，占用制，一条只能用一次
    pending_upload 已组包、还没传成功的请求体 ← 进程被杀也不丢的关键
    delivered     传成功过的幂等键（本地第二道闸）
    dead_letter   4xx / 409 这类重试也没用的，落表等人工

数据量大不了：一天 300 炉，一年的死信也就几万行。
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS cursor (
    path TEXT PRIMARY KEY,
    inode INTEGER NOT NULL,
    offset INTEGER NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS light_event (
    fp TEXT PRIMARY KEY,              -- 内容指纹，重扫时靠它去重
    payload TEXT NOT NULL,            -- 原始 JSON 行
    light_start TEXT NOT NULL,
    light_end TEXT,
    duration REAL,
    reaction_count INTEGER,
    received_at TEXT NOT NULL,
    matched INTEGER NOT NULL DEFAULT 0,
    record_id INTEGER
) STRICT;

CREATE TABLE IF NOT EXISTS plc_event (
    fp TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    feed_start TEXT NOT NULL,
    feed_end TEXT,
    received_at TEXT NOT NULL,
    matched INTEGER NOT NULL DEFAULT 0,
    record_id INTEGER
) STRICT;

CREATE TABLE IF NOT EXISTS button_event (
    fp TEXT PRIMARY KEY,
    pressed_at TEXT NOT NULL,
    received_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS temp_event (
    fp TEXT PRIMARY KEY,
    gun_no INTEGER NOT NULL,
    value REAL NOT NULL,
    measured_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    claimed INTEGER NOT NULL DEFAULT 0,
    claimed_record_id INTEGER
) STRICT;

CREATE TABLE IF NOT EXISTS pending_upload (
    payload_sha TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    body TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_at TEXT NOT NULL,
    last_error TEXT,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS delivered (
    device_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    record_id INTEGER,
    payload_sha TEXT,
    uploaded_at TEXT NOT NULL,
    PRIMARY KEY (device_id, external_id)
) STRICT;

CREATE TABLE IF NOT EXISTS dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT,
    raw TEXT,
    error TEXT,
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_light_unmatched ON light_event(matched, light_start);
CREATE INDEX IF NOT EXISTS idx_plc_unmatched ON plc_event(matched, feed_start);
CREATE INDEX IF NOT EXISTS idx_temp_unclaimed ON temp_event(claimed, measured_at);
CREATE INDEX IF NOT EXISTS idx_pending_due ON pending_upload(next_at);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _after(seconds: float) -> str:
    return (datetime.now() + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


class MergeState:
    """状态库门面。所有写操作都走这里，调用方不直接碰 SQL。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # WAL：读（人工查库）不挡写（服务在跑）
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------------- 游标 ----------------

    def get_cursor(self, path: Path) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT inode, offset FROM cursor WHERE path = ?", (str(path),)
        ).fetchone()

    def set_cursor(self, path: Path, inode: int, offset: int) -> None:
        """只写游标，不提交——调用方跟事件插入放进同一个事务。"""
        self.conn.execute(
            """
            INSERT INTO cursor (path, inode, offset, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                inode = excluded.inode,
                offset = excluded.offset,
                updated_at = excluded.updated_at
            """,
            (str(path), inode, offset, _now()),
        )

    # ---------------- 事件入队 ----------------

    def add_light(self, fp: str, payload: str, start: str, end: str | None,
                  duration: float | None, reaction_count: int | None) -> bool:
        """返回 True 表示新插入，False 表示重复（指纹已存在）。"""
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO light_event
                (fp, payload, light_start, light_end, duration, reaction_count, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (fp, payload, start, end, duration, reaction_count, _now()),
        )
        return cur.rowcount > 0

    def add_plc(self, fp: str, payload: str, feed_start: str, feed_end: str | None) -> bool:
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO plc_event (fp, payload, feed_start, feed_end, received_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (fp, payload, feed_start, feed_end, _now()),
        )
        return cur.rowcount > 0

    def add_button(self, fp: str, pressed_at: str) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO button_event (fp, pressed_at, received_at) VALUES (?, ?, ?)",
            (fp, pressed_at, _now()),
        )
        return cur.rowcount > 0

    def add_temp(self, fp: str, gun_no: int, value: float, measured_at: str) -> bool:
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO temp_event (fp, gun_no, value, measured_at, received_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (fp, gun_no, value, measured_at, _now()),
        )
        return cur.rowcount > 0

    # ---------------- 配对查询 ----------------

    def unmatched_lights(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM light_event WHERE matched = 0 ORDER BY light_start"
        ).fetchall()

    def unmatched_plcs(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM plc_event WHERE matched = 0 ORDER BY feed_start"
        ).fetchall()

    def buttons_between(self, start: str, end: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM button_event WHERE pressed_at BETWEEN ? AND ? ORDER BY pressed_at",
            (start, end),
        ).fetchall()

    def unclaimed_temps(self, gun_nos: Iterable[int]) -> list[sqlite3.Row]:
        guns = list(gun_nos)
        if not guns:
            return []
        marks = ",".join("?" for _ in guns)
        return self.conn.execute(
            f"SELECT * FROM temp_event WHERE claimed = 0 AND gun_no IN ({marks})"
            " ORDER BY measured_at DESC",
            guns,
        ).fetchall()

    def mark_matched(self, light_fp: str, plc_fp: str, record_id: int | None) -> None:
        self.conn.execute(
            "UPDATE light_event SET matched = 1, record_id = ? WHERE fp = ?",
            (record_id, light_fp),
        )
        self.conn.execute(
            "UPDATE plc_event SET matched = 1, record_id = ? WHERE fp = ?",
            (record_id, plc_fp),
        )

    def claim_temp(self, fp: str, record_id: int | None) -> bool:
        """占用制：一条温度只能挂一炉。返回 False 说明已经被别人占了。"""
        cur = self.conn.execute(
            "UPDATE temp_event SET claimed = 1, claimed_record_id = ?"
            " WHERE fp = ? AND claimed = 0",
            (record_id, fp),
        )
        return cur.rowcount == 1

    def purge_unmatched_lights(self, ttl_seconds: float) -> int:
        """清掉太久没配上的亮光（默认 24h），避免状态库无限涨。"""
        cutoff = (datetime.now() - timedelta(seconds=ttl_seconds)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        cur = self.conn.execute(
            "DELETE FROM light_event WHERE matched = 0 AND received_at < ?", (cutoff,)
        )
        return cur.rowcount

    def recent_light_misses(self, limit: int = 20) -> int:
        """最近连续多少条亮光没配上进线（按时间倒序数到第一条配上的为止）。"""
        rows = self.conn.execute(
            "SELECT matched FROM light_event ORDER BY light_start DESC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        streak = 0
        for row in rows:
            if row["matched"]:
                break
            streak += 1
        return streak

    # ---------------- 上传队列 ----------------

    def enqueue_upload(self, sha: str, device_id: str, external_id: str, body: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO pending_upload
                (payload_sha, device_id, external_id, body, attempts, next_at, created_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (sha, device_id, external_id, body, _now(), _now()),
        )

    def due_uploads(self, limit: int = 50) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM pending_upload WHERE next_at <= ? ORDER BY next_at LIMIT ?",
            (_now(), limit),
        ).fetchall()

    def is_delivered(self, device_id: str, external_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM delivered WHERE device_id = ? AND external_id = ?",
            (device_id, external_id),
        ).fetchone()
        return row is not None

    def mark_delivered(self, sha: str, device_id: str, external_id: str,
                       record_id: int | None) -> None:
        self.conn.execute(
            "DELETE FROM pending_upload WHERE payload_sha = ?", (sha,)
        )
        self.conn.execute(
            """
            INSERT INTO delivered (device_id, external_id, record_id, payload_sha, uploaded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(device_id, external_id) DO UPDATE SET
                record_id = excluded.record_id,
                payload_sha = excluded.payload_sha,
                uploaded_at = excluded.uploaded_at
            """,
            (device_id, external_id, record_id, sha, _now()),
        )

    def retry_later(self, sha: str, error: str, delay: float) -> int:
        cur = self.conn.execute(
            "UPDATE pending_upload SET attempts = attempts + 1, next_at = ?, last_error = ?"
            " WHERE payload_sha = ?",
            (_after(delay), error, sha),
        )
        row = self.conn.execute(
            "SELECT attempts FROM pending_upload WHERE payload_sha = ?", (sha,)
        ).fetchone()
        return row["attempts"] if row else 0

    def dead_letter(self, sha: str, source: str, external_id: str, raw: str,
                    error: str) -> None:
        self.conn.execute(
            "INSERT INTO dead_letter (source, external_id, raw, error, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (source, external_id, raw, error, _now()),
        )
        self.conn.execute("DELETE FROM pending_upload WHERE payload_sha = ?", (sha,))

    def pending_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM pending_upload").fetchone()[0]

    def dead_letter_rows(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM dead_letter ORDER BY id").fetchall()

    def clear_dead_letter(self, ids: Iterable[int]) -> None:
        ids = list(ids)
        if not ids:
            return
        marks = ",".join("?" for _ in ids)
        self.conn.execute(f"DELETE FROM dead_letter WHERE id IN ({marks})", ids)

    # ---------------- 事务 ----------------

    def commit(self) -> None:
        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        return False
