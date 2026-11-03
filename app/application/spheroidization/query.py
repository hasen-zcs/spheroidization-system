from typing import List, Optional

from app.domain.spheroidization.entities import SpheroidizationRecord
from app.domain.flash.repositories import FlashSegmentRepository
from app.domain.review.repositories import ReviewRepository
from app.domain.spheroidization.repositories import SpheroidizationRepository
from app.domain.temperature.entities import TemperatureRecord
from app.domain.temperature.repositories import TemperatureRepository


class QuerySpheroidizationUseCase:
    """
    查询球化检测记录。

    拆成三个明确的方法，而不是 execute(request) 里按 type 字符串分支：
    字符串魔法值拼错不会报错，只会走到 else 抛个语焉不详的异常；
    方法名拼错则是 AttributeError，立刻暴露。

    方法
    ----
    list_all()               查全部历史记录，前端历史列表页用
    list_abnormal()          查所有异常记录，异常记录页用
    get_by_id(record_id)     按主键查单条，记录详情页用

    返回值：列表无数据返回空列表；单条查不到返回 None。

    依赖：SpheroidizationRepository、ReviewRepository、TemperatureRepository
    """

    def __init__(
        self,
        spheroid_repo: SpheroidizationRepository,
        review_repo: ReviewRepository,
        temperature_repo: TemperatureRepository,
        segment_repo: FlashSegmentRepository | None = None,
    ):
        self.spheroid_repo = spheroid_repo
        self.review_repo = review_repo
        self.temperature_repo = temperature_repo
        # 分段仓储只给详情用，允许不传（老测试构造函数不用改）
        self.segment_repo = segment_repo

    def segments_for(self, record_id: int):
        """查一条记录的分段明细。没装分段仓储/没有分段都返回空列表。"""
        if self.segment_repo is None:
            return []
        return self.segment_repo.list_by_record(record_id)

    def list_all(self) -> List[SpheroidizationRecord]:
        """查全部球化检测记录，无数据返回空列表。"""
        return self.spheroid_repo.list_all()

    def list_abnormal(self) -> List[SpheroidizationRecord]:
        """查所有异常记录，无数据返回空列表。

        异常的定义：spheroidization_abnormal 等于 1。
        该字段可为空，NULL 按"不异常"处理。
        """
        return self.spheroid_repo.list_abnormal()

    def get_by_id(self, record_id: int) -> Optional[SpheroidizationRecord]:
        """按主键查单条，查不到返回 None。

        查不到返回 None 而不是抛异常：详情和图片两个接口都要用它，
        报什么错、返回什么信封是路由层的事，用例层不替调用方决定。
        """
        return self.spheroid_repo.get_by_id(record_id)

    def list_page(
        self,
        page: int,
        page_size: int,
        abnormal: bool | None = None,
        processed: bool | None = None,
        include_deleted: bool = False,
    ) -> tuple[List[SpheroidizationRecord], int]:
        offset = (page - 1) * page_size
        records = self.spheroid_repo.list_page(
            offset=offset,
            limit=page_size,
            abnormal=abnormal,
            processed=processed,
            include_deleted=include_deleted,
        )
        total = self.spheroid_repo.count(
            abnormal=abnormal, processed=processed, include_deleted=include_deleted
        )
        return records, total

    def latest_review_results(
        self,
        records: List[SpheroidizationRecord],
    ) -> dict[int, int]:
        record_ids = [
            record.spheroidization_record_id
            for record in records
            if record.spheroidization_record_id is not None
        ]
        return self.review_repo.get_latest_results(record_ids)

    def temperatures_for(
        self,
        records: List[SpheroidizationRecord],
    ) -> dict[int, TemperatureRecord]:
        """批量取出这批记录各自的温度，按球化记录主键索引。

        一条球化记录最多一条温度（没有"一路多枪"），所以返回 dict；
        万一库里真有多条，仓储按测温时刻正序返回，字典推导时后写的
        覆盖先写的，最终留下来的是最新那条。
        """
        record_ids = [
            record.spheroidization_record_id
            for record in records
            if record.spheroidization_record_id is not None
        ]
        if not record_ids:
            # 空列表不往仓储跑一趟，省一次往返
            return {}

        temperatures = self.temperature_repo.list_by_record_ids(record_ids)
        return {
            temperature.spheroidization_record_id: temperature
            for temperature in temperatures
            if temperature.spheroidization_record_id is not None
        }

    def stats(self) -> dict[str, int]:
        return {
            "total": self.spheroid_repo.count(),
            "abnormal": self.spheroid_repo.count(abnormal=True),
            "processed": self.spheroid_repo.count(processed=True),
            "unprocessed": self.spheroid_repo.count(processed=False),
        }
