"""旧库迁移脚本：v1.2（2026-09）→ 正式版（2026-10-31）。

为什么必须有它
--------------
`app/infrastructure/database/connection.py` 的 `create_tables()` 只在主表
不存在时才执行整份 schema.sql。拿旧库直接换新代码，结果是：
- UserAccount / TemperatureRecord / StandardSwitchLogs 一个都不会建 → 登录 500
- 主表缺 abnormal_type / abnormal_reason 两列 → 写入报 no such column
- 主表的温度列还是 NOT NULL，而新代码已经不再写这两列 → 写入约束失败

SQLite 不能直接删列、也不能改 NOT NULL，只能「建新表 → 拷数据 → 换名」，
所以这次升级必须跑脚本，不能靠启动时自动建表。

迁移内容
--------
1. 备份原库到 data/backups/
2. 补建 4 张新表 + 3 个序列触发器
3. 主表重建：删掉温度两列（数据先搬走）、放开 3 个 NOT NULL、补 2 个异常列
4. 老记录里的温度搬进 TemperatureRecord（gun_no=0 = 人工/历史数据，来源不明）
5. 迁移后核对行数，并调用 verify_schema 自检

用法
----
    python scripts/migrate_db.py                # 迁移 data/spheroidization.db
    python scripts/migrate_db.py --db 某路径     # 指定库
    python scripts/migrate_db.py --dry-run      # 只检查，不改

幂等：已经是新结构的库直接跳过，不会重复迁移。
"""

import argparse
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

SCHEMA_FILE = PROJECT_ROOT / "app" / "infrastructure" / "database" / "schema.sql"
DEFAULT_DB = PROJECT_ROOT / "data" / "spheroidization.db"
BACKUP_DIR = PROJECT_ROOT / "data" / "backups"

MAIN_TABLE = "SpheroidizationRecord"
OLD_ONLY_COLUMNS = (
    "spheroidization_temperature",
    "spheroidization_temperature_time",
)


def _tables(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def _columns(conn, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]


def _schema_statements() -> list[tuple[str, str]]:
    """把 schema.sql 拆成 (类型, 语句)。

    类型取 CREATE TABLE 的表名或 CREATE TRIGGER 的触发器名，方便按需跳过。
    """
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    # 不能用 split(";")：触发器体里 BEGIN…END 自带分号，会被切碎成
    # "incomplete input"。用 sqlite3.complete_statement 逐句累积才靠得住。
    statements = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        statements.append(buffer.strip())

    result = []
    for stmt in statements:
        m = re.match(r"CREATE\s+TABLE\s+(\w+)", stmt, re.I)
        if m:
            result.append((m.group(1), stmt))
            continue
        m = re.match(
            r"CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", stmt, re.I
        )
        if m:
            result.append((m.group(1), stmt))
    return result


def _main_table_ddl() -> str:
    """取出主表的建表语句，用来建 SpheroidizationRecord__new。"""
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    m = re.search(
        r"CREATE\s+TABLE\s+SpheroidizationRecord\s*\(.*?\)\s*STRICT;",
        sql,
        re.S | re.I,
    )
    if not m:
        raise RuntimeError("schema.sql 里找不到 SpheroidizationRecord 建表语句")
    return m.group(0)


def _ensure_v2_columns(conn) -> None:
    """v2：主表加 plc_button_time（按钮原始时刻）。

    只用 ALTER TABLE ADD COLUMN，不重建表，可在线执行；
    已有记录该列为 NULL，语义就是"当时没有按钮数据"。
    """
    columns = _columns(conn, MAIN_TABLE)
    if "plc_button_time" in columns:
        return
    print("  加列 SpheroidizationRecord.plc_button_time")
    conn.execute(f"ALTER TABLE {MAIN_TABLE} ADD COLUMN plc_button_time TEXT")


def _is_migrated(conn) -> bool:
    tables = _tables(conn)
    if MAIN_TABLE not in tables:
        return False
    cols = set(_columns(conn, MAIN_TABLE))
    has_new_cols = {"abnormal_type", "abnormal_reason", "plc_button_time"} <= cols
    no_old_cols = not (set(OLD_ONLY_COLUMNS) & cols)
    return has_new_cols and no_old_cols


def _backup(db_path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"{db_path.stem}-{stamp}.db"
    shutil.copy2(db_path, target)
    return target


def migrate(db_path: Path, dry_run: bool = False) -> int:
    if not db_path.exists():
        print(f"库不存在：{db_path}")
        print("全新部署不需要迁移，直接启动服务会自动建库（再跑 scripts/init_admin.py）。")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if _is_migrated(conn):
            print("已经是正式版结构，无需迁移。")
            return 0

        tables = _tables(conn)
        if MAIN_TABLE not in tables:
            raise RuntimeError(
                f"{db_path} 里没有 {MAIN_TABLE}，不像是球化系统的库，已中止。"
            )

        old_cols = _columns(conn, MAIN_TABLE)
        print(f"库：{db_path}")
        print(f"主表列数：{len(old_cols)}，含旧温度列："
              f"{[c for c in OLD_ONLY_COLUMNS if c in old_cols] or '无'}")

        if dry_run:
            print("dry-run：只检查不改动。确认无误后去掉 --dry-run 再跑一次。")
            return 0

        backup = _backup(db_path)
        print(f"已备份：{backup}")

        # 已经是"新版主表结构、只缺 v2 列"的库：只加列+补表，不重建。
        # 重建一次 130MB 的表没必要，而且风险高。
        needs_rebuild = (
            bool(set(OLD_ONLY_COLUMNS) & set(old_cols))
            or not ({"abnormal_type", "abnormal_reason"} <= set(old_cols))
        )
        if not needs_rebuild:
            conn.isolation_level = None
            conn.execute("BEGIN")
            existing = _tables(conn)
            for name, stmt in _schema_statements():
                if stmt.lstrip().upper().startswith("CREATE TABLE"):
                    if name in existing:
                        continue
                    print(f"  建表 {name}")
                conn.execute(stmt)
            _ensure_v2_columns(conn)
            conn.execute("COMMIT")
            from app.infrastructure.database.connection import verify_schema
            verify_schema(conn)
            print("迁移完成（仅加列/补表，未重建主表），自检通过。")
            return 0

        # SQLite 里重建被外键引用的表，必须先关外键，且只能在事务外切换
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.isolation_level = None
        conn.execute("BEGIN")

        # 1) 补建缺失的新表与触发器
        existing_tables = _tables(conn)
        for name, stmt in _schema_statements():
            if stmt.lstrip().upper().startswith("CREATE TABLE"):
                if name in existing_tables:
                    continue
                print(f"  建表 {name}")
            conn.execute(stmt)

        # 2) v2 加列（ALTER，不需要重建）
        _ensure_v2_columns(conn)

        # 3) 先把旧温度数据取出来（主表重建后这两列就没了）
        temp_rows = []
        if "spheroidization_temperature" in old_cols:
            temp_rows = [
                (row[0], row[1], row[2])
                for row in conn.execute(
                    "SELECT spheroidization_record_id, spheroidization_temperature,"
                    " spheroidization_temperature_time"
                    f" FROM {MAIN_TABLE}"
                    " WHERE spheroidization_temperature IS NOT NULL"
                )
            ]
            print(f"  待迁移温度记录：{len(temp_rows)} 条")

        # 3) 重建主表
        before = conn.execute(f"SELECT COUNT(*) FROM {MAIN_TABLE}").fetchone()[0]
        print(f"  主表行数（迁移前）：{before}")

        ddl = _main_table_ddl().replace(
            f"CREATE TABLE {MAIN_TABLE}",
            f"CREATE TABLE {MAIN_TABLE}__new",
            1,
        )
        conn.execute(f"DROP TABLE IF EXISTS {MAIN_TABLE}__new")
        conn.execute(ddl)

        new_cols = _columns(conn, f"{MAIN_TABLE}__new")
        shared = [c for c in new_cols if c in old_cols]
        col_list = ", ".join(f'"{c}"' for c in shared)
        conn.execute(
            f"INSERT INTO {MAIN_TABLE}__new ({col_list})"
            f" SELECT {col_list} FROM {MAIN_TABLE}"
        )

        conn.execute(f"DROP TABLE {MAIN_TABLE}")
        conn.execute(f"ALTER TABLE {MAIN_TABLE}__new RENAME TO {MAIN_TABLE}")

        after = conn.execute(f"SELECT COUNT(*) FROM {MAIN_TABLE}").fetchone()[0]
        print(f"  主表行数（迁移后）：{after}")
        if after != before:
            raise RuntimeError(f"行数对不上：迁移前 {before}，迁移后 {after}，已回滚")

        # 4) 温度搬进独立表
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inserted = 0
        for record_id, temperature, measured_at in temp_rows:
            conn.execute(
                "INSERT INTO TemperatureRecord"
                " (gun_no, temperature, measured_at, spheroidization_record_id, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (0, temperature, measured_at or now, record_id, now),
            )
            inserted += 1
        print(f"  已写入 TemperatureRecord：{inserted} 条（gun_no=0 表示历史/人工来源）")

        conn.execute("COMMIT")
        conn.execute("PRAGMA foreign_keys = ON")

        # 5) 自检
        from app.infrastructure.database.connection import verify_schema

        verify_schema(conn)
        print("迁移完成，自检通过。")
        print("下一步：python scripts/init_admin.py <管理员用户名>")
        return 0
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="球化系统旧库迁移")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="数据库文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只检查不改动")
    args = parser.parse_args()
    return migrate(Path(args.db).resolve(), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
