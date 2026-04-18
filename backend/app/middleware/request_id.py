"""Request ID 链路追踪中间件

每个请求自动生成 X-Request-ID，贯穿日志和响应头。
"""

import uuid
import logging
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# 上下文变量，供日志 filter 使用
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 优先使用客户端传入的 X-Request-ID，否则自动生成
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:12]
        request_id_var.set(rid)

        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class RequestIDFilter(logging.Filter):
    """日志 filter：自动注入 request_id 到日志记录"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")  # type: ignore
        return True
