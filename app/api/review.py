"""人工复核的路由。

只做四件事：收请求 → 转参数 → 调 UseCase → 包响应。
"""

from fastapi import APIRouter, Depends, Query, Request

from app.application.review.create import CreateReviewUseCase
from app.application.review.query import QueryReviewUseCase
from app.core import permissions as P
from app.core.security import Session
from app.dependencies import (
    get_audit_logger,
    get_create_review_uc,
    get_query_review_uc,
    require_login,
    require_permission,
)
from app.domain.audit.entities import AuditAction, AuditTarget
from app.domain.audit.service import AuditLogger, client_ip
from app.schemas.common import fail, ok
from app.schemas.review import ReviewCreateRequest, to_response, to_result_int

router = APIRouter(
    prefix="/api/reviews",
    tags=["复核记录"],
)


@router.post("")
def create_review(
    data: ReviewCreateRequest,
    request: Request,
    session: Session = Depends(require_permission(P.ACTION_REVIEW)),
    uc: CreateReviewUseCase = Depends(get_create_review_uc),
    audit: AuditLogger = Depends(get_audit_logger),
):
    # 复核人和处理人一样从登录态取，不能由前端随便填：
    # 人工判定是谁做的，事后要能追到人。
    # 对应的球化记录不存在时会抛 BusinessException，交给 main.py 的处理器。
    # 注意 execute 的参数顺序是 (球化记录id, 复核结果, 复核人, 复核说明)，用关键字传，别按位置。
    review = uc.execute(
        spheroidization_record_id=data.spheroidization_record_id,
        review_result=to_result_int(data.review_result),
        reviewer=session.username,
        review_remark=data.review_remark,
    )
    # 审计留痕：人工判定结果必须可追溯
    audit.record(
        actor=session.username,
        action=AuditAction.REVIEW_RECORD,
        target_type=AuditTarget.REVIEW,
        target_id=review.review_record_id,
        detail={
            "spheroidization_record_id": data.spheroidization_record_id,
            "review_result": to_result_int(data.review_result),
            "review_remark": data.review_remark,
        },
        ip=client_ip(request),
    )
    return ok(to_response(review), "复核成功")


@router.get("/{record_id}")
def query_reviews(
    record_id: int,
    include_deleted: bool = Query(False),
    session: Session = Depends(require_login),
    uc: QueryReviewUseCase = Depends(get_query_review_uc),
):
    # 登录即可，不挂页面权限：复核历史是详情页的组成部分，
    # 而详情页对 page:records 和 page:abnormal 的用户都要能用，
    # 挂任何单一页面权限都会挡掉另一边。
    # 游客看不到（异常记录的复核历史不对游客开放）。
    # 一条球化记录可以有多条复核，所以返回列表；没有复核返回空列表
    # 看已删除复核记录是管理动作：要 action:manage_data，无权限 403。
    # 已 require_login，session 必非空，只判权限。
    if (
        include_deleted
        and not session.is_admin
        and P.ACTION_MANAGE_DATA not in session.permissions
    ):
        return fail("没有该操作权限", 403)
    return ok(
        [
            to_response(review)
            for review in uc.execute(record_id, include_deleted=include_deleted)
        ]
    )
