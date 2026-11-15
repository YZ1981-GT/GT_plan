"""C8 真实 PostgreSQL：调整 outbox 失败可重放、重复句柄幂等。"""
from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.dataset_models import ImportEventOutbox
from app.services.import_event_outbox_service import ImportEventOutboxService
from app.services.workpaper_sync.outbox import DurableEventOutboxService

pytestmark = pytest.mark.pg_only
pytest_plugins = ("tests._adjustment_booking_pg_support",)


@pytest.mark.asyncio
async def test_pg_adjustment_outbox_failure_retry_and_duplicate(booking_pg_world, monkeypatch):
    world = booking_pg_world
    db = world.db
    event = EventPayload(
        event_type=EventType.ADJUSTMENT_APPROVED,
        project_id=world.project.id,
        year=2025,
        account_codes=["1122"],
    )
    publication = await DurableEventOutboxService.enqueue_event(
        db, event, remember=False,
    )
    await db.flush()
    original_publish_one = ImportEventOutboxService.publish_one

    async def fail_once(*_args, **_kwargs):
        raise RuntimeError("PG C8 故障注入")

    monkeypatch.setattr(ImportEventOutboxService, "publish_one", fail_once)
    failed = await DurableEventOutboxService.publish_pending(
        db, [publication], commit=False,
    )
    assert failed.failed == 1 and failed.published == 0
    pending = (await db.execute(sa.select(ImportEventOutbox.status).where(
        ImportEventOutbox.id == publication.outbox_id,
    ))).scalar_one()
    assert getattr(pending, "value", pending) == "pending"

    monkeypatch.setattr(ImportEventOutboxService, "publish_one", original_publish_one)
    retried = await DurableEventOutboxService.publish_pending(
        db, [publication], commit=False,
    )
    assert retried.published == 1 and retried.failed == 0
    duplicate = await DurableEventOutboxService.publish_pending(
        db, [publication], commit=False,
    )
    assert duplicate.already_published == 1
