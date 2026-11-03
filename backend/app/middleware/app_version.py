"""X-App-Version 响应头中间件。

在每个 HTTP 响应（含错误响应）注入 X-App-Version 头，值为当前实例的 git_commit。
放在中间件洋葱较外层以确保所有响应都带该头。

纯 ASGI（spec backend-startup-and-request-overhead R3.1）：在 ``http.response.start`` 上加头，与原
``BaseHTTPMiddleware`` 版本 ``response.headers[...] = ...`` 的结果相同（小写名、追加在末尾、已有则覆盖）。

# Feature: zero-downtime-deployment, Component 1c
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.build_version import get_build_version


class AppVersionHeaderMiddleware:
    """在每个响应注入 X-App-Version: {git_commit}。开销极小（启动时读一次缓存）。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_version(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-App-Version"] = get_build_version()["git_commit"]
            await send(message)

        await self.app(scope, receive, send_with_version)
