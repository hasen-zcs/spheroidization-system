"""分段明细与上传台账的仓储抽象。

事务约定（与其它仓储不同，重点看）
----------------------------------
这两个仓储的方法 **自己不提交事务**：调用方（用例层）负责开事务，
要么一起成功，要么一起回滚。原因见 CreateSpheroidizationUseCase：
建档、写分段、写台账必须是原子的，中途失败留下半条记录比不写更糟。

其它仓储（球化记录、标准…）沿用老约定，方法内部自带提交。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

from app.domain.flash.entities import FlashSegment, UploadLedgerEntry


class FlashSegmentRepository(ABC):
    @abstractmethod
    def save_many_no_commit(
        self, record_id: int, segments: Sequence[FlashSegment]
    ) -> None:
        """批量写入一条记录的分段。调用方负责事务与回滚。"""
        ...

    @abstractmethod
    def list_by_record(self, record_id: int) -> List[FlashSegment]:
        """按记录主键查分段，按段号升序；没有分段返回空列表。"""
        ...


class UploadLedgerRepository(ABC):
    @abstractmethod
    def find(self, device_id: str, external_id: str) -> Optional[UploadLedgerEntry]:
        """按幂等键查台账，没有返回 None。"""
        ...

    @abstractmethod
    def add_no_commit(self, entry: UploadLedgerEntry) -> UploadLedgerEntry:
        """写一条台账。调用方负责事务；唯一键冲突会抛 sqlite3.IntegrityError。"""
        ...
