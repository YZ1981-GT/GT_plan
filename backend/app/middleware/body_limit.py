"""请求体大小限制中间件 — 防止超大请求耗尽内存

在 ASGI 层面检查 Content-Length 头，超限直接返回 413。
对于没有 Content-Length 的 chunked 请求，在读取时累计检查。
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

_MAX_BYTES = settings.MAX_REQUEST_BODY_MB * 1024 * 1024


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    """拦截超过 MAX_REQUEST_BODY_MB 的请求体"""

    async def dispatch(self, request: Request, call_next):
        # 只检查有 body 的方法
        if request.method in ("GET", "HEAD", "OPTIONS", "DELETE"):
            return await call_next(request)

        # 检查 Content-Length 头
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "code": 413,
                    "message": f"请求体过大，上限 {settings.MAX_REQUEST_BODY_MB}MB",
                    "data": None,
                },
            )

        return await call_next(request)
