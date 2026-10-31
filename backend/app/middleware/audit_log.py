"""操作日志中间件

拦截 POST/PUT/PATCH/DELETE 请求，自动记录操作日志到 logs 表。
日志写入失败不影响业务响应。

Validates: Requirements 4.5, 4.6, 4.12
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from jose import JWTError
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.middleware._asgi import request_path

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
    "/api/events/",
    "/api/message/stream",
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


def _parse_json(body_bytes: bytes) -> object:
    """尝试把响应体解析为 JSON，失败返回 None。"""
    try:
        return json.loads(body_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


async def _write_log(
    user_id: uuid.UUID | None,
    action_type: str,
    object_type: str,
    object_id: uuid.UUID | None,
    old_value: dict | None,
    new_value: dict | None,
    ip_address: str | None,
) -> bool:
    """写一条审计日志（独立会话）。返回是否已提交；失败记 CRITICAL 并发管理员告警。

    🔴 明确不宣称与业务事务原子：业务写在自己的会话里早已提交，这里只保证「客户端拿到
    成功响应之前日志已落库」。真正的 transactional outbox 要等写路由统一事务 / 幂等
    （spec runtime-performance-and-reload-hardening-followup R4.3）。
    """
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
        return True
    except Exception:
        # fail-open：业务已提交，这里返回 503 会诱发客户端重试、造成重复写。
        logger.critical(
            "审计日志写入失败，业务响应仍按原状返回（action=%s object=%s/%s user=%s）",
            action_type, object_type, object_id, user_id, exc_info=True,
        )
        _record_failure(action_type, object_type)
        return False


#: 审计写失败的进程内可观测状态（``/api/health`` 的 ``audit_log``，并使 status=degraded）。
#:
#: 🔴 不往数据库写"告警"：审计写失败最常见的原因正是数据库不可用，再写一张表同样会失败；
#: 平台现扫也没有独立于 PG 的告警 sink。因此用 CRITICAL 日志 + 这个进程内状态把失败暴露出来，
#: 不假装有一条耐久告警通道。计数只增、进程重启才清 —— 审计完整性缺口不该自动"消失"。
_FAILURE_STATE: dict[str, object] = {"failed_count": 0, "last_at": None, "last_target": None}


def _record_failure(action_type: str, object_type: str) -> None:
    _FAILURE_STATE["failed_count"] = int(_FAILURE_STATE["failed_count"]) + 1  # type: ignore[arg-type]
    _FAILURE_STATE["last_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _FAILURE_STATE["last_target"] = f"{action_type} {object_type}"


def audit_log_failure_state() -> dict[str, object]:
    """审计日志写入失败的累计状态（只读副本）。"""
    return dict(_FAILURE_STATE)


class _CapturingSend:
    """2xx、非 SSE 的响应：缓冲到最后一段，重建后**交给中间件**决定何时发出；其余原样转发。

    R4.1：成功响应要在审计日志已 commit 之后才发给客户端 —— 否则客户端已经看到成功、
    日志还没落库，中间崩进程就留不下痕迹。只缓冲最终响应对象，不改重建方式。
    """

    def __init__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.scope, self.receive, self.send = scope, receive, send
        self.start: Message | None = None
        self.capturing = False
        self.chunks: list[bytes] = []
        self.body: bytes | None = None  # 抓到的完整响应体（要写日志时非 None）
        self.pending: Response | None = None  # 已重建、等日志提交后再发的响应

    async def __call__(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            content_type = Headers(raw=message["headers"]).get("content-type", "")
            # 仅对成功响应记录日志（2xx）；跳过 SSE 流式响应
            self.capturing = 200 <= message["status"] < 300 and "text/event-stream" not in content_type
            if self.capturing:
                self.start = message
            else:
                await self.send(message)
            return
        if not self.capturing or message["type"] != "http.response.body":
            await self.send(message)
            return
        self.chunks.append(message.get("body", b""))
        if message.get("more_body", False):
            return
        assert self.start is not None
        self.body = b"".join(self.chunks)
        self.chunks = []
        self.capturing = False
        # 与原版相同的重建（头、content-length 由 Starlette 同一段代码处理），先不发。
        self.pending = Response(content=self.body, status_code=self.start["status"],
                                headers=dict(Headers(raw=self.start["headers"])), media_type=None)

    async def flush(self) -> None:
        """把缓冲的最终响应发给客户端（审计日志已处理完之后调用）。"""
        response, self.pending = self.pending, None
        if response is not None:
            await response(self.scope, self.receive, self.send)


class AuditLogMiddleware:
    """操作日志中间件 — 对写操作自动记录审计日志。

    与 audit_decorator 的分工：
    - AuditLogMiddleware（本类）：HTTP 层面的粗粒度审计，记录所有写操作（POST/PUT/PATCH/DELETE）
      的请求路径、用户、IP、状态码。适合合规审计和安全监控。
    - audit_decorator（@audit_log）：业务层面的细粒度审计，记录具体业务对象的变更内容
      （old_value/new_value diff）。适合业务审计和数据追溯。
    两者互补，不重复：中间件记录"谁在什么时间做了什么操作"，装饰器记录"操作改变了什么数据"。

    纯 ASGI（spec backend-startup-and-request-overhead R3.1）：响应缓冲到最后一段后重建。
    成功响应在审计日志 commit 之后才发给客户端（follow-up R4.1）；日志失败仍 fail-open 发原响应。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # 仅拦截写方法；跳过无需记录的路径
        if scope["type"] != "http" or scope["method"] not in _WRITE_METHODS:
            await self.app(scope, receive, send)
            return
        path = request_path(scope)
        if path.startswith(_SKIP_PATHS):
            await self.app(scope, receive, send)
            return

        # 提取请求信息
        request = Request(scope, receive)
        user_id = _extract_user_id_from_token(request)
        ip_address = _extract_client_ip(request)
        action_type = _METHOD_ACTION_MAP.get(scope["method"], "unknown")
        object_type = _extract_object_type(path)
        object_id = _extract_object_id(path)

        # 执行业务逻辑
        capture = _CapturingSend(scope, receive, send)
        try:
            await self.app(scope, receive, capture)
            if capture.body is None:
                return

            # old_value 在中间件层暂不捕获，后续由具体 CRUD 服务增强
            new_value = _parse_json(capture.body)

            # V233（platform-global-display-settings-closure 任务 2）：
            # 偏好 PATCH 只落 revision+changed_fields，金额单位、字号、
            # 小数位、阈值、固定列内容及 pageKey 均不进日志。
            new_value = _redact_if_display_prefs(
                scope["method"], path, new_value, request,
            )

            await _write_log(
                user_id=user_id,
                action_type=action_type,
                object_type=object_type,
                object_id=object_id,
                old_value=None,
                new_value=new_value if isinstance(new_value, dict) else None,
                ip_address=ip_address,
            )
        finally:
            # fail-open：日志失败（已记 CRITICAL + 计数）也要把原响应发出去，
            # 返回 503 会让客户端重试、在业务已提交的前提下造成重复写。
            await capture.flush()
