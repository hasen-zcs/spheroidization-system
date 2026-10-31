"""账号与权限的路由。

登录、注销、查自己这三个接口免权限（登录本身当然不能要求先登录）；
其余全部挂 action:manage_users。
不提供删除账号的接口：账号只停用不删除，否则历史记录里的操作人就断链了。
"""

from fastapi import APIRouter, Depends, Request

from app.application.user.auth import LoginUseCase
from app.application.user.create import CreateUserUseCase
from app.application.user.manage import UserAccountManageUseCase
from app.application.user.permission import UserPermissionUseCase
from app.application.user.query import QueryUserUseCase
from app.core import permissions as P
from app.core.security import Session, revoke_token
from app.dependencies import (
    _extract_bearer,
    get_create_user_uc,
    get_login_uc,
    get_manage_user_uc,
    get_query_user_uc,
    get_user_permission_uc,
    require_login,
    require_permission,
)
from app.schemas.common import ok
from app.schemas.user import (
    EnabledRequest,
    LoginRequest,
    PasswordResetRequest,
    PermissionSetRequest,
    UserCreateRequest,
    to_response,
)

router = APIRouter(
    prefix="/api/users",
    tags=["账号权限"],
)


@router.post("/login")
def login(
    data: LoginRequest,
    uc: LoginUseCase = Depends(get_login_uc),
):
    # 失败只有一句"用户名或密码不正确"，由 LoginUseCase 抛，
    # 走 main.py 的统一处理器。这里不做任何额外的错误分支。
    payload = uc.execute(username=data.username, password=data.password)
    # 前端契约（2026-10-28 接口说明）：data = {token, user:{username,is_admin,
    # permission_keys}}。扁平字段保留一版做兼容，等前端全面切到 user 再删。
    payload["user"] = {
        "username": payload["username"],
        "is_admin": payload["is_admin"],
        "permission_keys": payload["permissions"],
    }
    return ok(payload, "登录成功")


@router.post("/logout")
def logout(
    request: Request,
    session: Session = Depends(require_login),
):
    token = _extract_bearer(request)
    revoke_token(token)
    # 必须返回信封：不写 return 的话响应体是字面量 null，
    # 前端读 body.code 直接抛异常，看着像后端挂了。
    return ok(None, "已退出登录")

@router.get("/me")
def me(session: Session = Depends(require_login)):
    # 前端刷新页面后靠这个接口恢复登录态，不用把 token 解出来自己猜
    return ok(
        {
            "username": session.username,
            "is_admin": session.is_admin,
            # 前端读 permission_keys；permissions 保留兼容
            "permission_keys": sorted(session.permissions),
            "permissions": sorted(session.permissions),
            "user_id": session.user_id,
        }
    )


@router.get("")
def list_users(
    session: Session = Depends(require_permission(P.ACTION_MANAGE_USERS)),
    uc: QueryUserUseCase = Depends(get_query_user_uc),
):
    return ok(
        [
            to_response(user, sorted(permission_keys))
            for user, permission_keys in uc.list_all()
        ]
    )


@router.post("")
def create_user(
    data: UserCreateRequest,
    session: Session = Depends(require_permission(P.ACTION_MANAGE_USERS)),
    uc: CreateUserUseCase = Depends(get_create_user_uc),
):
    # created_by 从登录态取：谁建的号，事后要查得到
    user = uc.execute(
        username=data.username,
        password=data.password,
        is_admin=data.is_admin,
        created_by=session.username,
    )
    return ok(to_response(user, []), "用户创建成功")


@router.put("/{user_id}/permissions")
def set_permissions(
    user_id: int,
    data: PermissionSetRequest,
    session: Session = Depends(require_permission(P.ACTION_MANAGE_USERS)),
    uc: UserPermissionUseCase = Depends(get_user_permission_uc),
):
    # 整体覆盖：前端把勾选框里的全部提交上来，后端先删后插。
    # 权限变更对已登录的人不实时生效，要对方重新登录（权限在登录时快照）。
    keys = uc.replace(user_id, data.permission_keys)
    return ok(sorted(keys), "权限已更新")


@router.post("/{user_id}/password")
def reset_password(
    user_id: int,
    data: PasswordResetRequest,
    session: Session = Depends(require_permission(P.ACTION_MANAGE_USERS)),
    uc: UserAccountManageUseCase = Depends(get_manage_user_uc),
):
    uc.reset_password(user_id, data.new_password)
    return ok(None, "密码已重置")


@router.put("/{user_id}/enabled")
def set_enabled(
    user_id: int,
    data: EnabledRequest,
    session: Session = Depends(require_permission(P.ACTION_MANAGE_USERS)),
    uc: UserAccountManageUseCase = Depends(get_manage_user_uc),
):
    uc.set_enabled(user_id, data.enabled)
    return ok(
    None,
    "已启用" if data.enabled == 1 else "已停用"
)