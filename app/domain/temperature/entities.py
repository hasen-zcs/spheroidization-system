from dataclasses import dataclass


@dataclass
class TemperatureRecord:
    """
    测温枪读数。
    温度是测温枪按自己节奏
    测出来的事实，和球化记录不是一对一。一条球化记录可能前后挂好几条读数，
    所以不塞进主表，单独一张表、单独一个实体。
    """

    # 测温枪号
    gun_no: int
    # 实测温度
    temperature: float
    # 测温时刻
    measured_at: str
    # 入库时间
    created_at: str | None = None
    # 匹配到哪条球化记录。可空：温度可能先到，对应的球化记录还没生成
    spheroidization_record_id: int | None = None
    # 放在最后：dataclass 要求有默认值的字段必须排在没默认值的字段后面。
    temperature_record_id: int | None = None
