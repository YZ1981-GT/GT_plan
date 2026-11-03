"""Request ID 链路追踪中间件

每个请求自动生成 X-Request-ID，贯穿日志和响应头。

纯 ASGI（spec backend-startup-and-request-overhead R3.1）：下游与本中间件在同一个任务里跑，上下文变量
在下游可见（原 ``BaseHTTPMiddleware`` 版本下游跑在新任务里，同样可见）；外层中间件此后的日志也能带上它。
"""

import uuid
import logging
from contextvars import ContextVar

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 上下文变量，供日志 filter 使用
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # 优先使用客户端传入的 X-Request-ID，否则自动生成
        rid = Headers(scope=scope).get("X-Request-ID") or str(uuid.uuid4())[:12]
        request_id_var.set(rid)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = rid
            await send(message)

        await self.app(scope, receive, send_with_id)


class RequestIDFilter(logging.Filter):
    """日志 filter：自动注入 request_id 到日志记录"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")  # type: ignore
        return True
