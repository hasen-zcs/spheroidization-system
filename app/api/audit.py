"""审计日志的查询路由。

只读：谁在何时改了什么，管理员才能翻。
写入入口在 domain/audit/service.py 的 AuditLogger，各写接口各自调用。
"""

from fastapi import APIRouter, Depends, Query

from app.core import permissions as P
from app.core.security import Session
from app.dependencies import get_audit_repo, require_permission
from app.domain.audit.repositories import AuditRepository
from app.schemas.audit import to_response
from app.schemas.common import ok

router = APIRouter(
    prefix="/api/audit",
    tags=["审计日志"],
)


@router.get("")
def list_audit_logs(
    start: str | None = Query(None, description="起始时间 YYYY-MM-DD HH:MM:SS，闭区间"),
    end: str | None = Query(None, description="截止时间 YYYY-MM-DD HH:MM:SS，闭区间"),
    actor: str | None = Query(None, description="按操作人过滤"),
    action: str | None = Query(None, description="按动作码过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(require_permission(P.ACTION_MANAGE_USERS)),
    repo: AuditRepository = Depends(get_audit_repo),
):
    # 审计账本只给管理员翻：超管直接放行，其余要 action:manage_users。
    # 游客 401、没权限 403，由 require_permission 统一给出（信封 code）。
    items, total = repo.list_records(
        actor=actor,
        action=action,
        start=start,
        end=end,
        page=page,
        page_size=page_size,
    )
    return ok(
        {
            "items": [to_response(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )
