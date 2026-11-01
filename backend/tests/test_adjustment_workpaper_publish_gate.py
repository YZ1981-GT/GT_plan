"""底稿来源调整集中复核门与同步 TB 发布。"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import (
    AccountCategory,
    AdjustmentType,
    ReviewStatus,
    TbPublishAck,
    TrialBalance,
)
from app.models.base import Base, UserRole
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.models.dataset_models import ImportEventConsumption, ImportEventOutbox
from app.services.adjustment_group_writer import AdjustmentGroupLine, AdjustmentGroupWriter
from app.services.tb_publish_service import TbPublishError, publish_workpaper_rows

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


@pytest_asyncio.fixture
async def world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        User.__table__, Project.__table__, TrialBalance.__table__,
        # writer 依赖的两张表通过 metadata 名称取，避免重复导入长清单
        Base.metadata.tables["adjustments"], Base.metadata.tables["adjustment_entries"],
        TbPublishAck.__table__, ImportEventOutbox.__table__, ImportEventConsumption.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(
            id=uuid.uuid4(), username="wp_publish_reviewer", email="wp_publish@test.local",
            hashed_password="x", role=UserRole.manager,
        )
        project = Project(
            id=uuid.uuid4(), name="【测试】底稿调整发布", client_name="【测试】底稿调整发布",
            project_type=ProjectType.annual, status=ProjectStatus.execution,
            company_code="913500001234567890", created_by=user.id,
        )
        db.add_all([user, project])
        await db.flush()
        tb = TrialBalance(
            project_id=project.id, year=2025, company_code="001",
            standard_account_code="1122", account_name="应收账款",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("1000"), aje_adjustment=Decimal("100"),
            rje_adjustment=Decimal("0"), wp_adjustment=Decimal("0"),
            audited_amount=Decimal("1100"),
        )
        db.add(tb)
        await db.commit()
        yield db, user, project, tb
    await engine.dispose()


async def _workpaper_adjustment(db, user, project, wp_id, status: ReviewStatus):
    return await AdjustmentGroupWriter(db).write_group(
        project_id=project.id, year=2025, company_code="001",
        adjustment_no="AJE-WP-001", adjustment_type=AdjustmentType.aje,
        description="底稿汇聚调整", entry_group_id=uuid.uuid4(),
        lines=[AdjustmentGroupLine(
            standard_account_code="1122", account_name="应收账款", debit_amount=Decimal("20"),
        )],
        content_revision=1, audit_phase="final", review_status=status,
        origin="workpaper", source_ref=f"{wp_id}:D2-adjustment-1", created_by=user.id,
    )


@pytest.mark.asyncio
async def test_unapproved_workpaper_adjustment_blocks_publish_and_keeps_tb(world):
    db, user, project, tb = world
    tb_id = tb.id
    wp_id = uuid.uuid4()
    await _workpaper_adjustment(db, user, project, wp_id, ReviewStatus.pending_review)
    await db.flush()
    with pytest.raises(TbPublishError) as caught:
        await publish_workpaper_rows(
            db, project_id=project.id, year=2025, wp_id=wp_id, wp_code="D2-1",
            rows=[{"account_code": "1122", "audited_amount": "1120"}],
            publish_token="blocked-token", confirmed_by=user.id,
        )
    assert caught.value.code == "WORKPAPER_ADJUSTMENTS_NOT_APPROVED"
    assert caught.value.detail["groups"][0]["adjustment_no"] == "AJE-WP-001"
    await db.rollback()
    audited = (await db.execute(sa.select(TrialBalance.audited_amount).where(
        TrialBalance.id == tb_id,
    ))).scalar_one()
    assert audited == Decimal("1100")
    assert (await db.execute(sa.select(sa.func.count()).select_from(TbPublishAck))).scalar_one() == 0


@pytest.mark.asyncio
async def test_approved_workpaper_adjustment_publishes_once_without_aje_double_count(world):
    db, user, project, tb = world
    wp_id = uuid.uuid4()
    written = await _workpaper_adjustment(db, user, project, wp_id, ReviewStatus.approved)
    result = await publish_workpaper_rows(
        db, project_id=project.id, year=2025, wp_id=wp_id, wp_code="D2-1",
        rows=[{"account_code": "1122", "audited_amount": "1120"}],
        publish_token="approved-token", confirmed_by=user.id,
    )
    await db.commit()
    await db.refresh(tb)
    assert result.duplicate is False
    assert result.related_adjustment_groups == (str(written.adjustments[0].entry_group_id),)
    assert tb.aje_adjustment == Decimal("100"), "底稿来源不得再次进入 AJE 列"
    assert tb.wp_adjustment == Decimal("20")
    assert tb.audited_amount == Decimal("1120")
    outbox = list((await db.execute(sa.select(ImportEventOutbox))).scalars().all())
    assert {row.event_type for row in outbox} == {"workpaper.saved", "trial_balance.updated"}
    typed = [row.payload["__typed_event_payload_v1"] for row in outbox]
    assert all(item["account_codes"] == ["1122"] for item in typed)

    duplicate = await publish_workpaper_rows(
        db, project_id=project.id, year=2025, wp_id=wp_id, wp_code="D2-1",
        rows=[{"account_code": "1122", "audited_amount": "9999"}],
        publish_token="approved-token", confirmed_by=user.id,
    )
    assert duplicate.duplicate is True
    await db.refresh(tb)
    assert tb.audited_amount == Decimal("1120")
