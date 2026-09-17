"""球化检测记录的请求 / 响应模型。

响应字段名跟前端现有契约保持一致（id、布尔值、布尔异常标记）。
实体那边叫 spheroidization_record_id，processed 和 spheroidization_abnormal 是 0 / 1 整数，
这些差异全部在 to_response 一个函数里消化掉。

等前端把字段名改成跟实体一致，把 to_response 删掉、直接把实体丢回去就行，
UseCase 和仓储一行都不用动。
"""

from pydantic import BaseModel

from app.domain.spheroidization.entities import SpheroidizationRecord


class SpheroidizationCreateRequest(BaseModel):
    # 只列 DDL 里真实存在的列。前端如果多发了别的字段，pydantic 默认忽略，不会报错。
    detection_time: str
    spheroidization_start_time: str
    spheroidization_end_time: str
    actual_spheroidization_time: float | None = None
    spheroidization_abnormal: bool | None = None


class SpheroidizationProcessRequest(BaseModel):
    processed_by: str


class SpheroidizationResponse(BaseModel):
    id: int
    detection_time: str
    spheroidization_start_time: str
    spheroidization_end_time: str
    actual_spheroidization_time: float | None = None
    spheroidization_abnormal: bool = False

    standard_spheroidization_time: float

    processed: bool = False
    processed_at: str | None = None
    processed_by: str | None = None


def to_response(record: SpheroidizationRecord) -> dict:
    """实体 -> 前端契约。字段名和 0/1 -> 布尔 的转换都在这里。

    只返回 DDL 里真实存在的列。早先为了兜住前端，这里补过 6 个固定空值
    （铁水重量、实际进线长度、机器结果、进线异常、两个快照值），
    那 6 列 DDL 里没有，已删。前端对应的展示位也一并去掉。
    """
    return {
        "id": record.spheroidization_record_id,
        "detection_time": record.detection_time,
        "spheroidization_start_time": record.spheroidization_start_time,
        "spheroidization_end_time": record.spheroidization_end_time,
        "actual_spheroidization_time": record.actual_spheroidization_time,
        # 前端用裸真值判断（record.processed ? ...），返回规范布尔最稳。
        # 注意 spheroidization_abnormal 允许是 None（机器没判），None 会变成 false。
        "spheroidization_abnormal": bool(record.spheroidization_abnormal),
        "standard_spheroidization_time": record.standard_spheroidization_time,
        "processed": bool(record.processed),
        "processed_at": record.processed_at,
        "processed_by": record.processed_by,
    }
