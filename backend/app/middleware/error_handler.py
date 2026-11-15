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
from fastapi.encoders import jsonable_encoder
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
    """处理 Pydantic 校验错误，返回 422 + 字段级错误详情。

    🔴 ``exc.errors()`` 必须经 ``jsonable_encoder``（FastAPI 自带处理器同样如此）：自定义 ``field_validator`` 抛
    ``ValueError`` 时错误里带 ``ctx.error``（异常对象），直接序列化会 TypeError ⇒ 本该 422 的请求变成 500。

    🔴 **PDF 创建路由的结构化脱敏**（spec platform-global-display-settings-closure 任务 10 / AC-22）：
    Pydantic v2 的错误条目里 `input` / `context` 会带**原始请求值**（密码、项目 id 等）。
    PDF create 带 `password` 字段，一旦校验失败就会把明文密码回显进 422 响应、应用日志与审计日志。
    这里对 PDF create 路径**结构化删除**这两个键（只留 `loc`/`msg`/`type`），
    不做序列化后字符串替换（后者脆且会漏掉嵌套结构）。
    """
    detail = jsonable_encoder(exc.errors())
    if _is_pdf_create_path(request.url.path):
        detail = _redact_validation_detail(detail)
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "message": "请求参数校验失败",
            "detail": detail,
        },
    )


#: PDF 创建路由的路径片段（结构匹配，不做前缀猜测）。
_PDF_CREATE_PATH_MARKERS = ("/pdf-export", "/pdf/export")


def _is_pdf_create_path(path: str) -> bool:
    """判断是否是 PDF 创建路由。

    🔴 用**路径片段**而非完整路径匹配：PDF 创建路由在不同 router 里的前缀可能变
    （`/api/projects/{id}/pdf-export`、`/api/export/pdf/export` 等），
    按前缀硬编码会漏掉。判据是「路径末段含 pdf 且含 export/create」这类形态。
    """
    lowered = path.lower().rstrip("/")
    if any(marker in lowered for marker in _PDF_CREATE_PATH_MARKERS):
        return True
    # 兜底：末段同时含 pdf 与 export
    tail = lowered.rsplit("/", 2)[-2:]
    joined = "/".join(tail)
    return "pdf" in joined and ("export" in joined or "create" in joined)


def _redact_validation_detail(detail):
    """结构化删除 `input` / `context`（保留 `loc` / `msg` / `type`）。

    🔴 为什么不整段丢弃：`loc` 与 `msg` 是调用方定位问题的唯一依据；
    `type` 用于前端做本地化。只删会带原始值的两个键。
    """
    if isinstance(detail, list):
        return [_redact_validation_detail(item) for item in detail]
    if isinstance(detail, dict):
        return {
            key: value
            for key, value in detail.items()
            if key not in ("input", "context")
        }
    return detail


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
    """处理未捕获异常，返回 500 通用消息，堆栈记录到日志文件。

    例外：异常是「表 / 列不存在」且磁盘上确有未执行的迁移 ⇒ 503 ``MIGRATION_PENDING``，说明数据库结构落后于程序
    （spec voucher-workflow-linkage-lineage-closure R2）。没有待执行迁移时照旧 500。
    """
    logger.error(
        "Unhandled exception on %s %s\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    from app.core.migration_pending import is_missing_schema_error, pending_migration_info

    if is_missing_schema_error(exc):
        pending = await pending_migration_info()
        if pending is not None:
            return JSONResponse(status_code=503, content={"code": 503, "message": pending.detail()})
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误"},
    )
