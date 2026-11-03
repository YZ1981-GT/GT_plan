"""调整链 typed durable outbox 完整载荷与回滚边界。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.dataset_models import ImportEventConsumption, ImportEventOutbox
from app.schemas.consol_context import ConsolContext
from app.services.event_bus import event_bus
from app.services.workpaper_sync.outbox import DurableEventOutboxService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


@pytest_asyncio.fixture
async def world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Project.__table__, ImportEventOutbox.__table__, ImportEventConsumption.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        project = Project(
            id=uuid.uuid4(), name="【测试】typed outbox", client_name="【测试】typed outbox",
            project_type=ProjectType.annual, status=ProjectStatus.execution,
        )
        db.add(project)
        await db.commit()
        yield db, project
    await engine.dispose()


@pytest.mark.asyncio
async def test_typed_outbox_roundtrips_top_level_identity_and_context(world, monkeypatch):
    db, project = world
    group_id = uuid.uuid4()
    captured: list[EventPayload] = []

    async def capture(payload: EventPayload):
        captured.append(payload)

    monkeypatch.setattr(event_bus, "publish_immediate", capture)
    event = EventPayload(
        event_type=EventType.ADJUSTMENT_APPROVED,
        project_id=project.id,
        year=2025,
        account_codes=["1122", "6702"],
        entry_group_id=group_id,
        context=ConsolContext.legacy(project_id=project.id, year=2025, source_version="adjustment-test"),
        extra={"tb_recalc_committed": True, "operator_id": str(uuid.uuid4())},
    )
    await DurableEventOutboxService.enqueue_event(db, event)
    await db.commit()
    report = await DurableEventOutboxService.publish_pending(db)

    assert report.published == 1 and report.failed == 0
    assert len(captured) == 1
    replayed = captured[0]
    assert replayed.event_type == event.event_type
    assert replayed.project_id == event.project_id
    assert replayed.year == event.year
    assert replayed.account_codes == event.account_codes
    assert replayed.entry_group_id == event.entry_group_id
    assert replayed.context == event.context
    assert replayed.extra["tb_recalc_committed"] is True
    assert replayed.extra["__event_id"]


@pytest.mark.asyncio
async def test_rolled_back_typed_event_is_never_published(world, monkeypatch):
    db, project = world
    captured: list[EventPayload] = []

    async def capture(payload: EventPayload):
        captured.append(payload)

    monkeypatch.setattr(event_bus, "publish_immediate", capture)
    publication = await DurableEventOutboxService.enqueue_event(db, EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=project.id,
        year=2025,
        account_codes=["1001"],
    ))
    await db.rollback()
    report = await DurableEventOutboxService.publish_pending(db, [publication])
    assert report.rolled_back == 1
    assert captured == []
