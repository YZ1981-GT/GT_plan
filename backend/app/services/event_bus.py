"""进程内事件总线 — 基于 asyncio + Redis Stream 持久化

提供 publish/subscribe 机制，用于服务间解耦联动：
- 调整分录 CRUD → 试算表增量重算
- 科目映射变更 → 试算表重算
- 数据导入完成 → 试算表全量重算
- 导入回滚 → 试算表全量重算
- 重要性水平变更 → 通知前端

Redis Stream 持久化：
- 事件发布时同时写入 Redis Stream（audit:events）
- 服务重启后可从 Stream 恢复未处理事件
- Redis 不可用时降级为纯内存模式

Validates: Requirements 10.1-10.6
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

from app.models.audit_platform_schemas import EventPayload, EventType

logger = logging.getLogger(__name__)

# Type alias for async event handlers
EventHandler = Callable[[EventPayload], Coroutine[Any, Any, None]]

# Redis Stream 配置
_STREAM_KEY = "audit:events"
_STREAM_MAX_LEN = 10000  # 保留最近 1 万条事件
_CONSUMER_GROUP = "event_handlers"


class EventBus:
    """进程内事件总线，基于 asyncio 实现，支持 debounce 去重 + Redis Stream 持久化"""

    def __init__(self, debounce_ms: int = 500) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._sse_queues: list[asyncio.Queue[EventPayload | None]] = []
        self._pending: dict[str, dict] = {}  # debounce 缓冲区
        self._debounce_ms: int = debounce_ms
        self._redis_available: bool | None = None  # 延迟检测

    def _build_dedup_key(self, payload: EventPayload) -> str:
        """构建 debounce 去重键。

        说明：
        - 同项目不同年度的事件不应互相合并。
        - year=None 视为“全年/未知年度”事件，单独归并。
        """
        year_key = payload.year if payload.year is not None else "ALL_YEARS"
        return f"{payload.event_type.value}:{payload.project_id}:{year_key}"

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """注册事件处理器"""
        self._handlers[event_type].append(handler)
        handler_name = getattr(handler, "__qualname__", repr(handler))
        logger.info("EventBus: subscribed %s to %s", handler_name, event_type.value)

    async def publish(self, payload: EventPayload) -> None:
        """发布事件，相同去重键在 debounce 窗口内合并为一次。"""
        dedup_key = self._build_dedup_key(payload)

        # 合并 account_codes
        if dedup_key in self._pending:
            self._pending[dedup_key]["handle"].cancel()
            existing_codes = self._pending[dedup_key]["payload"].account_codes or []
            new_codes = payload.account_codes or []
            if existing_codes or new_codes:
                # 保持去重且稳定顺序，避免 set 带来的顺序抖动
                payload.account_codes = list(dict.fromkeys(existing_codes + new_codes))
            else:
                payload.account_codes = None

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
        dedup_key = self._build_dedup_key(payload)
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

        # 持久化到 Redis Stream（异步，不阻断分发）
        asyncio.ensure_future(self._persist_to_stream(payload))

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
    # Redis Stream 持久化
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """获取 Redis 客户端，不可用返回 None"""
        if self._redis_available is False:
            return None
        try:
            from app.core.redis import redis_client
            await redis_client.ping()
            self._redis_available = True
            return redis_client
        except Exception:
            self._redis_available = False
            logger.debug("EventBus: Redis not available, running in memory-only mode")
            return None

    async def _persist_to_stream(self, payload: EventPayload) -> None:
        """将事件写入 Redis Stream，失败静默降级"""
        redis = await self._get_redis()
        if not redis:
            return
        try:
            event_data = {
                "event_type": payload.event_type.value,
                "project_id": str(payload.project_id) if payload.project_id else "",
                "year": str(payload.year) if payload.year else "",
                "account_codes": json.dumps(payload.account_codes) if payload.account_codes else "[]",
            }
            await redis.xadd(_STREAM_KEY, event_data, maxlen=_STREAM_MAX_LEN)
        except Exception as e:
            logger.debug("EventBus: failed to persist event to Redis Stream: %s", e)

    async def replay_pending_events(self) -> int:
        """服务重启后从 Redis Stream 恢复未确认事件（可在 lifespan 中调用）

        Returns:
            恢复并重新分发的事件数量
        """
        redis = await self._get_redis()
        if not redis:
            return 0

        try:
            # 确保 consumer group 存在
            try:
                await redis.xgroup_create(_STREAM_KEY, _CONSUMER_GROUP, id="0", mkstream=True)
            except Exception:
                pass  # group 已存在

            # 读取 pending 事件
            messages = await redis.xreadgroup(
                _CONSUMER_GROUP, "worker-1", {_STREAM_KEY: ">"}, count=100, block=0
            )
            if not messages:
                return 0

            count = 0
            for stream_name, entries in messages:
                for msg_id, data in entries:
                    try:
                        event_type = EventType(data.get("event_type", ""))
                        payload = EventPayload(
                            event_type=event_type,
                            project_id=data.get("project_id") or None,
                            year=int(data["year"]) if data.get("year") else None,
                            account_codes=json.loads(data.get("account_codes", "[]")) or None,
                        )
                        # 直接分发，不再持久化（避免循环）
                        handlers = self._handlers.get(event_type, [])
                        for handler in handlers:
                            try:
                                await handler(payload)
                            except Exception:
                                pass
                        # ACK
                        await redis.xack(_STREAM_KEY, _CONSUMER_GROUP, msg_id)
                        count += 1
                    except Exception:
                        # 无法解析的消息直接 ACK 跳过
                        await redis.xack(_STREAM_KEY, _CONSUMER_GROUP, msg_id)

            logger.info("EventBus: replayed %d pending events from Redis Stream", count)
            return count
        except Exception as e:
            logger.warning("EventBus: replay_pending_events failed: %s", e)
            return 0

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
