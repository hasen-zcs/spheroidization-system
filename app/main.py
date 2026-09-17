from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
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
        # 前端 vite 起在 5173。浏览器地址栏写 localhost 还是 127.0.0.1，
        # 发过来的 Origin 就是哪个，两个都得放行，少一个就整个被 CORS 拦掉。
        "http://localhost:5173",
        "http://127.0.0.1:5173",
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


@app.get("/api/health")
def health_check():
    return {
        "code": 200,
        "message": "success",
        "data": {
            "status": "running"
        }
    }