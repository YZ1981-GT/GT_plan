"""X-App-Version 响应头中间件。

在每个 HTTP 响应（含错误响应）注入 X-App-Version 头，值为当前实例的 git_commit。
放在中间件洋葱较外层以确保所有响应都带该头。

# Feature: zero-downtime-deployment, Component 1c
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.build_version import get_build_version


class AppVersionHeaderMiddleware(BaseHTTPMiddleware):
    """在每个响应注入 X-App-Version: {git_commit}。开销极小（启动时读一次缓存）。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-App-Version"] = get_build_version()["git_commit"]
        return response
