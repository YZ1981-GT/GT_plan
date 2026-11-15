"""C8：调整 durable outbox 失败可重试、重复投递幂等与 Redis 降级。"""
from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.dataset_models import ImportEventOutbox
from app.services.event_bus import event_bus
from app.services.import_event_outbox_service import ImportEventOutboxService
from app.services.workpaper_sync.outbox import DurableEventOutboxService

pytest_plugins = ("tests.test_adjustment_typed_outbox",)


@pytest.mark.asyncio
async def test_adjustment_outbox_failure_stays_retryable_then_duplicate_is_idempotent(world, monkeypatch):
    db, project = world
    captured: list[EventPayload] = []

    async def capture(payload: EventPayload):
        captured.append(payload)

    monkeypatch.setattr(event_bus, "publish_immediate", capture)
    original_publish_one = ImportEventOutboxService.publish_one
    event = EventPayload(
        event_type=EventType.ADJUSTMENT_APPROVED,
        project_id=project.id,
        year=2025,
        account_codes=["1122"],
    )
    publication = await DurableEventOutboxService.enqueue_event(db, event)
    await db.commit()

    async def fail_once(*_args, **_kwargs):
        raise RuntimeError("C8 故障注入")

    monkeypatch.setattr(ImportEventOutboxService, "publish_one", fail_once)
    failed = await DurableEventOutboxService.publish_pending(db, [publication])
    assert failed.failed == 1 and failed.published == 0
    pending = (await db.execute(sa.select(ImportEventOutbox.status).where(
        ImportEventOutbox.id == publication.outbox_id,
    ))).scalar_one()
    assert getattr(pending, "value", pending) == "pending"

    monkeypatch.setattr(ImportEventOutboxService, "publish_one", original_publish_one)
    retried = await DurableEventOutboxService.publish_pending(db, [publication])
    assert retried.published == 1 and retried.failed == 0
    assert len(captured) == 1

    duplicate = await DurableEventOutboxService.publish_pending(db, [publication])
    assert duplicate.already_published == 1
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_adjustment_event_bus_redis_failure_degrades_to_memory(monkeypatch):
    from app.core import redis as redis_module

    class BrokenRedis:
        async def ping(self):
            raise ConnectionError("Redis 不可用")

    previous = event_bus._redis_available
    monkeypatch.setattr(redis_module, "redis_client", BrokenRedis())
    event_bus._redis_available = None
    try:
        assert await event_bus._get_redis() is None
        assert event_bus._redis_available is False
    finally:
        event_bus._redis_available = previous
