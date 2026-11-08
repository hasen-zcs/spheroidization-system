"""管理员数据管理路由：四类数据的软删除 / 恢复 / 处理状态修改。

只做四件事：收请求 → 校验（原因非空、当前标准不可删、目标存在）→ 改库 → 留审计。

红线（老板已拍板，见 TASK-8）：
- 四类数据全部**软删除**：只置 deleted_at/deleted_by/delete_reason，绝不 DELETE FROM。
- 处理状态只有管理员能改（0↔1 可来回），处理人取登录账号。
- 全部接口挂 action:manage_data 权限，游客 401、无权限 403（由 require_permission 给）。
- 每个写操作写一条 AuditLog，actor 取登录账号。

幂等口径：
- 已删除的再删 / 未删除的再恢复 → 直接成功，不重复写审计。
- 目标在主键上查不到（行根本不存在）→ 404。
"""

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.application.admin.manage import ManageDataUseCase
from app.application.review.query import QueryReviewUseCase
from app.application.standard.switch import SwitchStandardUseCase
from app.core import permissions as P
from app.core.security import Session
from app.dependencies import (
    get_audit_logger,
    get_manage_data_uc,
    get_query_review_uc,
    get_switch_standard_uc,
    require_permission,
)
from app.domain.audit.entities import AuditAction, AuditTarget
from app.domain.audit.service import AuditLogger, client_ip
from app.schemas.common import fail, ok
from app.schemas.review import to_response as review_to_response
from app.schemas.standard import switch_log_to_response

router = APIRouter(
    prefix="/api/admin",
    tags=["管理员数据管理"],
)


class ReasonRequest(BaseModel):
    """软删除请求体：只收原因。删除人取登录态，不接受前端填。"""

    model_config = ConfigDict(extra="forbid")
    reason: str


class ProcessedRequest(BaseModel):
    """改处理状态请求体：0/1 + 原因。处理人取登录态。"""

    model_config = ConfigDict(extra="forbid")
    processed: int = Field(ge=0, le=1)
    reason: str


def _require_reason(reason: str):
    """原因去空格后为空 → 返回 400 信封；否则返回 None（放行）。"""
    if reason is None or not reason.strip():
        return fail("请填写原因", 400)
    return None


# 各操作的 (动作码, 对象类型) 映射，审计留痕统一用。
_DELETE_ACTIONS = {
    "record": (AuditAction.DELETE_RECORD, AuditTarget.SPHEROIDIZATION_RECORD),
    "standard": (AuditAction.DELETE_STANDARD, AuditTarget.STANDARD),
    "switch_log": (AuditAction.DELETE_SWITCH_LOG, AuditTarget.SWITCH_LOG),
    "review": (AuditAction.DELETE_REVIEW, AuditTarget.REVIEW),
}
_RESTORE_ACTIONS = {
    "record": (AuditAction.RESTORE_RECORD, AuditTarget.SPHEROIDIZATION_RECORD),
    "standard": (AuditAction.RESTORE_STANDARD, AuditTarget.STANDARD),
    "switch_log": (AuditAction.RESTORE_SWITCH_LOG, AuditTarget.SWITCH_LOG),
    "review": (AuditAction.RESTORE_REVIEW, AuditTarget.REVIEW),
}


def _audit(audit: AuditLogger, request: Request, session: Session, key: str,
           record_id: int, is_delete: bool, before: dict, after: dict) -> None:
    action, target_type = (
        _DELETE_ACTIONS[key] if is_delete else _RESTORE_ACTIONS[key]
    )
    audit.record(
        actor=session.username,
        action=action,
        target_type=target_type,
        target_id=record_id,
        detail={"before": before, "after": after},
        ip=client_ip(request),
    )


# ---------------------------------------------------------------------------
# 软删除
# ---------------------------------------------------------------------------

def _delete_endpoint(key: str, need_reason: bool):
    def endpoint(
        record_id: int,
        data: ReasonRequest,
        request: Request,
        session: Session = Depends(require_permission(P.ACTION_MANAGE_DATA)),
        uc: ManageDataUseCase = Depends(get_manage_data_uc),
        audit: AuditLogger = Depends(get_audit_logger),
    ):
        bad = _require_reason(data.reason) if need_reason else None
        if bad is not None:
            return bad

        # 当前生效标准不许软删（用例内抛 BusinessException(400)，统一信封）。
        result = uc.soft_delete(key, record_id, session.username, data.reason)
        if result.status == "not_found":
            return fail("目标不存在", 404)
        if result.status == "already":
            return ok(message="该数据已删除，无需重复操作")
        _audit(audit, request, session, key, record_id, is_delete=True,
               before=result.before, after=result.after)
        return ok(message="删除成功")

    return endpoint


router.add_api_route(
    "/records/{record_id}/delete",
    _delete_endpoint("record", True),
    methods=["POST"],
)
router.add_api_route(
    "/standards/{record_id}/delete",
    _delete_endpoint("standard", True),
    methods=["POST"],
)
router.add_api_route(
    "/switch-logs/{record_id}/delete",
    _delete_endpoint("switch_log", True),
    methods=["POST"],
)
router.add_api_route(
    "/reviews/{record_id}/delete",
    _delete_endpoint("review", True),
    methods=["POST"],
)


# ---------------------------------------------------------------------------
# 恢复
# ---------------------------------------------------------------------------

def _restore_endpoint(key: str):
    def endpoint(
        record_id: int,
        request: Request,
        session: Session = Depends(require_permission(P.ACTION_MANAGE_DATA)),
        uc: ManageDataUseCase = Depends(get_manage_data_uc),
        audit: AuditLogger = Depends(get_audit_logger),
    ):
        result = uc.restore(key, record_id)
        if result.status == "not_found":
            return fail("目标不存在", 404)
        if result.status == "already":
            return ok(message="该数据未删除，无需恢复")
        _audit(audit, request, session, key, record_id, is_delete=False,
               before=result.before, after=result.after)
        return ok(message="恢复成功")

    return endpoint


router.add_api_route(
    "/records/{record_id}/restore",
    _restore_endpoint("record"),
    methods=["POST"],
)
router.add_api_route(
    "/standards/{record_id}/restore",
    _restore_endpoint("standard"),
    methods=["POST"],
)
router.add_api_route(
    "/switch-logs/{record_id}/restore",
    _restore_endpoint("switch_log"),
    methods=["POST"],
)
router.add_api_route(
    "/reviews/{record_id}/restore",
    _restore_endpoint("review"),
    methods=["POST"],
)


# ---------------------------------------------------------------------------
# 改处理状态
# ---------------------------------------------------------------------------

@router.post("/records/{record_id}/processed")
def change_processed(
    record_id: int,
    data: ProcessedRequest,
    request: Request,
    session: Session = Depends(require_permission(P.ACTION_MANAGE_DATA)),
    uc: ManageDataUseCase = Depends(get_manage_data_uc),
    audit: AuditLogger = Depends(get_audit_logger),
):
    bad = _require_reason(data.reason)
    if bad is not None:
        return bad

    result = uc.set_processed(record_id, data.processed, session.username)
    if result.status == "not_found":
        return fail("目标不存在", 404)

    audit.record(
        actor=session.username,
        action=AuditAction.CHANGE_PROCESSED,
        target_type=AuditTarget.SPHEROIDIZATION_RECORD,
        target_id=record_id,
        detail={"before": result.before, "after": result.after, "reason": data.reason},
        ip=client_ip(request),
    )
    return ok(message="处理状态已更新")


# ---------------------------------------------------------------------------
# 全库分页列表（管理员数据管理页的四个 tab，TASK-9）
#
# 球化记录 / 检测标准两个 tab 直接复用现有接口
# （/api/spheroidization、/api/standards/history，均支持 include_deleted），
# 这里只补复核记录、切换记录两个全库列表：
# - 现有 /api/reviews/{record_id} 只能按单条球化记录查；
# - 现有 /api/standards/switch-logs 挂的是 page:standard，管理员页只认 action:manage_data。
# 分页结构与 GET /api/spheroidization 一致：{items, total, page, page_size, has_more}。
# ---------------------------------------------------------------------------

@router.get("/reviews")
def list_all_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    include_deleted: bool = Query(False),
    session: Session = Depends(require_permission(P.ACTION_MANAGE_DATA)),
    uc: QueryReviewUseCase = Depends(get_query_review_uc),
):
    records, total = uc.list_all_page(
        page, page_size, include_deleted=include_deleted
    )
    return ok(
        {
            "items": [review_to_response(record) for record in records],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": page * page_size < total,
        }
    )


@router.get("/switch-logs")
def list_all_switch_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    include_deleted: bool = Query(False),
    session: Session = Depends(require_permission(P.ACTION_MANAGE_DATA)),
    uc: SwitchStandardUseCase = Depends(get_switch_standard_uc),
):
    items = []
    for log, from_standard, to_standard in uc.list_logs(
        page, page_size, include_deleted=include_deleted
    ):
        item = switch_log_to_response(log)
        # 两条标准的球化时长，前端显示"标准X（Ys）"；
        # 标准被作废（软删）后 get_by_id 查不到，给 None，前端显示 —。
        item["from_value"] = (
            from_standard.standard_spheroidization_time
            if from_standard is not None
            else None
        )
        item["to_value"] = (
            to_standard.standard_spheroidization_time
            if to_standard is not None
            else None
        )
        items.append(item)

    total = uc.count_logs(include_deleted=include_deleted)
    return ok(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": page * page_size < total,
        }
    )
