from abc import ABC, abstractmethod

from app.domain.audit.entities import AuditLog


class AuditRepository(ABC):
    """
    审计日志仓储抽象接口。实现由 infrastructure 层提供。

    审计日志只增不改不删：没有 update / delete 方法。
    """

    @abstractmethod
    def add(self, audit: AuditLog) -> AuditLog:
        """
        新增一条审计记录，对应 INSERT。
        实现方负责生成 created_at（调用方没传时）并回填 audit_id。
        """
        ...

    @abstractmethod
    def list_records(
        self,
        actor: str | None = None,
        action: str | None = None,
        start: str | None = None,
        end: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """
        按条件分页查审计记录，返回 (当前页列表, 总条数)。

        过滤条件可空；start / end 是 "YYYY-MM-DD HH:MM:SS" 字符串，
        按 created_at 闭区间比较（该格式下字符串比较 = 时间比较）。
        排序：created_at 倒序，同秒按 audit_id 倒序，最新的最先出。
        """
        ...
