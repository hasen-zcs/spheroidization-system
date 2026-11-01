#!/usr/bin/env bash
#
# 球化监测系统 · 安装/初始化脚本（幂等，可重复执行）
#
# 功能：
#   1. 检测依赖（python3 必须；node 可选，有则构建前端）
#   2. 建 venv + 装 requirements
#   3. 初始化 SQLite 库（启动即建表）
#   4. 创建首个管理员（--no-admin 跳过；密码用环境变量或 getpass，不写死）
#   5. 播种一条生效标准（库为空标准时才播种，值可用环境变量覆盖）
#
# 用法：
#   bash deploy/install.sh                 # 完整安装（管理员密码交互输入）
#   bash deploy/install.sh --no-admin      # 不建管理员（沙盒/已有管理员时用）
#   bash deploy/install.sh --dry-run       # 只打印将要执行的步骤
#
# 相关环境变量（都可省略，有默认值）：
#   SPHEROIDIZATION_DB           库文件路径（默认 <项目根>/data/spheroidization.db）
#   INSTALL_VENV_DIR             venv 目录（默认 <项目根>/.venv）
#   INSTALL_SKIP_FRONTEND=1      跳过前端构建（无 node 时自动跳过）
#   ADMIN_USERNAME               管理员用户名（默认 admin）
#   ADMIN_PASSWORD               管理员密码（设置则非交互；否则 getpass 交互输入）
#   SEED_STANDARD_TIME           标准球化时长秒（默认 75）
#   SEED_STANDARD_TIME_UPPER     球化时长上限秒（默认 90）
#   SEED_STANDARD_TIME_LOWER     球化时长下限秒（默认 60）
#   SEED_STANDARD_WEIGHING       称重标准（默认 1800）
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=0
NO_ADMIN=0

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)  DRY_RUN=1 ;;
        --no-admin) NO_ADMIN=1 ;;
        -h|--help)  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "未知参数：$1（支持 --dry-run / --no-admin）" >&2; exit 2 ;;
    esac
    shift
done

VENV_DIR="${INSTALL_VENV_DIR:-$PROJECT_ROOT/.venv}"
DB="${SPHEROIDIZATION_DB:-$PROJECT_ROOT/data/spheroidization.db}"
ADMIN_USER="${ADMIN_USERNAME:-admin}"

say()  { echo "[install] $*"; }
step() {
    # step <说明> <命令...>：dry-run 时只打印
    local desc="$1"; shift
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "[dry-run] 将执行：$desc"
    else
        say "$desc ..."
        "$@"
    fi
}

say "项目根目录：$PROJECT_ROOT"
say "目标库：$DB"
say "venv：$VENV_DIR"

# ---------------------------------------------------------------- 依赖检测
PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[install] 缺少 python3，无法继续" >&2
    exit 1
fi
say "python3：$PYTHON_BIN（$("$PYTHON_BIN" --version 2>&1)）"

NODE_BIN="$(command -v node || true)"
if [ -n "$NODE_BIN" ] && [ "${INSTALL_SKIP_FRONTEND:-0}" != "1" ]; then
    say "node：$NODE_BIN（$("$NODE_BIN" --version 2>&1)）→ 将构建前端"
    BUILD_FRONTEND=1
else
    say "node 不可用（或 INSTALL_SKIP_FRONTEND=1）→ 跳过前端构建（已有 dist 仍可托管）"
    BUILD_FRONTEND=0
fi

# ---------------------------------------------------------------- 1. venv
if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] 将执行：venv 不存在则创建（$VENV_DIR）并安装 requirements.txt"
else
    if [ ! -x "$VENV_DIR/bin/python" ]; then
        say "创建 venv：$VENV_DIR"
        "$PYTHON_BIN" -m venv "$VENV_DIR"
    else
        say "venv 已存在，跳过创建：$VENV_DIR"
    fi
    say "安装 requirements.txt（幂等：已满足的依赖 pip 直接跳过）"
    "$VENV_DIR/bin/pip" install -q -r "$PROJECT_ROOT/requirements.txt"
fi

# ---------------------------------------------------------------- 2. 前端构建
if [ "$BUILD_FRONTEND" -eq 1 ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "[dry-run] 将执行：cd frontend && npm install && npm run build"
    else
        say "前端构建：npm install && npm run build（产物 frontend/dist，由后端同源托管）"
        (cd "$PROJECT_ROOT/frontend" && npm install --no-audit --no-fund && npm run build)
    fi
fi

# ---------------------------------------------------------------- 3. 建库
if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] 将执行：初始化 SQLite 库（建目录 + 建表）：$DB"
else
    say "初始化数据库：$DB"
    mkdir -p "$(dirname "$DB")"
    (
        cd "$PROJECT_ROOT"
        SPHEROIDIZATION_DB="$DB" "$VENV_DIR/bin/python" - <<'PY'
import os, sys
sys.path.insert(0, os.getcwd())
from app.dependencies import get_container
get_container()  # connect() 会建目录/建表/自检 schema
print(f"  数据库就绪：{os.environ['SPHEROIDIZATION_DB']}")
PY
    )
fi

# ---------------------------------------------------------------- 4. 管理员
if [ "$NO_ADMIN" -eq 1 ]; then
    say "跳过管理员创建（--no-admin）"
elif [ "$DRY_RUN" -eq 1 ]; then
    if [ -n "${ADMIN_PASSWORD:-}" ]; then
        echo "[dry-run] 将执行：创建管理员 $ADMIN_USER（密码来自环境变量 ADMIN_PASSWORD）"
    else
        echo "[dry-run] 将执行：创建管理员 $ADMIN_USER（交互 getpass 输入密码）"
    fi
else
    if [ -n "${ADMIN_PASSWORD:-}" ]; then
        say "创建管理员 $ADMIN_USER（密码来自环境变量，非交互）"
        (
            cd "$PROJECT_ROOT"
            SPHEROIDIZATION_DB="$DB" "$VENV_DIR/bin/python" - <<'PY'
import os, sys
sys.path.insert(0, os.getcwd())
from app.core.security import hash_password
from app.dependencies import get_container
from app.domain.user.entities import UserAccount

username = os.environ.get("ADMIN_USERNAME", "admin")
password = os.environ["ADMIN_PASSWORD"]
c = get_container()
if c.user_repo.get_by_username(username) is not None:
    print(f"  账号 {username} 已存在，跳过（不覆盖已有密码）")
    sys.exit(0)
c.user_repo.save(UserAccount(
    username=username,
    password_hash=hash_password(password),
    created_by="install",
    enabled=1,
    is_admin=1,
))
print(f"  管理员 {username} 创建成功（is_admin=1）")
PY
        )
    else
        if [ ! -t 0 ]; then
            echo "[install] 非交互终端且未设置 ADMIN_PASSWORD，无法建管理员。" >&2
            echo "         要么传 ADMIN_PASSWORD=***，要么交互执行，要么稍后手动：" >&2
            echo "         $VENV_DIR/bin/python scripts/init_admin.py $ADMIN_USER" >&2
            exit 1
        fi
        say "创建管理员 $ADMIN_USER（scripts/init_admin.py，getpass 交互输入）"
        (cd "$PROJECT_ROOT" && SPHEROIDIZATION_DB="$DB" "$VENV_DIR/bin/python" scripts/init_admin.py "$ADMIN_USER")
    fi
fi

# ---------------------------------------------------------------- 5. 播种生效标准
# 没有生效标准时，所有上传接口（merge/补录）都会被业务规则拒掉（400），
# 所以全新库必须自带一条。只在标准表为空时播种，绝不重复造标准。
SEED_DESC="播种生效标准（time=${SEED_STANDARD_TIME:-75} upper=${SEED_STANDARD_TIME_UPPER:-90} lower=${SEED_STANDARD_TIME_LOWER:-60} weighing=${SEED_STANDARD_WEIGHING:-1800}，仅标准表为空时执行）"
if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] 将执行：$SEED_DESC"
else
    say "$SEED_DESC"
    (
        cd "$PROJECT_ROOT"
        SPHEROIDIZATION_DB="$DB" "$VENV_DIR/bin/python" - <<'PY'
import os, sys
sys.path.insert(0, os.getcwd())
from app.dependencies import get_container

c = get_container()
count = c.conn.execute("SELECT COUNT(*) FROM StandardRecord").fetchone()[0]
if count:
    print(f"  库中已有 {count} 条标准，跳过播种")
    sys.exit(0)

time = float(os.environ.get("SEED_STANDARD_TIME", "75"))
upper = os.environ.get("SEED_STANDARD_TIME_UPPER", "90")
lower = os.environ.get("SEED_STANDARD_TIME_LOWER", "60")
weighing = float(os.environ.get("SEED_STANDARD_WEIGHING", "1800"))

from app.application.standard.create import CreateStandardUseCase
uc = CreateStandardUseCase(c.standard_repo, c.standard_application_state)
rec = uc.execute(
    standard_spheroidization_time=time,
    weighing_standard=weighing,
    created_by="install",
    standard_spheroidization_time_upper=float(upper) if upper else None,
    standard_spheroidization_time_lower=float(lower) if lower else None,
    remark="install.sh 初始播种（新标准创建即生效）",
)
print(f"  生效标准 #{rec.standard_record_id} 创建成功：")
print(f"    球化时长 {time:g}s（上限 {upper or '-'} / 下限 {lower or '-'}），称重 {weighing:g}")
PY
    )
fi

# ---------------------------------------------------------------- 完成
if [ "$DRY_RUN" -eq 1 ]; then
    say "dry-run 结束，未做任何改动"
else
    say "安装完成。下一步（现场执行，本脚本不自动做）："
    say "  1. 复制 deploy/env.example 到 /opt/spheroidization/env 并改值"
    say "  2. 部署 systemd unit（deploy/systemd/）后 systemctl start（本脚本不 enable）"
    say "  3. 跑 bash deploy/healthcheck.sh 验证"
fi
