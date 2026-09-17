"""
组装层。把「连接 → 仓储 → UseCase」串起来。

这个文件就是依赖注入的入口。
UseCase 的构造函数只声明"我需要一个 SpheroidizationRepository"，
到底塞给它 SQLite 版还是内存版，在下面 Container.__init__ 里决定。

好处：换实现只改那三行。比如以后要换成 PostgreSQL，写一个
PostgresSpheroidizationRepository 顶上就行，UseCase 和 API 层一行都不用动。

（早先有个内存版的 MemorySpheroidizationRepository 给测试用，已经删了。
现在测试也是打真 SQLite，只不过每个测试用一个临时空库，见 tests/conftest.py。）

两种用法
-------
1. 脚本 / 测试里直接用（不经过 FastAPI）：

       from app.dependencies import get_container
       uc = get_container().create_standard()
       uc.execute(70.0, 130.0, 1500.0, "张三")

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

from fastapi import Depends

from app.application.review.create import CreateReviewUseCase
from app.application.review.query import QueryReviewUseCase
from app.application.spheroidization.create import CreateSpheroidizationUseCase
from app.application.spheroidization.process import ProcessSpheroidizationUseCase
from app.application.spheroidization.query import QuerySpheroidizationUseCase
from app.application.standard.create import CreateStandardUseCase
from app.application.standard.query import QueryStandardUseCase
from app.infrastructure.database.connection import init_database
from app.infrastructure.database.sqlite import (
    SqliteReviewRepository,
    SqliteSpheroidizationRepository,
    SqliteStandardRepository,
)


class Container:
    """
    把连接、仓储、UseCase 装在一起。

    可以直接用（Container()），也可以让 FastAPI 通过 get_container() 拿。
    """

    def __init__(self, conn: sqlite3.Connection | None = None):
        # 不传连接就自己建一个（建连接 + 建表，见 connection.py）
        self.conn = conn if conn is not None else init_database()

        # ---- 仓储：决定用哪个实现，换实现只改这三行 ----
        self.spheroid_repo = SqliteSpheroidizationRepository(self.conn)
        self.standard_repo = SqliteStandardRepository(self.conn)
        self.review_repo = SqliteReviewRepository(self.conn)

    # ---- UseCase：本身不存状态，每次现构造，成本可忽略 ----

    def create_spheroidization(self) -> CreateSpheroidizationUseCase:
        return CreateSpheroidizationUseCase(self.spheroid_repo, self.standard_repo)

    def query_spheroidization(self) -> QuerySpheroidizationUseCase:
        return QuerySpheroidizationUseCase(self.spheroid_repo)

    def process_spheroidization(self) -> ProcessSpheroidizationUseCase:
        return ProcessSpheroidizationUseCase(self.spheroid_repo)

    def create_review(self) -> CreateReviewUseCase:
        return CreateReviewUseCase(self.review_repo, self.spheroid_repo)

    def query_review(self) -> QueryReviewUseCase:
        return QueryReviewUseCase(self.review_repo)

    def create_standard(self) -> CreateStandardUseCase:
        return CreateStandardUseCase(self.standard_repo)

    def query_standard(self) -> QueryStandardUseCase:
        return QueryStandardUseCase(self.standard_repo)


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
