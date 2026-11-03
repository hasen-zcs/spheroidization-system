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

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.core import permissions as P
from app.core.security import Session
from app.dependencies import Container, get_audit_logger, get_container, require_permission
from app.domain.audit.entities import AuditAction, AuditTarget
from app.domain.audit.service import AuditLogger, client_ip
from app.schemas.common import fail, ok

router = APIRouter(
    prefix="/api/admin",
    tags=["管理员数据管理"],
)


def _now() -> str:
    """当前时间，格式和其它表一致："YYYY-MM-DD HH:MM:SS"。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# 四类可软删数据的表配置：key -> (表名, 主键列, 审计要留痕的关键字段)。
# 关键字段刻意不含 spheroidization_image（BLOB，几十 KB，绝不能进审计 detail）。
_TABLES = {
    "record": (
        "SpheroidizationRecord",
        "spheroidization_record_id",
        ("detection_time", "processed", "processed_by", "processed_at"),
    ),
    "standard": (
        "StandardRecord",
        "standard_record_id",
        ("standard_spheroidization_time", "weighing_standard", "created_by"),
    ),
    "switch_log": (
        "StandardSwitchLogs",
        "switch_log_id",
        ("switched_at", "from_standard_record_id", "to_standard_record_id", "operated_by", "reason"),
    ),
    "review": (
        "ReviewRecord",
        "review_record_id",
        ("spheroidization_record_id", "review_result", "reviewer"),
    ),
}


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


def _fetch_row(conn, table: str, pk: str, record_id: int):
    """按主键取整行（含已删除的），查不到返回 None。"""
    return conn.execute(
        f'SELECT * FROM "{table}" WHERE {pk} = ?', (record_id,)
    ).fetchone()


def _snapshot(row, key_fields) -> dict:
    """审计留痕的关键字段快照：业务关键字段 + 软删除三列。不含图片 BLOB。"""
    data = {k: row[k] for k in key_fields}
    data["deleted_at"] = row["deleted_at"]
    data["deleted_by"] = row["deleted_by"]
    data["delete_reason"] = row["delete_reason"]
    return data


def _soft_delete(conn, key: str, record_id: int, actor: str, reason: str):
    """软删除。返回 (状态, before, after)。

    状态：not_found=行不存在 / already=已删除（幂等）/ created=本次真的删了。
    """
    table, pk, key_fields = _TABLES[key]
    row = _fetch_row(conn, table, pk, record_id)
    if row is None:
        return "not_found", None, None
    if row["deleted_at"] is not None:
        return "already", None, None
    before = _snapshot(row, key_fields)
    now = _now()
    with conn:
        conn.execute(
            f'UPDATE "{table}" SET deleted_at=?, deleted_by=?, delete_reason=?'
            f' WHERE {pk}=? AND deleted_at IS NULL',
            (now, actor, reason, record_id),
        )
    after = _snapshot(_fetch_row(conn, table, pk, record_id), key_fields)
    return "created", before, after


def _restore(conn, key: str, record_id: int):
    """恢复（清空软删除三列）。返回 (状态, before, after)。"""
    table, pk, key_fields = _TABLES[key]
    row = _fetch_row(conn, table, pk, record_id)
    if row is None:
        return "not_found", None, None
    if row["deleted_at"] is None:
        return "already", None, None
    before = _snapshot(row, key_fields)
    with conn:
        conn.execute(
            f'UPDATE "{table}" SET deleted_at=NULL, deleted_by=NULL, delete_reason=NULL'
            f' WHERE {pk}=? AND deleted_at IS NOT NULL',
            (record_id,),
        )
    after = _snapshot(_fetch_row(conn, table, pk, record_id), key_fields)
    return "created", before, after


def _set_processed(conn, record_id: int, processed: int, actor: str):
    """改球化记录人工处理状态。返回 (状态, before, after)。"""
    key_fields = _TABLES["record"][2]
    table, pk = _TABLES["record"][:2]
    row = _fetch_row(conn, table, pk, record_id)
    if row is None:
        return "not_found", None, None
    before = _snapshot(row, key_fields)
    with conn:
        if processed == 1:
            # 表上 CHECK：processed=1 时 by/at 必须齐
            conn.execute(
                "UPDATE SpheroidizationRecord"
                " SET processed=1, processed_by=?, processed_at=?"
                " WHERE spheroidization_record_id=?",
                (actor, _now(), record_id),
            )
        else:
            # 表上 CHECK：processed=0 时 by/at 必须全空
            conn.execute(
                "UPDATE SpheroidizationRecord"
                " SET processed=0, processed_by=NULL, processed_at=NULL"
                " WHERE spheroidization_record_id=?",
                (record_id,),
            )
    after = _snapshot(_fetch_row(conn, table, pk, record_id), key_fields)
    return "created", before, after


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
        container: Container = Depends(get_container),
        audit: AuditLogger = Depends(get_audit_logger),
    ):
        bad = _require_reason(data.reason) if need_reason else None
        if bad is not None:
            return bad

        # 当前生效标准不许软删：删了它"当前标准"就悬空了。
        if key == "standard":
            current = container.query_standard().get_current()
            if current is not None and current.standard_record_id == record_id:
                return fail("该标准当前生效，请先切换标准后再作废", 400)

        status, before, after = _soft_delete(
            container.conn, key, record_id, session.username, data.reason
        )
        if status == "not_found":
            return fail("目标不存在", 404)
        if status == "already":
            return ok(message="该数据已删除，无需重复操作")
        _audit(audit, request, session, key, record_id, is_delete=True,
               before=before, after=after)
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
        container: Container = Depends(get_container),
        audit: AuditLogger = Depends(get_audit_logger),
    ):
        status, before, after = _restore(container.conn, key, record_id)
        if status == "not_found":
            return fail("目标不存在", 404)
        if status == "already":
            return ok(message="该数据未删除，无需恢复")
        _audit(audit, request, session, key, record_id, is_delete=False,
               before=before, after=after)
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
    container: Container = Depends(get_container),
    audit: AuditLogger = Depends(get_audit_logger),
):
    bad = _require_reason(data.reason)
    if bad is not None:
        return bad

    status, before, after = _set_processed(
        container.conn, record_id, data.processed, session.username
    )
    if status == "not_found":
        return fail("目标不存在", 404)

    audit.record(
        actor=session.username,
        action=AuditAction.CHANGE_PROCESSED,
        target_type=AuditTarget.SPHEROIDIZATION_RECORD,
        target_id=record_id,
        detail={"before": before, "after": after, "reason": data.reason},
        ip=client_ip(request),
    )
    return ok(message="处理状态已更新")
