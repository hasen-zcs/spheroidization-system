from abc import ABC, abstractmethod
from typing import Optional

from app.domain.standard.switchlog_entities import StandardSwitchLog


class StandardSwitchLogRepository(ABC):
    """
    标准切换日志仓储抽象接口。实现由 infrastructure 层提供。

    跨方法约定（实现方必须遵守，调用方可依赖）：
    1. 主键由实现方生成：调用方传的实体主键为空，写入后由数据库自增分配，
       实现方回填再返回。
    2. 查列表无结果返回空列表。
    3. 只增不删：日志是审计凭证，不提供 update / delete。
    """

    @abstractmethod
    def save(self, log: StandardSwitchLog) -> StandardSwitchLog:
        """
        新增一条切换日志，对应 INSERT。

        :param log: 待新增的实体，主键为空
        :return: 保存后的实体，主键已填充
        场景：有权限的人切换了当前应用的标准。
        """
        ...

    @abstractmethod
    def list_all(
        self,
        offset: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> list[StandardSwitchLog]:
        """
        分页查切换日志，按 switch_log_id 倒序，最新的在最前面。

        :param offset: 跳过前几条
        :param limit: 最多返回几条
        :param include_deleted: 管理员"看已删除"用，默认 False（不含已软删除）
        :return: 日志实体列表，无数据返回空列表
        场景：标准页面的"切换记录"列表、管理员数据管理页。
        """
        ...

    @abstractmethod
    def count(self, include_deleted: bool = False) -> int:
        """
        统计切换日志条数，给全库分页列表的 total 用。
        :param include_deleted: 是否计入已软删除的行
        """
        ...

    @abstractmethod
    def get_by_id_including_deleted(self, switch_log_id: int) -> Optional[StandardSwitchLog]:
        """
        按主键查单条，**含已软删除的行**。
        :param switch_log_id: 切换日志主键
        :return: 实体；行根本不存在返回 None
        场景：管理员软删除 / 恢复前取整行做审计快照。
        """
        ...

    @abstractmethod
    def soft_delete(self, switch_log_id: int, deleted_by: str, delete_reason: str) -> bool:
        """
        软删除：置 deleted_at / deleted_by / delete_reason，绝不物理 DELETE。
        :param switch_log_id: 切换日志主键
        :param deleted_by: 删除人（登录账号）
        :param delete_reason: 删除原因
        :return: True=本次真删了；False=行不存在或已删除（幂等）
        """
        ...

    @abstractmethod
    def restore(self, switch_log_id: int) -> bool:
        """
        恢复：清空软删除三列。
        :param switch_log_id: 切换日志主键
        :return: True=本次真恢复了；False=行不存在或本来未删（幂等）
        """
        ...
