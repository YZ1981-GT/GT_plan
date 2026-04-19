"""进程内事件总线 — 基于 asyncio

提供 publish/subscribe 机制，用于服务间解耦联动：
- 调整分录 CRUD → 试算表增量重算
- 科目映射变更 → 试算表重算
- 数据导入完成 → 试算表全量重算
- 导入回滚 → 试算表全量重算
- 重要性水平变更 → 通知前端

Validates: Requirements 10.1-10.6
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

from app.models.audit_platform_schemas import EventPayload, EventType

logger = logging.getLogger(__name__)

# Type alias for async event handlers
EventHandler = Callable[[EventPayload], Coroutine[Any, Any, None]]


class EventBus:
    """进程内事件总线，基于 asyncio 实现，支持 debounce 去重"""

    def __init__(self, debounce_ms: int = 500) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._sse_queues: list[asyncio.Queue[EventPayload | None]] = []
        self._pending: dict[str, dict] = {}  # debounce 缓冲区
        self._debounce_ms: int = debounce_ms

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """注册事件处理器"""
        self._handlers[event_type].append(handler)
        handler_name = getattr(handler, "__qualname__", repr(handler))
        logger.info("EventBus: subscribed %s to %s", handler_name, event_type.value)

    async def publish(self, payload: EventPayload) -> None:
        """发布事件，相同 (event_type, project_id) 在 debounce 窗口内合并为一次"""
        dedup_key = f"{payload.event_type.value}:{payload.project_id}"

        # 合并 account_codes
        if dedup_key in self._pending:
            self._pending[dedup_key]["handle"].cancel()
            existing_codes = self._pending[dedup_key]["payload"].account_codes or []
            new_codes = payload.account_codes or []
            payload.account_codes = list(set(existing_codes + new_codes)) if (existing_codes or new_codes) else None

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的事件循环，直接分发
            await self._dispatch(payload)
            return

        handle = loop.call_later(
            self._debounce_ms / 1000,
            lambda p=payload: asyncio.ensure_future(self._dispatch(p)),
        )
        self._pending[dedup_key] = {"handle": handle, "payload": payload}

    async def publish_immediate(self, payload: EventPayload) -> None:
        """立即发布事件，不经过 debounce（供需要立即触发的场景使用）"""
        await self._dispatch(payload)

    async def _dispatch(self, payload: EventPayload) -> None:
        """实际分发事件到处理器"""
        dedup_key = f"{payload.event_type.value}:{payload.project_id}"
        self._pending.pop(dedup_key, None)

        event_type = payload.event_type
        handlers = self._handlers.get(event_type, [])
        logger.info(
            "EventBus: dispatching %s (project=%s, accounts=%s), %d handler(s)",
            event_type.value,
            payload.project_id,
            payload.account_codes,
            len(handlers),
        )

        for handler in handlers:
            try:
                await handler(payload)
            except Exception:
                handler_name = getattr(handler, "__qualname__", repr(handler))
                logger.exception(
                    "EventBus: handler %s failed for event %s",
                    handler_name,
                    event_type.value,
                )

        # Push to SSE queues for frontend notification
        await self._notify_sse(payload)

    # ------------------------------------------------------------------
    # SSE support
    # ------------------------------------------------------------------
    def create_sse_queue(self) -> asyncio.Queue[EventPayload | None]:
        """创建一个 SSE 订阅队列，供 SSE endpoint 使用"""
        queue: asyncio.Queue[EventPayload | None] = asyncio.Queue(maxsize=100)
        self._sse_queues.append(queue)
        logger.info("EventBus: SSE queue created, total=%d", len(self._sse_queues))
        return queue

    def remove_sse_queue(self, queue: asyncio.Queue[EventPayload | None]) -> None:
        """移除 SSE 订阅队列"""
        if queue in self._sse_queues:
            self._sse_queues.remove(queue)
            logger.info("EventBus: SSE queue removed, total=%d", len(self._sse_queues))

    async def _notify_sse(self, payload: EventPayload) -> None:
        """将事件推送到所有 SSE 队列"""
        for queue in self._sse_queues:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("EventBus: SSE queue full, dropping event")


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
try:
    from app.core.config import settings
    _debounce_ms = settings.EVENT_DEBOUNCE_MS
except Exception:
    _debounce_ms = 500

event_bus = EventBus(debounce_ms=_debounce_ms)
