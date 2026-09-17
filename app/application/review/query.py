from typing import List

from app.domain.review.entities import ReviewRecord
from app.domain.review.repositories import ReviewRepository


class QueryReviewUseCase:
    """
    查询某条球化检测记录的复核历史。

    返回列表而非单条：一个球化记录可以有多条复核记录，返回单条会丢数据。

    依赖：ReviewRepository
    """

    def __init__(self, review_repo: ReviewRepository):
        self.review_repo = review_repo

    def execute(self, spheroid_id: int) -> List[ReviewRecord]:
        """
        :param spheroid_id: 球化检测记录主键，不是复核记录的主键
        :return: 复核实体列表，无复核记录返回空列表
        """
        return self.review_repo.list_by_spheroid_id(spheroid_id)
