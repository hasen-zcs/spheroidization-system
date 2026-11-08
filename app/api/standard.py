"""检测标准的路由。

只做四件事：收请求 → 转参数 → 调 UseCase → 包响应。
"""

from fastapi import APIRouter, Depends, Query, Request

from app.application.admin.manage import ManageDataUseCase
from app.application.standard.create import CreateStandardUseCase
from app.application.standard.query import QueryStandardUseCase
from app.application.standard.switch import SwitchStandardUseCase
from app.application.standard.update import UpdateStandardUseCase
from app.core import permissions as P
from app.core.security import Session
from app.dependencies import (
    get_audit_logger,
    get_create_standard_uc,
    get_manage_data_uc,
    get_query_standard_uc,
    get_switch_standard_uc,
    get_update_standard_uc,
    require_login,
    require_permission,
)
from app.domain.audit.entities import AuditAction, AuditTarget
from app.domain.audit.service import AuditLogger, client_ip
from app.schemas.common import fail, ok
from app.schemas.standard import (
    StandardCreateRequest,
    StandardDeleteRequest,
    StandardSwitchRequest,
    StandardUpdateRequest,
    switch_log_to_response,
    to_response,
)

router = APIRouter(
    prefix="/api/standards",
    tags=["检测标准"],
)


def _switch_summary(log, from_standard, to_standard) -> str:
    """拼一句给人看的中文文案，前端直接显示。

    switched_at 是 "YYYY-MM-DD HH:MM:SS"，需求模板只要日期，取前 10 位。
    原标准可能为空（库里还没有标准时的第一次切换），要能处理 None——
    直接 f"{None}" 会显示成字面的 "None"，比不显示还糟。
    """
    from_text = (
        f"标准{from_standard.standard_record_id}"
        f"（{from_standard.standard_spheroidization_time:g}s）"
        if from_standard is not None
        else "（无）"
    )
    to_text = (
        f"标准{to_standard.standard_record_id}"
        f"（{to_standard.standard_spheroidization_time:g}s）"
        if to_standard is not None
        else "（无）"
    )
    return (
        f"{log.switched_at[:10]} 从{from_text}切换到{to_text}，原因：{log.reason}"
    )


@router.post("")
def create_standard(
    data: StandardCreateRequest,
    request: Request,
    session: Session = Depends(require_permission(P.ACTION_CREATE_STANDARD)),
    uc: CreateStandardUseCase = Depends(get_create_standard_uc),
    audit: AuditLogger = Depends(get_audit_logger),
):
    # 标准只增不改：创建一条新的，它立即成为当前有效标准，历史标准全部保留。
    # 创建人从登录态取，不读 data.created_by。
    standard = uc.execute(
        standard_spheroidization_time=data.standard_spheroidization_time,
        weighing_standard=data.weighing_standard,
        created_by=session.username,
        standard_spheroidization_time_upper=data.standard_spheroidization_time_upper,
        standard_spheroidization_time_lower=data.standard_spheroidization_time_lower,
        remark=data.remark,
    )
    # 审计留痕：业务已提交成功才写；写入失败只记日志，不影响响应
    audit.record(
        actor=session.username,
        action=AuditAction.CREATE_STANDARD,
        target_type=AuditTarget.STANDARD,
        target_id=standard.standard_record_id,
        detail={
            "standard_spheroidization_time": standard.standard_spheroidization_time,
            "weighing_standard": standard.weighing_standard,
            "remark": standard.remark,
        },
        ip=client_ip(request),
    )
    return ok(to_response(standard), "标准创建成功")


# 注意：/current、/history、/switch、/switch-logs 必须声明在 /{standard_id}
# 之前，否则 "switch" 会被当成 standard_id 去转 int，直接 422。
@router.get("/current")
def get_current_standard(
    uc: QueryStandardUseCase = Depends(get_query_standard_uc),
):
    # 不挂权限：监控页要显示当前标准，游客也要能看到。
    standard = uc.get_current()
    # 一条标准都没有时返回 null。
    # 不要写成 standards[-1] 那种取法——空表会 IndexError，变成 500。
    return ok(to_response(standard) if standard else None)


@router.get("/history")
def get_standard_history(
    include_deleted: bool = Query(False),
    session: Session = Depends(require_login),
    uc: QueryStandardUseCase = Depends(get_query_standard_uc),
):
    # 登录即可，不挂 page:standard：监控页的切换卡片要及时列出历史标准，
    # 而浇筑工只有 action:switch_standard、没有 page:standard，
    # 挂页面权限会把那张卡片直接打死。游客依然看不到（需要登录）。
    # 看已删除标准是管理动作：要 action:manage_data，无权限 403。
    # 这里已经 require_login，session 必非空，只判权限。
    if (
        include_deleted
        and not session.is_admin
        and P.ACTION_MANAGE_DATA not in session.permissions
    ):
        return fail("没有该操作权限", 403)
    return ok(
        [
            to_response(standard)
            for standard in uc.get_history(include_deleted=include_deleted)
        ]
    )


@router.post("/switch")
def switch_standard(
    data: StandardSwitchRequest,
    request: Request,
    session: Session = Depends(require_permission(P.ACTION_SWITCH_STANDARD)),
    uc: SwitchStandardUseCase = Depends(get_switch_standard_uc),
    audit: AuditLogger = Depends(get_audit_logger),
):
    # 切换会写日志，日志里的操作人只能是登录态里的人，不能由前端填。
    standard = uc.execute(
        to_standard_record_id=data.to_standard_record_id,
        reason=data.reason,
        operated_by=session.username,
    )
    # 审计留痕：SwitchStandardUseCase 已落 SwitchStandardLogs，
    # 这里再进一条统一格式的审计，方便和别的写操作一起查。
    audit.record(
        actor=session.username,
        action=AuditAction.SWITCH_STANDARD,
        target_type=AuditTarget.STANDARD,
        target_id=standard.standard_record_id,
        detail={
            "to_standard_record_id": data.to_standard_record_id,
            "reason": data.reason,
        },
        ip=client_ip(request),
    )
    return ok(to_response(standard), "标准切换成功")


@router.get("/switch-logs")
def list_switch_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    include_deleted: bool = Query(False),
    session: Session = Depends(require_permission(P.PAGE_STANDARD)),
    uc: SwitchStandardUseCase = Depends(get_switch_standard_uc),
):
    # 能进标准页的人就能看切换历史；action:switch_standard 只管"能不能切"。
    # 两个权限分开，不要合二为一——浇筑工能切但不该翻全厂的切换账。
    # 看已删除切换记录是管理动作：额外要 action:manage_data，无权限 403。
    if (
        include_deleted
        and not session.is_admin
        and P.ACTION_MANAGE_DATA not in session.permissions
    ):
        return fail("没有该操作权限", 403)
    items = []
    for log, from_standard, to_standard in uc.list_logs(
        page, page_size, include_deleted=include_deleted
    ):
        item = switch_log_to_response(log)
        # 结构化字段给前端自己排版，整句文案给前端直接显示
        item["from_standard"] = (
            to_response(from_standard) if from_standard is not None else None
        )
        item["to_standard"] = (
            to_response(to_standard) if to_standard is not None else None
        )
        item["summary"] = _switch_summary(log, from_standard, to_standard)
        # 前端 10-28 契约字段名（from_standard_id / to_value 等），保留原生字段做兼容
        item["from_standard_id"] = log.from_standard_record_id
        item["to_standard_id"] = log.to_standard_record_id
        item["from_value"] = (
            from_standard.standard_spheroidization_time
            if from_standard is not None
            else None
        )
        item["to_value"] = to_standard.standard_spheroidization_time
        items.append(item)

    return ok(
        {
            "items": items,
            "page": page,
            "page_size": page_size,
        }
    )


# /{standard_id} 路由放在所有字面量路由之后（见 /current 上方的注释），
# 否则 "current" / "history" 等会被当成 standard_id 去转 int，直接 422。
@router.put("/{standard_id}")
def update_standard(
    standard_id: int,
    data: StandardUpdateRequest,
    request: Request,
    session: Session = Depends(require_permission(P.ACTION_CREATE_STANDARD)),
    uc: UpdateStandardUseCase = Depends(get_update_standard_uc),
    audit: AuditLogger = Depends(get_audit_logger),
):
    # 修订只改 5 个业务字段；created_at / created_by 由仓储保证不动。
    # 权限和新增共用 action:create_standard（前端"检测标准管理"一个开关管增/改/删）。
    standard = uc.execute(
        standard_record_id=standard_id,
        standard_spheroidization_time=data.standard_spheroidization_time,
        standard_spheroidization_time_upper=data.standard_spheroidization_time_upper,
        standard_spheroidization_time_lower=data.standard_spheroidization_time_lower,
        weighing_standard=data.weighing_standard,
        remark=data.remark,
    )
    # 审计留痕：业务已提交成功才写；写入失败只记日志，不影响响应
    audit.record(
        actor=session.username,
        action=AuditAction.UPDATE_STANDARD,
        target_type=AuditTarget.STANDARD,
        target_id=standard.standard_record_id,
        detail={
            "standard_spheroidization_time": standard.standard_spheroidization_time,
            "standard_spheroidization_time_upper": standard.standard_spheroidization_time_upper,
            "standard_spheroidization_time_lower": standard.standard_spheroidization_time_lower,
            "weighing_standard": standard.weighing_standard,
            "remark": standard.remark,
        },
        ip=client_ip(request),
    )
    return ok(to_response(standard), "标准修改成功")


@router.delete("/{standard_id}")
def delete_standard(
    standard_id: int,
    data: StandardDeleteRequest,
    request: Request,
    session: Session = Depends(require_permission(P.ACTION_CREATE_STANDARD)),
    uc: ManageDataUseCase = Depends(get_manage_data_uc),
    audit: AuditLogger = Depends(get_audit_logger),
):
    # 软删除逻辑不另写：直接复用管理员数据管理的 ManageDataUseCase，
    # 当前生效标准被删时它会抛 400「该标准当前生效，请先切换标准后再作废」，
    # 和 admin 删除端点同一口径。
    result = uc.soft_delete("standard", standard_id, session.username, data.reason)
    if result.status == "not_found":
        return fail("目标不存在", 404)
    if result.status == "already":
        return ok(message="该标准已删除，无需重复操作")
    # 审计 detail 只带业务关键字段 + 软删三列，不含图片 BLOB（ManageDataUseCase 保证）
    audit.record(
        actor=session.username,
        action=AuditAction.DELETE_STANDARD,
        target_type=AuditTarget.STANDARD,
        target_id=standard_id,
        detail={"before": result.before, "after": result.after},
        ip=client_ip(request),
    )
    return ok(message="标准已删除")
