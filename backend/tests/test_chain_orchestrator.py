"""Tests for ChainOrchestrator — step dependency, mutex, execution history

Validates: Requirements 1.1-1.9, 9.1-9.4, 15.1-15.3
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.chain_execution import ChainExecution
from app.services.chain_orchestrator import (
    ChainConflictError,
    ChainOrchestrator,
    ChainStep,
    DEPENDENCIES,
    STEP_ORDER,
    StepStatus,
    _memory_locks,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite async session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()
    # Clean up memory locks
    _memory_locks.clear()


@pytest.fixture
def orchestrator():
    return ChainOrchestrator()


# ---------------------------------------------------------------------------
# Test: Step dependency auto-supplement (Property 1)
# ---------------------------------------------------------------------------


class TestStepDependencyResolution:
    """Property 1: 步骤依赖自动补充"""

    def test_none_returns_all_steps(self, orchestrator):
        """steps=None should return all 4 steps in order."""
        result = orchestrator._resolve_steps(None)
        assert result == list(STEP_ORDER)

    def test_single_step_no_deps(self, orchestrator):
        """recalc_tb has no dependencies, should return just itself."""
        result = orchestrator._resolve_steps([ChainStep.RECALC_TB])
        assert result == [ChainStep.RECALC_TB]

    def test_generate_notes_adds_reports(self, orchestrator):
        """Requesting generate_notes should auto-add generate_reports (and recalc_tb)."""
        result = orchestrator._resolve_steps([ChainStep.GENERATE_NOTES])
        assert ChainStep.GENERATE_REPORTS in result
        assert ChainStep.RECALC_TB in result
        assert ChainStep.GENERATE_NOTES in result

    def test_generate_reports_adds_recalc(self, orchestrator):
        """Requesting generate_reports should auto-add recalc_tb."""
        result = orchestrator._resolve_steps([ChainStep.GENERATE_REPORTS])
        assert ChainStep.RECALC_TB in result
        assert ChainStep.GENERATE_REPORTS in result

    def test_generate_workpapers_adds_recalc(self, orchestrator):
        """Requesting generate_workpapers should auto-add recalc_tb."""
        result = orchestrator._resolve_steps([ChainStep.GENERATE_WORKPAPERS])
        assert ChainStep.RECALC_TB in result
        assert ChainStep.GENERATE_WORKPAPERS in result

    def test_order_preserved(self, orchestrator):
        """Resolved steps should always be in STEP_ORDER."""
        result = orchestrator._resolve_steps([ChainStep.GENERATE_NOTES, ChainStep.GENERATE_WORKPAPERS])
        # Should include all 4 steps (notes→reports→recalc, workpapers→recalc)
        assert len(result) == 4
        # Verify order
        for i in range(len(result) - 1):
            assert STEP_ORDER.index(result[i]) < STEP_ORDER.index(result[i + 1])

    def test_duplicate_steps_deduplicated(self, orchestrator):
        """Duplicate steps in input should be deduplicated."""
        result = orchestrator._resolve_steps([ChainStep.RECALC_TB, ChainStep.RECALC_TB])
        assert result == [ChainStep.RECALC_TB]


# ---------------------------------------------------------------------------
# Test: Mutex lock (Property 2)
# ---------------------------------------------------------------------------


class TestMutexLock:
    """Property 2: 互斥锁保证单一执行"""

    @pytest.mark.asyncio
    async def test_lock_acquire_release(self, db_session, orchestrator):
        """Should acquire and release lock successfully."""
        pid = uuid4()
        acquired = await orchestrator._try_acquire_lock(db_session, pid, 2025)
        assert acquired is True
        await orchestrator._release_lock(db_session, pid, 2025)

    @pytest.mark.asyncio
    async def test_lock_conflict(self, db_session, orchestrator):
        """Second acquire on same key should fail."""
        pid = uuid4()
        acquired1 = await orchestrator._try_acquire_lock(db_session, pid, 2025)
        assert acquired1 is True

        acquired2 = await orchestrator._try_acquire_lock(db_session, pid, 2025)
        assert acquired2 is False

        await orchestrator._release_lock(db_session, pid, 2025)

    @pytest.mark.asyncio
    async def test_different_projects_no_conflict(self, db_session, orchestrator):
        """Different projects should not conflict."""
        pid1 = uuid4()
        pid2 = uuid4()

        acquired1 = await orchestrator._try_acquire_lock(db_session, pid1, 2025)
        acquired2 = await orchestrator._try_acquire_lock(db_session, pid2, 2025)

        assert acquired1 is True
        assert acquired2 is True

        await orchestrator._release_lock(db_session, pid1, 2025)
        await orchestrator._release_lock(db_session, pid2, 2025)

    @pytest.mark.asyncio
    async def test_different_years_no_conflict(self, db_session, orchestrator):
        """Same project different years should not conflict."""
        pid = uuid4()

        acquired1 = await orchestrator._try_acquire_lock(db_session, pid, 2024)
        acquired2 = await orchestrator._try_acquire_lock(db_session, pid, 2025)

        assert acquired1 is True
        assert acquired2 is True

        await orchestrator._release_lock(db_session, pid, 2024)
        await orchestrator._release_lock(db_session, pid, 2025)


# ---------------------------------------------------------------------------
# Test: Execution history
# ---------------------------------------------------------------------------


class TestExecutionHistory:
    """Requirements: 9.1-9.4"""

    @pytest.mark.asyncio
    async def test_get_empty_history(self, db_session, orchestrator):
        """Empty project should return empty list."""
        pid = uuid4()
        history = await orchestrator.get_execution_history(db_session, pid)
        assert history == []

    @pytest.mark.asyncio
    async def test_history_ordered_by_time(self, db_session):
        """History should be ordered by started_at descending."""
        pid = uuid4()

        # Insert 3 records
        for i in range(3):
            e = ChainExecution(
                id=str(uuid4()),
                project_id=str(pid),
                year=2025,
                status="completed",
                steps={},
                trigger_type="manual",
                started_at=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
            )
            db_session.add(e)
        await db_session.flush()

        orchestrator = ChainOrchestrator()
        history = await orchestrator.get_execution_history(db_session, pid)
        assert len(history) == 3
        # Most recent first (compare as strings for SQLite tz compat)
        for i in range(len(history) - 1):
            assert str(history[i].started_at) >= str(history[i + 1].started_at)

    @pytest.mark.asyncio
    async def test_history_filter_by_status(self, db_session):
        """Should filter by status."""
        pid = uuid4()

        for status in ["completed", "failed", "completed"]:
            e = ChainExecution(
                id=str(uuid4()),
                project_id=str(pid),
                year=2025,
                status=status,
                steps={},
                trigger_type="manual",
                started_at=datetime.now(timezone.utc),
            )
            db_session.add(e)
        await db_session.flush()

        orchestrator = ChainOrchestrator()
        history = await orchestrator.get_execution_history(db_session, pid, status="failed")
        assert len(history) == 1
        assert history[0].status == "failed"

    @pytest.mark.asyncio
    async def test_history_limit(self, db_session):
        """Should respect limit parameter."""
        pid = uuid4()

        for i in range(5):
            e = ChainExecution(
                id=str(uuid4()),
                project_id=str(pid),
                year=2025,
                status="completed",
                steps={},
                trigger_type="manual",
                started_at=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
            )
            db_session.add(e)
        await db_session.flush()

        orchestrator = ChainOrchestrator()
        history = await orchestrator.get_execution_history(db_session, pid, limit=3)
        assert len(history) == 3


# ---------------------------------------------------------------------------
# Test: ChainExecution model
# ---------------------------------------------------------------------------


class TestChainExecutionModel:
    """Test the ORM model."""

    @pytest.mark.asyncio
    async def test_create_execution(self, db_session):
        """Should create and persist a ChainExecution."""
        e = ChainExecution(
            id=str(uuid4()),
            project_id=str(uuid4()),
            year=2025,
            status="pending",
            steps={"recalc_tb": {"status": "pending"}},
            trigger_type="manual",
            started_at=datetime.now(timezone.utc),
        )
        db_session.add(e)
        await db_session.flush()

        assert e.id is not None
        assert e.status == "pending"
        assert e.steps == {"recalc_tb": {"status": "pending"}}
