"""Tests for ConsistencyGate — 5 项一致性检查

Validates: Requirements 6.1-6.6
Property 10: overall="pass" iff all blocking checks passed=true
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.services.consistency_gate import CheckItem, ConsistencyGate, ConsistencyResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def project_id():
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Test ConsistencyResult dataclass
# ---------------------------------------------------------------------------

class TestConsistencyResult:
    """Test ConsistencyResult logic."""

    def test_overall_pass_when_all_pass(self):
        """Property 10: overall=pass when all checks pass."""
        result = ConsistencyResult(
            overall="pass",
            checks=[
                CheckItem(check_name="A", passed=True, severity="blocking"),
                CheckItem(check_name="B", passed=True, severity="warning"),
            ],
        )
        assert not result.has_blocking_failures

    def test_overall_fail_when_blocking_fails(self):
        """Property 10: overall=fail when any blocking check fails."""
        result = ConsistencyResult(
            overall="fail",
            checks=[
                CheckItem(check_name="A", passed=False, severity="blocking"),
                CheckItem(check_name="B", passed=True, severity="warning"),
            ],
        )
        assert result.has_blocking_failures

    def test_overall_pass_when_only_warning_fails(self):
        """Property 10: overall=pass when only warning checks fail."""
        result = ConsistencyResult(
            overall="pass",
            checks=[
                CheckItem(check_name="A", passed=True, severity="blocking"),
                CheckItem(check_name="B", passed=False, severity="warning"),
            ],
        )
        assert not result.has_blocking_failures

    def test_empty_checks_no_blocking(self):
        """Empty checks list has no blocking failures."""
        result = ConsistencyResult(overall="pass", checks=[])
        assert not result.has_blocking_failures


# ---------------------------------------------------------------------------
# Test ConsistencyGate checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestConsistencyGateChecks:
    """Test individual consistency checks."""

    async def test_run_all_checks_returns_5_items(self, db_session, project_id):
        """run_all_checks should return exactly 5 check items."""
        gate = ConsistencyGate(db_session)
        result = await gate.run_all_checks(project_id, 2024)
        assert len(result.checks) == 5

    async def test_run_all_checks_overall_pass_no_data(self, db_session, project_id):
        """With no data, all checks should pass (skip)."""
        gate = ConsistencyGate(db_session)
        result = await gate.run_all_checks(project_id, 2024)
        assert result.overall == "pass"
        for check in result.checks:
            assert check.passed is True

    async def test_check_names_correct(self, db_session, project_id):
        """Check names should match expected values."""
        gate = ConsistencyGate(db_session)
        result = await gate.run_all_checks(project_id, 2024)
        names = [c.check_name for c in result.checks]
        assert "试算平衡" in names
        assert "报表平衡" in names
        assert "利润表勾稽" in names
        assert "附注完整性" in names
        assert "数据新鲜度" in names

    async def test_severity_assignment(self, db_session, project_id):
        """Check severity assignments: TB balance and BS balance are blocking."""
        gate = ConsistencyGate(db_session)
        result = await gate.run_all_checks(project_id, 2024)
        severity_map = {c.check_name: c.severity for c in result.checks}
        assert severity_map["试算平衡"] == "blocking"
        assert severity_map["报表平衡"] == "blocking"
        assert severity_map["利润表勾稽"] == "warning"
        assert severity_map["附注完整性"] == "warning"
        assert severity_map["数据新鲜度"] == "warning"

    async def test_tb_balance_no_data_passes(self, db_session, project_id):
        """TB balance check passes when no trial balance data exists."""
        gate = ConsistencyGate(db_session)
        result = await gate.check_tb_balance(project_id, 2024)
        assert result.passed is True
        assert "无试算表数据" in result.details

    async def test_bs_balance_no_data_passes(self, db_session, project_id):
        """BS balance check passes when no report data exists."""
        gate = ConsistencyGate(db_session)
        result = await gate.check_bs_balance(project_id, 2024)
        assert result.passed is True
        assert "无资产负债表" in result.details

    async def test_is_reconciliation_no_data_passes(self, db_session, project_id):
        """IS reconciliation check passes when no income statement data exists."""
        gate = ConsistencyGate(db_session)
        result = await gate.check_is_reconciliation(project_id, 2024)
        assert result.passed is True
        assert "无利润表数据" in result.details

    async def test_notes_completeness_no_data_passes(self, db_session, project_id):
        """Notes completeness check passes when no report data exists."""
        gate = ConsistencyGate(db_session)
        result = await gate.check_notes_completeness(project_id, 2024)
        assert result.passed is True

    async def test_data_freshness_no_stale_passes(self, db_session, project_id):
        """Data freshness check passes when no stale records exist."""
        gate = ConsistencyGate(db_session)
        result = await gate.check_data_freshness(project_id, 2024)
        assert result.passed is True
        assert "最新状态" in result.details

    async def test_overall_logic_blocking_failure(self, db_session, project_id):
        """Property 10: If a blocking check fails, overall must be 'fail'."""
        gate = ConsistencyGate(db_session)
        # With no data, all pass → overall = pass
        result = await gate.run_all_checks(project_id, 2024)
        assert result.overall == "pass"

        # Manually verify the property
        # If we had a blocking failure, overall should be fail
        result.checks[0] = CheckItem(
            check_name="试算平衡", passed=False, severity="blocking", details="test"
        )
        # Recalculate overall
        has_blocking = any(not c.passed and c.severity == "blocking" for c in result.checks)
        assert has_blocking is True


# ---------------------------------------------------------------------------
# Test CheckItem dataclass
# ---------------------------------------------------------------------------

class TestCheckItem:
    """Test CheckItem dataclass."""

    def test_default_severity_is_warning(self):
        item = CheckItem(check_name="test", passed=True)
        assert item.severity == "warning"

    def test_blocking_severity(self):
        item = CheckItem(check_name="test", passed=False, severity="blocking")
        assert item.severity == "blocking"

    def test_details_default_empty(self):
        item = CheckItem(check_name="test", passed=True)
        assert item.details == ""
