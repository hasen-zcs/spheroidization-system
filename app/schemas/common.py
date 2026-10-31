"""统一响应信封。

所有接口都返回 {"code", "message", "data"} 这个形状。
前端是按 body 里的 code 判断成败的（=== 200），不看 HTTP 状态码——
业务错误也是 HTTP 200 + code 400，所以路由失败时不要改 HTTP 状态码。
"""

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    code: int
    message: str
    data: Any = None


def ok(data: Any = None, message: str = "success") -> dict:
    """成功响应。"""
    return {"code": 200, "message": message, "data": data}


def fail(message: str, code: int = 400) -> dict:
    """路由自己判定的失败（业务规则的失败由 BusinessException 抛，见 main.py 的处理器）。"""
    return {"code": code, "message": message, "data": None}
