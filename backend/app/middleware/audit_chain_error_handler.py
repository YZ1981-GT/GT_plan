"""审计链写入被拒（分叉 / 绕过）→ 503 与中文原因。

写链内核对审计链 fail-closed：链有多个未确认链尾或链尾被绕过时，任何需要同事务写审计的操作都会被拒。
没有本处理器时这类异常落到泛型处理器，界面只显示「系统错误，请联系管理员」，看不出是审计链要处理
（spec enterprise-embedding-rerank-closure R10：2026-11-04 共享库全局链分叉 3 天，模型配置录 Key / 启用全部 500）。
"""
from __future__ import annotations

import logging

from fastapi import Request
from starlette.responses import JSONResponse

from app.services.audit_chain.head import AuditChainBypassed, AuditChainError

logger = logging.getLogger("audit_platform.error")


async def audit_chain_error_handler(request: Request, exc: AuditChainError) -> JSONResponse:
    logger.error("审计链拒绝写入 %s %s: %s", request.method, request.url.path, exc)
    if isinstance(exc, AuditChainBypassed):
        reason = "审计日志链尾与实际记录不一致（疑似有绕过写入）"
    else:
        reason = "审计日志链存在未确认的分叉"
    return JSONResponse(
        status_code=503,
        content={
            "code": 503,
            "error_code": "AUDIT_CHAIN_BLOCKED",
            "message": f"{reason}，系统已拒绝写入以保护审计记录；本次操作未保存，请联系管理员处理。",
        },
    )
