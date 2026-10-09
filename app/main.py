import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import spheroidization
from app.api import review
from app.api import standard
from app.core.exceptions import BusinessException
from app.dependencies import get_container


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时就把连接建好、表建好。
    # 数据库路径不对、schema.sql 有问题，都在启动那一刻就报出来，
    # 而不是等第一个请求进来才发现。
    get_container()
    yield


app = FastAPI(
    title="球化监测系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(spheroidization.router)
app.include_router(review.router)
app.include_router(standard.router)


@app.exception_handler(BusinessException)
async def business_exception_handler(
    request: Request,
    exc: BusinessException,
):
    return JSONResponse(
        status_code=200,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": None,
        },
    )


def _describe_validation_error(exc: RequestValidationError) -> str:
    """把 pydantic 的报错压成一行能直接读的中文。
    报错的 loc 第一段是 body / query / path，对前端没意义，去掉。
    """
    details = []
    for error in exc.errors():
        # loc 里可能混着数字（数组下标），统一转成字符串再拼
        field = ".".join(str(part) for part in error["loc"][1:]) or "请求体"
        details.append(f"{field}: {error['msg']}")
    return "请求参数不合法 — " + "；".join(details)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """把 FastAPI 自己的 422 也套进统一信封。

    不接这个处理器的话，漏传一个必填字段会返回 {"detail": [...]}——
    形状和别的接口完全不一样，前端那套"读 body.code"的判断会直接读到 undefined，
    表现成"点了按钮什么都没发生"。

    默认的 422 其实也是 HTTP 200，理由和 BusinessException 一样：前端只看 body.code。
    """
    return JSONResponse(
        status_code=200,
        content={
            "code": 422,
            "message": _describe_validation_error(exc),
            "data": None,
        },
    )


@app.exception_handler(sqlite3.IntegrityError)
async def sqlite_integrity_exception_handler(
    request: Request,
    exc: sqlite3.IntegrityError,
):
    """数据库约束失败也不能破坏统一响应信封。"""
    return JSONResponse(
        status_code=200,
        content={
            "code": 400,
            "message": "提交的数据不符合数据库约束",
            "data": None,
        },
    )


@app.get("/api/health")
def health_check():
    return {
        "code": 200,
        "message": "success",
        "data": {
            "status": "running"
        }
    }
