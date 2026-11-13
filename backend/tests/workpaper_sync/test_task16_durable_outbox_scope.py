"""R5：审批回执只消费本批耐久事件句柄。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.audit_platform_schemas import EventType
from app.services.import_event_outbox_service import ImportEventOutboxService
from app.services.workpaper_sync.outbox import DurableEventOutboxService, PendingPublication


@pytest.mark.asyncio
async def test_publish_pending_with_explicit_publications_keeps_other_session_handles(monkeypatch):
    first = PendingPublication(uuid4(), EventType.ADJUSTMENT_APPROVED, uuid4(), 2025)
    other = PendingPublication(uuid4(), EventType.TRIAL_BALANCE_UPDATED, uuid4(), 2025)
    db = SimpleNamespace(info={"workpaper_sync.durable_outbox.pending": [first, other]}, commit=AsyncMock())

    monkeypatch.setattr(ImportEventOutboxService, "get", AsyncMock(return_value=SimpleNamespace(status="pending")))
    monkeypatch.setattr(ImportEventOutboxService, "publish_one", AsyncMock(return_value=True))

    report = await DurableEventOutboxService.publish_pending(db, [first])

    assert report.attempted == 1
    assert report.published == 1
    assert db.info["workpaper_sync.durable_outbox.pending"] == [other]
