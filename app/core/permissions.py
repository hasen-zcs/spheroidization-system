"""
权限点常量与免登录白名单。

权限点一律用字符串，和 UserPermission 表里存的完全一致。
不要改成 Enum 再往库里塞——枚举对象存不进 TEXT 列，取出来还得再映射一次，
中间任何一处漏了转换，库里的值就和常量对不上了。

一共 10 个：page:* 四个（能进哪些页面）、action:* 六个（能做什么操作）。
首页和监控页游客也能进，没有可拦截的对象，所以 page:home、page:monitor
不设权限点。改这个数量的时候，用户管理页的勾选框要跟着改。
"""

PAGE_RECORDS = "page:records"
PAGE_ABNORMAL = "page:abnormal"
PAGE_STANDARD = "page:standard"
PAGE_USERS = "page:users"

ACTION_SWITCH_STANDARD = "action:switch_standard"
ACTION_CREATE_STANDARD = "action:create_standard"
ACTION_REVIEW = "action:review"
ACTION_PROCESS = "action:process"
ACTION_MANAGE_USERS = "action:manage_users"
ACTION_MANAGE_DATA = "action:manage_data"

ALL_PERMISSIONS = frozenset(
    {
        PAGE_RECORDS,
        PAGE_ABNORMAL,
        PAGE_STANDARD,
        PAGE_USERS,
        ACTION_SWITCH_STANDARD,
        ACTION_CREATE_STANDARD,
        ACTION_REVIEW,
        ACTION_PROCESS,
        ACTION_MANAGE_USERS,
        ACTION_MANAGE_DATA,
    }
)

# 免登录白名单。
#
# 本系统不写全局鉴权中间件，需要保护的接口逐个挂 require_permission(...)，
# 没挂依赖的接口天然免登录。所以这个集合不参与后端拦截，只作两处用途：
#   ① 前端路由守卫据此判断游客能进哪些页面；
#   ② 以后真要加中间件，拿它当现成配置。
#
# 只列精确路径，不按前缀放行。按前缀放行会把
# /api/spheroidization/1/process 这种 POST 也一起放进去——
# 游客能改数据的口子就是这么开的。
PUBLIC_PATHS = frozenset(
    {
        "/api/users/login",
        "/api/users/logout",
        "/api/users/accounts",  # 登录页账号下拉，免登录（内网环境，老板明确不要求防枚举）
        "/api/temperature",  # 测温枪上报，程序调用，没有登录态
        "/api/spheroidization",  # 监控页列表；游客带 abnormal=true 由接口内拒绝
        "/api/spheroidization/stats",  # 首页统计
        "/api/standards/current",
        "/api/health",
    }
)


def is_known_permission(permission_key: str) -> bool:
    """判断是不是我们认识的权限点。

    给授权接口做入参校验用：传进来一个拼错的 key，写进库也不会报错，
    只会变成一个永远不生效的幽灵权限，用户还以为给了。
    """
    return permission_key in ALL_PERMISSIONS
