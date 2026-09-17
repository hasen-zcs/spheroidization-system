"""
数据库连接。

全项目拿连接只有 connect() 这一个入口，别处不要直接调 sqlite3.connect()。
理由见下面那三行，少任何一行都会出事，而且是静默出事——
"每个人都记得加"这种约定靠不住，做成唯一入口才靠得住。
"""

import sqlite3
from pathlib import Path

# connection.py 在 app/infrastructure/database/ 下，往上数三层是项目根目录
项目根目录 = Path(__file__).resolve().parents[3]
默认数据库 = 项目根目录 / "data" / "spheroidization.db"
建表语句文件 = Path(__file__).parent / "schema.sql"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """
    建一个数据库连接。

    :param db_path: 数据库文件路径。不传就用 data/spheroidization.db
    :return: 配好的 sqlite3.Connection
    """
    path = Path(db_path) if db_path else 默认数据库
    # data/ 目录可能还不存在，第一次跑的时候要先建出来
    path.parent.mkdir(parents=True, exist_ok=True)

    # check_same_thread=False：
    #   FastAPI 在线程池里跑同步函数，连接可能被换个线程用。
    #   不加这句会报 SQLite objects created in a thread can only be used in that same thread
    #
    # row_factory = sqlite3.Row：
    #   查询结果能按列名取（row["detection_time"]），而不是只能按位置取（row[3]）。
    #   sqlite.py 里的 XxxRecord(**dict(row)) 靠的就是这个。
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # PRAGMA foreign_keys = ON：
    #   SQLite 的外键约束默认是【关闭】的，而且是【每个连接】都要单独开一次。
    #   不打开，schema.sql 里那些 FOREIGN KEY ... ON DELETE RESTRICT 全都是摆设，
    #   删掉被引用的标准不会报错，溯源 ID 会变成孤儿，而且不报任何错。
    #   实测：关着的时候 DELETE 直接成功，开着的时候抛 IntegrityError。
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """
    建表。已经在库里的话什么都不做。

    schema.sql 里的建表语句没有写 IF NOT EXISTS，是故意的：
    加了它，表结构和 DDL 不一致时会静默跳过，你以为建好了其实还是老表。
    改成先查一下表在不在，不在才建，达到同样的幂等效果但不会掩盖问题。

    注意：这个只保证"表存在"，不保证"表结构和最新的 DDL 一致"。
    建库的人改了 DDL 之后，要删掉 data/spheroidization.db 重新跑一次。
    """
    已存在 = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'SpheroidizationRecord'"
    ).fetchone()

    if 已存在:
        return

    # executescript 会自己处理事务，不用再包一层
    conn.executescript(建表语句文件.read_text(encoding="utf-8"))


def init_database(db_path: str | Path | None = None) -> sqlite3.Connection:
    """
    建连接 + 建表，一步到位。给应用启动时调用。

    :return: 可以直接交给仓储用的连接
    """
    conn = connect(db_path)
    create_tables(conn)
    return conn
