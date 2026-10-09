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
from datetime import datetime, timezone
from collections import defaultdict
from typing import Any, Callable, Coroutine

from app.models.audit_platform_schemas import EventPayload, EventType

logger = logging.getLogger(__name__)

# Type alias for async event handlers
EventHandler = Callable[[EventPayload], Coroutine[Any, Any, None]]

#: 订阅者会读 ``payload.year`` 的事件类型 —— 发布方漏传时由 ``_backfill_year`` 按项目
#: 审计年度补齐。**不是手填清单**：守卫 ``test_event_year_contract.py`` 现算「全仓
#: subscribe 的 handler 里读 year 的事件类型」并断言它 ⊆ 本集合，新增读 year 的订阅者
#: 而没登记到这里会打红（避免补齐覆盖面静默缩水）。
YEAR_SCOPED_EVENT_TYPES: frozenset[EventType] = frozenset({
    EventType.ADJUSTMENT_CREATED,
    EventType.ADJUSTMENT_UPDATED,
    EventType.ADJUSTMENT_DELETED,
    EventType.ADJUSTMENT_APPROVED,
    EventType.ADJUSTMENT_REVIEW_REVOKED,
    EventType.ADJUSTMENT_BATCH_COMMITTED,
    EventType.MAPPING_CHANGED,
    EventType.ACCOUNT_MAPPING_CHANGED,
    EventType.DATA_IMPORTED,
    EventType.IMPORT_ROLLED_BACK,
    EventType.LEDGER_DATASET_ACTIVATED,
    EventType.LEDGER_DATASET_ROLLED_BACK,
    EventType.MATERIALITY_CHANGED,
    EventType.TRIAL_BALANCE_UPDATED,
    EventType.REPORTS_UPDATED,
    EventType.REPORT_ROW_CHANGED,
    EventType.FORMULA_CONFIG_CHANGED,
    EventType.PREFILL_MAPPING_CHANGED,
    EventType.WORKPAPER_SAVED,
    EventType.NOTE_UPDATED,
    EventType.NOTE_SECTION_SAVED,
    EventType.CONFIRMATION_RECEIVED,
    EventType.CHECKLIST_COMPLETED,
    EventType.STANDARD_CHANGED,
    EventType.ELIMINATION_APPROVED,
    EventType.ELIMINATION_REVOKED,
})

# Redis Stream 配置
_STREAM_KEY = "audit:events"
#: 公开别名。**replay 读取方必须与写入方同一个键。**
#:
#: spec workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 35：
#: `GET /api/projects/{pid}/events/since` 原来自己写死了 `"events:stream"`，而写入侧
#: 一直是 `"audit:events"` —— 那个 replay 端点读的是一条**没有任何写入方**的 stream，
#: 因此断线补拉恒返回空列表。两处各写一份字面量正是这类缺陷的成因，故这里给出唯一真源。
EVENT_STREAM_KEY = _STREAM_KEY
_STREAM_MAX_LEN = 10000  # 保留最近 1 万条事件
#: Requirement 13.2 / Property 53：整份 EventPayload 的 canonical JSON。
#:
#: 旧实现只往 Stream 写 event_type/project_id/year/account_codes 四个扁平字段，
#: ``extra``（wp_id / revision / operation_id / source / adapter_id /
#: artifact_sha256）与 batch_id / entry_group_id 在**写入这一步**就已经蒸发，replay
#: 侧再怎么读也重建不出来 —— 所以修点在写入侧，不在 replay 侧。扁平字段保留，让
#: 本次改动之前已经躺在 Stream 里的旧条目仍可降级重建。
_STREAM_PAYLOAD_FIELD = "payload_json"
_CONSUMER_GROUP = "event_handlers"


def serialize_payload_for_stream(payload: EventPayload) -> str:
    """把整份 ``EventPayload`` 序列化成 Redis Stream 字段值（Requirement 13.2）。

    纯函数、无 Redis 依赖，便于守卫直接做 round-trip 断言。UUID / Enum 由 pydantic
    自己按 JSON 模式序列化，因此 ``project_id`` / ``batch_id`` / ``entry_group_id``
    与 ``extra`` 内嵌的值都能原样回来。
    """
    return payload.model_dump_json()


def deserialize_payload_from_stream(data: dict[str, Any]) -> EventPayload:
    """从 Stream 条目重建 ``EventPayload``。

    优先读 :data:`_STREAM_PAYLOAD_FIELD`（本次改动后写入的完整 payload）；缺失时按旧
    扁平字段降级重建 —— 那些条目本来就没有 ``extra``，降级不会"丢"任何已存在的东西。
    """
    raw = data.get(_STREAM_PAYLOAD_FIELD)
    if raw:
        return EventPayload.model_validate_json(raw)
    return EventPayload(
        event_type=EventType(data.get("event_type", "")),
        project_id=data.get("project_id") or None,
        year=int(data["year"]) if data.get("year") else None,
        account_codes=json.loads(data.get("account_codes", "[]")) or None,
    )


class EventBus:
    """进程内事件总线，基于 asyncio 实现，支持 debounce 去重 + Redis Stream 持久化"""

    def __init__(self, debounce_ms: int = 500) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        # SSE 队列同时承载强类型 EventPayload（publish 路径）+ raw dict（broadcast_raw 路径）
        # raw dict 形如 {"_raw": True, "event_type": str, "project_id": str|None, "year": int|None, "extra": {...}}
        self._sse_queues: list[asyncio.Queue[EventPayload | dict | None]] = []
        self._pending: dict[str, dict] = {}  # debounce 缓冲区
        self._debounce_ms: int = debounce_ms
        self._redis_available: bool | None = None  # 延迟检测
        self._last_replay_report: dict[str, Any] = {
            "checked_at": None,
            "redis_available": None,
            "read_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "acked_count": 0,
            # 与 replay_pending_events 的 report 保持同一形状：首次重放之前 /metrics
            # 也会读这个字典，缺键会直接 KeyError。
            "dropped_unparseable_count": 0,
            "last_error": None,
        }

    def _build_dedup_key(self, payload: EventPayload) -> str:
        """构建 debounce 去重键。

        同项目、同年度、同事件类型是基础范围；底稿保存与发布确认还需保留
        ``extra.wp_id`` / ``extra.publish_token`` 身份，调整事件还需保留
        ``entry_group_id``，避免不同底稿、确认或调整组互相覆盖。
        ``entry_group_id`` 的新载荷位置是顶层字段；旧发布方仍可从 ``extra`` 回退。
        携带 typed ``ConsolContext`` 时，再把节点、模板、树和输入版本纳入身份，
        避免同一项目同一年度的不同合并计算上下文在防抖窗口内互相覆盖。
        未携带非空身份字段的事件保持原有去重键，不把缺失值序列化成 ``None``。
        """
        year_key = payload.year if payload.year is not None else "ALL_YEARS"
        base_key = f"{payload.event_type.value}:{payload.project_id}:{year_key}"
        extra = payload.extra or {}
        identity = []
        for field in ("wp_id", "publish_token", "entry_group_id"):
            # entry_group_id 已有顶层字段；extra 只为兼容旧发布方提供回退。
            value = getattr(payload, field, None) if field == "entry_group_id" else extra.get(field)
            if value is None or not str(value).strip():
                if field == "entry_group_id":
                    value = extra.get(field)
            if value is None:
                continue
            value_text = str(value).strip()
            if value_text:
                identity.append((field, value_text))
        if payload.context is not None:
            # project_id/year 已在 base_key 中，其他字段是合并上下文的稳定身份。
            context_identity = payload.context.identity_dict()
            context_identity.pop("project_id", None)
            context_identity.pop("year", None)
            identity.append(("consol_context", context_identity))
        if not identity:
            return base_key
        identity_key = json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return f"{base_key}:{identity_key}"

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """注册事件处理器"""
        self._handlers[event_type].append(handler)
        handler_name = getattr(handler, "__qualname__", repr(handler))
        logger.debug("EventBus: subscribed %s to %s", handler_name, event_type.value)

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

    async def _backfill_year(self, payload: EventPayload) -> None:
        """发布方漏传 ``year`` 时，在唯一派发口按项目审计年度补齐。

        🔴 修复前（2026-09-29 现扫）：数据链事件里有 11 个发布点不传 year
        （OnlyOffice 在线保存 / 底稿上传 / 底稿导入 / 函证 ×3 发 WORKPAPER_SAVED，
        科目表编辑发 ACCOUNT_MAPPING_CHANGED，报表公式 / 预填种子发
        FORMULA_CONFIG_CHANGED / PREFILL_MAPPING_CHANGED …），而订阅者对缺 year
        的处置各写各的：``if not year: return``（静默跳过 —— 如 OnlyOffice 保存后
        stale 传播、C/D/F 循环联动一律不跑）或 ``payload.year or 2025``（对 2024
        项目是**错年份**）。在派发口补一次，所有订阅者拿到同一个正确年份。

        只对 :data:`YEAR_SCOPED_EVENT_TYPES` 补（其订阅者真的读 year）；
        补不到（项目无任何年度信息）则保持 None，由订阅者的显式守卫可见降级。
        """
        if payload.year is not None or payload.event_type not in YEAR_SCOPED_EVENT_TYPES:
            return
        if not payload.project_id:
            return
        from app.services.project_audit_year import fetch_project_audit_year_standalone

        year = await fetch_project_audit_year_standalone(payload.project_id)
        if year is not None:
            payload.year = year
            logger.info(
                "EventBus: %s 发布方未传 year，已按项目审计年度补齐 year=%s (project=%s)",
                payload.event_type.value, year, payload.project_id,
            )
        else:
            logger.warning(
                "EventBus: %s 缺 year 且项目 %s 无审计年度可补，订阅者将按缺年度处理",
                payload.event_type.value, payload.project_id,
            )

    def broadcast_raw(self, event_type: str, extra: dict | None = None) -> None:
        """轻量级广播原始事件（同步调用）— 用于不走完整 EventBus dispatch 的场景。

        proposal-remaining-18 task 5.7 / C-3：批量导出 SSE 进度推送 + presence 类
        进程内事件总线，仅持久化到 Redis Stream 给 SSE 端订阅，不触发 _handlers。

        与 ``publish/publish_immediate`` 区别：
        - 不需要 EventPayload schema（接受任意 ``event_type`` 字符串）
        - 不入 debounce（实时推）
        - 不触发 _handlers（避免循环触发）
        - 仅写 Redis Stream + log

        Args:
            event_type: 事件类型字符串（如 "export.progress" / "presence.joined"）
            extra: 附加 payload（含 project_id / task_id / 业务字段）
        """
        extra = extra or {}
        logger.info(
            "EventBus.broadcast_raw: %s (project=%s, extra_keys=%s)",
            event_type, extra.get("project_id"), list(extra.keys()),
        )
        # 推送到所有内存 SSE 队列（让 SSE endpoint 实时感知 raw 事件）
        # 注意：与 publish/_dispatch 路径并行，不触发 _handlers，避免双发
        raw_event = {
            "_raw": True,
            "event_type": event_type,
            "project_id": extra.get("project_id"),
            "year": extra.get("year"),
            "extra": extra,
        }
        for queue in list(self._sse_queues):
            try:
                queue.put_nowait(raw_event)
            except asyncio.QueueFull:
                logger.warning(
                    "EventBus.broadcast_raw: SSE queue full, removing zombie queue"
                )
                self.remove_sse_queue(queue)
        # 异步持久化到 Redis Stream（不阻断调用方）
        try:
            asyncio.ensure_future(self._persist_raw_to_stream(event_type, extra))
        except RuntimeError:
            # 测试环境无 running event loop 时静默
            pass

    async def _persist_raw_to_stream(self, event_type: str, extra: dict) -> None:
        """把 raw event 写入 Redis Stream（XADD）"""
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            if redis is None:
                return
            stream_key = f"sse:project:{extra.get('project_id', 'global')}"
            await redis.xadd(
                stream_key,
                {
                    "event_type": event_type,
                    "payload": json.dumps(extra, default=str),
                },
                maxlen=1000,
                approximate=True,
            )
        except Exception as exc:
            logger.debug("[EventBus] broadcast_raw persist failed (non-blocking): %s", exc)

    async def _dispatch(self, payload: EventPayload) -> None:
        """实际分发事件到处理器"""
        dedup_key = self._build_dedup_key(payload)
        self._pending.pop(dedup_key, None)
        # 先按原 dedup_key 清 pending（补齐会改 year → 改 key），再补年度
        await self._backfill_year(payload)

        event_type = payload.event_type
        handlers = self._handlers.get(event_type, [])
        logger.debug(
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
            except Exception as exc:
                handler_name = getattr(handler, "__qualname__", repr(handler))
                logger.exception(
                    "EventBus: handler %s failed for event %s",
                    handler_name,
                    event_type.value,
                )
                # 发布 SYNC_FAILED 事件通知前端（避免递归：SYNC_FAILED 自身失败不再发布）
                if event_type != EventType.SYNC_FAILED:
                    try:
                        fail_payload = EventPayload(
                            event_type=EventType.SYNC_FAILED,
                            project_id=payload.project_id,
                            year=payload.year,
                            account_codes=payload.account_codes,
                            extra={
                                "source_event": event_type.value,
                                "handler": handler_name,
                                "error": str(exc),
                            },
                        )
                        await self._notify_sse(fail_payload)
                        asyncio.ensure_future(self._persist_to_stream(fail_payload))
                    except Exception:
                        logger.warning("EventBus: failed to publish SYNC_FAILED notification")

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
                # Requirement 13.2 / Property 53：typed replay 必须原样保留整份 payload。
                _STREAM_PAYLOAD_FIELD: serialize_payload_for_stream(payload),
            }
            await redis.xadd(_STREAM_KEY, event_data, maxlen=_STREAM_MAX_LEN)
        except Exception as e:
            logger.debug("EventBus: failed to persist event to Redis Stream: %s", e)

    async def replay_pending_events(self) -> int:
        """服务重启后从 Redis Stream 恢复未确认事件（可在 lifespan 中调用）

        Returns:
            恢复并重新分发的事件数量
        """
        report = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "redis_available": False,
            "read_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "acked_count": 0,
            # Requirement 13.9：无法解析而被 ACK 跳过的条目必须可观测。旧实现把它们
            # 直接 xack 丢掉且只并入 failed_count，运维看不出"事件被丢弃"这件事。
            "dropped_unparseable_count": 0,
            "last_error": None,
        }
        redis = await self._get_redis()
        if not redis:
            self._last_replay_report = report
            return 0

        try:
            report["redis_available"] = True
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
                self._last_replay_report = report
                return 0

            count = 0
            for stream_name, entries in messages:
                for msg_id, data in entries:
                    report["read_count"] += 1
                    try:
                        payload = deserialize_payload_from_stream(data)
                        event_type = payload.event_type
                        # 直接分发，不再持久化（避免循环）
                        handlers = self._handlers.get(event_type, [])
                        for handler in handlers:
                            try:
                                await handler(payload)
                            except Exception:
                                report["failed_count"] += 1
                                report["last_error"] = f"handler failed for {event_type.value}"
                        # ACK
                        await redis.xack(_STREAM_KEY, _CONSUMER_GROUP, msg_id)
                        report["acked_count"] += 1
                        report["success_count"] += 1
                        count += 1
                    except Exception as item_exc:
                        report["failed_count"] += 1
                        report["dropped_unparseable_count"] += 1
                        report["last_error"] = str(item_exc)
                        # 仍然 ACK：不 ACK 会让 consumer group 队头永久阻塞。但必须记
                        # ERROR + 单独计数，否则"事件被丢弃"这件事在日志和 /metrics 里
                        # 都不可见（Requirement 13.9）。
                        logger.error(
                            "EventBus: 丢弃无法解析的 Stream 条目 msg_id=%s fields=%s: %s",
                            msg_id,
                            sorted(data.keys()) if isinstance(data, dict) else type(data).__name__,
                            item_exc,
                        )
                        await redis.xack(_STREAM_KEY, _CONSUMER_GROUP, msg_id)
                        report["acked_count"] += 1

            logger.info("EventBus: replayed %d pending events from Redis Stream", count)
            self._last_replay_report = report
            return count
        except Exception as e:
            logger.warning("EventBus: replay_pending_events failed: %s", e)
            report["last_error"] = str(e)
            self._last_replay_report = report
            return 0

    def get_replay_report(self) -> dict[str, Any]:
        return dict(self._last_replay_report)

    # ------------------------------------------------------------------
    # SSE support
    # ------------------------------------------------------------------
    def create_sse_queue(self) -> asyncio.Queue[EventPayload | dict | None]:
        """创建一个 SSE 订阅队列，供 SSE endpoint 使用。

        队列同时接收：
        - EventPayload（publish/publish_immediate 强类型路径）
        - dict（broadcast_raw 路径，含 ``"_raw": True`` 标记）
        - None（关闭信号）
        """
        queue: asyncio.Queue[EventPayload | dict | None] = asyncio.Queue(maxsize=100)
        self._sse_queues.append(queue)
        logger.info("EventBus: SSE queue created, total=%d", len(self._sse_queues))
        return queue

    def remove_sse_queue(
        self, queue: asyncio.Queue[EventPayload | dict | None]
    ) -> None:
        """移除 SSE 订阅队列"""
        if queue in self._sse_queues:
            self._sse_queues.remove(queue)
            logger.info("EventBus: SSE queue removed, total=%d", len(self._sse_queues))

    async def _notify_sse(self, payload: EventPayload) -> None:
        """将事件推送到所有 SSE 队列"""
        for queue in list(self._sse_queues):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("EventBus: SSE queue full, removing zombie queue")
                self.remove_sse_queue(queue)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
try:
    from app.core.config import settings
    _debounce_ms = settings.EVENT_DEBOUNCE_MS
except Exception:
    _debounce_ms = 500

event_bus = EventBus(debounce_ms=_debounce_ms)
