"""账号与权限的请求 / 响应模型。

UserResponse 里没有 password_hash，这是安全边界的一部分：
路由把实体转成响应时显式列字段，不要图省事 model(**user.__dict__)，
那样会把哈希直接带出去。
"""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    is_admin: bool
    permissions: list[str]


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str
    # 请求里用 bool，落库前转成 0 / 1，跟 spheroidization_abnormal 的习惯一致
    is_admin: bool = False


class PermissionSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 整体覆盖用：前端把勾选框里选中的全部提交上来
    permission_keys: list[str]


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str


class SelfPasswordChangeRequest(BaseModel):
    """自查改密的入参。两个字段都要给：旧密码用来确认本人，新密码过策略。"""

    model_config = ConfigDict(extra="forbid")

    old_password: str
    new_password: str


class EnabledRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: int = Field(ge=0, le=1)


class UserResponse(BaseModel):
    """账号响应。字段是显式列的，**不含 password_hash**。"""

    id: int
    username: str
    enabled: bool
    is_admin: bool
    created_by: str
    created_at: str | None = None
    permissions: list[str] = []


def to_response(user, permissions: list[str]) -> dict:
    """实体 -> 前端契约。主键从 user_id 映射成 id，0/1 转布尔。

    permissions 由调用方查好传进来：实体本身不持有权限，
    权限在 UserPermission 表里单独存。
    """
    return {
        "id": user.user_id,
        "username": user.username,
        "enabled": bool(user.enabled),
        "is_admin": bool(user.is_admin),
        "created_by": user.created_by,
        "created_at": user.created_at,
        # 2026-10-31 对齐《前端登录与用户接口说明》：前端读 permission_keys。
        # permissions 保留一版做兼容，等前端不再读它再删。
        "permission_keys": permissions,
        "permissions": permissions,
    }
