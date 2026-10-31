"""检测标准的请求 / 响应模型。

实体主键叫 standard_record_id，前端读的是 id，转换在 to_response 里做。
"""

from pydantic import BaseModel, ConfigDict, Field

from app.domain.standard.entities import StandardRecord


class StandardCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standard_spheroidization_time: float = Field(gt=0)
    weighing_standard: float
    created_by: str
    # 2026-09 新增，可为空。不传就是 NULL，不补 0——
    # 补 0 的话"没设上下限"和"上下限就是 0"就分不清了。
    standard_spheroidization_time_upper: float | None = Field(default=None, gt=0)
    standard_spheroidization_time_lower: float | None = Field(default=None, gt=0)
    remark: str = ""


class StandardResponse(BaseModel):
    id: int
    standard_spheroidization_time: float
    standard_spheroidization_time_upper: float | None = None
    standard_spheroidization_time_lower: float | None = None
    weighing_standard: float
    created_at: str | None = None
    created_by: str
    remark: str | None = None


def to_response(standard: StandardRecord) -> dict:
    """实体 -> 前端契约。"""
    return {
        "id": standard.standard_record_id,
        "standard_spheroidization_time": standard.standard_spheroidization_time,
        "standard_spheroidization_time_upper": (
            standard.standard_spheroidization_time_upper
        ),
        "standard_spheroidization_time_lower": (
            standard.standard_spheroidization_time_lower
        ),
        "weighing_standard": standard.weighing_standard,
        "created_at": standard.created_at,
        "created_by": standard.created_by,
        "remark": standard.remark,
    }
