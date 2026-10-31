"""球化检测记录的请求 / 响应模型。

响应字段名跟前端现有契约保持一致（id、布尔值、布尔异常标记）。
实体那边叫 spheroidization_record_id，processed 和 spheroidization_abnormal 是 0 / 1 整数，
这些差异全部在 to_response 一个函数里消化掉。

等前端把字段名改成跟实体一致，把 to_response 删掉、直接把实体丢回去就行，
UseCase 和仓储一行都不用动。
"""

import base64
import binascii

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.spheroidization.entities import SpheroidizationRecord


class SpheroidizationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 只列 DDL 里真实存在的列。前端如果多发了别的字段，pydantic 默认忽略，不会报错。
    detection_time: str
    spheroidization_start_time: str
    spheroidization_end_time: str
    actual_spheroidization_time: float
    spheroidization_abnormal: bool | None = None

    # 2026-09 新增的物性数据，全部来自上游推送，本系统只存储、不做任何运算。
    # 表上这几列都是 NOT NULL，所以这里也都是必填——上游少发一个，整条记录会被拒。
    spheroidization_temperature: float
    spheroidization_temperature_time: str
    spheroidization_wire_entry_start_time: str
    spheroidization_wire_entry_end_time: str
    spheroidization_wire_entry_total_duration: float
    spheroidization_weight: float

    # 图片二进制。JSON 里按 base64 字符串传，下面那个校验器负责解码。
    # 表上这一列允许 NULL，这里也允许不传。
    spheroidization_image: bytes | None = None

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

    processed_by: str


class SpheroidizationResponse(BaseModel):
    """响应形状说明。实际序列化走 to_response() 返回的 dict，这个类只当文档用。

    注意 spheroidization_image 只有详情接口才有：列表接口不带（原因见 to_response）。
    """

    id: int
    detection_time: str
    spheroidization_start_time: str
    spheroidization_end_time: str
    actual_spheroidization_time: float
    spheroidization_abnormal: bool = False

    standard_spheroidization_time: float

    spheroidization_temperature: float
    spheroidization_temperature_time: str
    spheroidization_wire_entry_start_time: str
    spheroidization_wire_entry_end_time: str
    spheroidization_wire_entry_total_duration: float
    spheroidization_weight: float

    processed: bool = False
    processed_at: str | None = None
    processed_by: str | None = None
    review_result: str | None = None


def to_response(
    record: SpheroidizationRecord,
    with_image: bool = False,
    review_result: int | None = None,
) -> dict:
    """实体 -> 前端契约。字段名和 0/1 -> 布尔 的转换都在这里。

    只返回 DDL 里真实存在的列。早先为了兜住前端，这里补过 6 个固定空值
    （铁水重量、实际进线长度、机器结果、进线异常、两个快照值），
    那 6 列 DDL 里没有，已删。前端对应的展示位也一并去掉。

    with_image 默认 False，是有意的：图片在库里是 BLOB，转成 base64 之后
    一条就是几百 KB，而列表接口一次要返几十上百条，带上图会直接把响应撑爆。
    只有详情接口传 True。要拿图就用记录 id 单独请求详情，别指望列表里带。

    带图时必须自己 base64 编码，不能把 bytes 直接塞进 dict：FastAPI 的
    jsonable_encoder 对 bytes 是按 UTF-8 解码的，真图片（JPEG 里随处可见
    0x80 以上的字节）会当场 UnicodeDecodeError 变成 500。
    """
    data = {
        "id": record.spheroidization_record_id,
        "detection_time": record.detection_time,
        "spheroidization_start_time": record.spheroidization_start_time,
        "spheroidization_end_time": record.spheroidization_end_time,
        "actual_spheroidization_time": record.actual_spheroidization_time,
        # 前端用裸真值判断（record.processed ? ...），返回规范布尔最稳。
        # 注意 spheroidization_abnormal 允许是 None（机器没判），None 会变成 false。
        "spheroidization_abnormal": bool(record.spheroidization_abnormal),
        "standard_spheroidization_time": record.standard_spheroidization_time,
        "spheroidization_temperature": record.spheroidization_temperature,
        "spheroidization_temperature_time": record.spheroidization_temperature_time,
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
