from app.domain.standard.entities import StandardRecord
from app.domain.standard.repositories import StandardRepository


class CreateStandardUseCase:
    """
    新增检测标准。

    管理员调整检测标准时新增一条，新标准立即成为当前有效标准。

    业务规则
    --------
    - 只新增，不修改任何历史标准，也不修改历史球化检测记录
      （历史记录里存的是各自的标准快照）。
    - "当前标准"的定义是"主键最大的那条"，由 get_current() 保证，
      所以这里不用去把旧标准标记失效，标准表保持纯追加。
    - 创建时间由仓储实现方生成，调用方只传创建人。
    - 不做取值范围校验。库表上已经有限定（标准球化时间 65~75、
      标准进线长度大于 0），在这里再写一遍只会多一份要同步的规则。

    依赖：StandardRepository
    """

    def __init__(self, standard_repo: StandardRepository):
        self.standard_repo = standard_repo

    def execute(
        self,
        standard_spheroidization_time: float,
        standard_entry_length: float,
        weighing_standard: float,
        created_by: str,
        remark: str | None = None,
    ) -> StandardRecord:
        """
        :param standard_spheroidization_time: 标准球化时间（秒），库表限定 65~75
        :param standard_entry_length: 标准进线长度，库表限定大于 0
        :param weighing_standard: 称重标准
        :param created_by: 创建人
        :param remark: 备注 / 调整原因，可为空
        :return: StandardRecord，保存后的完整实体
        """
        new_standard = StandardRecord(
            standard_spheroidization_time=standard_spheroidization_time,
            standard_entry_length=standard_entry_length,
            weighing_standard=weighing_standard,
            created_by=created_by,
            remark=remark,
            # created_at 由仓储实现方生成。
            # standard_record_id 由仓储实现方生成并回填。
        )

        return self.standard_repo.save(new_standard)
