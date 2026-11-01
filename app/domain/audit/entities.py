"""审计日志实体与常量。

动作码一律用字符串，和 AuditLog 表里存的完全一致，
不要改成 Enum 再往库里塞（理由同 permissions.py 的权限点）。
"""

from dataclasses import dataclass


class AuditAction:
    """写操作的动作码，对应 AuditLog.action。"""

    CREATE_STANDARD = "create_standard"  # 新建检测标准
    SWITCH_STANDARD = "switch_standard"  # 切换当前标准
    PROCESS_RECORD = "process_record"  # 人工处置球化记录
    REVIEW_RECORD = "review_record"  # 人工复核
    CREATE_USER = "create_user"  # 建账号
    CHANGE_PASSWORD = "change_password"  # 重置密码
    GRANT_PERMISSION = "grant_permission"  # 权限变更（整体覆盖）


class AuditTarget:
    """对象类型，对应 AuditLog.target_type。"""

    STANDARD = "standard"
    SPHEROIDIZATION_RECORD = "spheroidization_record"
    REVIEW = "review"
    USER = "user"


@dataclass
class AuditLog:
    """一条审计记录。

    约定：
    - audit_id / created_at 由仓储实现方生成并回填，调用方传 None。
    - detail 是 JSON 字符串（或 None），存改前/改后关键字段摘要。
      **禁止把密码、令牌等敏感明文写进 detail。**
    - target_id 统一存字符串：不同表的 ID 都是数字，但 TEXT 列存
      字符串最省心，查询接口按字符串过滤也对得上。
    """

    audit_id: int | None
    actor: str
    action: str
    target_type: str
    target_id: str | None = None
    detail: str | None = None
    ip: str | None = None
    created_at: str | None = None
