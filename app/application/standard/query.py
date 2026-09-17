from typing import List, Optional

from app.domain.standard.entities import StandardRecord
from app.domain.standard.repositories import StandardRepository


class QueryStandardUseCase:
    """
    查询检测标准。

    同 QuerySpheroidizationUseCase，拆成明确方法而不是按 type 字符串分支。

    方法
    ----
    get_current()    查当前有效标准，前端展示当前标准用
    get_history()    查全部标准含历史，标准历史页用

    返回值：get_current 无标准时返回 None；get_history 无数据返回空列表。

    依赖：StandardRepository
    """

    def __init__(self, standard_repo: StandardRepository):
        self.standard_repo = standard_repo

    def get_current(self) -> Optional[StandardRecord]:
        """查当前有效标准 = 主键最大的那条，无标准时返回 None。"""
        return self.standard_repo.get_current()

    def get_history(self) -> List[StandardRecord]:
        """查全部标准，含当前和历史，无数据返回空列表。"""
        return self.standard_repo.get_history()
