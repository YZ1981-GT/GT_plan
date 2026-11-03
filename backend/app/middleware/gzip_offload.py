"""GZip 压缩：大块响应体在工作线程里压（spec writeback-followup-issue-closure R5）。

Starlette 的 ``GZipMiddleware`` 在事件循环线程上同步压缩响应体：实测 27.6 MB 的地址库整库
载荷（level 9）压一次 0.35 s，期间事件循环什么也做不了。zlib 压缩时释放 GIL，放进工作线程后
事件循环照常运转。行为与上游逐项一致（同样的判据、同样的头），只换了大块的压缩位置：

- 上游会压的每一段（首段或后续段、整段或流式）只要 ≥ :data:`OFFLOAD_MIN_BYTES` 就在工作线程里压；
  整段和流式都要接管：内层中间件原来都是 ``BaseHTTPMiddleware``，会把每个响应改成流式（数据段
  ``more_body=True`` + 末尾空段），那时大响应体到这里全是「流式首段」；改成纯 ASGI 之后（spec
  backend-startup-and-request-overhead R3.1）普通响应到这里是整段，``StreamingResponse`` 仍是流式；
- 小段、已带 ``Content-Encoding`` 或被排除的类型照上游原逻辑；
- 预先算好的结果只在上游随后对**同一个 body 对象、同一个 more_body** 调用 ``apply_compression``
  时交出；对不上（上游实现变了）直接报错，不会交错位的数据。
"""

from __future__ import annotations

import asyncio

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware, GZipResponder
from starlette.types import Message, Receive, Scope, Send

#: 低于此大小仍在事件循环上压（压缩耗时远小于线程切换的代价）。
OFFLOAD_MIN_BYTES = 256 * 1024


class _OffloadingGZipResponder(GZipResponder):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._precomputed: tuple[bytes, bool, bytes] | None = None

    def _upstream_compresses(self, message: Message) -> bool:
        """上游 ``send_with_compression`` 对这一段会不会调 ``apply_compression``（逐分支照抄判据）。"""
        if message["type"] != "http.response.body":
            return False
        if self.content_encoding_set or self.content_type_is_excluded:
            return False
        if not self.started and len(message.get("body", b"")) < self.minimum_size and not message.get("more_body", False):
            return False
        return True

    async def send_with_compression(self, message: Message) -> None:
        if self._upstream_compresses(message) and len(message.get("body", b"")) >= OFFLOAD_MIN_BYTES:
            body, more_body = message["body"], message.get("more_body", False)
            compressed = await asyncio.to_thread(GZipResponder.apply_compression, self, body, more_body=more_body)
            self._precomputed = (body, more_body, compressed)
        await super().send_with_compression(message)

    def apply_compression(self, body: bytes, *, more_body: bool) -> bytes:
        pre, self._precomputed = self._precomputed, None
        if pre is None:
            return super().apply_compression(body, more_body=more_body)
        if pre[0] is body and pre[1] == more_body:
            return pre[2]
        raise RuntimeError("gzip 预压缩结果与上游调用对不上（Starlette GZipResponder 实现已变）")


class OffloadingGZipMiddleware(GZipMiddleware):
    """与 ``GZipMiddleware`` 参数、行为相同；大块响应体在工作线程里压缩。"""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and "gzip" in Headers(scope=scope).get("Accept-Encoding", ""):
            responder = _OffloadingGZipResponder(self.app, self.minimum_size, compresslevel=self.compresslevel)
            await responder(scope, receive, send)
            return
        await super().__call__(scope, receive, send)
