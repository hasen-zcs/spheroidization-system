"""
数据库连接。
全项目拿连接只有 connect() 这一个入口，别处不要直接调 sqlite3.connect()。
理由见下面那三行，少任何一行都会出事，而且是静默出事——
"每个人都记得加"这种约定靠不住，做成唯一入口才靠得住。
"""

import os
import sqlite3
from pathlib import Path

# connection.py 在 app/infrastructure/database/ 下，往上数三层是项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]
def default_db_path() -> Path:
    """允许用环境变量指定库文件：测试隔离、多实例部署、现场换盘都用得上。

    每次调用都读环境变量，而不是在 import 时算成常量——
    测试里 monkeypatch.setenv 之后再建容器才能生效。
    """
    return Path(
        os.getenv("SPHEROIDIZATION_DB", str(PROJECT_ROOT / "data" / "spheroidization.db"))
    )


DEFAULT_DB_PATH = default_db_path()
SCHEMA_FILE = Path(__file__).parent / "schema.sql"

# 这三个触发器里的 FROM <表> 是"物理删除后把 AUTOINCREMENT 序列回退到当前
# 最大 ID"的完整性计算（SELECT MAX(...)），不是业务读路径，所以**不**加
# deleted_at IS NULL 过滤。本系统改用软删除后，这四张表不再发生物理 DELETE，
# 触发器实际不会触发，保留它们只是兼容老的物理删除序列回退逻辑。
SEQUENCE_TRIGGER_SQL = (
    """
    CREATE TRIGGER IF NOT EXISTS standard_sync_sequence
    AFTER DELETE ON StandardRecord
    BEGIN
        UPDATE sqlite_sequence
           SET seq = (
               SELECT COALESCE(MAX(standard_record_id), 0)
               FROM StandardRecord
           )
         WHERE name = 'StandardRecord';
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS spheroidization_sync_sequence
    AFTER DELETE ON SpheroidizationRecord
    BEGIN
        UPDATE sqlite_sequence
           SET seq = (
               SELECT COALESCE(MAX(spheroidization_record_id), 0)
               FROM SpheroidizationRecord
           )
         WHERE name = 'SpheroidizationRecord';
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS review_sync_sequence
    AFTER DELETE ON ReviewRecord
    BEGIN
        UPDATE sqlite_sequence
           SET seq = (
               SELECT COALESCE(MAX(review_record_id), 0)
               FROM ReviewRecord
           )
         WHERE name = 'ReviewRecord';
    END;
    """,
)


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """
    建一个数据库连接。
    :param db_path: 数据库文件路径。不传就用 data/spheroidization.db
    :return: 配好的 sqlite3.Connection
    """
    path = Path(db_path) if db_path else default_db_path()
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
    建表并在每次启动时确保序列同步触发器存在。
    schema.sql 里的建表语句没有写 IF NOT EXISTS，是故意的：
    加了它，表结构和 DDL 不一致时会静默跳过，你以为建好了其实还是老表。
    改成先查一下表在不在，不在才建，达到同样的幂等效果但不会掩盖问题。
    注意：这个只保证"表存在"，不保证"表结构和最新的 DDL 一致"。
    建库的人改了 DDL 之后，要删掉 data/spheroidization.db 重新跑一次。
    """
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'SpheroidizationRecord'"
    ).fetchone()
    if not table_exists:
        # executescript 会自己处理事务，不用再包一层
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))

    # 已有数据库也必须补触发器，保证直接删表数据后序列能回退。
    for trigger_sql in SEQUENCE_TRIGGER_SQL:
        conn.execute(trigger_sql)
    conn.commit()


REQUIRED_TABLES = (
    "StandardRecord",
    "SpheroidizationRecord",
    "ReviewRecord",
    "TemperatureRecord",
    "StandardSwitchLogs",
    "UserAccount",
    "UserPermission",
    # v3（2026-11-01）：上传幂等台账 + 分段明细。老库不补这两张表，
    # 上游一上传就会 OperationalError，所以放进启动自检。
    "UploadLedger",
    "FlashSegment",
    # v4（2026-11-01）：审计日志。老库缺这张表时写操作留痕全部失败，
    # 而且启动自检要把它当成结构不完整处理。
    "AuditLog",
)

# 升级过表结构的列：老库缺这些列时，任何写入都会 OperationalError，
# 与其等第一个请求 500，不如启动时直接拒绝。
# v6：软删除三列缺了，读路径的 deleted_at IS NULL 会报 no such column，
# 一样要启动即失败，指向迁移脚本。
REQUIRED_COLUMNS = {
    "SpheroidizationRecord": (
        "abnormal_type", "abnormal_reason", "plc_button_time",
        "deleted_at", "deleted_by", "delete_reason",
    ),
    "StandardRecord": ("deleted_at", "deleted_by", "delete_reason"),
    "StandardSwitchLogs": ("deleted_at", "deleted_by", "delete_reason"),
    "ReviewRecord": ("deleted_at", "deleted_by", "delete_reason"),
}


def verify_schema(conn: sqlite3.Connection) -> None:
    """启动自检：表/列不齐就报错退出。

    背景：create_tables() 只在主表不存在时执行整份 DDL，老库升级不会自动
    建新表、加新列。少了这一层，现场表现是"登录 500 / 写入报 no such column"，
    排查成本远高于启动即失败。
    """
    existing = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = [name for name in REQUIRED_TABLES if name not in existing]
    if missing:
        raise RuntimeError(
            "数据库表结构不完整，缺少表："
            + "、".join(missing)
            + "。请先执行 scripts/migrate_db.py 迁移旧库（旧库不能直接换新代码）。"
        )

    for table, columns in REQUIRED_COLUMNS.items():
        actual = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
        lack = [col for col in columns if col not in actual]
        if lack:
            raise RuntimeError(
                f"数据库表 {table} 缺少列：{'、'.join(lack)}。"
                "请先执行 scripts/migrate_db.py 迁移旧库。"
            )


def init_database(db_path: str | Path | None = None) -> sqlite3.Connection:
    """
    建连接 + 建表，一步到位。给应用启动时调用。
    :return: 可以直接交给仓储用的连接
    """
    conn = connect(db_path)
    create_tables(conn)
    verify_schema(conn)
    return conn
