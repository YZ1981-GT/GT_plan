"""大 JSON 载荷在工作线程里编码 / 解码（spec writeback-followup-issue-closure R5）。

事件循环上整包编码数万条记录是秒级停顿：FastAPI 默认对返回的 dict 先跑 ``jsonable_encoder``
（逐值递归，实测 5 万条地址 0.75 s），C 实现的 ``json.dumps`` / ``json.loads`` 处理整包时也一直持有
GIL，放进工作线程照样挡住事件循环。这里统一两件事：

- **分块**：每块 :data:`JSON_CHUNK_ITEMS` 条，块与块之间回到 Python 字节码，GIL 能切回事件循环；
  每块的临时对象随块释放，不会整批活到老年代、触发全量 GC；
- **预编码响应**：路由把业务载荷编好字节后用 :func:`preencoded_json_response` 返回，
  ``ResponseWrapperMiddleware`` 认 :data:`PREENCODED_PAYLOAD_HEADER` 按字节拼统一信封，
  不再 ``json.loads`` + ``json.dumps`` 重编码一遍。

调用方负责把编码放进工作线程（``await asyncio.to_thread(...)``）；本模块函数都是同步纯函数。
"""

from __future__ import annotations

import enum
import json
from typing import Any, Iterable, Iterator, Mapping

from starlette.responses import Response

#: 内部标记头：响应体是**未包信封**的 2xx 业务载荷 JSON 字节。只认值 ``"1"``；
#: ``ResponseWrapperMiddleware`` 包信封时摘掉，不会发到浏览器。
PREENCODED_PAYLOAD_HEADER = "x-gt-preencoded-payload"

#: 每块条数：5 万条地址约 25 块，每块 C 层编码约 5 ms。
JSON_CHUNK_ITEMS = 2000


def _json_default(value: Any) -> Any:
    """与 ``jsonable_encoder`` 对这两类的口径一致；其余类型照常抛 ``TypeError``（不静默转字符串）。"""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (set, frozenset)):
        return list(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _dumps(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, default=_json_default).encode("utf-8")


def _batches(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def encode_json_array_chunked(items: Iterable[Any], chunk_size: int = JSON_CHUNK_ITEMS) -> bytes:
    """``json.dumps(list(items), ensure_ascii=False)`` 的分块等价（字节逐一相同）。"""
    return b"[" + b", ".join(_dumps(b)[1:-1] for b in _batches(items, chunk_size)) + b"]"


def encode_object_with_chunked_array(
    head: Mapping[str, Any], key: str, items: Iterable[Any], chunk_size: int = JSON_CHUNK_ITEMS
) -> bytes:
    """``json.dumps({**head, key: list(items)}, ensure_ascii=False)`` 的分块等价（字节逐一相同）。"""
    if key in head:
        raise ValueError(f"{key!r} 已在 head 里")
    head_bytes = _dumps(dict(head))
    sep = b", " if head else b""
    return head_bytes[:-1] + sep + _dumps(key) + b": " + encode_json_array_chunked(items, chunk_size) + b"}"


def encode_json_lines(items: Iterable[Any], chunk_size: int = JSON_CHUNK_ITEMS) -> bytes:
    """每行一个 JSON 数组（≤ ``chunk_size`` 条）。``json.dumps`` 会把字符串里的换行转义，行内不含裸换行。"""
    return b"\n".join(_dumps(b) for b in _batches(items, chunk_size))


def iter_json_line_batches(raw: bytes | str) -> Iterator[list[Any]]:
    """逐行解出 :func:`encode_json_lines` 的各块；整包单个 JSON 数组（旧格式）就是只有一行。"""
    lines = raw.split(b"\n") if isinstance(raw, (bytes, bytearray)) else raw.split("\n")
    for line in lines:
        if line.strip():
            yield json.loads(line)


def preencoded_json_response(body: bytes, status_code: int = 200) -> Response:
    """返回已编码好的业务载荷；统一信封由 ``ResponseWrapperMiddleware`` 按字节拼上。"""
    return Response(
        content=body,
        status_code=status_code,
        media_type="application/json",
        headers={PREENCODED_PAYLOAD_HEADER: "1"},
    )
