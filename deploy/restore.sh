#!/usr/bin/env bash
#
# 球化监测系统 · 恢复
#
# 用法：
#   bash deploy/restore.sh <备份>
#   <备份> 可以是：
#     - backup.sh 产出的目录（含 spheroidization.db + active_standard.json，推荐）
#     - 单个 spheroidization.db 文件（只恢复库，不动 active_standard.json）
#
# 行为：
#   1. 先校验备份（integrity_check + 必须有 StandardRecord 表）
#   2. 恢复前自动对当前库做一次 backup.sh（防误恢复）
#   3. 覆盖目标库（+ active_standard.json，若备份目录里带）
#
# ⚠️ 恢复期间服务写数据会冲突：建议先停服务再恢复（见 RUNBOOK）。
#
# 环境变量：
#   SPHEROIDIZATION_DB  恢复到哪个库（默认 <项目根>/data/spheroidization.db）
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DB="${SPHEROIDIZATION_DB:-$PROJECT_ROOT/data/spheroidization.db}"
TARGET_JSON="$(dirname "$TARGET_DB")/active_standard.json"

if [ $# -ne 1 ]; then
    echo "用法：bash deploy/restore.sh <备份目录|备份.db文件>" >&2
    exit 2
fi
SRC="$1"

# ------------------------------------------------------------ 定位备份内容
if [ -d "$SRC" ]; then
    SRC_DB="$SRC/spheroidization.db"
    SRC_JSON="$SRC/active_standard.json"
    [ -f "$SRC_JSON" ] || SRC_JSON=""
elif [ -f "$SRC" ]; then
    SRC_DB="$SRC"
    SRC_JSON=""
else
    echo "[restore] 备份不存在：$SRC" >&2
    exit 1
fi
[ -f "$SRC_DB" ] || { echo "[restore] 备份里没有数据库文件：$SRC_DB" >&2; exit 1; }

echo "[restore] 备份：$SRC_DB"
[ -n "$SRC_JSON" ] && echo "[restore] 附带 active_standard.json：$SRC_JSON"

# ------------------------------------------------------------ 校验备份
SRC_DB="$SRC_DB" python3 - <<'PY'
import os, sqlite3, sys
path = os.environ["SRC_DB"]
con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
try:
    check = con.execute("PRAGMA integrity_check").fetchone()[0]
    if check != "ok":
        print(f"[restore] 备份损坏，拒绝恢复：integrity_check={check}", file=sys.stderr)
        sys.exit(1)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "StandardRecord" not in tables:
        print("[restore] 备份缺少 StandardRecord 表，不是本系统的库，拒绝恢复",
              file=sys.stderr)
        sys.exit(1)
    n = con.execute("SELECT COUNT(*) FROM StandardRecord").fetchone()[0]
    print(f"  备份校验通过：integrity_check=ok，{len(tables)} 张表，{n} 条标准")
finally:
    con.close()
PY

# ------------------------------------------------------------ 恢复前自动备份
if [ -f "$TARGET_DB" ]; then
    echo "[restore] 恢复前自动备份当前库 ..."
    SPHEROIDIZATION_DB="$TARGET_DB" bash "$PROJECT_ROOT/deploy/backup.sh"
else
    echo "[restore] 目标库不存在：$TARGET_DB（首次恢复，跳过自动备份）"
fi

# ------------------------------------------------------------ 执行恢复
mkdir -p "$(dirname "$TARGET_DB")"
cp -f "$SRC_DB" "$TARGET_DB"
echo "[restore] 库已恢复：$TARGET_DB"

if [ -n "$SRC_JSON" ]; then
    cp -f "$SRC_JSON" "$TARGET_JSON"
    echo "[restore] active_standard.json 已恢复：$TARGET_JSON"
fi

cat <<EOF

[restore] 完成。后续动作（见 RUNBOOK）：
  1. 重启服务让内存里的连接/缓存对齐：systemctl restart spheroidization-api
  2. bash deploy/healthcheck.sh 验证
  3. 浏览器登录检查：能否进、当前生效标准是否为预期值
EOF
