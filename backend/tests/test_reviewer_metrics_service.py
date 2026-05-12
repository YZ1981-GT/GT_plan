"""R3 需求 6：复核人深度指标服务单元测试

覆盖：
  1. compute_metrics 计算 5 项指标
  2. compute_all_reviewers 批量计算并持久化
  3. get_metrics 查询快照
  4. 边界情况：无数据时返回 None

Validates: Requirements 6 (refinement-round3-quality-control)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.phase15_models import IssueTicket
from app.models.qc_inspection_models import QcInspection, QcInspectionItem
from app.models.qc_rating_models import ReviewerMetricsSnapshot
from app.models.workpaper_models import (
    ReviewCommentStatus,
    ReviewRecord,
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpSourceType,
    WpStatus,
)

# SQLite 不支持 JSONB，用 JSON 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

FAKE_USER_ID = uuid.uuid4()
FAKE_REVIEWER_ID = uuid.uuid4()
FAKE_REVIEWER_ID_2 = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
YEAR = 2025


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    """Seed project, wp_index, working_paper, and review records."""
    project = Project(
        id=FAKE_PROJECT_ID,
        name="测试项目_2025",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    wp_index = WpIndex(
        id=uuid.uuid4(),
        project_id=FAKE_PROJECT_ID,
        wp_code="D-01",
        wp_name="测试底稿",
        status=WpStatus.in_progress,
    )
    db_session.add(wp_index)
    await db_session.flush()

    wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=FAKE_PROJECT_ID,
        wp_index_id=wp_index.id,
        file_path="/test/path",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        reviewer=FAKE_REVIEWER_ID,
    )
    db_session.add(wp)
    await db_session.flush()

    # Create review records for the reviewer
    base_time = datetime(YEAR, 3, 15, 10, 0, 0)

    # Record 1: resolved after 30 minutes
    r1 = ReviewRecord(
        id=uuid.uuid4(),
        working_paper_id=wp.id,
        comment_text="请核对金额",
        commenter_id=FAKE_REVIEWER_ID,
        status=ReviewCommentStatus.resolved,
        created_at=base_time,
        updated_at=base_time + timedelta(minutes=30),
    )
    # Record 2: resolved after 60 minutes
    r2 = ReviewRecord(
        id=uuid.uuid4(),
        working_paper_id=wp.id,
        comment_text="数据来源不明",
        commenter_id=FAKE_REVIEWER_ID,
        status=ReviewCommentStatus.resolved,
        created_at=base_time + timedelta(hours=1),
        updated_at=base_time + timedelta(hours=1, minutes=60),
    )
    # Record 3: still open (should not count for avg_review_time)
    r3 = ReviewRecord(
        id=uuid.uuid4(),
        working_paper_id=wp.id,
        comment_text="待确认",
        commenter_id=FAKE_REVIEWER_ID,
        status=ReviewCommentStatus.open,
        created_at=base_time + timedelta(hours=2),
        updated_at=base_time + timedelta(hours=2),
    )
    db_session.add_all([r1, r2, r3])
    await db_session.flush()

    # Create an IssueTicket linked to r1 (source='review_comment')
    ticket = IssueTicket(
        id=uuid.uuid4(),
        project_id=FAKE_PROJECT_ID,
        wp_id=wp.id,
        source="review_comment",
        source_ref_id=r1.id,
        severity="major",
        category="data_mismatch",
        title="金额不符",
        owner_id=FAKE_USER_ID,
        status="open",
        trace_id=str(uuid.uuid4()),
        created_at=base_time,
        updated_at=base_time,
    )
    db_session.add(ticket)
    await db_session.flush()

    return {
        "project": project,
        "wp_index": wp_index,
        "wp": wp,
        "reviews": [r1, r2, r3],
        "ticket": ticket,
    }


@pytest.mark.asyncio
async def test_compute_avg_review_time(db_session: AsyncSession, seeded):
    """avg_review_time_min should be average of resolved records' duration."""
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    metrics = await reviewer_metrics_service.compute_metrics(
        db_session, FAKE_REVIEWER_ID, YEAR
    )
    # r1: 30 min, r2: 60 min → avg = 45 min
    assert metrics["avg_review_time_min"] == 45.0


@pytest.mark.asyncio
async def test_compute_avg_comments_per_wp(db_session: AsyncSession, seeded):
    """avg_comments_per_wp = total comments / distinct WPs."""
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    metrics = await reviewer_metrics_service.compute_metrics(
        db_session, FAKE_REVIEWER_ID, YEAR
    )
    # 3 comments on 1 WP → 3.0
    assert metrics["avg_comments_per_wp"] == 3.0


@pytest.mark.asyncio
async def test_compute_rejection_rate(db_session: AsyncSession, seeded):
    """rejection_rate = rejected WPs / total reviewed WPs."""
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    # No rejections in seeded data
    metrics = await reviewer_metrics_service.compute_metrics(
        db_session, FAKE_REVIEWER_ID, YEAR
    )
    assert metrics["rejection_rate"] == 0.0


@pytest.mark.asyncio
async def test_compute_rejection_rate_with_rejection(db_session: AsyncSession, seeded):
    """rejection_rate should reflect actual rejections."""
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    # Mark the WP as rejected by the reviewer
    wp = seeded["wp"]
    wp.rejected_by = FAKE_REVIEWER_ID
    wp.rejected_at = datetime(YEAR, 4, 1, 10, 0, 0)
    db_session.add(wp)
    await db_session.flush()

    metrics = await reviewer_metrics_service.compute_metrics(
        db_session, FAKE_REVIEWER_ID, YEAR
    )
    # 1 rejection / 1 WP = 1.0
    assert metrics["rejection_rate"] == 1.0


@pytest.mark.asyncio
async def test_compute_qc_rule_catch_rate(db_session: AsyncSession, seeded):
    """qc_rule_catch_rate = reviewer issues / all review_comment issues."""
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    metrics = await reviewer_metrics_service.compute_metrics(
        db_session, FAKE_REVIEWER_ID, YEAR
    )
    # 1 issue by this reviewer / 1 total review_comment issue = 1.0
    assert metrics["qc_rule_catch_rate"] == 1.0


@pytest.mark.asyncio
async def test_compute_sampled_rework_rate_no_data(db_session: AsyncSession, seeded):
    """sampled_rework_rate should be None when no QC inspections exist."""
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    metrics = await reviewer_metrics_service.compute_metrics(
        db_session, FAKE_REVIEWER_ID, YEAR
    )
    assert metrics["sampled_rework_rate"] is None


@pytest.mark.asyncio
async def test_compute_sampled_rework_rate_with_inspection(
    db_session: AsyncSession, seeded
):
    """sampled_rework_rate = failed inspections / total inspections for reviewer's WPs."""
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    wp = seeded["wp"]

    # Create a QC inspection with items
    inspection = QcInspection(
        id=uuid.uuid4(),
        project_id=FAKE_PROJECT_ID,
        strategy="random",
        reviewer_id=uuid.uuid4(),  # QC reviewer (different from WP reviewer)
        status="completed",
    )
    db_session.add(inspection)
    await db_session.flush()

    # Item 1: pass
    item1 = QcInspectionItem(
        id=uuid.uuid4(),
        inspection_id=inspection.id,
        wp_id=wp.id,
        status="completed",
        qc_verdict="pass",
        created_at=datetime(YEAR, 5, 1),
    )
    # Item 2: fail (rework needed)
    item2 = QcInspectionItem(
        id=uuid.uuid4(),
        inspection_id=inspection.id,
        wp_id=wp.id,
        status="completed",
        qc_verdict="fail",
        created_at=datetime(YEAR, 5, 2),
    )
    db_session.add_all([item1, item2])
    await db_session.flush()

    metrics = await reviewer_metrics_service.compute_metrics(
        db_session, FAKE_REVIEWER_ID, YEAR
    )
    # 1 fail / 2 total = 0.5
    assert metrics["sampled_rework_rate"] == 0.5


@pytest.mark.asyncio
async def test_compute_all_reviewers(db_session: AsyncSession, seeded):
    """compute_all_reviewers should persist snapshots for all reviewers."""
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    count = await reviewer_metrics_service.compute_all_reviewers(db_session, YEAR)
    assert count == 1  # Only FAKE_REVIEWER_ID has records

    # Verify snapshot was persisted
    from sqlalchemy import select

    stmt = select(ReviewerMetricsSnapshot).where(
        ReviewerMetricsSnapshot.reviewer_id == FAKE_REVIEWER_ID
    )
    result = await db_session.execute(stmt)
    snapshot = result.scalar_one_or_none()
    assert snapshot is not None
    assert snapshot.year == YEAR
    assert snapshot.avg_review_time_min == 45.0


@pytest.mark.asyncio
async def test_get_metrics(db_session: AsyncSession, seeded):
    """get_metrics should return stored snapshots."""
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    # First compute and persist
    await reviewer_metrics_service.compute_all_reviewers(db_session, YEAR)
    await db_session.commit()

    # Then query
    results = await reviewer_metrics_service.get_metrics(
        db_session, reviewer_id=FAKE_REVIEWER_ID, year=YEAR
    )
    assert len(results) == 1
    assert results[0]["reviewer_id"] == str(FAKE_REVIEWER_ID)
    assert results[0]["year"] == YEAR
    assert results[0]["avg_review_time_min"] == 45.0


@pytest.mark.asyncio
async def test_no_data_returns_none(db_session: AsyncSession, seeded):
    """Metrics should return None for a reviewer with no records."""
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    metrics = await reviewer_metrics_service.compute_metrics(
        db_session, FAKE_REVIEWER_ID_2, YEAR
    )
    assert metrics["avg_review_time_min"] is None
    assert metrics["avg_comments_per_wp"] is None
    assert metrics["rejection_rate"] is None
    assert metrics["qc_rule_catch_rate"] is None
    assert metrics["sampled_rework_rate"] is None
