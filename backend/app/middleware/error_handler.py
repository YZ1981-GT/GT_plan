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


async def evidence_governance_error_handler(request: Request, exc):
    """把 ``EvidenceGovernanceError`` 映射为脱敏 HTTP 响应（design §7.2）。

    没有该处理器时，治理层从 router 抛出的稳定错误会落到 ``generic_exception_handler``
    并统一返回 500 —— 这会把 R4.2 / design §7.2 要求的 clean 4xx
    ``SCOPE_NOT_FOUND_OR_FORBIDDEN`` 误报成 500。此处按 ``error_code`` 的主 HTTP 状态
    返回 ``code/error_code/message/retryable``，message 已是脱敏通用提示，不含目标名称、
    项目、客户或路径。
    """
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "code": exc.http_status,
            "error_code": exc.error_code.value,
            "message": str(exc),
            "retryable": bool(getattr(exc, "retryable", False)),
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
