from typing import List, Optional

from app.domain.standard.application_state import StandardApplicationState
from app.domain.standard.entities import StandardRecord
from app.domain.standard.repositories import StandardRepository


class QueryStandardUseCase:
    """
    查询检测标准。
    同 QuerySpheroidizationUseCase，拆成明确方法而不是按 type 字符串分支。
    方法
    ----
    get_current()    查当前应用标准（切换过就以切换后的为准）
    get_history()    查全部标准含历史，标准历史页用
    返回值：get_current 无标准时返回 None；get_history 无数据返回空列表。
    依赖：StandardRepository、StandardApplicationState
    """

    def __init__(
        self,
        standard_repo: StandardRepository,
        application_state: StandardApplicationState,
    ):
        self.standard_repo = standard_repo
        self.application_state = application_state

    def get_current(self) -> Optional[StandardRecord]:
        """查当前应用标准。

        标准和球化记录不一样：标准是纯追加的，"当前"不一定是主键最大那条——
        切到旧标准之后，主键最大的那条仍然不是当前标准。所以先看状态文件，
        文件缺失或指向一个已经不存在的主键时，再回退到"主键最大"。
        """
        application = self.application_state.load()
        if application is not None:
            standard = self.standard_repo.get_by_id(application.standard_record_id)
            if standard is not None:
                return standard
        return self.standard_repo.get_current()

    def get_history(self, include_deleted: bool = False) -> List[StandardRecord]:
        """查全部标准，含当前和历史，无数据返回空列表。默认不含已软删除。"""
        return self.standard_repo.get_history(include_deleted=include_deleted)
