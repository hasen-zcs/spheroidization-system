"""分段明细 + 上传台账的 SQLite 实现。

**本文件的写方法一律不提交事务**：调用方用 `with conn:` 包住整段写入，
中途任何一步失败都整体回滚（见 CreateSpheroidizationUseCase）。

浮点统一 round 到 3 位再入库：判定侧和显示侧都是 3 位，
库里存 102.47999999999999 这种噪声，查询/导出时还得再洗一遍。
"""

import sqlite3
from typing import List, Optional, Sequence

from app.domain.flash.entities import FlashSegment, UploadLedgerEntry
from app.domain.flash.repositories import (
    FlashSegmentRepository,
    UploadLedgerRepository,
)


def _r3(value: float) -> float:
    return round(float(value), 3)


class SqliteFlashSegmentRepository(FlashSegmentRepository):
    """对应表 FlashSegment。写完由调用方提交。"""

    _table_name = "FlashSegment"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def save_many_no_commit(
        self, record_id: int, segments: Sequence[FlashSegment]
    ) -> None:
        if not segments:
            return
        self._conn.executemany(
            f"""
            INSERT INTO {self._table_name} (
                spheroidization_record_id, seg_index,
                start_offset, end_offset, gap_before, duration
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record_id,
                    int(seg.seg_index),
                    _r3(seg.start_offset),
                    _r3(seg.end_offset),
                    None if seg.gap_before is None else _r3(seg.gap_before),
                    _r3(seg.duration),
                )
                for seg in segments
            ],
        )

    def list_by_record(self, record_id: int) -> List[FlashSegment]:
        rows = self._conn.execute(
            f"""
            SELECT segment_id, spheroidization_record_id, seg_index,
                   start_offset, end_offset, gap_before, duration
              FROM {self._table_name}
             WHERE spheroidization_record_id = ?
             ORDER BY seg_index
            """,
            (record_id,),
        ).fetchall()
        return [
            FlashSegment(
                seg_index=row["seg_index"],
                start_offset=row["start_offset"],
                end_offset=row["end_offset"],
                gap_before=row["gap_before"],
                duration=row["duration"],
                segment_id=row["segment_id"],
                spheroidization_record_id=row["spheroidization_record_id"],
            )
            for row in rows
        ]


class SqliteUploadLedgerRepository(UploadLedgerRepository):
    """对应表 UploadLedger。写完由调用方提交。"""

    _table_name = "UploadLedger"

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def find(self, device_id: str, external_id: str) -> Optional[UploadLedgerEntry]:
        row = self._conn.execute(
            f"""
            SELECT ledger_id, device_id, external_id, record_id, payload_sha, created_at
              FROM {self._table_name}
             WHERE device_id = ? AND external_id = ?
            """,
            (device_id, external_id),
        ).fetchone()
        if row is None:
            return None
        return UploadLedgerEntry(
            device_id=row["device_id"],
            external_id=row["external_id"],
            record_id=row["record_id"],
            payload_sha=row["payload_sha"],
            created_at=row["created_at"],
            ledger_id=row["ledger_id"],
        )

    def add_no_commit(self, entry: UploadLedgerEntry) -> UploadLedgerEntry:
        cursor = self._conn.execute(
            f"""
            INSERT INTO {self._table_name}
                (device_id, external_id, record_id, payload_sha, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entry.device_id,
                entry.external_id,
                entry.record_id,
                entry.payload_sha,
                entry.created_at,
            ),
        )
        entry.ledger_id = cursor.lastrowid
        return entry
