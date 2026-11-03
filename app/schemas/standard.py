"""检测标准的请求 / 响应模型。

实体主键叫 standard_record_id，前端读的是 id，转换在 to_response 里做。
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.standard.entities import StandardRecord
from app.domain.standard.switchlog_entities import StandardSwitchLog


class StandardCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standard_spheroidization_time: float = Field(gt=0)
    weighing_standard: float
    # 创建人不再由前端传，路由从登录态取。
    # extra="forbid" 会让前端多传的 created_by 直接 422，提醒它改。
    # 2026-09 新增，可为空。不传就是 NULL，不补 0——
    # 补 0 的话"没设上下限"和"上下限就是 0"就分不清了。
    standard_spheroidization_time_upper: float | None = Field(default=None, gt=0)
    standard_spheroidization_time_lower: float | None = Field(default=None, gt=0)
    remark: str = ""


class StandardSwitchRequest(BaseModel):
    """切换当前应用标准的请求。

    只有"切到哪套"和"为什么切"两个字段。
    from_standard_record_id 不让前端传——由后端读当前生效标准，
    前端传错了日志就和实际对不上，而这种对不上事后查不出来。
    """

    model_config = ConfigDict(extra="forbid")

    # 两种写法都收：to_standard_record_id 是后端原生命名，standard_id 是
    # 前端 10-28 接口说明里的写法。正式版统一走 standard_id，旧的保留兼容。
    to_standard_record_id: int | None = None
    standard_id: int | None = None
    reason: str

    @model_validator(mode="after")
    def _normalize_target(self):
        target = self.to_standard_record_id or self.standard_id
        if target is None:
            raise ValueError(
                "缺少要切换到的标准：standard_id 或 to_standard_record_id"
            )
        self.to_standard_record_id = target
        return self

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """原因不能全是空格。

        用 strip 后判空而不是判 None：前端传 "   " 也算没填，
        放进去日志里就是一条空白原因，等于没有审计。
        """
        if not value.strip():
            raise ValueError("切换原因不能为空")
        return value


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
        # v6 软删除信息：未删除时为 None
        "deleted_at": standard.deleted_at,
        "deleted_by": standard.deleted_by,
        "delete_reason": standard.delete_reason,
    }


def switch_log_to_response(log: StandardSwitchLog) -> dict:
    """切换日志实体 -> 前端契约。主键同样从 switch_log_id 映射成 id。"""
    return {
        "id": log.switch_log_id,
        "switched_at": log.switched_at,
        "from_standard_record_id": log.from_standard_record_id,
        "to_standard_record_id": log.to_standard_record_id,
        "operated_by": log.operated_by,
        "reason": log.reason,
        # v6 软删除信息：未删除时为 None
        "deleted_at": log.deleted_at,
        "deleted_by": log.deleted_by,
        "delete_reason": log.delete_reason,
    }
