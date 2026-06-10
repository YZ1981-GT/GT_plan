"""In-flight HTTP 请求计数中间件。

维护进程级 in-flight 请求计数，供 drain 等待判定。
探针请求（/livez /readyz）不计数（避免健康检查永远阻止 drain 完成）。

# Feature: zero-downtime-deployment, Component 3a
"""
import asyncio

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class _InflightCounter:
    """线程安全（asyncio 单线程无需锁）的 in-flight 计数器。"""

    def __init__(self):
        self._count: int = 0

    def increment(self):
        self._count += 1

    def decrement(self):
        self._count -= 1

    def value(self) -> int:
        return self._count


# 进程级单例
inflight_counter = _InflightCounter()

_SKIP_PATHS = frozenset({"/livez", "/readyz"})


class InflightTrackingMiddleware(BaseHTTPMiddleware):
    """维护进程级 in-flight HTTP 请求计数。探针不计数。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)
        inflight_counter.increment()
        try:
            return await call_next(request)
        finally:
            inflight_counter.decrement()
