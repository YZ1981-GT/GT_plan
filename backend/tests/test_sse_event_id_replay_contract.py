# -*- coding: utf-8 -*-
"""typed live SSE id 与 replay 同源（runtime-performance-and-reload-hardening-followup R3.1）。

判据：业务 handler 保持原顺序；XADD 成功后、SSE notify 前拿到稳定 Redis id；队列对象仍是
EventPayload 子类（不破坏既有 spy/消费者），但 frame 带 `id:`；Redis 不可用 / XADD 失败时
live 仍下发普通 payload 且不伪造 id；replay 投影保留完整顶层字段。
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from app.models.audit_platform_schemas import EventPayload, EventType
from app.routers.events import _format_typed_sse
from app.services.event_bus import EventBus, SSEEventPayload
from app.services.workpaper_sync.content_events import REPLAY_ITEM_KEYS, replay_entry_projection


class _Redis:
    def __init__(self, event_id: str | bytes = b"1700000000000-7", *, fail: bool = False) -> None:
        self.event_id = event_id
        self.fail = fail
        self.entries: list[tuple[str, dict, dict]] = []

    async def xadd(self, key, fields, **kwargs):
        if self.fail:
            raise ConnectionError("redis dropped")
        self.entries.append((key, fields, kwargs))
        return self.event_id


class _TrackingBus(EventBus):
    def __init__(self, order: list[str]) -> None:
        super().__init__(debounce_ms=0)
        self.order = order
        self.notified: list[EventPayload] = []

    async def _notify_sse(self, payload: EventPayload) -> None:
        self.order.append("notify")
        self.notified.append(payload)
        await super()._notify_sse(payload)


def _payload() -> EventPayload:
    return EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=uuid.UUID("11111111-2222-3333-4444-555555555555"),
        year=2025,
        account_codes=["1001"],
        batch_id=uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        entry_group_id=uuid.UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff"),
        extra={"wp_id": "wp-1", "revision": 9},
    )


@pytest.mark.asyncio
async def test_handler_then_xadd_then_live_notify_with_same_id():
    order: list[str] = []
    redis = _Redis()
    bus = _TrackingBus(order)
    queue = bus.create_sse_queue()

    async def handler(_payload: EventPayload) -> None:
        order.append("handler")

    bus.subscribe(EventType.WORKPAPER_SAVED, handler)
    original_xadd = redis.xadd

    async def xadd(*args, **kwargs):
        order.append("xadd")
        return await original_xadd(*args, **kwargs)

    redis.xadd = xadd  # type: ignore[method-assign]
    bus._get_redis = AsyncMock(return_value=redis)  # type: ignore[method-assign]
    await bus.publish_immediate(_payload())

    assert order == ["handler", "xadd", "notify"]
    queued = queue.get_nowait()
    assert isinstance(queued, SSEEventPayload)
    assert queued.stream_event_id == "1700000000000-7"
    assert queued.event_type == EventType.WORKPAPER_SAVED
    # 传输 id 不得污染业务 canonical payload
    assert "stream_event_id" not in queued.model_dump(mode="json")


@pytest.mark.asyncio
async def test_redis_unavailable_keeps_live_payload_without_fake_id():
    bus = EventBus(debounce_ms=0)
    queue = bus.create_sse_queue()
    bus._get_redis = AsyncMock(return_value=None)  # type: ignore[method-assign]
    payload = _payload()
    await bus.publish_immediate(payload)
    queued = queue.get_nowait()
    assert queued is payload, "Redis down 时保持原 EventPayload 与旧 live 行为"
    assert not hasattr(queued, "stream_event_id")
    assert not _format_typed_sse(queued).startswith("id:")


@pytest.mark.asyncio
async def test_xadd_failure_is_live_fail_open_and_marks_redis_unavailable():
    bus = EventBus(debounce_ms=0)
    queue = bus.create_sse_queue()
    bus._redis_available = True
    bus._get_redis = AsyncMock(return_value=_Redis(fail=True))  # type: ignore[method-assign]
    payload = _payload()
    await bus.publish_immediate(payload)
    assert queue.get_nowait() is payload
    assert bus._redis_available is False


def test_typed_sse_frame_emits_redis_id_and_full_payload():
    payload = _payload()
    envelope = SSEEventPayload(**payload.model_dump(mode="python"), stream_event_id="1700000000001-3")
    frame = _format_typed_sse(envelope)
    assert frame.startswith("id: 1700000000001-3\nevent: workpaper.saved\ndata: ")
    data = json.loads(next(line[6:] for line in frame.splitlines() if line.startswith("data: ")))
    assert data["batch_id"] == str(payload.batch_id)
    assert data["entry_group_id"] == str(payload.entry_group_id)
    assert data["extra"] == payload.extra


def test_plain_typed_sse_frame_has_no_id_line():
    frame = _format_typed_sse(_payload())
    assert not frame.startswith("id:")
    assert "\nid: " not in frame


@pytest.mark.asyncio
async def test_persist_returns_string_for_bytes_and_string_ids():
    bus = EventBus(debounce_ms=0)
    for raw, expected in ((b"1-2", "1-2"), ("3-4", "3-4")):
        bus._get_redis = AsyncMock(return_value=_Redis(raw))  # type: ignore[method-assign]
        assert await bus._persist_to_stream(_payload()) == expected


def test_replay_projection_preserves_live_top_level_fields():
    payload = _payload()
    item = replay_entry_projection(
        "1700000000001-3",
        {"payload_json": payload.model_dump_json()},
    )
    assert item is not None
    assert set(item) == set(REPLAY_ITEM_KEYS)
    assert item["event_id"] == "1700000000001-3"
    assert item["batch_id"] == str(payload.batch_id)
    assert item["entry_group_id"] == str(payload.entry_group_id)
    assert item["extra"] == payload.extra


@pytest.mark.asyncio
async def test_since_scans_past_foreign_project_page(monkeypatch):
    """Redis count 在项目过滤前生效：前 100 条属别的项目时必须继续扫，不能假返回空。"""
    from types import SimpleNamespace

    import app.core.redis as redis_module
    from app.routers import events as events_router

    own = _payload()
    foreign = own.model_copy(update={"project_id": uuid.UUID("99999999-8888-7777-6666-555555555555")})
    first_page = [
        (f"{1000 + i}-0", {"payload_json": foreign.model_dump_json()})
        for i in range(100)
    ]
    second_page = [("1100-0", {"payload_json": own.model_dump_json()})]

    class _PagedRedis:
        def __init__(self):
            self.calls = []

        async def xrange(self, _key, **kwargs):
            self.calls.append(kwargs)
            return first_page if len(self.calls) == 1 else second_page

    fake = _PagedRedis()
    monkeypatch.setattr(redis_module, "redis_client", fake)
    monkeypatch.setattr(events_router, "check_project_access", AsyncMock(return_value=None))
    result = await events_router.get_events_since(
        project_id=own.project_id,
        last_event_id="999-0",
        since_timestamp=None,
        current_user=SimpleNamespace(id=uuid.uuid4()),
        db=AsyncMock(),
    )
    assert len(fake.calls) == 2
    assert fake.calls[0]["min"] == "(999-0"
    assert fake.calls[1]["min"] == "(1099-0"
    assert [item["event_id"] for item in result] == ["1100-0"]


def test_stream_route_validates_last_event_id_shape():
    """非法 cursor 应在 FastAPI 参数层 422，不能原样交给 XRANGE 后吞成空列表。"""
    import inspect

    from app.routers.events import get_events_since

    annotation = inspect.signature(get_events_since).parameters["last_event_id"].default
    pattern = getattr(annotation, "metadata", None)
    assert pattern, "last_event_id Query 缺 pattern 元数据（判据不可空转）"
    assert any(getattr(item, "pattern", None) == r"^\d+-\d+$" for item in pattern)
