from datetime import datetime

from app.domain.standard.entities import StandardRecord
from app.domain.standard.application_state import (
    StandardApplication,
    StandardApplicationState,
)
from app.domain.standard.repositories import StandardRepository


class CreateStandardUseCase:
    """
    新增检测标准。

    管理员调整检测标准时新增一条，新标准立即成为当前应用标准。

    业务规则
    --------
    - 只新增，不修改任何历史标准，也不修改历史球化检测记录
      （历史记录里存的是各自的标准快照）。
    - 新标准保存成功后写入标准应用状态文件，使其立即成为当前标准。
      标准表本身仍保持纯追加，不修改旧标准。
    - 创建时间由仓储实现方生成，调用方只传创建人。
    - 不做取值范围校验。库表上只限定"标准球化时间大于 0"，
      在这里再写一遍只会多一份要同步的规则。

    依赖：StandardRepository
    """

    def __init__(
        self,
        standard_repo: StandardRepository,
        application_state: StandardApplicationState,
    ):
        self.standard_repo = standard_repo
        self.application_state = application_state

    def execute(
        self,
        standard_spheroidization_time: float,
        weighing_standard: float,
        created_by: str,
        standard_spheroidization_time_upper: float | None = None,
        standard_spheroidization_time_lower: float | None = None,
        remark: str | None = None,
    ) -> StandardRecord:
        """
        :param standard_spheroidization_time: 标准球化时间（秒），库表限定大于 0
        :param weighing_standard: 称重标准
        :param created_by: 创建人
        :param standard_spheroidization_time_upper: 球化时长上限（秒），可为空
        :param standard_spheroidization_time_lower: 球化时长下限（秒），可为空
        :param remark: 备注 / 调整原因，可为空
        :return: StandardRecord，保存后的完整实体
        """
        new_standard = StandardRecord(
            standard_spheroidization_time=standard_spheroidization_time,
            standard_spheroidization_time_upper=standard_spheroidization_time_upper,
            standard_spheroidization_time_lower=standard_spheroidization_time_lower,
            weighing_standard=weighing_standard,
            created_by=created_by,
            remark=remark,
            # created_at 由仓储实现方生成。
            # standard_record_id 由仓储实现方生成并回填。
        )

        saved = self.standard_repo.save(new_standard)
        if saved.standard_record_id is None:
            raise RuntimeError("保存标准后未获得主键")

        self.application_state.save(
            StandardApplication(
                standard_record_id=saved.standard_record_id,
                applied_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
        return saved
