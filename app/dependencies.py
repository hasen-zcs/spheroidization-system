"""
组装层。把「连接 → 仓储 → UseCase」串起来。

这个文件就是依赖注入的入口。
UseCase 的构造函数只声明"我需要一个 SpheroidizationRepository"，
到底塞给它 SQLite 版还是内存版，在下面 Container.__init__ 里决定。

好处：换实现只改那几行。比如以后要换成 PostgreSQL，写一个
PostgresSpheroidizationRepository 顶上就行，UseCase 和 API 层一行都不用动。

（早先有个内存版的 MemorySpheroidizationRepository 给测试用，已经删了。
现在测试也是打真 SQLite，只不过每个测试用一个临时空库，见 tests/conftest.py。）

两种用法
-------
1. 脚本 / 测试里直接用（不经过 FastAPI）：

       from app.dependencies import get_container
       uc = get_container().create_standard()
       uc.execute(70.0, 1500.0, "张三")

2. API 层用 FastAPI 注入：

       from fastapi import Depends
       from app.application.standard.create import CreateStandardUseCase
       from app.dependencies import get_create_standard_uc

       @router.post("")
       def create_standard(
           data: StandardCreateRequest,
           uc: CreateStandardUseCase = Depends(get_create_standard_uc),
       ):
           return uc.execute(...)

下面 get_xxx_uc() 那一批函数只是为了第 2 种用法存在——
FastAPI 靠 Depends 解析参数，所以必须有人把 Depends 写出来。
真正的组装逻辑全在 Container 里，不重复。

注意：路由函数里不要自己写业务逻辑，也不要直接碰数据库。
业务规则（处置不可逆、标准快照、复核只增不删）都在 UseCase 里，
路由只负责"收请求 → 调 UseCase → 返响应"。
"""

import sqlite3
from functools import lru_cache

from fastapi import Depends, Request

from app.application.review.create import CreateReviewUseCase
from app.application.review.query import QueryReviewUseCase
from app.application.spheroidization.create import CreateSpheroidizationUseCase
from app.application.spheroidization.process import ProcessSpheroidizationUseCase
from app.application.spheroidization.query import QuerySpheroidizationUseCase
from app.application.standard.apply import ApplyStandardUseCase
from app.application.standard.create import CreateStandardUseCase
from app.application.standard.query import QueryStandardUseCase
from app.application.standard.switch import SwitchStandardUseCase
from app.application.temperature.create import CreateTemperatureUseCase
from app.application.user.auth import LoginUseCase
from app.application.user.create import CreateUserUseCase
from app.application.user.manage import UserAccountManageUseCase
from app.application.user.permission import UserPermissionUseCase
from app.application.user.query import QueryUserUseCase
from app.core.exceptions import BusinessException
from app.core.security import Session, get_session
from app.domain.standard.application_state import StandardApplicationState
from app.infrastructure.database.connection import init_database
from app.infrastructure.database.flash_repo import (
    SqliteFlashSegmentRepository,
    SqliteUploadLedgerRepository,
)
from app.infrastructure.database.sqlite import (
    SqliteReviewRepository,
    SqliteSpheroidizationRepository,
    SqliteStandardRepository,
    SqliteStandardSwitchLogRepository,
    SqliteTemperatureRepository,
    SqliteUserPermissionRepository,
    SqliteUserRepository,
)
from app.infrastructure.state.active_standard import JsonStandardApplicationState


class Container:
    """
    把连接、仓储、UseCase 装在一起。

    可以直接用（Container()），也可以让 FastAPI 通过 get_container() 拿。
    """

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        standard_application_state: StandardApplicationState | None = None,
    ):
        # 不传连接就自己建一个（建连接 + 建表，见 connection.py）
        self.conn = conn if conn is not None else init_database()
        self.standard_application_state = (
            standard_application_state
            if standard_application_state is not None
            else JsonStandardApplicationState()
        )

        # ---- 仓储：决定用哪个实现，换实现只改这几行 ----
        # 全部共用同一条 self.conn，不要各自去 connect()：
        # 一条连接对 SQLite 够用，各自建连接只会让锁的问题更难查。
        self.spheroid_repo = SqliteSpheroidizationRepository(self.conn)
        self.standard_repo = SqliteStandardRepository(self.conn)
        self.review_repo = SqliteReviewRepository(self.conn)
        self.temperature_repo = SqliteTemperatureRepository(self.conn)
        self.switchlog_repo = SqliteStandardSwitchLogRepository(self.conn)
        self.user_repo = SqliteUserRepository(self.conn)
        self.user_permission_repo = SqliteUserPermissionRepository(self.conn)
        # v3：幂等台账 + 分段明细（写方法不提交事务，由用例统一控制）
        self.upload_ledger_repo = SqliteUploadLedgerRepository(self.conn)
        self.flash_segment_repo = SqliteFlashSegmentRepository(self.conn)

    # ---- UseCase：本身不存状态，每次现构造，成本可忽略 ----

    def create_spheroidization(self) -> CreateSpheroidizationUseCase:
        # 幂等路径要"建档+分段+台账"一个事务，所以把连接和两个新仓储一起传进去
        return CreateSpheroidizationUseCase(
            self.spheroid_repo,
            self.standard_repo,
            ledger_repo=self.upload_ledger_repo,
            segment_repo=self.flash_segment_repo,
            conn=self.conn,
        )

    def query_spheroidization(self) -> QuerySpheroidizationUseCase:
        # 列表和详情要同时查最新复核结果和关联温度，三个仓储都得传
        return QuerySpheroidizationUseCase(
            self.spheroid_repo,
            self.review_repo,
            self.temperature_repo,
            segment_repo=self.flash_segment_repo,
        )

    def process_spheroidization(self) -> ProcessSpheroidizationUseCase:
        return ProcessSpheroidizationUseCase(self.spheroid_repo)

    def create_review(self) -> CreateReviewUseCase:
        return CreateReviewUseCase(self.review_repo, self.spheroid_repo)

    def query_review(self) -> QueryReviewUseCase:
        return QueryReviewUseCase(self.review_repo)

    def create_standard(self) -> CreateStandardUseCase:
        return CreateStandardUseCase(
            self.standard_repo,
            self.standard_application_state,
        )

    def apply_standard(self) -> ApplyStandardUseCase:
        return ApplyStandardUseCase(
            self.standard_repo,
            self.standard_application_state,
        )

    def query_standard(self) -> QueryStandardUseCase:
        return QueryStandardUseCase(
            self.standard_repo,
            self.standard_application_state,
        )

    def create_temperature(self) -> CreateTemperatureUseCase:
        return CreateTemperatureUseCase(self.temperature_repo, self.spheroid_repo)

    def switch_standard(self) -> SwitchStandardUseCase:
        return SwitchStandardUseCase(
            self.standard_repo,
            self.standard_application_state,
            self.switchlog_repo,
        )

    def create_user(self) -> CreateUserUseCase:
        return CreateUserUseCase(self.user_repo)

    def manage_user(self) -> UserAccountManageUseCase:
        return UserAccountManageUseCase(self.user_repo)

    def user_permission(self) -> UserPermissionUseCase:
        return UserPermissionUseCase(self.user_repo, self.user_permission_repo)

    def login(self) -> LoginUseCase:
        return LoginUseCase(self.user_repo, self.user_permission_repo)

    def query_user(self) -> QueryUserUseCase:
        return QueryUserUseCase(self.user_repo, self.user_permission_repo)


@lru_cache(maxsize=1)
def get_container() -> Container:
    """
    拿全局容器。整个进程只建一次，连接也就只有一条。

    共用一条连接对 SQLite 够用：它内部会把并发访问串行化，
    这个项目的并发量很小，没必要搞连接池。

    测试时可以覆盖：app.dependency_overrides[get_container] = lambda: 测试用容器
    或者直接构造：Container(conn=自己的连接)
    """
    return Container()


# ==========================================================
# FastAPI 注入用的包装。每个一行，真正的组装在 Container 里。
# ==========================================================
def get_spheroid_repo(container: Container = Depends(get_container)):
    return container.spheroid_repo


def get_standard_repo(container: Container = Depends(get_container)):
    return container.standard_repo


def get_review_repo(container: Container = Depends(get_container)):
    return container.review_repo


def get_create_spheroidization_uc(
    container: Container = Depends(get_container),
) -> CreateSpheroidizationUseCase:
    return container.create_spheroidization()


def get_query_spheroidization_uc(
    container: Container = Depends(get_container),
) -> QuerySpheroidizationUseCase:
    return container.query_spheroidization()


def get_process_spheroidization_uc(
    container: Container = Depends(get_container),
) -> ProcessSpheroidizationUseCase:
    return container.process_spheroidization()


def get_create_review_uc(
    container: Container = Depends(get_container),
) -> CreateReviewUseCase:
    return container.create_review()


def get_query_review_uc(
    container: Container = Depends(get_container),
) -> QueryReviewUseCase:
    return container.query_review()


def get_create_standard_uc(
    container: Container = Depends(get_container),
) -> CreateStandardUseCase:
    return container.create_standard()


def get_query_standard_uc(
    container: Container = Depends(get_container),
) -> QueryStandardUseCase:
    return container.query_standard()


def get_apply_standard_uc(
    container: Container = Depends(get_container),
) -> ApplyStandardUseCase:
    return container.apply_standard()


def get_create_temperature_uc(
    container: Container = Depends(get_container),
) -> CreateTemperatureUseCase:
    return container.create_temperature()


def get_switch_standard_uc(
    container: Container = Depends(get_container),
) -> SwitchStandardUseCase:
    return container.switch_standard()


def get_create_user_uc(
    container: Container = Depends(get_container),
) -> CreateUserUseCase:
    return container.create_user()


def get_manage_user_uc(
    container: Container = Depends(get_container),
) -> UserAccountManageUseCase:
    return container.manage_user()


def get_user_permission_uc(
    container: Container = Depends(get_container),
) -> UserPermissionUseCase:
    return container.user_permission()


def get_login_uc(
    container: Container = Depends(get_container),
) -> LoginUseCase:
    return container.login()


def get_query_user_uc(
    container: Container = Depends(get_container),
) -> QueryUserUseCase:
    return container.query_user()


# ==========================================================
# 登录态。两种用法，按需选一种，不要混着用：
#   require_login            只要登录，不限权限
#   require_permission(key)  要登录 + 要有某个权限
#   get_optional_session     不拦截，拿不到就返回 None（游客场景）
# ==========================================================
def _extract_bearer(request: Request) -> str | None:
    """从 Authorization: Bearer <token> 里取出 token。

    格式不对一律当没带。不放 cookie：前端是 SPA，跨域 cookie 会引入 CSRF。
    """
    header = request.headers.get("Authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def get_optional_session(request: Request) -> Session | None:
    """拿当前登录态，游客返回 None，不抛异常。

    给"游客能进、但要按身份区别对待"的接口用，例如监控页列表：
    游客能看正常记录，带 abnormal=true 就拒掉。
    """
    token = _extract_bearer(request)
    if not token:
        return None
    return get_session(token)


def require_login(request: Request) -> Session:
    """只要登录，不限权限。

    详情页、复核历史这类"登录用户都能看"的接口用它。
    不挂任何页面权限，是因为详情页对 page:records 和 page:abnormal
    的用户都要能用，挂哪一个都会挡掉另一边。
    """
    token = _extract_bearer(request)
    session = get_session(token) if token else None
    if session is None:
        raise BusinessException("请先登录", 401)
    return session


def require_permission(permission_key: str):
    """生成一个"必须有某权限"的依赖。

    :param permission_key: core/permissions.py 里的常量

    失败抛 BusinessException(401/403)，走 main.py 的统一处理器，
    返回 HTTP 200 + body.code——全项目都是这个信封，前端按 code 判断。
    不要改成 HTTPException：那会绕开信封，前端拿到的结构就变了。

    超管直接放行，不看权限表。
    """

    def _dep(request: Request) -> Session:
        token = _extract_bearer(request)
        session = get_session(token) if token else None
        if session is None:
            raise BusinessException("请先登录", 401)
        if not session.is_admin and permission_key not in session.permissions:
            raise BusinessException("没有该操作权限", 403)
        return session

    return _dep
