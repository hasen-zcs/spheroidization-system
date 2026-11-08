from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.review.entities import ReviewRecord


class ReviewRepository(ABC):
    """
    人工复核记录仓储抽象接口。实现由 infrastructure 层提供。
    复核记录追加保存，只增不改不删：
    一个球化记录可以存在多条复核记录。
    跨方法约定（实现方必须遵守，调用方可依赖）：
    1. 主键由实现方生成：调用方传的实体主键为空，写入后由数据库自增分配，
       实现方回填再返回。
    2. 时间由实现方生成：reviewed_at 调用方不传，
       格式 "2026-09-05 08:30:15"。
    3. 查列表无结果返回空列表，不返回 None。
    4. 不提供 update / delete 方法。
    """

    @abstractmethod
    def save(self, review: ReviewRecord) -> ReviewRecord:
        """
        新增一条复核记录，只增，不修改任何已有复核记录。
        :param review: 待新增的实体，主键为空
        :return: 保存后的实体，主键已填充
        场景：操作人员对某条球化记录提交复核结果。
        review_result 是 0(正常) / 1(异常) 的整数，不是"正常"/"异常"字符串，
        库表上有 CHECK 限定只能是 0 或 1。
        本方法也不能借此修改球化记录的原始机器检测结果。
        """
        ...

    @abstractmethod
    def list_by_spheroid_id(self, spheroid_id: int) -> List[ReviewRecord]:
        """
        查某条球化记录的全部复核历史。
        :param spheroid_id: 球化检测记录主键
        :return: 复核实体列表，无记录返回空列表
        场景：查看某条球化记录的复核历史。
        一个球化记录可以有多条复核，所以返回列表而不是单条。
        """
        ...

    @abstractmethod
    def list_page(
        self,
        offset: int,
        limit: int,
        include_deleted: bool = False,
    ) -> List[ReviewRecord]:
        """
        分页查全库复核记录，按主键倒序，最新的在最前面。
        :param offset: 跳过前几条
        :param limit: 最多返回几条
        :param include_deleted: 管理员"看已删除"用，默认 False（不含已软删除）
        :return: 复核实体列表，无记录返回空列表
        场景：管理员数据管理页的"复核记录"tab。
        """
        ...

    @abstractmethod
    def count(self, include_deleted: bool = False) -> int:
        """
        统计复核记录条数，给全库分页列表的 total 用。
        :param include_deleted: 是否计入已软删除的行
        """
        ...

    @abstractmethod
    def get_by_id_including_deleted(self, review_record_id: int) -> Optional[ReviewRecord]:
        """
        按主键查单条，**含已软删除的行**。
        :param review_record_id: 复核记录主键
        :return: 实体；行根本不存在返回 None
        场景：管理员软删除 / 恢复前取整行做审计快照。
        """
        ...

    @abstractmethod
    def soft_delete(self, review_record_id: int, deleted_by: str, delete_reason: str) -> bool:
        """
        软删除：置 deleted_at / deleted_by / delete_reason，绝不物理 DELETE。
        :param review_record_id: 复核记录主键
        :param deleted_by: 删除人（登录账号）
        :param delete_reason: 删除原因
        :return: True=本次真删了；False=行不存在或已删除（幂等）
        """
        ...

    @abstractmethod
    def restore(self, review_record_id: int) -> bool:
        """
        恢复：清空软删除三列。
        :param review_record_id: 复核记录主键
        :return: True=本次真恢复了；False=行不存在或本来未删（幂等）
        """
        ...
