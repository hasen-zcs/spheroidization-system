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
        spheroidization_start_time: str,
        spheroidization_end_time: str,
        actual_spheroidization_time: float | None = None,
        spheroidization_abnormal: int | None = None,
    ) -> SpheroidizationRecord:
        """
        入参全部是上游推送的机器检测事实，本用例不改其中任何一个。
        后两个可以留空（库里对应列允许 NULL），留空就是 None，不要自己编 0 去填。

        :param detection_time: 检测时间，"2026-09-05 08:30:15" 格式的字符串
        :param spheroidization_start_time: 球化开始时间，同上格式
        :param spheroidization_end_time: 球化结束时间，同上格式
        :param actual_spheroidization_time: 实际反应时间（秒），可为空
        :param spheroidization_abnormal: 机器判定是否异常，0 正常 / 1 异常，可为空
        :return: SpheroidizationRecord，保存后的完整实体
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
            spheroidization_abnormal=spheroidization_abnormal,
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
