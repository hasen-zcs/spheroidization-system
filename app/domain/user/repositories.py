from abc import ABC, abstractmethod
from typing import Iterable

from app.domain.user.entities import UserAccount


class UserAccountRepository(ABC):
    """
    登录账号仓储抽象接口。实现由 infrastructure 层提供。

    跨方法约定（实现方必须遵守，调用方可依赖）：
    1. 主键由实现方生成：调用方传的实体主键为空，写入后由数据库自增分配，
       实现方回填再返回。
    2. 时间由实现方生成：created_at 调用方不传，格式 "2026-09-05 08:30:15"。
    3. 查单条无结果返回 None。
    4. 不提供删除方法：账号只停用不删除，否则历史操作记录里的
       操作人就对不上了。
    """

    @abstractmethod
    def save(self, user: UserAccount) -> UserAccount:
        """
        新增一个账号，对应 INSERT。
        """
        ...

    @abstractmethod
    def get_by_username(self, username: str) -> UserAccount | None:
        """
        按登录名查账号，登录时用，调用方需要拿到 password_hash 去比对。
        """
        ...

    @abstractmethod
    def get_by_id(self, user_id: int) -> UserAccount | None:
        """按主键查账号，查不到返回 None。"""
        ...

    @abstractmethod
    def list_all(self) -> list[UserAccount]:
        """
        查全部账号。
        """
        ...

    @abstractmethod
    def set_enabled(self, user_id: int, enabled: int) -> None:
        """启用 / 停用一个账号。目标账号不存在时由实现方报错。"""
        ...

    @abstractmethod
    def update_password(self, user_id: int, password_hash: str) -> None:
        """改密码。传进来的已经是哈希，实现方不再做哈希。"""
        ...


class UserPermissionRepository(ABC):
    """
    用户权限仓储抽象接口。实现由 infrastructure 层提供。

    一行一个权限点，(user_id, permission_key) 联合主键，
    所以同一个用户的同一个权限天然只有一条。
    权限点一多，用集合表示比建实体类省事，这里就不建实体了。
    """

    @abstractmethod
    def list_keys_by_user(self, user_id: int) -> set[str]:
        """
        查某个用户拥有的全部权限点。
        """
        ...

    @abstractmethod
    def grant(self, user_id: int, permission_key: str) -> None:
        """
        给某个用户加一个权限点。
        """
        ...

    @abstractmethod
    def revoke(self, user_id: int, permission_key: set[str]) -> None:
        """去掉某个用户的一个权限点。本来就没有这个权限时什么也不做。"""
        ...

    @abstractmethod
    def replace_all(
        self,
        user_id: int,
        permission_keys: Iterable[str],
    ) -> None:
        """
        整体覆盖某个用户的权限，用户管理页"保存"走这个。

        必须在一个事务里先删干净再插新的。中途失败要整体回滚，
        不能留下"删了一半还没插"的空权限状态——那等于把人权限清零了。
        """
        ...
