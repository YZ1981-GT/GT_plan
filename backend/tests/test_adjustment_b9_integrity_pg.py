"""B9：分录组 CAS、数据库约束和真实 PostgreSQL 结构验收。"""
from __future__ import annotations

from decimal import Decimal
import uuid

import pytest
import sqlalchemy as sa

from app.models.audit_platform_models import AdjustmentEntry, AdjustmentType, ReviewStatus
from app.models.audit_platform_schemas import AdjustmentUpdate
from app.services.adjustment_group_writer import AdjustmentGroupLine, AdjustmentGroupWriter
from app.services.adjustment_service import AdjustmentService

pytestmark = pytest.mark.pg_only
pytest_plugins = ("tests._adjustment_booking_pg_support",)


async def _draft_group(world):
    group_id = uuid.uuid4()
    await AdjustmentGroupWriter(world.db).write_group(
        project_id=world.project.id,
        year=2025,
        company_code="001",
        adjustment_no=f"AJE-PG-CAS-{uuid.uuid4().hex[:8]}",
        adjustment_type=AdjustmentType.aje,
        description="B9 CAS 测试",
        entry_group_id=group_id,
        lines=[
            AdjustmentGroupLine(
                standard_account_code="1122",
                account_name="应收账款",
                debit_amount=Decimal("10"),
            ),
            AdjustmentGroupLine(
                standard_account_code="6702",
                account_name="信用减值损失",
                credit_amount=Decimal("10"),
            ),
        ],
        content_revision=1,
        audit_phase="final",
        review_status=ReviewStatus.draft,
        created_by=world.actor.id,
    )
    await world.db.flush()
    return group_id


@pytest.mark.asyncio
async def test_pg_stale_group_revision_is_rejected(booking_pg_world):
    world = booking_pg_world
    group_id = await _draft_group(world)
    service = AdjustmentService(world.db)

    updated = await service.update_entry(
        world.project.id,
        group_id,
        AdjustmentUpdate(expected_revision=1, description="第一次编辑"),
        world.actor.id,
    )
    await world.db.flush()
    assert updated.entry_group_id == group_id
    assert updated.content_revision == 2

    with pytest.raises(ValueError, match="当前版本 2"):
        await service.update_entry(
            world.project.id,
            group_id,
            AdjustmentUpdate(expected_revision=1, description="陈旧编辑"),
            world.actor.id,
        )


@pytest.mark.asyncio
async def test_pg_entry_amount_constraint_rejects_negative_value(booking_pg_world):
    world = booking_pg_world
    anchor = (await world.db.execute(sa.select(AdjustmentEntry).where(
        AdjustmentEntry.entry_group_id == world.group_id,
        AdjustmentEntry.is_deleted.is_(False),
    ).limit(1))).scalar_one()

    with pytest.raises(sa.exc.IntegrityError):
        async with world.db.begin_nested():
            world.db.add(AdjustmentEntry(
                id=uuid.uuid4(),
                adjustment_id=anchor.adjustment_id,
                entry_group_id=world.group_id,
                line_no=99,
                standard_account_code="1122",
                account_name="应收账款",
                debit_amount=Decimal("-1"),
                credit_amount=Decimal("0"),
            ))
            await world.db.flush()


@pytest.mark.asyncio
async def test_pg_adjustment_rls_objects_are_force_enabled(booking_pg_world):
    world = booking_pg_world
    rows = (await world.db.execute(sa.text("""
        SELECT c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema()
          AND c.relname IN (
            'adjustment_review_tasks',
            'adjustment_client_bookings',
            'adjustment_treatment_events'
          )
        ORDER BY c.relname
    """))).all()
    assert len(rows) == 3
    assert all(row.relrowsecurity and row.relforcerowsecurity for row in rows)
