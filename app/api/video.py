"""视频流反向代理。

前端监控页要两路 MJPEG（/api/video_feed1、/api/video_feed2），但视频服务
不在本进程里——现场是检测程序单独起的 5080。之前只靠 Vite 开发代理，
打包上线后这两个地址就是 404，监控页黑框。

这里做一层薄代理：
- 地址由环境变量 VIDEO_FEED_BASE 指定（默认 http://127.0.0.1:5080）；
- 原样流式转发，不缓冲整段，MJPEG 才能持续出帧；
- 上游连不上返回 503 + 信封，前端 <img> 表现为裂图，不影响其它功能。

注意：这是"够用"的实现——每个连接占一个线程（FastAPI 同步栈本来如此）。
两路视频只有两个连接，现场规模完全够；要更高并发再换 nginx 反代。
"""

import os
import urllib.error
import urllib.request

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix="/api", tags=["视频流"])

DEFAULT_BASE = "http://127.0.0.1:5080"
CHUNK_SIZE = 64 * 1024
# 上游 5 秒没有任何字节就断开，浏览器会自己重连（前端带 ?t= 时间戳）
UPSTREAM_TIMEOUT = 5


def _upstream_base() -> str:
    return os.getenv("VIDEO_FEED_BASE", DEFAULT_BASE).rstrip("/")


def _proxy(name: str):
    url = f"{_upstream_base()}/{name}"
    try:
        upstream = urllib.request.urlopen(url, timeout=UPSTREAM_TIMEOUT)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return JSONResponse(
            {
                "code": 503,
                "message": f"视频服务不可用：{exc}",
                "data": None,
            },
            status_code=503,
        )

    content_type = upstream.headers.get("Content-Type", "multipart/x-mixed-replace")

    def stream():
        try:
            while True:
                chunk = upstream.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            upstream.close()

    return StreamingResponse(
        stream(),
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/video_feed1")
def video_feed1():
    return _proxy("video_feed1")


@router.get("/video_feed2")
def video_feed2():
    return _proxy("video_feed2")
