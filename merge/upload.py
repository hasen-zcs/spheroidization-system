"""上传：幂等键 + 退避重试 + 死信。

重试口径（第一刀方案 v2 第 3.6 节）：
- 网络错误 / 5xx：无限次重试，退避 1→2→4…封顶 60 秒；只有挂了 24 小时才进死信
- 4xx（除 409）和 409：**立刻死信**，重试没有意义——
  4xx 是我发错了，409 是上游流水号撞了，重来一百次也一样

死信不是垃圾桶：表里有原始 body 和错误原因，人工改完可以 --replay-dead-letter。
"""

import json
import urllib.error
import urllib.request
from typing import Optional

from .config import Config


class TransportError(Exception):
    """网络层失败（连接不上、超时）。当成 5xx 处理，可以重试。"""


class HttpTransport:
    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def post(self, url: str, body: str) -> tuple[int, dict]:
        data = body.encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                return resp.status, _decode(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _decode(exc.read())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(str(exc)) from exc


def _decode(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"code": None, "raw": raw.decode("utf-8", "replace")}


class Uploader:
    def __init__(self, cfg: Config, transport: Optional[HttpTransport] = None):
        self.cfg = cfg
        self.transport = transport or HttpTransport(cfg.http_timeout)

    @property
    def url(self) -> str:
        return self.cfg.backend_url.rstrip("/") + "/api/spheroidization"

    def send(self, body: str) -> tuple[int, dict]:
        return self.transport.post(self.url, body)

    def backoff(self, attempts: int) -> float:
        """1, 2, 4, 8 … 封顶 retry_max_delay 秒。"""
        return min(self.cfg.retry_max_delay, float(2 ** max(0, attempts)))
