"""Tests for QC Annual Report Service — Round 3 需求 9

Tests:
1. generate_annual_report creates a job and generates report
2. Idempotent lock: second call for same year returns existing job
3. list_annual_reports returns paginated results
4. get_report_download_url returns file info for completed job
5. _build_report_data gathers all chapter data
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.base import ProjectStatus
from app.models.core import Project, User
from app.models.phase13_models import ExportJob, ExportJobStatus
from app.models.phase15_models import IssueTicket
from app.models.qc_inspection_models import QcInspection
from app.models.qc_rating_models import ProjectQualityRating, ReviewerMetricsSnapshot
from app.services.qc_annual_report_service import (
    ANNUAL_REPORT_DIR,
    QcAnnualReportService,
    qc_annual_report_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    """Create an in-memory SQLite async engine for testing."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine):
    """Create a test database session."""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def test_user(db: AsyncSession):
    """Create a test user."""
    user = User(
        id=uuid.uuid4(),
        username="qc_admin",
        email="qc@test.com",
        hashed_password="hashed",
        role="qc",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def test_project(db: AsyncSession, test_user: User):
    """Create a test project."""
    project = Project(
        id=uuid.uuid4(),
        name="Test Project 2025",
        client_name="Test Client",
        status=ProjectStatus.execution,
        audit_period_start=date(2025, 1, 1),
        audit_period_end=date(2025, 12, 31),
        created_by=test_user.id,
    )
    db.add(project)
    await db.flush()
    return project


@pytest_asyncio.fixture
async def test_rating(db: AsyncSession, test_project: Project):
    """Create a test quality rating."""
    rating = ProjectQualityRating(
        id=uuid.uuid4(),
        project_id=test_project.id,
        year=2025,
        rating="B",
        score=78,
        dimensions={"qc_pass_rate": 85, "review_depth": 72},
        computed_at=datetime.now(timezone.utc),
        computed_by_rule_version=1,
    )
    db.add(rating)
    await db.flush()
    return rating


@pytest_asyncio.fixture
async def test_issue(db: AsyncSession, test_project: Project, test_user: User):
    """Create a test issue ticket."""
    issue = IssueTicket(
        id=uuid.uuid4(),
        project_id=test_project.id,
        source="Q",
        severity="major",
        category="data_mismatch",
        title="现金流量表补充资料不平衡",
        description="差异超过 100 元",
        owner_id=test_user.id,
        trace_id=str(uuid.uuid4()),
        created_at=datetime(2025, 6, 15),
    )
    db.add(issue)
    await db.flush()
    return issue


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateAnnualReport:
    """Test generate_annual_report method."""

    @pytest.mark.asyncio
    async def test_creates_job_and_generates_report(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        """Should create an export job and generate a report file."""
        svc = QcAnnualReportService()
        result = await svc.generate_annual_report(db, year=2025, user_id=test_user.id)

        assert result["job_id"] is not None
        assert result["status"] == ExportJobStatus.succeeded.value
        assert result["year"] == 2025
        assert "已启动" in result["message"]

        # Verify job exists in DB
        job_stmt = select(ExportJob).where(ExportJob.id == uuid.UUID(result["job_id"]))
        job_result = await db.execute(job_stmt)
        job = job_result.scalar_one()
        assert job.job_type == "qc_annual_report"
        assert job.payload["year"] == 2025
        assert job.status == ExportJobStatus.succeeded.value

    @pytest.mark.asyncio
    async def test_idempotent_lock_returns_existing_job(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        """Second call for same year should return existing running job."""
        svc = QcAnnualReportService()

        # First call
        result1 = await svc.generate_annual_report(db, year=2025, user_id=test_user.id)
        job_id_1 = result1["job_id"]

        # Manually set job back to running to simulate in-progress
        job_stmt = select(ExportJob).where(ExportJob.id == uuid.UUID(job_id_1))
        job_result = await db.execute(job_stmt)
        job = job_result.scalar_one()
        job.status = ExportJobStatus.running.value
        await db.flush()

        # Second call should return same job
        result2 = await svc.generate_annual_report(db, year=2025, user_id=test_user.id)
        assert result2["job_id"] == job_id_1
        assert "已在运行中" in result2["message"]

    @pytest.mark.asyncio
    async def test_different_year_creates_new_job(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        """Different year should create a new job."""
        svc = QcAnnualReportService()

        result1 = await svc.generate_annual_report(db, year=2025, user_id=test_user.id)
        result2 = await svc.generate_annual_report(db, year=2024, user_id=test_user.id)

        assert result1["job_id"] != result2["job_id"]

    @pytest.mark.asyncio
    async def test_no_projects_returns_error(self, db: AsyncSession, test_user: User):
        """Should return error when no projects exist."""
        svc = QcAnnualReportService()
        result = await svc.generate_annual_report(db, year=2025, user_id=test_user.id)

        assert result["job_id"] is None
        assert result["status"] == "failed"
        assert "无项目" in result["message"]


class TestListAnnualReports:
    """Test list_annual_reports method."""

    @pytest.mark.asyncio
    async def test_returns_paginated_results(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        """Should return paginated list of annual report jobs."""
        svc = QcAnnualReportService()

        # Generate a report first
        await svc.generate_annual_report(db, year=2025, user_id=test_user.id)

        result = await svc.list_annual_reports(db, page=1, page_size=10)

        assert result["total"] >= 1
        assert result["page"] == 1
        assert result["page_size"] == 10
        assert len(result["items"]) >= 1

        item = result["items"][0]
        assert item["year"] == 2025
        assert item["status"] == ExportJobStatus.succeeded.value

    @pytest.mark.asyncio
    async def test_empty_list(self, db: AsyncSession):
        """Should return empty list when no reports exist."""
        svc = QcAnnualReportService()
        result = await svc.list_annual_reports(db)

        assert result["total"] == 0
        assert result["items"] == []


class TestGetReportDownloadUrl:
    """Test get_report_download_url method."""

    @pytest.mark.asyncio
    async def test_returns_file_info_for_completed_job(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        """Should return download info for a completed report."""
        svc = QcAnnualReportService()

        gen_result = await svc.generate_annual_report(db, year=2025, user_id=test_user.id)
        report_id = uuid.UUID(gen_result["job_id"])

        info = await svc.get_report_download_url(db, report_id)

        assert info is not None
        assert info["year"] == 2025
        assert info["status"] == ExportJobStatus.succeeded.value
        assert info["file_path"] is not None

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_report(self, db: AsyncSession):
        """Should return None for non-existent report ID."""
        svc = QcAnnualReportService()
        info = await svc.get_report_download_url(db, uuid.uuid4())
        assert info is None


class TestBuildReportData:
    """Test _build_report_data method."""

    @pytest.mark.asyncio
    async def test_gathers_all_chapter_data(
        self,
        db: AsyncSession,
        test_project: Project,
        test_rating: ProjectQualityRating,
        test_issue: IssueTicket,
    ):
        """Should gather data for all report chapters."""
        svc = QcAnnualReportService()
        data = await svc._build_report_data(db, year=2025)

        # Project scale
        assert "project_scale" in data
        assert data["project_scale"]["total_projects"] >= 1

        # Rating distribution
        assert "rating_distribution" in data
        assert data["rating_distribution"]["distribution"]["B"] >= 1

        # Top10 issues
        assert "top10_issues" in data
        assert len(data["top10_issues"]) >= 1
        assert data["top10_issues"][0]["title"] == "现金流量表补充资料不平衡"

        # Reviewer performance
        assert "reviewer_performance" in data

        # LLM suggestions (placeholder)
        assert "llm_suggestions" in data

        # Appendix
        assert "appendix" in data
        assert "inspection_count" in data["appendix"]

    @pytest.mark.asyncio
    async def test_empty_data_year(self, db: AsyncSession, test_project: Project):
        """Should handle year with no data gracefully."""
        svc = QcAnnualReportService()
        data = await svc._build_report_data(db, year=1999)

        assert data["project_scale"]["total_projects"] == 0
        assert data["rating_distribution"]["total"] == 0
        assert data["top10_issues"] == []
        assert data["reviewer_performance"] == []


class TestRenderReportText:
    """Test _render_report_text method."""

    def test_renders_all_sections(self):
        """Should render all sections in the text report."""
        svc = QcAnnualReportService()
        data = {
            "project_scale": {"total_projects": 10, "annual_count": 8, "year": 2025},
            "rating_distribution": {
                "distribution": {"A": 3, "B": 4, "C": 2, "D": 1},
                "total": 10,
            },
            "top10_issues": [
                {"title": "Issue 1", "severity": "major", "occurrence_count": 5},
            ],
            "reviewer_performance": [
                {
                    "reviewer_id": str(uuid.uuid4()),
                    "avg_review_time_min": 45.0,
                    "avg_comments_per_wp": 3.2,
                    "rejection_rate": 0.15,
                    "qc_rule_catch_rate": 0.8,
                    "sampled_rework_rate": 0.05,
                },
            ],
            "llm_suggestions": "建议加强复核深度",
            "appendix": {
                "inspection_count": 12,
                "rule_changes_note": "本年新增 3 条规则",
            },
        }

        text = svc._render_report_text(2025, data)

        assert "2025 年度审计质量报告" in text
        assert "项目规模与分布" in text
        assert "评级分布" in text
        assert "A 级：3 个" in text
        assert "典型问题 Top10" in text
        assert "Issue 1" in text
        assert "复核人表现" in text
        assert "改进建议" in text
        assert "建议加强复核深度" in text
        assert "附录" in text
        assert "12" in text  # inspection_count
