from app.core.exceptions import BusinessException
from app.domain.spheroidization.entities import SpheroidizationRecord
from app.domain.spheroidization.repositories import SpheroidizationRepository


class ProcessSpheroidizationUseCase:
    """
    标记球化检测记录为已处理。

    步骤
    ----
    1. 按主键查记录；查不到抛业务异常
    2. 已经是已处理的，抛业务异常，不重复处理
    3. 只改人工处理状态，机器检测事实不动
    4. 保存并返回

    业务规则
    --------
    - 处理与复核是两个独立状态，不要求先有复核记录。
    - 处置不可逆：一条记录只允许一次人工处置，不回退状态。
      对已处理的记录再调一次直接抛异常，不静默覆盖处理人；
      本层也没有"撤销处理"入口。这条规则来自数据库表，不是本层自己定的。
    - 处理时间由仓储实现方生成，调用方只传处理人。

    依赖：SpheroidizationRepository
    """

    def __init__(self, spheroid_repo: SpheroidizationRepository):
        self.spheroid_repo = spheroid_repo

    def execute(self, record_id: int, processed_by: str) -> SpheroidizationRecord:
        """
        :param record_id: 球化检测记录主键
        :param processed_by: 处理人
        :return: SpheroidizationRecord，更新后的实体
        """
        record = self.spheroid_repo.get_by_id(record_id)
        if record is None:
            raise BusinessException("找不到该球化检测记录，无法标记为已处理")

        # 已处理过的不许再处理。处置不可逆又没有撤销入口，
        # 不拦的话就成了"悄悄改掉上一个处理人"。
        if record.processed == 1:
            raise BusinessException(
                f"该球化检测记录已经是已处理状态（处理人：{record.processed_by}），"
                "处置不可逆，不能重复处理"
            )

        record.processed = 1
        record.processed_by = processed_by
        # processed_at 不在这里赋值，由仓储实现方在 update 时生成。

        return self.spheroid_repo.update(record)
