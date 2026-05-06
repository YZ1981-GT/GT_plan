"""审计日志中间件 — 拦截写操作，记录到 logs 表

拦截 POST/PUT/PATCH/DELETE 请求，自动记录操作日志。
日志写入失败不影响业务响应。

## 与 audit_decorator 的分工

| 维度 | AuditLogMiddleware（本文件） | audit_decorator |
|------|------------------------------|-----------------|
| 层次 | HTTP 中间件（传输层） | 服务层装饰器（业务层） |
| 触发 | 所有写请求（POST/PUT/PATCH/DELETE） | 仅被 @audit_log 装饰的方法 |
| 粒度 | 粗粒度：记录 HTTP 请求体 + 响应状态 | 细粒度：记录 before/after diff |
| 上下文 | 无业务上下文（只有 URL + body） | 有完整业务上下文（project_id、user_id、ORM 快照） |
| 适用场景 | 通用操作审计（谁在什么时间做了什么） | 关键业务操作（调整分录审批、底稿状态变更等） |

两者可共存：中间件提供全量覆盖，装饰器提供精细 diff。

Validates: Requirements 1.5
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.database import async_session
from app.core.security import decode_token
from app.models.core import Log
from app.models.collaboration_models import OpType

logger = logging.getLogger("audit_platform.audit_log")

# 需要记录日志的 HTTP 方法
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 跳过日志记录的路径前缀
SKIP_PATHS = (
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)

# HTTP 方法 → operation_type 映射
METHOD_OP_MAP = {
    "POST": OpType.create,
    "PUT": OpType.update,
    "PATCH": OpType.update,
    "DELETE": OpType.delete,
}

# UUID 正则
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


async def get_client_ip(request: Request) -> str:
    """提取客户端 IP"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _extract_object_type(path: str) -> str:
    """从 URL 路径提取 object_type"""
    clean = path.removeprefix("/api/").removeprefix("/wopi/")
    segments = [s for s in clean.split("/") if s]
    if not segments:
        return "unknown"
    resource = segments[0]
    if resource.endswith("s") and len(resource) > 1:
        return resource[:-1]
    return resource


def _extract_object_id(path: str) -> uuid.UUID | None:
    """从 URL 路径中提取 UUID"""
    match = UUID_PATTERN.search(path)
    if match:
        return uuid.UUID(match.group())
    return None


async def _extract_user_id(request: Request) -> uuid.UUID | None:
    """从 Authorization header 提取 user_id"""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:]
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if sub:
            return uuid.UUID(sub)
    except (JWTError, ValueError):
        pass
    return None


class AuditLogMiddleware(BaseHTTPMiddleware):
    """操作日志中间件 — 对写操作自动记录审计日志"""

    async def dispatch(self, request: Request, call_next):
        if request.method not in WRITE_METHODS:
            return await call_next(request)

        path = request.url.path
        if path.startswith(SKIP_PATHS):
            return await call_next(request)

        response = None
        old_value = None
        new_value = None

        # 读取请求体（POST/PUT/PATCH）
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if body:
                try:
                    new_value = json.loads(body)
                except Exception:
                    new_value = {"raw": body.decode("utf-8", errors="replace")}

        response = await call_next(request)

        # 仅对成功响应记录日志
        if response.status_code >= 400:
            return response

        # 异步写入日志
        try:
            async with async_session() as session:
                user_id = await _extract_user_id(request)
                project_id = getattr(request.state, "project_id", None)
                
                operation = METHOD_OP_MAP.get(request.method, OpType.update)

                log_entry = Log(
                    user_id=user_id,
                    action_type=operation.value if hasattr(operation, 'value') else str(operation),
                    object_type=_extract_object_type(path),
                    object_id=getattr(request.state, "object_id", None) or _extract_object_id(path),
                    old_value=old_value,
                    new_value=new_value if isinstance(new_value, dict) else None,
                    ip_address=await get_client_ip(request),
                )
                session.add(log_entry)
                await session.commit()
        except Exception:
            logger.error("Failed to write audit log", exc_info=True)

        return response
