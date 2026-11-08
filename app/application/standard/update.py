from app.core.exceptions import BusinessException
from app.domain.standard.entities import StandardRecord
from app.domain.standard.repositories import StandardRepository


class UpdateStandardUseCase:
    """
    修订检测标准。
    业务规则
    --------
    - 只改 5 个业务字段（球化时间 / 上限 / 下限 / 称重标准 / 备注），
      created_at / created_by 由仓储保证不动——标准是谁、什么时候建的一律保持原样。
    - 目标行不存在或已被软删 → 404「标准不存在」。
      已删的行不允许再改：改完也查不到，等于白改还留一份假账。
    - 不做取值范围校验。库表上只限定"标准球化时间大于 0"，
      和 create 保持同一口径，校验在请求模型（StandardUpdateRequest）里。
    - "当前标准"的指向不受影响：标准是状态文件指到哪条就是哪条，
      修订只是改字段，不新增、不删行。
    依赖：StandardRepository
    """

    def __init__(self, standard_repo: StandardRepository):
        self.standard_repo = standard_repo

    def execute(
        self,
        standard_record_id: int,
        standard_spheroidization_time: float,
        standard_spheroidization_time_upper: float | None,
        standard_spheroidization_time_lower: float | None,
        weighing_standard: float,
        remark: str,
    ) -> StandardRecord:
        """
        :param standard_record_id: 要修订的标准主键
        :param standard_spheroidization_time: 标准球化时间（秒），库里限定大于 0
        :param standard_spheroidization_time_upper: 球化时长上限（秒），可为空
        :param standard_spheroidization_time_lower: 球化时长下限（秒），可为空
        :param weighing_standard: 称重标准
        :param remark: 备注 / 调整原因
        :return: 更新后的完整实体
        :raises BusinessException: 行不存在或已软删（404，「标准不存在」）
        """
        updated = self.standard_repo.update(
            standard_record_id=standard_record_id,
            standard_spheroidization_time=standard_spheroidization_time,
            standard_spheroidization_time_upper=standard_spheroidization_time_upper,
            standard_spheroidization_time_lower=standard_spheroidization_time_lower,
            weighing_standard=weighing_standard,
            remark=remark,
        )
        if updated is None:
            raise BusinessException("标准不存在", 404)
        return updated
