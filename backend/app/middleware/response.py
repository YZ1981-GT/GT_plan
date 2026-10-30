"""统一响应包装中间件

成功响应（2xx）自动包装为 {"code": status_code, "message": "success", "data": <payload>}

纯 ASGI（spec backend-startup-and-request-overhead R3.1）：看到响应头时判定要不要包（判据与原
``BaseHTTPMiddleware`` 版本逐条相同），不包的原样转发；要包的缓冲到最后一段，再用与原版相同的 ``Response(...)``
重建（头、内容长度、content-type 的处理都由 Starlette 同一段代码完成）。与原版的差别：无 content-length 的流式
JSON 超过 5MB 时，原版只交出已读的部分（响应体被截断），这里把已缓冲的和之后的原样转发。

Validates: Requirements 4.1
"""

import json

from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.offloop_json import PREENCODED_PAYLOAD_HEADER
from app.middleware._asgi import request_path


# 跳过包装的路径前缀
_SKIP_PATHS = ("/docs", "/redoc", "/openapi.json", "/wopi/", "/api/events/", "/api/message/stream", "/livez", "/readyz")

# OnlyOffice callback 路径需精确跳过（OnlyOffice 协议要求原始 {"error": 0} 顶层格式，
# 不能被 ApiResponse 信封包装）。底稿编辑端点路由为 ".../onlyoffice-callback"（连字符），
# 交付中心旧端点为 ".../onlyoffice/callback"（斜杠），两种写法都需覆盖。
_SKIP_CONTAINS = ("onlyoffice/callback", "onlyoffice-callback")

# 跳过 blob / 大文件下载响应（二进制流、文件下载等）
_BINARY_TYPES = (
    "application/octet-stream",
    "application/vnd.",
    "application/pdf",
    "application/zip",
    "image/",
    "audio/",
    "video/",
)

#: 缓冲上限（> 5MB 不包：避免整包解析的内存压力）
_MAX_WRAP_BYTES = 5 * 1024 * 1024


def _mode_for(start: Message) -> str:
    """看响应头决定：preencoded（按字节拼信封）/ buffer（可能要包，先缓冲）/ pass（原样转发）。"""
    headers = Headers(raw=start["headers"])
    # 路由已在工作线程里编好业务载荷（app.core.offloop_json）：按字节拼信封，不解析、不重编码；
    # 不受 5MB 上限约束（那条是为了避开整包解析，这里没有解析）。标记头一律摘掉。
    if headers.get(PREENCODED_PAYLOAD_HEADER) is not None:
        return "preencoded"
    if not (200 <= start["status"] < 300):
        return "pass"
    content_type = headers.get("content-type", "")
    if "application/json" not in content_type or "text/event-stream" in content_type:
        return "pass"
    if any(t in content_type for t in _BINARY_TYPES):
        return "pass"
    if "attachment" in headers.get("content-disposition", ""):
        return "pass"
    content_length = headers.get("content-length")
    if content_length and int(content_length) > _MAX_WRAP_BYTES:
        return "pass"
    return "buffer"


def _rebuild(start: Message, body: bytes) -> Response:
    """缓冲到完整响应体之后：与原版相同的判定与 ``Response(...)`` 重建。"""
    status = start["status"]
    headers = Headers(raw=start["headers"])
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # 无法解析则原样返回
        return Response(content=body, status_code=status, headers=dict(headers), media_type=None)
    # 已经是 ApiResponse 格式则跳过
    if isinstance(payload, dict) and "code" in payload and "message" in payload:
        return Response(content=body, status_code=status, headers=dict(headers), media_type=None)
    wrapped = {"code": status, "message": "success", "data": payload}
    wrapped_bytes = json.dumps(wrapped, ensure_ascii=False).encode("utf-8")
    # 去掉原始 Content-Length，Response 会自动根据新 body 计算；其余头（X-Response-Time 等）保留
    kept = {k: v for k, v in headers.items() if k.lower() != "content-length"}
    return Response(content=wrapped_bytes, status_code=status, headers=kept, media_type="application/json")


def _wrap_preencoded(start: Message, body: bytes) -> Response:
    """预编码载荷：2xx 拼成与 ``json.dumps(wrapped)`` 同形的信封字节；其余状态原样返回。都摘掉标记头。"""
    status = start["status"]
    if 200 <= status < 300:
        body = b'{"code": %d, "message": "success", "data": ' % status + body + b"}"
    drop = {"content-length", PREENCODED_PAYLOAD_HEADER}
    headers = Headers(raw=start["headers"])
    return Response(
        content=body,
        status_code=status,
        headers={k: v for k, v in headers.items() if k.lower() not in drop},
        media_type="application/json",
    )


class _WrappingSend:
    def __init__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.scope, self.receive, self.send = scope, receive, send
        self.mode = ""
        self.start: Message | None = None
        self.chunks: list[bytes] = []
        self.size = 0

    async def __call__(self, message: Message) -> None:
        kind = message["type"]
        if kind == "http.response.start":
            self.start = message
            self.mode = _mode_for(message)
            if self.mode == "pass":
                await self.send(message)
            return
        if self.mode in ("pass", "done") or kind != "http.response.body":
            if self.mode in ("buffer", "preencoded"):  # 缓冲中途来了别的消息（不应出现）：先把缓冲的原样交出
                await self._give_up(more_body=True)
            await self.send(message)
            return
        body = message.get("body", b"")
        more_body = message.get("more_body", False)
        self.chunks.append(body)
        self.size += len(body)
        if self.mode == "buffer" and self.size > _MAX_WRAP_BYTES:
            await self._give_up(more_body=more_body)  # 累积超限：放弃包装，之后原样转发
            return
        if more_body:
            return
        assert self.start is not None
        full = b"".join(self.chunks)
        self.chunks = []
        mode, self.mode = self.mode, "done"
        response = _rebuild(self.start, full) if mode == "buffer" else _wrap_preencoded(self.start, full)
        await response(self.scope, self.receive, self.send)

    async def _give_up(self, *, more_body: bool) -> None:
        assert self.start is not None
        await self.send(self.start)
        await self.send({"type": "http.response.body", "body": b"".join(self.chunks), "more_body": more_body})
        self.chunks = []
        self.mode = "pass"


class ResponseWrapperMiddleware:
    """将 2xx JSON 响应统一包装为 ApiResponse 格式。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = request_path(scope)
        # 跳过文档路径；跳过 OnlyOffice callback（OnlyOffice 要求原始 {"error": 0} 格式）
        if path.startswith(_SKIP_PATHS) or any(seg in path for seg in _SKIP_CONTAINS):
            await self.app(scope, receive, send)
            return
        await self.app(scope, receive, _WrappingSend(scope, receive, send))
