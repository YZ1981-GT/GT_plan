"""试算表审定数统一写入器契约测试。"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import (
    AccountCategory,
    TrialBalance,
)
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.tb_audited_writer import publish_rows

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid


@pytest_asyncio.fixture
async def writer_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_project(session: AsyncSession) -> uuid.UUID:
    project_id = uuid.uuid4()
    session.add(
        Project(
            id=project_id,
            name="审定数写入器测试",
            client_name="测试客户",
            project_type=ProjectType.annual,
            status=ProjectStatus.execution,
            created_by=uuid.uuid4(),
        )
    )
    await session.flush()
    return project_id


def _tb_row(
    project_id: uuid.UUID,
    code: str,
    company_code: str = "001",
    *,
    is_deleted: bool = False,
) -> TrialBalance:
    return TrialBalance(
        id=uuid.uuid4(),
        project_id=project_id,
        year=2025,
        company_code=company_code,
        standard_account_code=code,
        account_name=code,
        account_category=AccountCategory.asset,
        unadjusted_amount=Decimal("100.00"),
        rje_adjustment=Decimal("5.00"),
        aje_adjustment=Decimal("-2.00"),
        audited_amount=Decimal("103.00"),
        is_deleted=is_deleted,
    )


@pytest.mark.asyncio
async def test_publish_rows_updates_all_components_in_one_transaction(writer_session):
    project_id = await _seed_project(writer_session)
    row = _tb_row(project_id, "1001")
    writer_session.add(row)
    await writer_session.commit()

    report = await publish_rows(
        writer_session,
        project_id,
        2025,
        [{"account_code": "1001", "audited_amount": "120.00"}],
        source="test:publish-to-tb",
    )

    assert report.updated_account_codes == ["1001"]
    assert report.skipped == []
    await writer_session.refresh(row)
    assert row.audited_amount == Decimal("120.00")
    assert row.wp_adjustment == Decimal("17.00")
    assert row.wp_publish_base == Decimal("100.00")
    assert row.wp_published_at is not None

    await writer_session.rollback()
    await writer_session.refresh(row)
    assert row.audited_amount == Decimal("103.00")


@pytest.mark.asyncio
async def test_publish_rows_skips_missing_deleted_and_multi_company_rows(writer_session):
    project_id = await _seed_project(writer_session)
    deleted = _tb_row(project_id, "1002", is_deleted=True)
    company_a = _tb_row(project_id, "1003", company_code="001")
    company_b = _tb_row(project_id, "1003", company_code="002")
    writer_session.add_all([deleted, company_a, company_b])
    await writer_session.flush()

    report = await publish_rows(
        writer_session,
        project_id,
        2025,
        [
            {"account_code": "1002", "audited_amount": 10},
            {"account_code": "1003", "audited_amount": 20},
            {"account_code": "1099", "audited_amount": 30},
        ],
        source="test:publish-to-tb",
    )

    assert report.updated_count == 0
    assert {item.account_code for item in report.skipped} == {"1002", "1003", "1099"}
    assert any("多个公司编码" in item.reason for item in report.skipped)
    await writer_session.refresh(company_a)
    await writer_session.refresh(company_b)
    assert company_a.audited_amount == Decimal("103.00")
    assert company_b.audited_amount == Decimal("103.00")


@pytest.mark.asyncio
async def test_publish_rows_rejects_invalid_amount_without_writing(writer_session):
    project_id = await _seed_project(writer_session)
    row = _tb_row(project_id, "1004")
    writer_session.add(row)
    await writer_session.flush()

    with pytest.raises(ValueError, match="不是有效金额"):
        await publish_rows(
            writer_session,
            project_id,
            2025,
            [{"account_code": "1004", "audited_amount": "not-a-number"}],
            source="test:publish-to-tb",
        )

    await writer_session.refresh(row)
    assert row.audited_amount == Decimal("103.00")


@pytest.mark.asyncio
async def test_publish_rows_requires_source(writer_session):
    project_id = await _seed_project(writer_session)
    with pytest.raises(ValueError, match="source 不能为空"):
        await publish_rows(writer_session, project_id, 2025, [], source="")


def test_v176_and_r176_contract():
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    forward = (migrations / "V176__trial_balance_workpaper_adjustment.sql").read_text(
        encoding="utf-8"
    )
    rollback = (migrations / "R176__rollback_trial_balance_workpaper_adjustment.sql").read_text(
        encoding="utf-8"
    )

    assert "ADD COLUMN IF NOT EXISTS wp_adjustment NUMERIC(20, 2) NOT NULL DEFAULT 0" in forward
    assert "ADD COLUMN IF NOT EXISTS wp_publish_base NUMERIC(20, 2)" in forward
    assert "ADD COLUMN IF NOT EXISTS wp_published_at TIMESTAMPTZ" in forward
    assert "audited_amount" in forward
    assert "COALESCE(unadjusted_amount, 0)" in forward
    assert "DROP COLUMN IF EXISTS wp_adjustment" in rollback
    assert "DROP COLUMN IF EXISTS wp_publish_base" in rollback
    assert "DROP COLUMN IF EXISTS wp_published_at" in rollback
