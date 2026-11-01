#!/usr/bin/env bash
#
# 球化监测系统 · 在线备份
#
# 备份内容（必须同批，缺一会丢「当前生效标准」指针）：
#   - SQLite 库（sqlite3 在线 .backup 协议，服务不用停）
#   - data/active_standard.json（当前生效标准指针）
# 每个备份是一个目录：backup-YYYYmmdd-HHMMSS/{spheroidization.db, active_standard.json, manifest.json}
# 备份后自动校验：integrity_check + 表数与源库一致；校验不过就删掉这份备份并以非 0 退出。
# 自动保留最近 N 份（BACKUP_KEEP，默认 10）。
#
# 环境变量：
#   SPHEROIDIZATION_DB         要备份的库（默认 <项目根>/data/spheroidization.db）
#   SPHEROIDIZATION_BACKUP_DIR 备份目录（默认 <项目根>/data/backups）
#   BACKUP_KEEP                保留份数（默认 10）
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="${SPHEROIDIZATION_DB:-$PROJECT_ROOT/data/spheroidization.db}"
STANDARD_JSON="$(dirname "$DB")/active_standard.json"
BACKUP_DIR="${SPHEROIDIZATION_BACKUP_DIR:-$PROJECT_ROOT/data/backups}"
KEEP="${BACKUP_KEEP:-10}"

if [ ! -f "$DB" ]; then
    echo "[backup] 库不存在：$DB" >&2
    exit 1
fi
if ! [[ "$KEEP" =~ ^[1-9][0-9]*$ ]]; then
    echo "[backup] BACKUP_KEEP 必须是正整数（当前：$KEEP）" >&2
    exit 2
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/backup-$STAMP"
mkdir -p "$DEST"

echo "[backup] 在线备份 $DB → $DEST"

# 在线备份 + 校验 + manifest（纯标准库 sqlite3，不需要 sqlite3 命令行）
DB="$DB" DEST="$DEST" STAMP="$STAMP" STANDARD_JSON="$STANDARD_JSON" python3 - <<'PY'
import json, os, sqlite3, sys

db = os.environ["DB"]
dest = os.environ["DEST"]
dst_path = os.path.join(dest, "spheroidization.db")

src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
try:
    src_tables = sorted(
        r[0] for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    )
    dst = sqlite3.connect(dst_path)
    try:
        with dst:
            src.backup(dst)
        # 校验 1：完整性
        check = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            print(f"[backup] 校验失败：integrity_check={check}", file=sys.stderr)
            sys.exit(1)
        # 校验 2：表数与源库一致（防半截备份）
        dst_tables = sorted(
            r[0] for r in dst.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        if dst_tables != src_tables:
            print("[backup] 校验失败：表清单与源库不一致 "
                  f"(src={len(src_tables)} dst={len(dst_tables)})", file=sys.stderr)
            sys.exit(1)
    finally:
        dst.close()
finally:
    src.close()

manifest = {
    "created_at": os.environ["STAMP"],
    "source_db": db,
    "tables": src_tables,
    "has_active_standard": os.path.exists(os.environ["STANDARD_JSON"]),
    "db_size_bytes": os.path.getsize(dst_path),
}
with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print(f"  备份完成：{len(src_tables)} 张表，integrity_check=ok")
PY

# active_standard.json 必须和库同批备份
if [ -f "$STANDARD_JSON" ]; then
    cp -p "$STANDARD_JSON" "$DEST/active_standard.json"
    echo "  已备份 active_standard.json"
else
    echo "  警告：没找到 $STANDARD_JSON（没有生效标准指针）"
fi

# 清理旧备份：只删本备份目录下 backup-* 命名的目录，保留最近 KEEP 份
OLD="$(find "$BACKUP_DIR" -maxdepth 1 -mindepth 1 -type d -name 'backup-*' -printf '%f\n' \
    | sort | head -n -"$KEEP" || true)"
if [ -n "$OLD" ]; then
    while IFS= read -r d; do
        echo "[backup] 清理旧备份：$BACKUP_DIR/$d"
        rm -rf "$BACKUP_DIR/$d"
    done <<< "$OLD"
fi

echo "[backup] 完成：$DEST"
