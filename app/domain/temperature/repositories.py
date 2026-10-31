from abc import ABC, abstractmethod

from app.domain.temperature.entities import TemperatureRecord


class TemperatureRepository(ABC):
    """
    测温枪读数仓储抽象接口。实现由 infrastructure 层提供。

    跨方法约定（实现方必须遵守，调用方可依赖）：
    1. 主键由实现方生成：调用方传的实体主键为空，写入后由数据库自增分配，
       实现方回填再返回。
    2. 时间由实现方生成：created_at 调用方不传，格式 "2026-09-05 08:30:15"。
    3. 查单条无结果返回 None；查列表无结果返回空列表。
    4. 不提供 update / delete。温度是测量事实，入库后不改不删。
       attach_to_record 是唯一的例外，它改的是"挂到哪条球化记录上"这个关联，
       不动温度值本身。
    """

    @abstractmethod
    def save(self, record: TemperatureRecord) -> TemperatureRecord:
        ...

    @abstractmethod
    def get_by_id(self, record_id: int) -> TemperatureRecord | None:
        """按主键查单条，查不到返回 None。"""
        ...

    @abstractmethod
    def list_by_record_ids(self, ids: list[int]) -> list[TemperatureRecord]:
        """
        根据多个球化记录 ID，批量查询关联的温度记录。
        必须使用一次 IN 查询完成，而不是循环查询。
        """
        ...

    @abstractmethod
    def attach_to_record(
        self,
        temperature_id: int,
        spheroidization_record_id: int,
    ) -> None:
        """
        把已采到的温度挂到某条球化记录上，对应 UPDATE。

        :param temperature_id: 温度记录主键
        :param spheroidization_record_id: 要挂到的球化记录主键

        温度先到、球化记录后生成时用这个补关联。
        目标温度不存在时由实现方报错，不能装作成功。
        """
        ...
