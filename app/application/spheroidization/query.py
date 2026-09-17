from typing import List, Optional

from app.domain.spheroidization.entities import SpheroidizationRecord
from app.domain.spheroidization.repositories import SpheroidizationRepository


class QuerySpheroidizationUseCase:
    """
    查询球化检测记录。

    拆成三个明确的方法，而不是 execute(request) 里按 type 字符串分支：
    字符串魔法值拼错不会报错，只会走到 else 抛个语焉不详的异常；
    方法名拼错则是 AttributeError，立刻暴露。

    方法
    ----
    list_all()               查全部历史记录，前端历史列表页用
    list_abnormal()          查所有异常记录，异常记录页用
    get_by_id(record_id)     按主键查单条，记录详情页用

    返回值：列表无数据返回空列表；单条查不到返回 None。

    依赖：SpheroidizationRepository
    """

    def __init__(self, spheroid_repo: SpheroidizationRepository):
        self.spheroid_repo = spheroid_repo

    def list_all(self) -> List[SpheroidizationRecord]:
        """查全部球化检测记录，无数据返回空列表。"""
        return self.spheroid_repo.list_all()

    def list_abnormal(self) -> List[SpheroidizationRecord]:
        """查所有异常记录，无数据返回空列表。

        异常的定义：spheroidization_abnormal 等于 1。
        该字段可为空，NULL 按"不异常"处理。
        """
        return self.spheroid_repo.list_abnormal()

    def get_by_id(self, record_id: int) -> Optional[SpheroidizationRecord]:
        """按主键查单条，查不到返回 None。"""
        return self.spheroid_repo.get_by_id(record_id)
