from app.core.exceptions import BusinessException
from app.domain.spheroidization.repositories import SpheroidizationRepository
from app.domain.temperature.entities import TemperatureRecord
from app.domain.temperature.repositories import TemperatureRepository


class CreateTemperatureUseCase:
    """
    记录一条测温枪读数。

    温度从球化记录里拆出来单独成表，因为它有自己的产生节奏：
    测温枪什么时候测就什么时候报，可能比球化记录先到、也可能后到。

    业务规则
    --------
    - 属于哪条球化记录，由检测程序自己判定后传进来。后端不猜、
      不按时间窗口去匹配——匹配规则一旦有两份，早晚会对不上。
    - 传了 spheroidization_record_id 就校验记录存在；没传就存成未关联，
      之后再通过 attach 补挂。
    - 入库时间由仓储实现方生成，调用方只传测温时刻。

    依赖：TemperatureRepository、SpheroidizationRepository
    """

    def __init__(
        self,
        temperature_repo: TemperatureRepository,
        spheroid_repo: SpheroidizationRepository,
    ):
        self.temperature_repo = temperature_repo
        self.spheroid_repo = spheroid_repo

    def execute(
        self,
        gun_no: int,
        temperature: float,
        measured_at: str,
        spheroidization_record_id: int | None = None,
    ) -> TemperatureRecord:
        """
        :param gun_no: 测温枪号
        :param temperature: 实测温度，原值，不做取整
        :param measured_at: 测温时刻，"2026-09-05 08:30:15" 格式
        :param spheroidization_record_id: 归属的球化记录主键，可为空
        :return: TemperatureRecord，保存后的完整实体
        """
        if spheroidization_record_id is not None:
            # 先挡住"挂到一条不存在的记录上"：外键也会拦，
            # 但外键报的是 IntegrityError，提示看不懂，对上游不友好。
            record = self.spheroid_repo.get_by_id(spheroidization_record_id)
            if record is None:
                raise BusinessException(
                    f"要关联的球化检测记录不存在："
                    f"spheroidization_record_id={spheroidization_record_id}"
                )

        temperature_record = TemperatureRecord(
            gun_no=gun_no,
            temperature=temperature,
            measured_at=measured_at,
            spheroidization_record_id=spheroidization_record_id,
            # created_at 由仓储实现方生成。
            # temperature_record_id 由仓储实现方生成并回填。
        )

        return self.temperature_repo.save(temperature_record)
