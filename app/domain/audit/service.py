"""审计日志的写入封装：路由层只认这一层，不直接碰仓储。

策略（明确写死，测试也要按这个断言）：
**审计写入失败只记日志，不抛异常、不回滚业务。**
审计是旁路留痕，主业务（建标准、处置、复核……）已经提交成功，
不能因为审计表出故障就把用户的操作打回去——那是拿留痕功能绑架主流程。
代价是极端情况下会丢一条审计，属于可接受风险。
"""

import json
import logging
from datetime import datetime

from app.domain.audit.entities import AuditLog
from app.domain.audit.repositories import AuditRepository

logger = logging.getLogger("app.audit")


def client_ip(request) -> str | None:
    """从 FastAPI Request 里取客户端 IP，取不到返回 None，不抛异常。"""
    try:
        return request.client.host if request.client else None
    except Exception:
        return None


class AuditLogger:
    """一次一个 record() 调用 = 一条审计。detail 支持传 dict，内部转 JSON。"""

    def __init__(self, repo: AuditRepository):
        self._repo = repo

    def record(
        self,
        actor: str,
        action: str,
        target_type: str,
        target_id: int | str | None = None,
        detail: dict | str | None = None,
        ip: str | None = None,
    ) -> None:
        """
        写一条审计记录。任何异常都只记日志，绝不向调用方传播。
        :param actor: 操作人（登录账号），由路由从登录态取
        :param action: AuditAction 里的动作码
        :param target_type: AuditTarget 里的对象类型
        :param target_id: 对象 ID，可空；数字会被转成字符串入库
        :param detail: 关键字段摘要；传 dict 时转成 JSON 字符串。
                       调用方自己保证不含密码/令牌明文
        """
        try:
            if detail is not None and not isinstance(detail, str):
                detail = json.dumps(detail, ensure_ascii=False)
            self._repo.add(
                AuditLog(
                    audit_id=None,  # 主键由数据库自增分配
                    actor=actor,
                    action=action,
                    target_type=target_type,
                    target_id=(
                        None if target_id is None else str(target_id)
                    ),
                    detail=detail,
                    ip=ip,
                    created_at=None,  # 由仓储实现方生成
                )
            )
        except Exception:
            # 审计失败不阻断业务：只留一条服务端日志方便事后发现
            logger.exception(
                "审计日志写入失败（不影响主业务）：actor=%s action=%s",
                actor,
                action,
            )
