"""球化检测记录的请求 / 响应模型。

响应字段名跟前端现有契约保持一致（id、布尔值、布尔异常标记）。
实体那边叫 spheroidization_record_id，processed 和 spheroidization_abnormal 是 0 / 1 整数，
这些差异全部在 to_response 一个函数里消化掉。

等前端把字段名改成跟实体一致，把 to_response 删掉、直接把实体丢回去就行，
UseCase 和仓储一行都不用动。
"""

import base64
import binascii

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.spheroidization.entities import SpheroidizationRecord
from app.domain.temperature.entities import TemperatureRecord


class SpheroidizationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 只列 DDL 里真实存在的列。extra="forbid" 是有意的：
    # 上游要是还在发已经删掉的温度字段，这里直接 422，
    # 能立刻发现上游没跟着改；静默丢掉的话，数据没了都没人知道。
    detection_time: str
    spheroidization_start_time: str | None = None
    spheroidization_end_time: str | None = None
    actual_spheroidization_time: float | None = None
    spheroidization_abnormal: int | None = Field(
    default=None,
    ge=0,
    le=1,
)

    # 异常分类 1~4，由上游检测程序判定，这里只收不判。
    # ge/le 在模型层就挡掉非法值，比让数据库 CHECK 报错友好得多——
    # 数据库报的是 "CHECK constraint failed"，前端没法直接展示。
    # 0 正常 / 1 进站未球化 / 2 进线中断 / 3 超标准 / 4 低于标准 /
    # 5 分段多次球化 / 6 未判定（vpmin 现有口径，2026-10-29 定）
    # 0 必须收：vpmin 正常炉给的是 0，不是 null（10-31 联动实验实测撞到）
    abnormal_type: int | None = Field(default=None, ge=0, le=6)
    abnormal_reason: str | None = None

    # 补录专用的温度入参：机器正常流程走 POST /api/temperature，
    # 只有人工补录才随记录一起带温度。gun_no 默认 0 = 人工录入。
    temperature: float | None = None
    temperature_time: str | None = None
    gun_no: int = 0

    # 物性数据，全部来自上游推送，本系统只存储、不做任何运算。
    # 表上这几列都是 NOT NULL，所以这里也都是必填——上游少发一个，整条记录会被拒。
    spheroidization_wire_entry_start_time: str
    spheroidization_wire_entry_end_time: str
    spheroidization_wire_entry_total_duration: float
    spheroidization_weight: float

    # 图片二进制。JSON 里按 base64 字符串传，下面那个校验器负责解码。
    # 表上这一列允许 NULL，这里也允许不传。
    spheroidization_image: bytes | None = None

    @model_validator(mode="after")
    def _temperature_pair(self):
        """补录温度必须成对出现，单项没法落库也没法展示。"""
        if (self.temperature is None) != (self.temperature_time is None):
            raise ValueError("temperature 和 temperature_time 必须同时提供")
        return self

    @field_validator("spheroidization_image", mode="before")
    @classmethod
    def _decode_image(cls, value):
        """base64 字符串 -> bytes。

        这个校验器不能省。pydantic v2 的 bytes 字段收到 JSON 字符串时是按 UTF-8
        编码成字节，**不是** base64 解码（v1 才是 base64）。少了这一步，库里存的
        会是 base64 文本本身的字节，图整个是坏的——而且因为读写两头都错得一样，
        接口自己看着还挺"一致"，只有直查数据库才发现得了。

        validate=True 是为了让坏数据当场 422。默认的 validate=False 会把不认识的
        字符悄悄丢掉，等于存进去一张损坏的图，而我们只存不处理，事后没人能发现。
        先去掉空白是照顾 MIME 那种按行折过的 base64。
        """
        if not isinstance(value, str):
            return value
        try:
            return base64.b64decode("".join(value.split()), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"spheroidization_image 不是合法的 base64：{exc}") from exc


class SpheroidizationProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 处理人不再由前端传，从登录态取。
    # 保留这个空类是为了让 {"processed_by": "张三"} 这类旧请求直接 422，
    # 提醒调用方已经改口径，而不是被静默忽略。
    # 不要为了"干净"把类删掉或禁止空对象——这里 {} 是合法请求体。


class SpheroidizationResponse(BaseModel):
    """响应形状说明。实际序列化走 to_response() 返回的 dict，这个类只当文档用。

    注意 spheroidization_image 只有详情接口才有：列表接口不带（原因见 to_response）。
    """

    id: int
    detection_time: str
    spheroidization_start_time: str | None = None
    spheroidization_end_time: str | None = None
    actual_spheroidization_time: float | None = None
    spheroidization_abnormal: int | None = None
    standard_spheroidization_time: float

    # 异常分类和说明，由上游给，可为空
    abnormal_type: int | None = None
    abnormal_reason: str | None = None

    spheroidization_wire_entry_start_time: str
    spheroidization_wire_entry_end_time: str
    spheroidization_wire_entry_total_duration: float
    spheroidization_weight: float

    # 温度已经从主表拆出去了，这里返回的是关联到的那条测温读数
    temperature: float | None = None
    temperature_time: str | None = None

    processed: int = 0
    processed_at: str | None = None
    processed_by: str | None = None
    review_result: str | None = None


def to_response(
    record: SpheroidizationRecord,
    with_image: bool = False,
    review_result: int | None = None,
    temperature: TemperatureRecord | None = None,
) -> dict:
    """实体 -> 前端契约。字段名和 0/1 -> 布尔 的转换都在这里。

    只返回 DDL 里真实存在的列。

    with_image 默认 False，是有意的：图片在库里是 BLOB，转成 base64 之后
    一条就是几百 KB，而列表接口一次要返几十上百条，带上图会直接把响应撑爆。
    只有详情接口传 True。要拿图就用记录 id 单独请求详情，别指望列表里带。

    带图时必须自己 base64 编码，不能把 bytes 直接塞进 dict：FastAPI 的
    jsonable_encoder 对 bytes 是按 UTF-8 解码的，真图片（JPEG 里随处可见
    0x80 以上的字节）会当场 UnicodeDecodeError 变成 500。

    temperature 为空时 temperature / temperature_time 返回 None，前端要能处理
    "这条记录还没有关联温度"这种情况。
    """
    data = {
        "id": record.spheroidization_record_id,
        "detection_time": record.detection_time,
        "spheroidization_start_time": record.spheroidization_start_time,
        "spheroidization_end_time": record.spheroidization_end_time,
        "actual_spheroidization_time": record.actual_spheroidization_time,
        # 0/1 -> 布尔；None 保持 None（机器没给判定，不能冒充"正常"）
        "spheroidization_abnormal": (
            None
            if record.spheroidization_abnormal is None
            else bool(record.spheroidization_abnormal)
        ),
        "standard_spheroidization_time": record.standard_spheroidization_time,
        # 异常分类和说明原样透传，不做任何映射
        "abnormal_type": record.abnormal_type,
        "abnormal_reason": record.abnormal_reason,
        "spheroidization_wire_entry_start_time": (
            record.spheroidization_wire_entry_start_time
        ),
        "spheroidization_wire_entry_end_time": (
            record.spheroidization_wire_entry_end_time
        ),
        "spheroidization_wire_entry_total_duration": (
            record.spheroidization_wire_entry_total_duration
        ),
        "spheroidization_weight": record.spheroidization_weight,
        "temperature": temperature.temperature if temperature else None,
        "temperature_time": temperature.measured_at if temperature else None,
        "processed": bool(record.processed),
        "processed_at": record.processed_at,
        "processed_by": record.processed_by,
        "review_result": (
            None
            if review_result is None
            else ("异常" if review_result == 1 else "正常")
        ),
    }

    if with_image:
        image = record.spheroidization_image
        data["spheroidization_image"] = (
            base64.b64encode(image).decode("ascii") if image is not None else None
        )

    return data
