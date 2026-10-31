from typing import Iterable

from app.core.exceptions import BusinessException
from app.core.permissions import is_known_permission
from app.domain.user.repositories import (
    UserAccountRepository,
    UserPermissionRepository,
)


class UserPermissionUseCase:
    """
    查看和调整某个用户的权限点。

    业务规则
    --------
    - 用户必须存在，不存在按 404 报。
    - 权限点必须在常量集合内。拼错的 key 写进库不会报错，只会变成
      一条永远不生效的幽灵权限，用户还以为给了——所以在入口挡掉。
    - 超管（is_admin=1）的权限表允许改，但不影响实际放行：
      鉴权时超管直接短路放行，权限表写什么都不看。用户管理页要提示
      "该账号是管理员，拥有全部权限"，免得运维在那勾半天没效果。

    依赖：UserAccountRepository、UserPermissionRepository
    """

    def __init__(
        self,
        user_repo: UserAccountRepository,
        permission_repo: UserPermissionRepository,
    ):
        self.user_repo = user_repo
        self.permission_repo = permission_repo

    def _ensure_user(self, user_id: int) -> None:
        if self.user_repo.get_by_id(user_id) is None:
            raise BusinessException(f"用户不存在：user_id={user_id}", 404)

    @staticmethod
    def _ensure_known(key: str) -> None:
        if not is_known_permission(key):
            raise BusinessException(f"未知权限点：{key}")

    def list(self, user_id: int) -> set[str]:
        """查某个用户当前拥有的权限点。"""
        self._ensure_user(user_id)
        return self.permission_repo.list_keys_by_user(user_id)

    def grant(self, user_id: int, key: str) -> None:
        """给用户加一个权限点。"""
        self._ensure_user(user_id)
        self._ensure_known(key)
        self.permission_repo.grant(user_id, key)

    def revoke(self, user_id: int, key: str) -> None:
        """去掉用户的一个权限点。"""
        self._ensure_user(user_id)
        self._ensure_known(key)
        self.permission_repo.revoke(user_id, key)

    def replace(self, user_id: int, keys: Iterable[str]) -> set[str]:
        """整体覆盖用户的权限，用户管理页"保存"走这个。

        先把所有 key 校验一遍再落库，不要边校边写：
        边校边写会在遇到第一个非法 key 时留下"写了一半"的权限集合。
        """
        self._ensure_user(user_id)
        key_list = list(dict.fromkeys(keys))  # 去重且保持顺序
        for key in key_list:
            self._ensure_known(key)

        self.permission_repo.replace_all(user_id, key_list)
        return set(key_list)
