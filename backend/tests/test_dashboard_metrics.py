"""Tests for dashboard_service.py — 5 real metrics (Task Group 8)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpQcResult,
    WpReviewStatus,
    WpSourceType,
    WpIndex,
)
from app.models.audit_platform_models import Adjustment, AdjustmentType, ReviewStatus
from app.services.dashboard_service import DashboardService

# Import all models so metadata is complete
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.report_models  # noqa: F401
import app.models.workpaper_models  # noqa: F401
import app.models.staff_models  # noqa: F401

from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_project(db, *, status=ProjectStatus.execution, days_ago=0):
    p = Project(
        id=uuid.uuid4(),
        name=f"Test-{uuid.uuid4().hex[:6]}",
        client_name="Client",
        status=status,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.add(p)
    await db.flush()
    return p


async def _create_wp_index(db, project_id, code="E1-1"):
    idx = WpIndex(
        id=uuid.uuid4(),
        project_id=project_id,
        wp_code=code,
        wp_name=f"WP {code}",
        audit_cycle="E",
    )
    db.add(idx)
    await db.flush()
    return idx


async def _create_working_paper(db, project_id, wp_index_id, *, review_status=WpReviewStatus.not_submitted):
    wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=project_id,
        wp_index_id=wp_index_id,
        file_path="/tmp/test.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        review_status=review_status,
    )
    db.add(wp)
    await db.flush()
    return wp


async def _create_qc_result(db, wp_id, *, passed=True):
    qc = WpQcResult(
        id=uuid.uuid4(),
        working_paper_id=wp_id,
        check_timestamp=datetime.now(timezone.utc),
        findings={},
        passed=passed,
    )
    db.add(qc)
    await db.flush()
    return qc


async def _create_adjustment(db, project_id, *, is_deleted=False):
    adj = Adjustment(
        id=uuid.uuid4(),
        project_id=project_id,
        year=2025,
        company_code="001",
        adjustment_no=f"AJE-{uuid.uuid4().hex[:4]}",
        adjustment_type=AdjustmentType.aje,
        account_code="1001",
        debit_amount=100,
        credit_amount=0,
        entry_group_id=uuid.uuid4(),
        review_status=ReviewStatus.draft,
        is_deleted=is_deleted,
        created_by=uuid.uuid4(),
    )
    db.add(adj)
    await db.flush()
    return adj


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overdue_projects_counts_old_active(db_session):
    """8.1: overdue_projects counts projects created >180 days ago in execution/planning."""
    svc = DashboardService(db_session)

    await _create_project(db_session, status=ProjectStatus.execution, days_ago=200)
    await _create_project(db_session, status=ProjectStatus.execution, days_ago=10)
    await _create_project(db_session, status=ProjectStatus.archived, days_ago=300)
    await _create_project(db_session, status=ProjectStatus.planning, days_ago=190)

    count = await svc._get_overdue_projects()
    assert count == 2


@pytest.mark.asyncio
async def test_pending_review_workpapers(db_session):
    """8.2: pending_review_workpapers counts WPs with pending_level1/2."""
    svc = DashboardService(db_session)
    p = await _create_project(db_session)

    await _create_working_paper(
        db_session, p.id,
        (await _create_wp_index(db_session, p.id, "W1")).id,
        review_status=WpReviewStatus.pending_level1,
    )
    await _create_working_paper(
        db_session, p.id,
        (await _create_wp_index(db_session, p.id, "W2")).id,
        review_status=WpReviewStatus.pending_level2,
    )
    await _create_working_paper(
        db_session, p.id,
        (await _create_wp_index(db_session, p.id, "W3")).id,
        review_status=WpReviewStatus.not_submitted,
    )

    count = await svc._get_pending_review_workpapers()
    assert count == 2


@pytest.mark.asyncio
async def test_qc_pass_rate(db_session):
    """8.3: qc_pass_rate = passed / total * 100."""
    svc = DashboardService(db_session)
    p = await _create_project(db_session)
    wp = await _create_working_paper(
        db_session, p.id,
        (await _create_wp_index(db_session, p.id)).id,
    )

    await _create_qc_result(db_session, wp.id, passed=True)
    await _create_qc_result(db_session, wp.id, passed=True)
    await _create_qc_result(db_session, wp.id, passed=False)

    metrics = await svc.get_quality_metrics()
    assert metrics["qc_pass_rate"] == pytest.approx(66.7, abs=0.1)


@pytest.mark.asyncio
async def test_review_completion_rate(db_session):
    """8.4: review_completion_rate = reviewed / total * 100."""
    svc = DashboardService(db_session)
    p = await _create_project(db_session)

    await _create_working_paper(
        db_session, p.id,
        (await _create_wp_index(db_session, p.id, "R1")).id,
        review_status=WpReviewStatus.level1_passed,
    )
    await _create_working_paper(
        db_session, p.id,
        (await _create_wp_index(db_session, p.id, "R2")).id,
        review_status=WpReviewStatus.level2_passed,
    )
    await _create_working_paper(
        db_session, p.id,
        (await _create_wp_index(db_session, p.id, "R3")).id,
        review_status=WpReviewStatus.pending_level1,
    )
    await _create_working_paper(
        db_session, p.id,
        (await _create_wp_index(db_session, p.id, "R4")).id,
        review_status=WpReviewStatus.not_submitted,
    )

    metrics = await svc.get_quality_metrics()
    assert metrics["review_completion_rate"] == 50.0


@pytest.mark.asyncio
async def test_adjustment_count(db_session):
    """8.5: adjustment_count = active (non-deleted) adjustments."""
    svc = DashboardService(db_session)
    p = await _create_project(db_session)

    await _create_adjustment(db_session, p.id, is_deleted=False)
    await _create_adjustment(db_session, p.id, is_deleted=False)
    await _create_adjustment(db_session, p.id, is_deleted=True)

    metrics = await svc.get_quality_metrics()
    assert metrics["adjustment_count"] == 2


@pytest.mark.asyncio
async def test_overview_includes_all_metrics(db_session):
    """get_overview returns overdue_projects and pending_review_workpapers."""
    svc = DashboardService(db_session)
    result = await svc.get_overview()

    assert "overdue_projects" in result
    assert "pending_review_workpapers" in result
    assert isinstance(result["overdue_projects"], int)
    assert isinstance(result["pending_review_workpapers"], int)
