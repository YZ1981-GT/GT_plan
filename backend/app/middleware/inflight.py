"""In-flight HTTP 请求计数中间件。

维护进程级 in-flight 请求计数，供 drain 等待判定。
探针请求（/livez /readyz）不计数（避免健康检查永远阻止 drain 完成）。

纯 ASGI（spec backend-startup-and-request-overhead R3.1）：计数覆盖到下游调用结束（响应体发完）。原
``BaseHTTPMiddleware`` 版本在拿到响应头时就减一，流式响应还在输出时已不计入。

流式（SSE）请求另记一份子计数（spec runtime-performance-and-reload-hardening-followup 任务 5）：
``text/event-stream`` 响应能挂几十分钟，只要有一个浏览器标签订阅，``value()`` 就永远不为 0。
drain 仍用 ``value()``（停旧 worker 前必须等 SSE 也断开或被强停），而「等一个真正空闲窗口做
GC freeze」只能用 ``value_excluding_streams()``，否则 freeze 永不发生。
识别走响应头 ``content-type``，不按路由清单——全仓 10 处 SSE 分散在 8 个 router，清单必漂。

# Feature: zero-downtime-deployment, Component 3a
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.middleware._asgi import request_path

#: 判定「长连接流式响应」的响应头值（小写前缀匹配）。
STREAM_MEDIA_TYPE = b"text/event-stream"


class _InflightCounter:
    """线程安全（asyncio 单线程无需锁）的 in-flight 计数器。"""

    def __init__(self):
        self._count: int = 0
        self._streaming: int = 0

    def increment(self):
        self._count += 1

    def decrement(self):
        self._count -= 1

    def mark_streaming(self):
        self._streaming += 1

    def unmark_streaming(self):
        self._streaming -= 1

    def value(self) -> int:
        return self._count

    def streaming(self) -> int:
        return self._streaming

    def value_excluding_streams(self) -> int:
        """扣掉已开始输出的 SSE 长连接后的在途请求数（GC 空闲窗口判定用）。"""
        return self._count - self._streaming


# 进程级单例
inflight_counter = _InflightCounter()

_SKIP_PATHS = frozenset({"/livez", "/readyz"})


def _is_stream_start(message: Message) -> bool:
    """只看 ``http.response.start`` 的 content-type 是否为 SSE。"""
    for name, value in message.get("headers") or ():
        if name.lower() == b"content-type":
            return value.lower().startswith(STREAM_MEDIA_TYPE)
    return False


class InflightTrackingMiddleware:
    """维护进程级 in-flight HTTP 请求计数。探针不计数。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or request_path(scope) in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return
        inflight_counter.increment()
        seen_start = False
        streaming = False

        async def send_wrapper(message: Message) -> None:
            nonlocal seen_start, streaming
            if not seen_start and message["type"] == "http.response.start":
                seen_start = True
                if _is_stream_start(message):
                    streaming = True
                    inflight_counter.mark_streaming()
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if streaming:
                inflight_counter.unmark_streaming()
            inflight_counter.decrement()
