"""操作日志中间件

拦截 POST/PUT/PATCH/DELETE 请求，自动记录操作日志到 logs 表。
日志写入失败不影响业务响应。

Validates: Requirements 4.5, 4.6, 4.12
"""

import json
import logging
import re
import uuid

from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.database import async_session
from app.core.security import decode_token
from app.models.core import Log

logger = logging.getLogger("audit_platform.audit_log")

# 需要记录日志的 HTTP 方法
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 跳过日志记录的路径
_SKIP_PATHS = (
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)

# HTTP 方法 → action_type 映射
_METHOD_ACTION_MAP = {
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}

# UUID 正则（用于从路径中提取 object_id）
_UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def _extract_client_ip(request: Request) -> str | None:
    """提取客户端 IP：优先 X-Forwarded-For（第一个 IP），回退 request.client.host。"""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # X-Forwarded-For 格式: client, proxy1, proxy2
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _extract_user_id_from_token(request: Request) -> uuid.UUID | None:
    """从 Authorization header 中提取 user_id，失败返回 None（不阻断请求）。"""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:]  # 去掉 "Bearer " 前缀
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if sub:
            return uuid.UUID(sub)
    except (JWTError, ValueError):
        pass
    return None


def _extract_object_type(path: str) -> str:
    """从 URL 路径提取 object_type。

    例如:
        /api/users       → "user"
        /api/users/123   → "user"
        /api/projects    → "project"
        /api/auth/logout → "auth"
    """
    # 去掉 /api/ 前缀
    clean = path.removeprefix("/api/").removeprefix("/wopi/")
    # 按 / 分割，取第一个非空段
    segments = [s for s in clean.split("/") if s]
    if not segments:
        return "unknown"
    resource = segments[0]
    # 去掉尾部 s 做单数化（简单处理）
    if resource.endswith("s") and len(resource) > 1:
        return resource[:-1]
    return resource


def _extract_object_id(path: str) -> uuid.UUID | None:
    """从 URL 路径中提取 UUID 格式的 object_id。"""
    match = _UUID_PATTERN.search(path)
    if match:
        return uuid.UUID(match.group())
    return None


async def _read_response_body(response: Response) -> tuple[bytes, dict | None]:
    """读取响应体并尝试解析为 JSON。返回 (原始字节, 解析后的 dict 或 None)。"""
    body_bytes = b""
    async for chunk in response.body_iterator:  # type: ignore[union-attr]
        if isinstance(chunk, str):
            body_bytes += chunk.encode("utf-8")
        else:
            body_bytes += chunk

    parsed = None
    try:
        parsed = json.loads(body_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    return body_bytes, parsed


async def _write_log(
    user_id: uuid.UUID | None,
    action_type: str,
    object_type: str,
    object_id: uuid.UUID | None,
    old_value: dict | None,
    new_value: dict | None,
    ip_address: str | None,
) -> None:
    """异步写入日志记录，使用独立数据库会话。写入失败仅记录错误日志。"""
    try:
        async with async_session() as session:
            log_entry = Log(
                user_id=user_id,
                action_type=action_type,
                object_type=object_type,
                object_id=object_id,
                old_value=old_value,
                new_value=new_value,
                ip_address=ip_address,
            )
            session.add(log_entry)
            await session.commit()
    except Exception:
        logger.error("Failed to write audit log", exc_info=True)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """操作日志中间件 — 对写操作自动记录审计日志。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 仅拦截写方法
        if request.method not in _WRITE_METHODS:
            return await call_next(request)

        # 跳过无需记录的路径
        path = request.url.path
        if path.startswith(_SKIP_PATHS):
            return await call_next(request)

        # 提取请求信息
        user_id = _extract_user_id_from_token(request)
        ip_address = _extract_client_ip(request)
        action_type = _METHOD_ACTION_MAP.get(request.method, "unknown")
        object_type = _extract_object_type(path)
        object_id = _extract_object_id(path)

        # 执行业务逻辑
        response = await call_next(request)

        # 仅对成功响应记录日志（2xx）
        if not (200 <= response.status_code < 300):
            return response

        # 读取响应体，尝试解析为 new_value
        body_bytes, new_value = await _read_response_body(response)

        # 异步写入日志（不阻断响应）
        # old_value 在中间件层暂不捕获，后续由具体 CRUD 服务增强
        await _write_log(
            user_id=user_id,
            action_type=action_type,
            object_type=object_type,
            object_id=object_id,
            old_value=None,
            new_value=new_value if isinstance(new_value, dict) else None,
            ip_address=ip_address,
        )

        # 重建响应（因为 body_iterator 已被消费）
        return Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
