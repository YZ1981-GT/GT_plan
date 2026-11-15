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
    if _is_ai_chat_run_path(request.url.path):
        # 需求 4.3 / 6.5：未保存草稿正文不得进入日志 / 审计链 payload（只存 hash 与长度）。
        # Pydantic 的 ``errors()`` 每条都带 ``input``（客户端原始值）⇒ 校验失败会把
        # **整段草稿正文**回显进 422 响应体。实测泄漏面（2026-11-15）：
        #   * 超长草稿 ⇒ ``loc=["body","draft_overlay","content"]`` + ``input=<全文>``；
        #   * host 不一致（after-validator）⇒ ``loc=["body"]`` + ``input=<整份请求体>``。
        # 422 响应体本身不进 ``logs``（注册的 ``AuditLogMiddleware`` 只缓冲 2xx，
        # 已实测），但它会被 ``generic_exception_handler`` 之外的每一层看到：
        # 浏览器网络面板、前端错误上报、以及任何在上层再记一次响应的日志 / APM。
        # 因此**在这里**（响应构造的唯一出口）脱敏，而不是依赖调用方自觉。
        detail = _redact_draft_overlay_detail(detail)
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


#: Chat Run 创建路由的路径片段（结构匹配）。
_AI_CHAT_RUN_PATH_MARKERS = ("/ai-chat/runs",)

#: 「请求体里带了未保存草稿」的校验错误定位前缀。
#:
#: 三种真实形态（2026-11-15 逐条实测 ``ChatRunRequest.model_validate``）：
#: * ``("draft_overlay", "content")`` —— content 校验失败（超长 / 空白）；
#: * ``("draft_overlay",)`` —— overlay 整体类型不对；
#: * ``()`` —— ``model_validator(mode="after")`` 抛错（host_id 不一致），
#:   此时 ``input`` 是**整个请求体 dict**，草稿正文原样在内。
_DRAFT_OVERLAY_LOC_PREFIX = "draft_overlay"


def _is_ai_chat_run_path(path: str) -> bool:
    """是否是 Chat Run 创建路由（草稿 overlay 的唯一入口）。"""
    return any(marker in path.lower().rstrip("/") for marker in _AI_CHAT_RUN_PATH_MARKERS)


def _payload_carries_draft_overlay(value: object) -> bool:
    """该 ``input`` 值是否是「含 draft_overlay 的请求体」。

    🔴 这是**内容判据**而不是只按 ``loc`` 判：``model_validator(mode="after")`` 的
    ``loc`` 是空元组（见上），只按路径前缀过滤会漏掉那一整类。两者都判、任一条命中
    即脱敏（fail-closed：宁可少给一个字段的细节）。

    只认 dict 且**顶层有该键**：不把任意字符串都当成正文（那会把 query / sheet_name
    等无关字段的 input 一起删掉，改变与草稿无关的既有 422 契约）。
    """
    return isinstance(value, dict) and _DRAFT_OVERLAY_LOC_PREFIX in value


def _redact_draft_overlay_detail(detail):
    """Chat Run 创建路由的 422 详情：草稿正文一律不进响应体。

    🔴 为什么必须在**这里**（响应构造的唯一出口）脱敏，而不是只在调用点自觉：
    422 响应体是框架自动生成的，任何"由调用方注意不要回显"的做法都覆盖不到它；
    而这个响应体会被浏览器网络面板、前端错误上报、以及上层日志 / APM 看到。
    实测（2026-11-15）：注册的 ``AuditLogMiddleware`` 只缓冲 **2xx** 响应体，
    因此 422 目前**不会**落进 ``logs`` 表 —— 这条脱敏的价值在于把"框架自动回显
    客户端原始值"这条链路整体掐掉，而不依赖某个中间件的当前实现细节。

    保留 ``loc`` / ``msg`` / ``type``（前端定位与本地化所需），并对命中草稿的条目
    删掉 ``input`` / ``ctx``；``ctx`` 里的 ``ValueError`` 本身不含正文，但它与
    ``input`` 成对出现，一并删除以免将来有人往 ctx 里塞内容。
    """
    if isinstance(detail, list):
        return [_redact_draft_overlay_detail(item) for item in detail]
    if not isinstance(detail, dict):
        return detail

    loc = detail.get("loc")
    # 🔴 FastAPI 会在 ``loc`` 前面插一段 ``"body"``（实测：``["body","draft_overlay","content"]``）。
    #    只比 ``loc[0]`` 会整类漏掉 —— 那正是"超长草稿正文被回显"的那一类。
    loc_path = [str(part) for part in loc] if isinstance(loc, (list, tuple)) else []
    if loc_path and loc_path[0] == "body":
        loc_path = loc_path[1:]
    touches_overlay = bool(loc_path) and loc_path[0] == _DRAFT_OVERLAY_LOC_PREFIX
    if not touches_overlay and not _payload_carries_draft_overlay(detail.get("input")):
        # 与草稿无关的校验错误：照既有行为原样返回（不改变既有契约）。
        return {key: _redact_draft_overlay_detail(value) for key, value in detail.items()}

    return {
        key: _redact_draft_overlay_detail(value)
        for key, value in detail.items()
        if key not in ("input", "ctx")
    }


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
