"""
密码哈希与会话令牌。

会话表放在进程内存里，不落库也不落文件：
- 好处是改权限、停用账号这些操作不用去同步一份"登录态表"，
  服务一重启所有人重新登录，状态天然干净。
- 代价是必须单进程跑。uvicorn --workers N（N>1）时每个 worker 各有一份
  内存表，登录拿到的 token 换到别的 worker 就查不到，表现为"时好时坏的 401"。
  所以启动命令写死 --workers 1，见 main.py 与部署说明。

token 从 Authorization: Bearer <token> 取，不放 cookie：
前端是 SPA，跨域 cookie 会顺带把 CSRF 问题引进来。
"""

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable

import bcrypt

# bcrypt 只认密码前 72 字节，4.x 起超过 72 字节直接抛 ValueError。
# 这里显式挡在哈希之前，给出能看懂的报错，而不是让人对着底层堆栈猜。
MAX_PASSWORD_BYTES = 72

# 会话有效期 8 小时，对齐车间一个班次：上班登录，下班自然过期。
SESSION_TTL_SECONDS = 8 * 60 * 60

# 每个 bcrypt 轮数开销约几十毫秒，12 是通用默认值
_BCRYPT_ROUNDS = 12


@dataclass(frozen=True)
class Session:
    """一次登录的会话快照。

    permissions 是登录那一刻从库里读出来冻结的，之后管理员改了权限，
    要等这个人重新登录才生效。这样做是为了让"每次请求都查一次权限表"
    这种高频操作用不上——代价是权限变更不实时，接口说明里要写清楚。
    """

    user_id: int
    username: str
    is_admin: bool
    permissions: frozenset[str] = field(default_factory=frozenset)
    expires_at: float = 0.0


# token -> Session。FastAPI 的同步路由跑在线程池里，多个请求会同时读写这个字典，
# 所以每次访问都要在锁里做，不能只靠 GIL——"先读后写"在 GIL 下照样能被切走。
_SESSIONS: dict[str, Session] = {}
_SESSIONS_LOCK = threading.Lock()


def hash_password(plain: str) -> str:
    """把明文密码哈希成可入库的字符串。

    :raises ValueError: 密码超过 72 字节（bcrypt 的硬限制）
    """
    encoded = plain.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"密码不能超过 {MAX_PASSWORD_BYTES} 字节")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(_BCRYPT_ROUNDS)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码和库里的哈希是否匹配。

    哈希格式损坏、超长、空串一律返回 False，不抛异常：
    调用方只需要知道"对不对"，登录失败都走同一句提示。
    """
    try:
        encoded = plain.encode("utf-8")
        if len(encoded) > MAX_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(encoded, hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_token(
    user_id: int,
    username: str = "",
    is_admin: bool = False,
    permissions: Iterable[str] = (),
) -> str:
    """生成令牌并把会话登记进内存表，返回令牌字符串。

    :param permissions: 该用户的权限点。超管由调用方直接传 ALL_PERMISSIONS，
        不在这里判断——"超管等于全部权限"是业务规则，放在应用层更好找。
    """
    token = secrets.token_urlsafe(32)
    session = Session(
        user_id=user_id,
        username=username,
        is_admin=is_admin,
        permissions=frozenset(permissions),
        expires_at=time.time() + SESSION_TTL_SECONDS,
    )
    with _SESSIONS_LOCK:
        _SESSIONS[token] = session
    return token


def validate_password_policy(password: str) -> list[str]:
    """密码强度策略：长度 ≥8，且同时含字母和数字。

    返回不满足项的列表（空列表 = 合格）。统一在这一处判，
    自查改密和管理员重置走同一把尺子，避免两套策略漂移。
    """
    problems = []
    if len(password) < 8:
        problems.append("长度不足 8 位")
    if not any(c.isalpha() for c in password):
        problems.append("必须包含字母")
    if not any(c.isdigit() for c in password):
        problems.append("必须包含数字")
    return problems


def revoke_token(token: str) -> None:
    """注销令牌。令牌本来就不存在时什么也不做。"""
    with _SESSIONS_LOCK:
        _SESSIONS.pop(token, None)


def revoke_all_tokens_for_user(user_id: int) -> int:
    """按用户吊销全部已签发令牌（改密码后调用）。

    内存会话表本来就是全量 token -> Session，按 user_id 扫一遍删掉即可，
    包括当前这次请求正在用的那个 token——改密成功后它立刻作废，
    下次再拿它请求就 401。返回被吊销的条数，方便排查。
    """
    with _SESSIONS_LOCK:
        stale = [key for key, item in _SESSIONS.items() if item.user_id == user_id]
        for key in stale:
            del _SESSIONS[key]
        return len(stale)


def get_session(token: str) -> Session | None:
    """按令牌取会话，取不到或已过期返回 None。

    顺手清掉过期项，不起后台清理线程——
    后台线程和多进程/容器化部署容易打架，这点内存不值得。
    """
    now = time.time()
    with _SESSIONS_LOCK:
        expired = [key for key, item in _SESSIONS.items() if item.expires_at <= now]
        for key in expired:
            del _SESSIONS[key]

        session = _SESSIONS.get(token)
        if session is None or session.expires_at <= now:
            return None
        return session
