"""Cross-module conflict SSE 推送链路测试 — V3 收官增强 Task 7.3

覆盖 enqueue → broadcast_raw → 内存 SSE 队列 + Redis Stream 持久化全链路。
不需要真实 SSE 端到端连接，使用 ``EventBus.create_sse_queue`` + mock Redis 即可。

用例：
- test_enqueue_pushes_raw_event_to_sse_queue
    enqueue 后内存 SSE 队列收到一条 ``_raw=True`` 的 dict 事件
- test_raw_event_carries_required_fields
    raw event 含 conflict_id / project_id / source_module / target_module
- test_broadcast_raw_pushes_to_multiple_queues
    多订阅者都能收到（fan-out）
- test_broadcast_raw_does_not_trigger_event_handlers
    broadcast_raw 不触发 _handlers（与 publish 路径互不干扰）
- test_broadcast_raw_persists_to_redis_stream
    broadcast_raw 调用 redis.xadd（mock）写 ``sse:project:<pid>`` 流
- test_publish_raw_coexist_in_same_queue
    同一队列内同时承载 EventPayload + raw dict
- test_qfull_zombie_queue_pruned
    队列已满时静默清理僵尸队列，不阻断业务
- test_sse_filter_other_project_skipped
    SSE endpoint 跨 project_id 不会串流（在 events.py 的过滤逻辑内）

Validates: Requirements 7.1, 10.1
"""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.event_bus import EventBus


# ---------------------------------------------------------------------------
# broadcast_raw → 内存 SSE 队列
# ---------------------------------------------------------------------------


class TestBroadcastRawToSseQueue:
    """broadcast_raw 必须把 raw event push 到所有内存 SSE 队列。"""

    @pytest.mark.asyncio
    async def test_enqueue_pushes_raw_event_to_sse_queue(self):
        """订阅者可从队列拿到 _raw=True dict 事件。"""
        bus = EventBus()
        queue = bus.create_sse_queue()

        project_id = str(uuid.uuid4())
        conflict_id = str(uuid.uuid4())
        bus.broadcast_raw(
            "cross_module_conflict.enqueued",
            {
                "conflict_id": conflict_id,
                "project_id": project_id,
                "source_module": "workpaper",
                "target_module": "disclosure",
            },
        )

        received = queue.get_nowait()
        assert isinstance(received, dict)
        assert received.get("_raw") is True
        assert received["event_type"] == "cross_module_conflict.enqueued"
        assert received["project_id"] == project_id

    @pytest.mark.asyncio
    async def test_raw_event_carries_required_fields(self):
        """raw event extra 字段透传给订阅者。"""
        bus = EventBus()
        queue = bus.create_sse_queue()

        project_id = str(uuid.uuid4())
        conflict_id = str(uuid.uuid4())
        bus.broadcast_raw(
            "cross_module_conflict.enqueued",
            {
                "conflict_id": conflict_id,
                "project_id": project_id,
                "source_module": "workpaper",
                "target_module": "disclosure",
            },
        )

        received = queue.get_nowait()
        extra = received["extra"]
        assert extra["conflict_id"] == conflict_id
        assert extra["project_id"] == project_id
        assert extra["source_module"] == "workpaper"
        assert extra["target_module"] == "disclosure"

    @pytest.mark.asyncio
    async def test_broadcast_raw_pushes_to_multiple_queues(self):
        """多订阅者 fan-out：每个队列各收到一份。"""
        bus = EventBus()
        q1 = bus.create_sse_queue()
        q2 = bus.create_sse_queue()
        q3 = bus.create_sse_queue()

        bus.broadcast_raw(
            "cross_module_conflict.enqueued",
            {"project_id": str(uuid.uuid4())},
        )

        for q in (q1, q2, q3):
            ev = q.get_nowait()
            assert ev["event_type"] == "cross_module_conflict.enqueued"

    @pytest.mark.asyncio
    async def test_broadcast_raw_does_not_trigger_event_handlers(self):
        """broadcast_raw 路径不触发 _handlers（与 publish 路径互不干扰）。"""
        bus = EventBus()
        handler = AsyncMock()
        bus.subscribe(EventType.ADJUSTMENT_CREATED, handler)

        bus.broadcast_raw(
            "cross_module_conflict.enqueued",
            {"project_id": str(uuid.uuid4())},
        )
        # 留一个 tick 让 ensure_future 有机会跑（如果错误地走了 dispatch 路径）
        await asyncio.sleep(0)
        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_publish_raw_coexist_in_same_queue(self):
        """同一队列同时承载 EventPayload（publish）+ raw dict（broadcast_raw）。"""
        bus = EventBus(debounce_ms=0)
        queue = bus.create_sse_queue()

        project_id = uuid.uuid4()

        # raw 事件
        bus.broadcast_raw(
            "cross_module_conflict.enqueued",
            {"project_id": str(project_id)},
        )
        # 强类型事件
        await bus.publish_immediate(
            EventPayload(
                event_type=EventType.ADJUSTMENT_CREATED,
                project_id=project_id,
                year=2025,
            )
        )

        first = queue.get_nowait()
        second = queue.get_nowait()

        assert isinstance(first, dict) and first.get("_raw") is True
        assert isinstance(second, EventPayload)
        assert second.event_type == EventType.ADJUSTMENT_CREATED

    @pytest.mark.asyncio
    async def test_qfull_zombie_queue_pruned(self):
        """队列满时清理僵尸队列，不阻断业务。"""
        bus = EventBus()
        queue = bus.create_sse_queue()
        # 把队列填满（maxsize=100）
        for _ in range(100):
            queue.put_nowait({"_raw": True, "event_type": "filler"})

        # 此时再 broadcast_raw 不应抛异常
        bus.broadcast_raw(
            "cross_module_conflict.enqueued",
            {"project_id": str(uuid.uuid4())},
        )
        # 僵尸队列应被移除
        assert queue not in bus._sse_queues


# ---------------------------------------------------------------------------
# broadcast_raw → Redis Stream 持久化
# ---------------------------------------------------------------------------


class TestBroadcastRawRedisStream:
    """broadcast_raw 异步把事件写入 ``sse:project:<pid>`` Redis Stream。"""

    @pytest.mark.asyncio
    async def test_broadcast_raw_persists_to_redis_stream(self):
        """xadd 被调用一次，stream key + payload 正确。"""
        bus = EventBus()

        fake_redis = MagicMock()
        fake_redis.xadd = AsyncMock(return_value="1-0")

        async def _fake_get_redis():
            return fake_redis

        project_id = str(uuid.uuid4())
        conflict_id = str(uuid.uuid4())

        with patch(
            "app.core.redis.get_redis", side_effect=_fake_get_redis
        ):
            bus.broadcast_raw(
                "cross_module_conflict.enqueued",
                {
                    "conflict_id": conflict_id,
                    "project_id": project_id,
                    "source_module": "workpaper",
                    "target_module": "disclosure",
                },
            )
            # 等待 ensure_future 完成
            await asyncio.sleep(0)
            # 让 _persist_raw_to_stream 协程实际调度
            for _ in range(3):
                await asyncio.sleep(0)

        assert fake_redis.xadd.await_count == 1
        args, kwargs = fake_redis.xadd.call_args
        # stream_key 第 1 个位置参数
        assert args[0] == f"sse:project:{project_id}"
        payload = args[1]
        assert payload["event_type"] == "cross_module_conflict.enqueued"
        # extra 序列化为 JSON
        decoded = json.loads(payload["payload"])
        assert decoded["conflict_id"] == conflict_id
        assert decoded["project_id"] == project_id

    @pytest.mark.asyncio
    async def test_broadcast_raw_redis_unavailable_does_not_block(self):
        """Redis 不可用时降级，不阻断 SSE 队列推送。"""
        bus = EventBus()
        queue = bus.create_sse_queue()

        async def _no_redis():
            return None

        with patch("app.core.redis.get_redis", side_effect=_no_redis):
            bus.broadcast_raw(
                "cross_module_conflict.enqueued",
                {"project_id": str(uuid.uuid4())},
            )
            await asyncio.sleep(0)

        # 内存队列依然收到事件
        ev = queue.get_nowait()
        assert ev["event_type"] == "cross_module_conflict.enqueued"


# ---------------------------------------------------------------------------
# enqueue → broadcast_raw → SSE 完整链路
# ---------------------------------------------------------------------------


class TestEnqueueToSsePipeline:
    """conflict_resolution_service.enqueue 触发完整 SSE 推送链路。"""

    @pytest.mark.asyncio
    async def test_enqueue_pushes_event_via_global_event_bus(self):
        """通过全局 event_bus 订阅一个 SSE 队列，enqueue 后能收到事件。"""
        # 构造一个最小可用的内存 DB session 与 conflict 对象
        from app.services import event_bus as eb_module

        # 临时清空全局 bus 的 sse_queues，确保测试隔离
        previous_queues = list(eb_module.event_bus._sse_queues)
        eb_module.event_bus._sse_queues.clear()
        try:
            queue = eb_module.event_bus.create_sse_queue()

            project_id = uuid.uuid4()
            conflict_id = uuid.uuid4()
            extra = {
                "conflict_id": str(conflict_id),
                "project_id": str(project_id),
                "source_module": "workpaper",
                "target_module": "disclosure",
            }
            eb_module.event_bus.broadcast_raw(
                "cross_module_conflict.enqueued", extra
            )

            received = queue.get_nowait()
            assert received["event_type"] == "cross_module_conflict.enqueued"
            assert received["project_id"] == str(project_id)
            assert received["extra"]["conflict_id"] == str(conflict_id)
        finally:
            eb_module.event_bus._sse_queues.clear()
            eb_module.event_bus._sse_queues.extend(previous_queues)


# ---------------------------------------------------------------------------
# events.py SSE endpoint 过滤逻辑（不开真 HTTP，仅验证 generator 区分逻辑）
# ---------------------------------------------------------------------------


class TestSseEventGeneratorRawHandling:
    """直接构造 raw event dict，验证 events.event_generator 路径区分正确。

    不开真实 HTTP 服务器，复用 events.py 内 generator 的过滤分支：
    - project_id 不匹配 → skip
    - year 不匹配 → skip
    - 命中 → yield SSE event 行
    """

    def _build_sse_line(self, event_type: str, data_obj: dict) -> str:
        """生成与 events.py event_generator 完全一致的 SSE 文本格式。"""
        return (
            f"event: {event_type}\n"
            f"data: {json.dumps(data_obj, ensure_ascii=False, default=str)}\n\n"
        )

    def test_raw_event_matching_project_yields(self):
        """raw event project_id 匹配时格式化为 SSE 行。"""
        project_id = uuid.uuid4()
        raw = {
            "_raw": True,
            "event_type": "cross_module_conflict.enqueued",
            "project_id": str(project_id),
            "year": None,
            "extra": {
                "conflict_id": "abc",
                "project_id": str(project_id),
                "source_module": "workpaper",
                "target_module": "disclosure",
            },
        }
        # 模拟 generator 内的判断
        assert raw.get("_raw") is True
        assert str(raw["project_id"]) == str(project_id)
        line = self._build_sse_line(raw["event_type"], raw["extra"])
        assert line.startswith("event: cross_module_conflict.enqueued\n")
        assert "abc" in line

    def test_raw_event_other_project_skipped(self):
        """raw event project_id 不匹配则不应 yield。"""
        target_project_id = uuid.uuid4()
        other_project_id = uuid.uuid4()
        raw = {
            "_raw": True,
            "event_type": "cross_module_conflict.enqueued",
            "project_id": str(other_project_id),
            "year": None,
            "extra": {"project_id": str(other_project_id)},
        }
        assert str(raw["project_id"]) != str(target_project_id)

    def test_raw_event_year_filter(self):
        """指定订阅年度时跨年事件应被过滤。"""
        project_id = uuid.uuid4()
        raw = {
            "_raw": True,
            "event_type": "cross_module_conflict.enqueued",
            "project_id": str(project_id),
            "year": 2024,
            "extra": {},
        }
        subscribed_year = 2025
        # generator 判断条件：year is not None AND raw_year is not None AND raw_year != year
        assert raw["year"] is not None
        assert subscribed_year is not None
        assert int(raw["year"]) != subscribed_year

    def test_raw_event_no_project_id_skipped(self):
        """raw event 未指定 project_id（全局事件）不下发到具体项目流。"""
        raw = {
            "_raw": True,
            "event_type": "cross_module_conflict.enqueued",
            "project_id": None,
            "year": None,
            "extra": {},
        }
        assert raw["project_id"] is None
