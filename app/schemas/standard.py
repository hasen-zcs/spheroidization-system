"""检测标准的请求 / 响应模型。

实体主键叫 standard_record_id，前端读的是 id，转换在 to_response 里做。
"""

from pydantic import BaseModel

from app.domain.standard.entities import StandardRecord


class StandardCreateRequest(BaseModel):
    standard_spheroidization_time: float
    standard_entry_length: float
    weighing_standard: float
    created_by: str
    remark: str = ""


class StandardResponse(BaseModel):
    id: int
    standard_spheroidization_time: float
    standard_entry_length: float
    weighing_standard: float
    created_at: str | None = None
    created_by: str
    remark: str | None = None


def to_response(standard: StandardRecord) -> dict:
    """实体 -> 前端契约。"""
    return {
        "id": standard.standard_record_id,
        "standard_spheroidization_time": standard.standard_spheroidization_time,
        "standard_entry_length": standard.standard_entry_length,
        "weighing_standard": standard.weighing_standard,
        "created_at": standard.created_at,
        "created_by": standard.created_by,
        "remark": standard.remark,
    }
