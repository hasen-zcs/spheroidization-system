"""人工复核的路由。

只做四件事：收请求 → 转参数 → 调 UseCase → 包响应。
"""

from fastapi import APIRouter, Depends

from app.application.review.create import CreateReviewUseCase
from app.application.review.query import QueryReviewUseCase
from app.dependencies import get_create_review_uc, get_query_review_uc
from app.schemas.common import ok
from app.schemas.review import ReviewCreateRequest, to_response, to_result_int

router = APIRouter(
    prefix="/api/reviews",
    tags=["复核记录"],
)


@router.post("")
def create_review(
    data: ReviewCreateRequest,
    uc: CreateReviewUseCase = Depends(get_create_review_uc),
):
    # 对应的球化记录不存在时会抛 BusinessException，交给 main.py 的处理器。
    # 注意 execute 的参数顺序是 (球化记录id, 复核结果, 复核人, 复核说明)，用关键字传，别按位置。
    review = uc.execute(
        spheroidization_record_id=data.spheroidization_record_id,
        review_result=to_result_int(data.review_result),
        reviewer=data.reviewer,
        review_remark=data.review_remark,
    )
    return ok(to_response(review), "复核成功")


@router.get("/{record_id}")
def query_reviews(
    record_id: int,
    uc: QueryReviewUseCase = Depends(get_query_review_uc),
):
    # 一条球化记录可以有多条复核，所以返回列表；没有复核返回空列表
    return ok([to_response(review) for review in uc.execute(record_id)])
