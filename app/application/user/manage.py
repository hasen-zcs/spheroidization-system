from app.core.exceptions import BusinessException
from app.core.security import hash_password, validate_password_policy, verify_password
from app.domain.user.entities import UserAccount
from app.domain.user.repositories import UserAccountRepository


class UserAccountManageUseCase:
    """
    账号本身的维护：重置密码、启用 / 停用。

    单独成一个用例而不是塞进 CreateUserUseCase 或 QueryUserUseCase：
    那两个一个管"建"、一个管"读"，把"改"混进去以后调用方分不清
    哪个类该用哪个方法。账号只有这三种操作，分三个类刚好。

    业务规则
    --------
    - 目标账号必须存在，不存在按 404 报。
    - 密码在这一层哈希，实体里只存哈希。
    - 停用只是把 enabled 置 0，不删除账号；登录时目前不校验 enabled
      （老板 2026-10-28 明确不考虑禁用用户），需要时再在登录处加上判断。

    依赖：UserAccountRepository
    """

    def __init__(self, user_repo: UserAccountRepository):
        self.user_repo = user_repo

    def _ensure_user(self, user_id: int) -> UserAccount:
        user = self.user_repo.get_by_id(user_id)
        if user is None:
            raise BusinessException(f"用户不存在：user_id={user_id}", 404)
        return user

    @staticmethod
    def _ensure_password_policy(new_password: str) -> None:
        """密码强度策略（长度 ≥8 + 字母 + 数字）。不满足报 422，写明缺什么。

        自查改密和管理员重置都过这道闸：弱密码不再静默接受。
        """
        problems = validate_password_policy(new_password)
        if problems:
            raise BusinessException(
                "新密码不符合策略：" + "、".join(problems), 422
            )

    def change_password(
        self, user_id: int, old_password: str, new_password: str
    ) -> None:
        """自查改密：先验旧密码，再套新密码策略。

        - 旧密码错误 → 400
        - 新密码与旧密码相同 → 422
        - 新密码不满足策略 → 422
        """
        user = self._ensure_user(user_id)
        if not verify_password(old_password, user.password_hash):
            raise BusinessException("旧密码不正确", 400)
        if old_password == new_password:
            raise BusinessException("新密码不能与旧密码相同", 422)
        self._ensure_password_policy(new_password)
        try:
            password_hash = hash_password(new_password)
        except ValueError as exc:
            raise BusinessException(str(exc)) from exc
        self.user_repo.update_password(user_id, password_hash)

    def reset_password(self, user_id: int, new_password: str) -> None:
        """重置密码。传进来的明文在这里哈希，之后就不存在了。"""
        self._ensure_user(user_id)
        self._ensure_password_policy(new_password)
        try:
            password_hash = hash_password(new_password)
        except ValueError as exc:
            # bcrypt 只吃 72 字节以内，超了要给出能看懂的提示
            raise BusinessException(str(exc)) from exc
        self.user_repo.update_password(user_id, password_hash)

    def set_enabled(self, user_id: int, enabled: int) -> None:
    
        self._ensure_user(user_id)

        if enabled not in (0, 1):
            raise BusinessException("账号状态只能是 0 或 1")

        self.user_repo.set_enabled(user_id, enabled)
