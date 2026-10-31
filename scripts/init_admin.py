"""初始化第一个管理员账号。

为什么必须有这个脚本：UserAccount 是空表时没有任何人能登录，而建用户的接口
本身要求 action:manage_users 权限——没有第一个管理员就永远进不去，是个死锁。
所以第一个管理员只能从命令行塞进去。

用法（在项目根目录执行）：

    python scripts/init_admin.py <用户名>

密码用 getpass 交互输入，不回显，也不进 shell 历史。
不要把密码写成命令行参数：那样会留在 shell history 和 ps 输出里。

幂等：同名账号已存在就打印提示退出，不覆盖已有密码。
（覆盖密码有时候会被当成"重置管理员密码"的用法，但那等于悄悄改掉一个
可能正在用的账号，所以这里宁可拒绝，让人自己决定要不要删库重来。）

部署流程固定为：删库 → 启动服务 → 跑本脚本建管理员 → 交付。
少这一步，现场谁也登不进去。
"""

import getpass
import sys
from pathlib import Path

# 直接 `python scripts/init_admin.py` 时，sys.path[0] 是 scripts/ 而不是项目根目录，
# `import app.xxx` 会报 ModuleNotFoundError。把项目根目录插到最前面。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.security import hash_password  # noqa: E402
from app.dependencies import get_container  # noqa: E402
from app.domain.user.entities import UserAccount  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("用法：python scripts/init_admin.py <用户名>", file=sys.stderr)
        return 2

    username = sys.argv[1].strip()
    if not username:
        print("用户名不能为空", file=sys.stderr)
        return 2

    container = get_container()
    user_repo = container.user_repo

    if user_repo.get_by_username(username) is not None:
        print(f"账号 {username} 已存在，未做任何修改。")
        return 0

    password = getpass.getpass("请输入管理员密码（输入时不显示）：")
    confirm = getpass.getpass("请再输入一次：")
    if password != confirm:
        print("两次输入的密码不一致", file=sys.stderr)
        return 1
    if not password:
        print("密码不能为空", file=sys.stderr)
        return 1

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        # bcrypt 只认 72 字节以内，给出能看懂的提示，别让人对着堆栈猜
        print(f"密码不合要求：{exc}", file=sys.stderr)
        return 1

    user_repo.save(
        UserAccount(
            username=username,
            password_hash=password_hash,
            # 自举的管理员，"谁建的"只能是系统自己
            created_by="system",
            # created_at 由仓储实现方生成
            enabled=1,
            is_admin=1,
        )
    )

    print(f"管理员 {username} 创建成功（is_admin=1，拥有全部权限）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
