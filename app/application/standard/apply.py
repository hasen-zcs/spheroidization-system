from datetime import datetime

from app.core.exceptions import BusinessException
from app.domain.standard.application_state import (
    StandardApplication,
    StandardApplicationState,
)
from app.domain.standard.entities import StandardRecord
from app.domain.standard.repositories import StandardRepository


class ApplyStandardUseCase:
    """把指定标准设置为当前应用标准。"""

    def __init__(
        self,
        standard_repo: StandardRepository,
        application_state: StandardApplicationState,
    ):
        self.standard_repo = standard_repo
        self.application_state = application_state

    def execute(
        self,
        standard_id: int,
        applied_by: str | None = None,
    ) -> StandardRecord:
        standard = self.standard_repo.get_by_id(standard_id)
        if standard is None:
            raise BusinessException("指定标准不存在，无法应用", 404)

        current = self.application_state.load()
        if current is None or current.standard_record_id != standard_id:
            self.application_state.save(
                StandardApplication(
                    standard_record_id=standard_id,
                    applied_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    applied_by=applied_by,
                )
            )

        return standard
