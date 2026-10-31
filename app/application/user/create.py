from app.core.exceptions import BusinessException
from app.core.security import MAX_PASSWORD_BYTES, hash_password
from app.domain.user.entities import UserAccount
from app.domain.user.repositories import UserAccountRepository


# 用户名长度上限
MAX_USERNAME_LENGTH = 32


class CreateUserUseCase:
    """
    新建登录账号。

    业务规则：
    1. 用户名去除首尾空格后不能为空，长度不超过 32。
    2. 用户名不能重复。
    3. 密码经过哈希处理后保存，不保存明文密码。
    4. created_by 由路由层从已验证的登录状态获取。
    5. 新账号默认没有任何页面或操作权限。
    """

    def __init__(self, user_repo: UserAccountRepository):
        self.user_repo = user_repo

    def execute(
        self,
        username: str,
        password: str,
        is_admin: int,
        created_by: str,
    ) -> UserAccount:
        """
        创建用户账号。

        :param username: 登录用户名
        :param password: 明文密码，仅用于哈希
        :param is_admin: 管理员标识，只能为 0 或 1
        :param created_by: 创建人，由路由层从登录状态获取
        :return: 创建成功后的用户实体
        """

        # 1. 检查用户名
        name = username.strip()

        if not name:
            raise BusinessException("用户名不能为空")

        if len(name) > MAX_USERNAME_LENGTH:
            raise BusinessException(
                f"用户名不能超过 {MAX_USERNAME_LENGTH} 个字符"
            )

        # 2. 检查管理员标识
        #    路由层传进来的是 Pydantic 的 bool（True/False），实体存的是 0/1 整数。
        #    这里两种都收：bool 先换成 int 再统一校验。
        #    不能用 type(is_admin) is not int 来挡——bool 虽然是 int 的子类，
        #    type(True) 却是 bool，那样从接口建管理员（is_admin=true）会被自己挡住。
        if isinstance(is_admin, bool):
            is_admin = int(is_admin)
        if is_admin not in (0, 1):
            raise BusinessException("管理员标识只能是 0 或 1")

        # 3. 检查密码长度
        if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise BusinessException(
                f"密码不能超过 {MAX_PASSWORD_BYTES} 字节"
            )

        # 4. 检查用户名是否重复
        if self.user_repo.get_by_username(name) is not None:
            raise BusinessException("用户名已存在")

        # 5. 对密码进行哈希处理
        try:
            password_hash = hash_password(password)
        except ValueError as exc:
            raise BusinessException(str(exc)) from exc

        # 6. 创建用户实体
        new_user = UserAccount(
            username=name,
            password_hash=password_hash,
            created_by=created_by,
            is_admin=is_admin,
            enabled=1,
        )

        # 7. 保存用户
        return self.user_repo.save(new_user)