from abc import ABC, abstractmethod

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
    ) -> list[StandardSwitchLog]:
        """
        分页查切换日志，按 switch_log_id 倒序，最新的在最前面。

        :param offset: 跳过前几条
        :param limit: 最多返回几条
        :return: 日志实体列表，无数据返回空列表
        场景：标准页面的"切换记录"列表。
        """
        ...
