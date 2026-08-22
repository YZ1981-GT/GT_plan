"""SSE 帧编码 + run 事件流（TTL Redis Stream + 有界本地镜像）· Task 5

Feature: dsh-agent-panel-integration
Requirements:
  - 4.1：两阶段 API 的第二阶段 —— 订阅某个 run 的事件；断线重连订阅**原 run**。
  - 4.4：每个事件携带单调 event ID；本模块把它写进 SSE 的 ``id:`` 字段，
    使客户端的 ``Last-Event-ID`` 与服务端序号同源。
  - 4.8：SSE 帧必须**自定界** —— 任意网络字节分片下解析结果与未分片一致；
    多行 data、心跳（注释帧）与 CRLF/LF 都不能破坏边界。
  - 4.9：drain 时发出可识别的中止帧（``server_draining``），且该帧**不带 id**
    —— 否则客户端会把它当业务事件推进 ``Last-Event-ID``，重连后丢掉真正的下一条。
  - 4.12：active run 的短时回放走 Redis Stream（``MAXLEN`` + ``TTL``）或**等价有界缓冲**；
    数据库只存 run/message/tool 摘要，``delta`` 不逐 token 写行。
Design: "Components and Interfaces → 5. Run Coordinator、SSE Replay 与取消"
  第 3 步（事件写入带 TTL 的有界 Redis Stream ``ai-chat:run:{run_id}``）与
  第 5 步（SSE endpoint 按 ``Last-Event-ID`` 回放并订阅新事件）。
Properties: 9（SSE 任意分片与续传等价）

## 为什么"永远同时写本地有界镜像"

Req 4.12 明确允许"平台已有 Redis 能力**或等价有界缓冲**"。这里两者都要，但分工不同：

- **Redis Stream** 是跨进程真源：多 worker 部署下，执行 run 的进程与承载 SSE 连接的
  进程可能不是同一个，只有 Redis 能把事件递过去。
- **本地有界镜像** 是同进程兜底：Redis 掉线时 run 不该整条哑掉。它是 ring buffer
  （每 run ``maxlen`` 条、最多 ``max_runs`` 个 run、按 TTL 淘汰），不会无界增长。

:meth:`RunEventStream.history` **合并两个来源并按 event 序号去重**，因此"发布时 Redis 在、
订阅时 Redis 掉了"（或反过来）都不会丢事件也不会重复 —— 这正是 Property 9 后半句
（重连不丢不重）在后端侧的落点。

## 帧形态（自定界是分片安全的唯一前提）

```text
id: 000000000002
event: delta
data: {"event_id":"000000000002", ...}
<空行>
```

三条不可动的规则：

1. **每帧以空行结束**。少了它，两条事件会被客户端并成一条（分片时才暴露）。
2. **data 里不得出现裸换行**。:func:`_data_lines` 把 ``\\n`` / ``\\r\\n`` 拆成多个
   ``data:`` 行（SSE 规范规定客户端用 ``\\n`` 重新拼接），否则半条 JSON 会被当成完整帧。
3. **心跳是注释帧**（``: heartbeat``），不带 ``id``/``event``/``data`` —— 客户端不 dispatch，
   也不会推进 ``Last-Event-ID``。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.services.ai_chat.run_contract import (
    TERMINAL_EVENT_TYPES,
    ChatEvent,
    event_seq,
)

logger = logging.getLogger(__name__)

__all__ = [
    "STREAM_KEY_TEMPLATE",
    "DRAINING_EVENT_NAME",
    "HEARTBEAT_COMMENT",
    "stream_key",
    "encode_frame",
    "encode_event",
    "encode_comment",
    "encode_heartbeat",
    "encode_draining",
    "LocalEventMirror",
    "RunEventStream",
    "get_event_stream",
]

#: Redis Stream key 模板（Design 第 3 步逐字给定）。
STREAM_KEY_TEMPLATE = "ai-chat:run:{run_id}"

#: drain 帧的 event 名。**不是** :class:`~app.services.ai_chat.run_contract.ChatEventType`
#: 的成员：它是传输层信号而非业务事件，混进业务枚举会让"事件类型 ↔ design 清单"
#: 的双向契约失真，也会让前端把它当成一次回答的终态。
DRAINING_EVENT_NAME = "server_draining"

#: 心跳注释内容。
HEARTBEAT_COMMENT = "heartbeat"


def stream_key(run_id: UUID | str) -> str:
    return STREAM_KEY_TEMPLATE.format(run_id=run_id)


# ---------------------------------------------------------------------------
# SSE 帧编码（Req 4.8：自定界）
# ---------------------------------------------------------------------------


def _data_lines(data: str) -> list[str]:
    """把 data 负载拆成不含裸换行的多行。

    空负载也返回 ``[""]`` —— 必须发出 ``data: `` 那一行，否则整帧只剩 ``id:``/``event:``，
    客户端按 SSE 规范**不会 dispatch**（data buffer 为空即丢弃），事件静默消失。
    """
    normalized = (data or "").replace("\r\n", "\n").replace("\r", "\n")
    return normalized.split("\n")


def encode_frame(
    *,
    data: str,
    event: str | None = None,
    event_id: str | None = None,
    retry_ms: int | None = None,
) -> str:
    """编码一个自定界 SSE 帧（末尾恒为空行）。

    :raises ValueError: ``event_id`` / ``event`` 含换行 —— 那会伪造出额外字段行，
        把一帧劈成两帧。
    """
    lines: list[str] = []
    if event_id is not None:
        if "\n" in event_id or "\r" in event_id:
            raise ValueError(f"event_id 不得含换行：{event_id!r}")
        lines.append(f"id: {event_id}")
    if event is not None:
        if "\n" in event or "\r" in event:
            raise ValueError(f"event 名不得含换行：{event!r}")
        lines.append(f"event: {event}")
    if retry_ms is not None:
        lines.append(f"retry: {int(retry_ms)}")
    lines.extend(f"data: {line}" for line in _data_lines(data))
    # 每行一个 LF + 帧尾空行 ⇒ 任意分片下边界仍然唯一。
    return "".join(f"{line}\n" for line in lines) + "\n"


def encode_event(event: ChatEvent) -> str:
    """把 :class:`ChatEvent` 编成 SSE 帧。

    ``id:`` 用事件自己的 ``event_id``（零填充定宽）⇒ 客户端回传的 ``Last-Event-ID``
    与服务端序号同源，字典序与数值序一致（Req 4.4/4.8）。
    """
    return encode_frame(
        data=event.model_dump_json(),
        event=event.type.value,
        event_id=event.event_id,
    )


def encode_comment(text: str) -> str:
    """注释帧（不 dispatch、不推进 Last-Event-ID）。"""
    safe = (text or "").replace("\r", " ").replace("\n", " ")
    return f": {safe}\n\n"


def encode_heartbeat() -> str:
    return encode_comment(HEARTBEAT_COMMENT)


def encode_draining(reason: str = "服务端正在优雅关闭，请稍后重连该会话") -> str:
    """drain 中止帧（Req 4.9）。**刻意不带 id** —— 见模块 docstring。"""
    return encode_frame(
        data=json.dumps(
            {"code": "server_draining", "message": reason}, ensure_ascii=False
        ),
        event=DRAINING_EVENT_NAME,
    )


# ---------------------------------------------------------------------------
# 有界本地镜像（Req 4.12 的"等价有界缓冲"）
# ---------------------------------------------------------------------------


@dataclass
class _RunBuffer:
    events: deque[ChatEvent]
    notify: asyncio.Event = field(default_factory=asyncio.Event)
    touched: float = field(default_factory=time.monotonic)


class LocalEventMirror:
    """进程内有界事件镜像：每 run 一个 ring buffer，按 TTL 与 run 数双重设界。"""

    def __init__(self, *, maxlen: int, max_runs: int, ttl_seconds: float) -> None:
        self._maxlen = max(1, int(maxlen))
        self._max_runs = max(1, int(max_runs))
        self._ttl = float(ttl_seconds)
        self._buffers: dict[str, _RunBuffer] = {}

    def _buffer(self, run_id: UUID | str) -> _RunBuffer:
        key = str(run_id)
        buf = self._buffers.get(key)
        if buf is None:
            self._prune()
            buf = _RunBuffer(events=deque(maxlen=self._maxlen))
            self._buffers[key] = buf
        return buf

    def publish(self, event: ChatEvent) -> None:
        buf = self._buffer(event.run_id)
        buf.events.append(event)
        buf.touched = time.monotonic()
        buf.notify.set()

    def history(self, run_id: UUID | str, after_seq: int = 0) -> list[ChatEvent]:
        buf = self._buffers.get(str(run_id))
        if buf is None:
            return []
        return [e for e in buf.events if event_seq(e.event_id) > after_seq]

    def notifier(self, run_id: UUID | str) -> asyncio.Event:
        return self._buffer(run_id).notify

    def clear_notification(self, run_id: UUID | str) -> None:
        buf = self._buffers.get(str(run_id))
        if buf is not None:
            buf.notify.clear()

    def forget(self, run_id: UUID | str) -> None:
        self._buffers.pop(str(run_id), None)

    def _prune(self) -> None:
        """按 TTL 淘汰，仍超出 run 数上限时淘汰最久未活动的（保证有界）。"""
        now = time.monotonic()
        for key in [k for k, b in self._buffers.items() if now - b.touched > self._ttl]:
            self._buffers.pop(key, None)
        while len(self._buffers) >= self._max_runs:
            oldest = min(self._buffers.items(), key=lambda kv: kv[1].touched)[0]
            self._buffers.pop(oldest, None)

    @property
    def tracked_runs(self) -> int:
        return len(self._buffers)


# ---------------------------------------------------------------------------
# RunEventStream
# ---------------------------------------------------------------------------

RedisProvider = Callable[[], Awaitable[Any]]


@dataclass(frozen=True)
class _Fetch:
    events: list[ChatEvent]
    last_stream_id: str | None


class RunEventStream:
    """run 事件的发布 / 回放 / 订阅。

    ``publish`` 永远写本地镜像，Redis 可用时**额外**写 Stream；``history`` 合并两侧
    并按 event 序号去重排序。这样"Redis 中途掉线/恢复"不会造成事件丢失或重复
    （Property 9 后半句）。
    """

    def __init__(
        self,
        *,
        ttl_seconds: int | None = None,
        maxlen: int | None = None,
        mirror: LocalEventMirror | None = None,
        redis_provider: RedisProvider | None = None,
        client_recheck_seconds: float = 5.0,
    ) -> None:
        from app.core.config import settings

        self._ttl = int(
            ttl_seconds
            if ttl_seconds is not None
            else settings.AI_CHAT_EVENT_STREAM_TTL_SECONDS
        )
        self._maxlen = int(
            maxlen if maxlen is not None else settings.AI_CHAT_EVENT_STREAM_MAXLEN
        )
        self._mirror = mirror or LocalEventMirror(
            maxlen=self._maxlen,
            max_runs=int(settings.AI_CHAT_EVENT_MIRROR_MAX_RUNS),
            ttl_seconds=self._ttl,
        )
        if redis_provider is None:
            from app.core.redis import get_redis

            redis_provider = get_redis
        self._redis_provider = redis_provider
        self._client: Any = None
        self._client_checked_at: float = 0.0
        self._recheck = float(client_recheck_seconds)

    # ------------------------------------------------------------------
    @property
    def mirror(self) -> LocalEventMirror:
        return self._mirror

    async def _redis(self) -> Any:
        """取（缓存的）Redis 客户端。

        ``get_redis()`` 每次都 ``ping`` —— 逐 delta 调用等于每个 token 一次额外往返。
        故按 ``client_recheck_seconds`` 缓存；异常时立刻失效并在下次重新探测。
        """
        now = time.monotonic()
        if self._client is not None and now - self._client_checked_at < self._recheck:
            return self._client
        if self._client is None and now - self._client_checked_at < self._recheck:
            return None
        try:
            self._client = await self._redis_provider()
        except Exception as exc:  # noqa: BLE001 — Redis 不可用是可降级状态，不是 500
            logger.warning("[ai-chat] Redis 不可用，事件流退回本地有界镜像：%s", exc)
            self._client = None
        self._client_checked_at = now
        return self._client

    def _invalidate(self) -> None:
        self._client = None
        self._client_checked_at = time.monotonic()

    # ------------------------------------------------------------------
    async def publish(self, event: ChatEvent) -> None:
        """发布一条事件（先本地镜像，再 Redis Stream）。"""
        self._mirror.publish(event)
        client = await self._redis()
        if client is None:
            return
        key = stream_key(event.run_id)
        try:
            await client.xadd(
                key,
                {
                    "event_id": event.event_id,
                    "type": event.type.value,
                    "event": event.model_dump_json(),
                },
                maxlen=self._maxlen,
                approximate=True,
            )
            await client.expire(key, self._ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ai-chat] 事件写入 Redis Stream 失败（已入本地镜像）：%s", exc)
            self._invalidate()

    async def _read_redis(
        self, run_id: UUID | str, after_stream_id: str | None
    ) -> _Fetch:
        client = await self._redis()
        if client is None:
            return _Fetch(events=[], last_stream_id=after_stream_id)
        try:
            rows = await client.xrange(
                stream_key(run_id),
                min=f"({after_stream_id}" if after_stream_id else "-",
                max="+",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ai-chat] 读取 Redis Stream 失败（退回本地镜像）：%s", exc)
            self._invalidate()
            return _Fetch(events=[], last_stream_id=after_stream_id)

        events: list[ChatEvent] = []
        last = after_stream_id
        for stream_id, fields in rows:
            last = stream_id
            raw = fields.get("event") if isinstance(fields, dict) else None
            if not raw:
                continue
            try:
                events.append(ChatEvent.model_validate_json(raw))
            except Exception as exc:  # noqa: BLE001 — 坏行跳过，不让一条脏数据打断整条流
                logger.warning("[ai-chat] Stream 中的事件无法解析，已跳过：%s", exc)
        return _Fetch(events=events, last_stream_id=last)

    @staticmethod
    def _merge(*groups: list[ChatEvent]) -> list[ChatEvent]:
        """按 event 序号去重 + 升序排序（跨后端合并的唯一收敛点）。"""
        by_seq: dict[int, ChatEvent] = {}
        for group in groups:
            for ev in group:
                by_seq.setdefault(event_seq(ev.event_id), ev)
        return [by_seq[k] for k in sorted(by_seq)]

    async def history(
        self, run_id: UUID | str, after_event_id: str | None = None
    ) -> list[ChatEvent]:
        """``Last-Event-ID`` 之后的全部事件（Redis + 本地镜像合并去重）。"""
        after = event_seq(after_event_id) if after_event_id else 0
        fetched = await self._read_redis(run_id, None)
        merged = self._merge(fetched.events, self._mirror.history(run_id, after))
        return [e for e in merged if event_seq(e.event_id) > after]

    async def follow(
        self,
        run_id: UUID | str,
        *,
        after_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
        poll_interval: float = 0.4,
        max_seconds: float | None = None,
        stop: Callable[[], bool] | None = None,
    ) -> AsyncIterator[ChatEvent | None]:
        """回放 + 订阅。``yield None`` 表示"空转到心跳窗口"，由调用方发心跳帧。

        终态事件 yield 之后立即结束 —— 一个 run 只有一个终态（Req 4.5），
        继续挂着只会占住连接。
        """
        high = event_seq(after_event_id) if after_event_id else 0
        last_stream_id: str | None = None
        started = time.monotonic()
        last_activity = started

        while True:
            if stop is not None and stop():
                return
            fetched = await self._read_redis(run_id, last_stream_id)
            last_stream_id = fetched.last_stream_id
            batch = self._merge(fetched.events, self._mirror.history(run_id, high))
            delivered = False
            for ev in batch:
                seq = event_seq(ev.event_id)
                if seq <= high:
                    continue
                high = seq
                delivered = True
                yield ev
                if ev.type in TERMINAL_EVENT_TYPES:
                    return
            now = time.monotonic()
            if delivered:
                last_activity = now
                continue
            if max_seconds is not None and now - started >= max_seconds:
                return
            self._mirror.clear_notification(run_id)
            try:
                await asyncio.wait_for(
                    self._mirror.notifier(run_id).wait(), timeout=poll_interval
                )
            except asyncio.TimeoutError:
                pass
            if time.monotonic() - last_activity >= heartbeat_interval:
                last_activity = time.monotonic()
                yield None

    async def drop(self, run_id: UUID | str) -> None:
        """显式清理某个 run 的缓冲（终态且客户端已收完时可调；TTL 也会兜住）。"""
        self._mirror.forget(run_id)
        client = await self._redis()
        if client is None:
            return
        try:
            await client.delete(stream_key(run_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ai-chat] 清理 Redis Stream 失败（TTL 兜底）：%s", exc)


_STREAM: RunEventStream | None = None


def get_event_stream() -> RunEventStream:
    """进程级单例（发布方与订阅方必须共享同一本地镜像）。"""
    global _STREAM
    if _STREAM is None:
        _STREAM = RunEventStream()
    return _STREAM
