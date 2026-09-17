from abc import ABC, abstractmethod
from typing import List

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
