from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class StandardApplication:
    """当前应用标准状态。"""

    standard_record_id: int
    applied_at: str
    applied_by: str | None = None


class StandardApplicationState(ABC):
    """标准应用状态的持久化抽象。"""

    @abstractmethod
    def load(self) -> StandardApplication | None:
        """读取当前应用状态，不存在或损坏时返回 None。"""
        ...

    @abstractmethod
    def save(self, application: StandardApplication) -> None:
        """保存当前应用状态。"""
        ...
