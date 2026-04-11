"""全局异常处理器

注册为 FastAPI exception_handler，统一错误响应格式。

- HTTPException → 对应状态码和消息
- RequestValidationError → 422 + 字段级错误详情
- Exception → 500 "服务器内部错误"，记录堆栈到日志文件

Validates: Requirements 4.2, 4.3, 4.4
"""

import logging
import traceback

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

logger = logging.getLogger("audit_platform.error")


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """处理 HTTPException，返回对应状态码和消息。"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": exc.detail},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """处理 Pydantic 校验错误，返回 422 + 字段级错误详情。"""
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "message": "请求参数校验失败",
            "detail": exc.errors(),
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理未捕获异常，返回 500 通用消息，堆栈记录到日志文件。"""
    logger.error(
        "Unhandled exception on %s %s\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误"},
    )
