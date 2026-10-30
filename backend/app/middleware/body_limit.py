"""请求体大小限制中间件 — 防止超大请求耗尽内存

在 ASGI 层面检查 Content-Length 头，超限直接返回 413。
没有 Content-Length 的 chunked 请求不在这里限制（原版注释写「读取时累计检查」，实际从未实现）。

纯 ASGI（spec backend-startup-and-request-overhead R3.1），判定与原版相同。
"""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings

_MAX_BYTES = settings.MAX_REQUEST_BODY_MB * 1024 * 1024


class RequestBodyLimitMiddleware:
    """拦截超过 MAX_REQUEST_BODY_MB 的请求体"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # 只检查有 body 的方法
        # DELETE 跳过：RFC 7231 允许 DELETE 携带 body，但实践中极少使用，
        # 且 DELETE 请求通常只传 ID（路径参数），无需限制 body 大小。
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS", "DELETE"):
            await self.app(scope, receive, send)
            return

        # 检查 Content-Length 头
        content_length = Headers(scope=scope).get("content-length")
        if content_length and int(content_length) > _MAX_BYTES:
            response = JSONResponse(
                status_code=413,
                content={
                    "code": 413,
                    "message": f"请求体过大，上限 {settings.MAX_REQUEST_BODY_MB}MB",
                    "data": None,
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
