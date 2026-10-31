from app.domain.user.entities import UserAccount
from app.domain.user.repositories import (
    UserAccountRepository,
    UserPermissionRepository,
)


class QueryUserUseCase:
    """
    查账号列表和单个账号。

    返回的实体里带 password_hash——这是仓储层的原样数据，本层不负责裁剪。
    路由层转响应时由响应模型天然挡掉（UserResponse 里没有这个字段）。
    如果哪天有人给实体加了 password_hash 之外的东西，记得同步检查响应模型。

    依赖：UserAccountRepository、UserPermissionRepository
    """

    def __init__(
        self,
        user_repo: UserAccountRepository,
        permission_repo: UserPermissionRepository,
    ):
        self.user_repo = user_repo
        self.permission_repo = permission_repo

    def list_all(self) -> list[tuple[UserAccount, set[str]]]:
        """查全部账号，每个账号附上它的权限点集合。

        用户量小，不分页，一次全取。逐个查权限会有 N+1 次往返，
        但 N 是个位数，换来的是代码简单——真要多了再改成一条 JOIN。
        """
        return [
            (user, self.permission_repo.list_keys_by_user(user.user_id))
            for user in self.user_repo.list_all()
        ]

    def get(self, user_id: int) -> UserAccount | None:
        """按主键查单个账号，查不到返回 None。"""
        return self.user_repo.get_by_id(user_id)
