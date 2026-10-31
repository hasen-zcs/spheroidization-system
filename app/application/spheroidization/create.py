from app.core.exceptions import BusinessException
from app.domain.spheroidization.entities import SpheroidizationRecord
from app.domain.spheroidization.repositories import SpheroidizationRepository
from app.domain.standard.repositories import StandardRepository


class CreateSpheroidizationUseCase:
    """
    创建球化检测记录。
    接收上游推送的一条检测结果，取当前有效标准生成快照，建档保存。
    步骤
    ----
    1. 取当前有效标准；取不到抛业务异常
    2. 记下标准主键（溯源）和标准球化时间（快照）
    3. 组装实体，人工处理状态初始为未处理
    4. 保存并返回

    业务规则
    --------
    - 快照取自"创建这一刻的当前标准"，之后标准怎么改都不影响这条记录。
    - 原始机器检测结果创建后不可修改。
    - 是否已处理、是否已复核都在创建之后才产生，本用例不涉及。
    - 异常类型和异常说明由上游检测程序判定，这里原样落库，不做推导。

    依赖：SpheroidizationRepository、StandardRepository
    """

    def __init__(
        self,
        spheroid_repo: SpheroidizationRepository,
        standard_repo: StandardRepository,
    ):
        self.spheroid_repo = spheroid_repo
        self.standard_repo = standard_repo

    def execute(
        self,
        detection_time: str,
        spheroidization_wire_entry_start_time: str,
        spheroidization_wire_entry_end_time: str,
        spheroidization_wire_entry_total_duration: float,
        spheroidization_weight: float,
        spheroidization_start_time: str | None = None,
        spheroidization_end_time: str | None = None,
        actual_spheroidization_time: float | None = None,
        spheroidization_abnormal: int | None = None,
        abnormal_type: int | None = None,
        abnormal_reason: str | None = None,
        plc_button_time: str | None = None,
        spheroidization_image: bytes | None = None,
    ) -> SpheroidizationRecord:
        """
        入参全部是上游推送的机器检测事实，本用例不改其中任何一个。
        必填的是检测时间、进线起止时间、进线总时长、重量这 5 个。
        三个球化时间（开始 / 结束 / 实际时长）可选：进站未球化、
        进线提前中止这两类异常下球化没跑完，本来就没有值，传 None 就好，
        不要拿 0 或空串去凑必填.
        必填参数排在可选参数前面。三个球化时间原先必填、现在改成可选，
        直接原地加 = None 会变成"有默认值的参数后面跟着没默认值的参数"，
        是 SyntaxError，所以把它们挪到必填参数之后。
        """
        current_standard = self.standard_repo.get_current()
        if current_standard is None:
            raise BusinessException("不存在生效检测标准，无法创建球化检测记录")

        new_record = SpheroidizationRecord(
            # 溯源：这条记录用了当前这套标准。仅作标识，
            # 业务运算用的是下面的快照值，不是实时去查标准表。
            standard_record_id=current_standard.standard_record_id,
            # 机器检测事实，原样搬自上游
            detection_time=detection_time,
            spheroidization_start_time=spheroidization_start_time,
            spheroidization_end_time=spheroidization_end_time,
            actual_spheroidization_time=actual_spheroidization_time,
            spheroidization_wire_entry_start_time=(
                spheroidization_wire_entry_start_time
            ),
            spheroidization_wire_entry_end_time=spheroidization_wire_entry_end_time,
            spheroidization_wire_entry_total_duration=(
                spheroidization_wire_entry_total_duration
            ),
            spheroidization_weight=spheroidization_weight,
            spheroidization_abnormal=spheroidization_abnormal,
            # 异常分类和说明原样存：判定是上游的事，后端只记录。
            # 这里一推导，将来两边口径不一致就查不清是谁改的。
            abnormal_type=abnormal_type,
            abnormal_reason=abnormal_reason,
            plc_button_time=plc_button_time,
            spheroidization_image=spheroidization_image,
            # 标准快照：创建这一刻的标准球化时间
            standard_spheroidization_time=(
                current_standard.standard_spheroidization_time
            ),
            # 人工处理状态：新建一律未处理
            processed=0,
            # processed_at / processed_by 未处理时为 None。
            # spheroidization_record_id 由仓储实现方生成并回填。
        )

        return self.spheroid_repo.save(new_record)
