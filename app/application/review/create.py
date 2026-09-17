from app.core.exceptions import BusinessException
from app.domain.review.entities import ReviewRecord
from app.domain.review.repositories import ReviewRepository
from app.domain.spheroidization.repositories import SpheroidizationRepository


class CreateReviewUseCase:
    """
    提交人工复核。

    步骤
    ----
    1. 确认对应的球化检测记录存在；不存在抛业务异常
    2. 组装复核记录实体
    3. 保存并返回

    业务规则
    --------
    - 复核记录只增不改不删，一个球化记录可以有多条复核。
    - 复核不修改原始机器检测结果。机器判异常而人工判正常时，
      存的是"机器异常 + 人工复核正常"两条信息，而不是把机器结果改掉。
    - 复核完成不等于处理完成，两者独立：提交复核不会把记录标成已处理，
      也不会被"已处理"挡住。
    - 复核时间由仓储实现方生成。

    依赖：ReviewRepository、SpheroidizationRepository
    """

    def __init__(
        self,
        review_repo: ReviewRepository,
        spheroid_repo: SpheroidizationRepository,
    ):
        self.review_repo = review_repo
        self.spheroid_repo = spheroid_repo

    def execute(
        self,
        spheroidization_record_id: int,
        review_result: int,
        reviewer: str,
        review_remark: str | None = None,
    ) -> ReviewRecord:
        """
        :param spheroidization_record_id: 球化检测记录主键
        :param review_result: 复核结果，整数 0 正常 / 1 异常，
                              不是"正常"/"异常"字符串（库表 CHECK 限定只能是 0 或 1）
        :param reviewer: 复核人
        :param review_remark: 复核说明，可为空
        :return: ReviewRecord，保存后的完整实体
        """
        spheroid_record = self.spheroid_repo.get_by_id(spheroidization_record_id)
        if spheroid_record is None:
            raise BusinessException("对应的球化检测记录不存在，无法提交复核")

        new_review = ReviewRecord(
            spheroidization_record_id=spheroidization_record_id,
            review_result=review_result,
            reviewer=reviewer,
            review_remark=review_remark,
            # reviewed_at 由仓储实现方生成。
            # review_record_id 由仓储实现方生成并回填。
        )

        return self.review_repo.save(new_review)
