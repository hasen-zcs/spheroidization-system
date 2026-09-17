"""复核记录的请求 / 响应模型。

前端发和收的 review_result 都是中文字符串（"正常" / "异常"），
实体和数据库里是 0 / 1 整数。转换只在 to_result_int 和 to_response 里做。
"""

from pydantic import BaseModel

from app.domain.review.entities import ReviewRecord


class ReviewCreateRequest(BaseModel):
    spheroidization_record_id: int
    review_result: str
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
    """前端的中文 -> 库里的 0 / 1。只有"异常"是 1，其余（含"正常"）都算 0。"""
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
