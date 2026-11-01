"""审计日志的响应结构。"""

from app.domain.audit.entities import AuditLog


def to_response(log: AuditLog) -> dict:
    """实体转响应。detail 原样返回（JSON 字符串或 None），前端自己解析。"""
    return {
        "audit_id": log.audit_id,
        "actor": log.actor,
        "action": log.action,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "detail": log.detail,
        "ip": log.ip,
        "created_at": log.created_at,
    }
