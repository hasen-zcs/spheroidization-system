from dataclasses import dataclass


@dataclass
class UserAccount:
    username: str
    password_hash: str
    created_by: str
    # 创建时间，由仓储实现方生成，调用方不传。
    # 和 StandardRecord / ReviewRecord 一样给默认值，
    # 由 Xxx(**dict(row)) 直接构造时也不用额外补字段。
    created_at: str | None = None
    enabled: int = 1
    # 账号是否启用，1 表示启用，0 表示禁用，默认启用。
    is_admin: int = 0
    #是否为管理员，1 表示管理员，0 表示普通用户，默认普通用户。
    user_id: int | None = None