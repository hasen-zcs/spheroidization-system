"""复核记录的请求 / 响应模型。

前端发和收的 review_result 都是中文字符串（"正常" / "异常"），
实体和数据库里是 0 / 1 整数。转换只在 to_result_int 和 to_response 里做。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.review.entities import ReviewRecord


class ReviewCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spheroidization_record_id: int
    # 只能是这两个值，多一个字都不行。
    # to_result_int 是"非异常即正常"，收下 "异常 " 这种带空格的写法会静默存成"正常"——
    # 人工判定被悄悄反过来的记录，事后没人查得出来。这里用 Literal 直接挡在门口，
    # 发错了是 422 并点名 review_result，不是默默存反。
    review_result: Literal["正常", "异常"]
    reviewer: str
    review_remark: str | None = None


class ReviewResponse(BaseModel):
    id: int
    spheroidization_record_id: int
    review_result: str
    reviewer: str
    review_remark: str | None = None
    reviewed_at: str | None = None


def to_result_int(review_result: str) -> int:
    """前端的中文 -> 库里的 0 / 1。只有"异常"是 1，其余都算 0。

    入参已经被 ReviewCreateRequest 的 Literal 卡成两个值之一了，
    所以这里的 else 分支只会是"正常"。别把这个函数单独拿去用。
    """
    return 1 if review_result == "异常" else 0


def to_response(review: ReviewRecord) -> dict:
    """实体 -> 前端契约。"""
    return {
        "id": review.review_record_id,
        "spheroidization_record_id": review.spheroidization_record_id,
        "review_result": "异常" if review.review_result == 1 else "正常",
        "reviewer": review.reviewer,
        "review_remark": review.review_remark,
        "reviewed_at": review.reviewed_at,
    }
