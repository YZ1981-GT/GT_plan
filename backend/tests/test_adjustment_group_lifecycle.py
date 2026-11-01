"""调整分录删除、回收站展示、恢复与永久删除均以分录组为单位。"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.pagination import PaginationParams
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountSource,
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    TrialBalance,
)
from app.models.base import Base, UserRole
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.models.audit_platform_schemas import AdjustmentCreate, AdjustmentLineItem
from app.routers.recycle_bin import list_recycle_bin, permanently_delete, restore_item
from app.services.adjustment_service import AdjustmentService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


@pytest_asyncio.fixture
async def world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        User.__table__, Project.__table__, AccountChart.__table__,
        Adjustment.__table__, AdjustmentEntry.__table__, TrialBalance.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(
            id=uuid.uuid4(), username="adj_lifecycle_admin", email="adj_lifecycle@test.local",
            hashed_password="x", role=UserRole.admin,
        )
        project = Project(
            id=uuid.uuid4(), name="【测试】调整组生命周期", client_name="【测试】调整组生命周期",
            project_type=ProjectType.annual, status=ProjectStatus.execution,
            company_code="913500001234567890", created_by=user.id,
        )
        db.add_all([user, project])
        await db.flush()
        for code, name, direction, category in [
            ("1001", "库存现金", AccountDirection.debit, AccountCategory.asset),
            ("6001", "主营业务收入", AccountDirection.credit, AccountCategory.revenue),
        ]:
            db.add(AccountChart(
                project_id=project.id, account_code=code, account_name=name,
                direction=direction, category=category, level=1, source=AccountSource.standard,
            ))
        await db.commit()
        yield db, user, project
    await engine.dispose()


async def _create_group(db: AsyncSession, user: User, project: Project):
    result = await AdjustmentService(db).create_entry(
        project.id,
        AdjustmentCreate(
            adjustment_type=AdjustmentType.aje,
            year=2025,
            description="组级删除恢复",
            line_items=[
                AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("100")),
                AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("100")),
            ],
        ),
        user.id,
    )
    await db.commit()
    return result


@pytest.mark.asyncio
async def test_delete_list_and_restore_operate_on_whole_group(world):
    db, user, project = world
    created = await _create_group(db, user, project)
    await AdjustmentService(db).delete_entry(
        project.id, created.entry_group_id, expected_revision=1, user_id=user.id,
    )
    await db.commit()

    rows = list((await db.execute(sa.select(Adjustment).where(
        Adjustment.entry_group_id == created.entry_group_id,
    ))).scalars().all())
    entries = list((await db.execute(sa.select(AdjustmentEntry).where(
        AdjustmentEntry.entry_group_id == created.entry_group_id,
    ))).scalars().all())
    assert len(rows) == len(entries) == 2
    assert all(row.is_deleted and row.deleted_at and row.updated_by == user.id for row in rows)
    assert all(row.is_deleted and row.deleted_at for row in entries)

    listing = await list_recycle_bin(
        item_type="adjustment", pagination=PaginationParams(page=1, page_size=20), db=db, user=user,
    )
    assert listing["total"] == 1
    assert len(listing["items"]) == 1
    assert listing["items"][0]["entry_group_id"] == str(created.entry_group_id)

    restored = await restore_item("adjustment", uuid.UUID(listing["items"][0]["id"]), db=db, user=user)
    assert restored["entry_group_id"] == str(created.entry_group_id)
    assert not any((await db.execute(sa.select(Adjustment.is_deleted).where(
        Adjustment.entry_group_id == created.entry_group_id,
    ))).scalars().all())
    assert not any((await db.execute(sa.select(AdjustmentEntry.is_deleted).where(
        AdjustmentEntry.entry_group_id == created.entry_group_id,
    ))).scalars().all())


@pytest.mark.asyncio
async def test_permanent_delete_removes_group_and_entries(world):
    db, user, project = world
    created = await _create_group(db, user, project)
    await AdjustmentService(db).delete_entry(project.id, created.entry_group_id, user_id=user.id)
    await db.commit()
    anchor = (await db.execute(sa.select(Adjustment).where(
        Adjustment.entry_group_id == created.entry_group_id,
    ))).scalars().first()

    result = await permanently_delete("adjustment", anchor.id, db=db, user=user)
    assert result["entry_group_id"] == str(created.entry_group_id)
    assert (await db.execute(sa.select(sa.func.count()).select_from(Adjustment).where(
        Adjustment.entry_group_id == created.entry_group_id,
    ))).scalar_one() == 0
    assert (await db.execute(sa.select(sa.func.count()).select_from(AdjustmentEntry).where(
        AdjustmentEntry.entry_group_id == created.entry_group_id,
    ))).scalar_one() == 0
