"""NOTE_SECTION_SAVED 的 debounce 身份必须包含章节号。"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.event_bus import EventBus


def _payload(section: str, *, action: str = "save") -> EventPayload:
    return EventPayload(
        event_type=EventType.NOTE_SECTION_SAVED,
        project_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        year=2025,
        extra={"section_code": section, "action": action},
    )


@pytest.mark.asyncio
async def test_two_note_sections_both_dispatch_through_real_debounce(monkeypatch):
    bus = EventBus(debounce_ms=10)
    received: list[EventPayload] = []

    async def handler(payload: EventPayload) -> None:
        received.append(payload)

    async def no_redis(_payload: EventPayload) -> None:
        return None

    monkeypatch.setattr(bus, "_persist_to_stream", no_redis)
    bus.subscribe(EventType.NOTE_SECTION_SAVED, handler)
    queue = bus.create_sse_queue()

    await bus.publish(_payload("八、1"))
    await bus.publish(_payload("八、2"))
    await asyncio.sleep(0.06)

    assert {p.extra["section_code"] for p in received} == {"八、1", "八、2"}
    queued = [queue.get_nowait(), queue.get_nowait()]
    assert {p.extra["section_code"] for p in queued} == {"八、1", "八、2"}
    assert bus._pending == {}


@pytest.mark.asyncio
async def test_same_note_section_still_debounces_to_last_payload(monkeypatch):
    bus = EventBus(debounce_ms=10)
    received: list[EventPayload] = []

    async def no_redis(_payload: EventPayload) -> None:
        return None

    async def handler(payload: EventPayload) -> None:
        received.append(payload)

    monkeypatch.setattr(bus, "_persist_to_stream", no_redis)
    bus.subscribe(EventType.NOTE_SECTION_SAVED, handler)
    await bus.publish(_payload("八、1", action="first"))
    await bus.publish(_payload("八、1", action="last"))
    await asyncio.sleep(0.06)
    assert [p.extra["action"] for p in received] == ["last"]


def test_section_code_changes_only_note_saved_dedup_identity():
    bus = EventBus()
    first, second = _payload("八、1"), _payload("八、2")
    assert bus._build_dedup_key(first) != bus._build_dedup_key(second)
    first.extra["action"], second.extra["section_code"] = "other", "八、1"
    assert bus._build_dedup_key(first) == bus._build_dedup_key(second)

    other_a = EventPayload(event_type=EventType.REPORTS_UPDATED, project_id=first.project_id, year=2025,
                           extra={"section_code": "八、1"})
    other_b = EventPayload(event_type=EventType.REPORTS_UPDATED, project_id=first.project_id, year=2025,
                           extra={"section_code": "八、2"})
    assert bus._build_dedup_key(other_a) == bus._build_dedup_key(other_b)
