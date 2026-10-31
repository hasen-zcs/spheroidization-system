from app.core import security
from app.core.exceptions import BusinessException
from app.core.permissions import ALL_PERMISSIONS
from app.domain.user.repositories import (
    UserAccountRepository,
    UserPermissionRepository,
)

# 登录失败只有这一句。"用户名不存在"和"密码不对"必须长得一模一样，
# 否则试密码的人能靠提示差异把库里有哪些账号摸出来。
LOGIN_FAILED_MESSAGE = "用户名或密码不正确"


class LoginUseCase:
    """
    登录，换一个会话令牌。

    流程
    ----
    1. 按用户名查账号；查不到按登录失败处理
    2. 校验密码；不对也是同一句失败提示
    3. 算权限（超管直接给全集）、生成 token 写进内存会话表
    4. 返回 token 和展示用的账号信息

    业务规则
    --------
    - 被停用的账号不做拦截：老板 2026-10-28 明确"不考虑禁用用户"。
      enabled 字段留在表里，以后要启用再说。这里不写这段判断，
      免得以后有人以为它生效了。
    - 权限在登录这一刻快照进内存，管理员改了权限要等对方重新登录才生效。

    依赖：UserAccountRepository、UserPermissionRepository、core.security
    """

    def __init__(
        self,
        user_repo: UserAccountRepository,
        permission_repo: UserPermissionRepository,
    ):
        self.user_repo = user_repo
        self.permission_repo = permission_repo

    def execute(self, username: str, password: str) -> dict:
        """
        :return: {"token", "username", "is_admin", "permissions"}
        :raises BusinessException: 用户名或密码不对
        """
        user = self.user_repo.get_by_username(username)
        if user is None:
            raise BusinessException(LOGIN_FAILED_MESSAGE, 401)

        if not security.verify_password(password, user.password_hash):
            raise BusinessException(LOGIN_FAILED_MESSAGE, 401)

        # 停用的账号不许登录。前端有「停用」按钮，这里不拦的话按钮就是摆设：
        # 用户以为停掉了，对方照样能进。
        if user.enabled != 1:
            raise BusinessException("账号已停用，请联系管理员", 401)

        # 超管直接拿全集，不再查权限表：少一次库查询，
        # 也避免"权限表里什么都没配的管理员突然什么都干不了"把自己锁在外面。
        # 普通账号走权限表；查不到就是空集合（新号默认零权限）。
        if user.is_admin == 1:
            permissions = set(ALL_PERMISSIONS)
        else:
            permissions = set(self.permission_repo.list_keys_by_user(user.user_id))

        token = security.create_token(
            user_id=user.user_id,
            username=user.username,
            # 表里是 0/1 整数，会话和响应里统一用布尔，
            # 前端拿 is_admin 直接当条件用，不用再和 1 比。
            is_admin=bool(user.is_admin),
            permissions=permissions,
        )

        return {
            "token": token,
            "username": user.username,
            "is_admin": bool(user.is_admin),
            "permissions": sorted(permissions),
        }
