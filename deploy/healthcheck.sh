#!/usr/bin/env bash
#
# 球化监测系统 · 健康检查（供 cron / 现场巡检用）
#
# 检查三项，任一失败整体非 0：
#   1. API /api/health 可达且返回 code=200
#   2. 数据库文件存在且可读（integrity_check=ok）
#   3. 数据库可写（建临时探针表 → 插入 → 删除 → 删表）
#
# 环境变量：
#   SPHEROIDIZATION_HOST  API 地址（默认 127.0.0.1）
#   SPHEROIDIZATION_PORT  API 端口（默认 8000）
#   SPHEROIDIZATION_DB    库路径（默认 <项目根>/data/spheroidization.db）
#
set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${SPHEROIDIZATION_HOST:-127.0.0.1}"
PORT="${SPHEROIDIZATION_PORT:-8000}"
DB="${SPHEROIDIZATION_DB:-$PROJECT_ROOT/data/spheroidization.db}"

FAIL=0
note() { echo "[healthcheck] $*"; }
fail() { echo "[healthcheck] ❌ $*" >&2; FAIL=1; }

# ------------------------------------------------------------ 1. API
if ! command -v curl >/dev/null; then
    fail "缺少 curl，无法检查 API"
else
    URL="http://$HOST:$PORT/api/health"
    if RESP="$(curl -fsS -m 5 "$URL" 2>&1)"; then
        CODE="$(printf '%s' "$RESP" | python3 -c \
            'import sys, json; print(json.load(sys.stdin).get("code"))' 2>/dev/null || echo '?')"
        if [ "$CODE" = "200" ]; then
            note "✅ API $URL → code=200"
        else
            fail "API $URL 返回异常（body=$RESP）"
        fi
    else
        fail "API 不可达：$URL（$RESP）"
        if ! ss -lnt 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${PORT}\$"; then
            fail "  端口 $PORT 没有进程在监听 → 服务大概率没启动（systemctl start spheroidization-api）"
        fi
    fi
fi

# ------------------------------------------------------------ 2+3. 数据库
if [ ! -f "$DB" ]; then
    fail "数据库文件不存在：$DB（服务没起过？先跑 deploy/install.sh）"
else
    if OUT="$(DB="$DB" python3 - <<'PY' 2>&1
import os, sqlite3, sys
db = os.environ["DB"]
try:
    con = sqlite3.connect(db, timeout=5)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            print("数据库 integrity_check 不为 ok")
            sys.exit(1)
        # 可写探针：建表 → 写 → 删，全程不碰业务表
        con.execute("CREATE TEMPORARY TABLE healthcheck_probe (id INTEGER PRIMARY KEY)")
        con.execute("INSERT INTO healthcheck_probe VALUES (1)")
        con.commit()
        n = con.execute("SELECT COUNT(*) FROM healthcheck_probe").fetchone()[0]
        if n != 1:
            print("数据库可写探针读回异常")
            sys.exit(1)
        print(f"OK: 数据库可读可写：{db}（integrity_check=ok，探针表通过）")
    finally:
        con.close()
except sqlite3.OperationalError as e:
    print(f"数据库操作失败：{e}")
    sys.exit(1)
PY
)"; then
        note "✅ $OUT"
    else
        fail "数据库检查失败：$OUT"
    fi
fi

if [ "$FAIL" -ne 0 ]; then
    note "结果：异常（见上方 ❌）"
    exit 1
fi
note "结果：全部通过"
exit 0
