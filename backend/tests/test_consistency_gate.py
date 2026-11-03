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
                CheckItem(status="passed", check_name="A", passed=True, severity="blocking"),
                CheckItem(status="passed", check_name="B", passed=True, severity="warning"),
            ],
        )
        assert not result.has_blocking_failures

    def test_overall_fail_when_blocking_fails(self):
        """Property 10: overall=fail when any blocking check fails."""
        result = ConsistencyResult(
            overall="fail",
            checks=[
                CheckItem(status="failed", check_name="A", passed=False, severity="blocking"),
                CheckItem(status="passed", check_name="B", passed=True, severity="warning"),
            ],
        )
        assert result.has_blocking_failures

    def test_overall_pass_when_only_warning_fails(self):
        """Property 10: overall=pass when only warning checks fail."""
        result = ConsistencyResult(
            overall="pass",
            checks=[
                CheckItem(status="passed", check_name="A", passed=True, severity="blocking"),
                CheckItem(status="failed", check_name="B", passed=False, severity="warning"),
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
        """run_all_checks should return at least 5 base check items + E1 + D4."""
        gate = ConsistencyGate(db_session)
        result = await gate.run_all_checks(project_id, 2024)
        # 5 base + 3 E1↔CFS + 4 D4 勾稽 = 12
        assert len(result.checks) >= 5

    async def test_run_all_checks_no_data_not_executed(self, db_session, project_id):
        """无数据：检查项是「未执行」而不是「通过」（spec formula-hub-integrity-closure 需求 16.2；原断言「全部 passed」
        固化的正是 F29 缺陷）。阻断级未执行 ⇒ overall 不是 pass；但 has_blocking_failures 仍只看「失败」，
        observe 下的阻断结果与改造前相同（需求 16.4）。"""
        gate = ConsistencyGate(db_session)
        result = await gate.run_all_checks(project_id, 2024)
        statuses = {c.check_name: c.status for c in result.checks}
        assert set(statuses.values()) <= {"passed", "not_executed"}, statuses
        assert statuses["试算平衡"] == "not_executed"
        for check in result.checks:
            if check.status == "not_executed":
                assert check.passed is False and check.reason and check.branch_id, check
        assert result.overall == "fail"
        assert result.has_blocking_failures is False
        assert result.would_block_when_enforced is True

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

    async def test_tb_balance_no_data_not_executed(self, db_session, project_id):
        """无试算表数据 ⇒ 未执行（原因写在 reason，分支编号稳定）。"""
        gate = ConsistencyGate(db_session)
        result = await gate.check_tb_balance(project_id, 2024)
        assert (result.status, result.passed, result.branch_id) == ("not_executed", False, "tb_balance.1.missing")
        assert "无试算表数据" in result.reason

    async def test_bs_balance_no_data_not_executed(self, db_session, project_id):
        """无资产负债表合计行 ⇒ 未执行。"""
        gate = ConsistencyGate(db_session)
        result = await gate.check_bs_balance(project_id, 2024)
        assert (result.status, result.passed, result.branch_id) == ("not_executed", False, "bs_balance.1.missing")
        assert "无资产负债表" in result.reason

    async def test_is_reconciliation_no_data_not_executed(self, db_session, project_id):
        """无利润表数据 ⇒ 未执行。"""
        gate = ConsistencyGate(db_session)
        result = await gate.check_is_reconciliation(project_id, 2024)
        assert (result.status, result.passed, result.branch_id) == (
            "not_executed", False, "is_reconciliation.1.missing")
        assert "无利润表数据" in result.reason

    async def test_notes_completeness_no_data_not_executed(self, db_session, project_id):
        """无有数据的报表行次 ⇒ 未执行。"""
        gate = ConsistencyGate(db_session)
        result = await gate.check_notes_completeness(project_id, 2024)
        assert (result.status, result.passed, result.branch_id) == (
            "not_executed", False, "notes_completeness.1.missing")

    async def test_notes_completeness_report_without_notes_fails_with_reason(self, db_session, project_id):
        """有数据的报表行次、附注未生成 ⇒ 失败且写明原因（五态改造曾把这句原因丢成空串，界面只剩「未通过」）。"""
        from app.models.report_models import FinancialReport, FinancialReportType

        db_session.add(FinancialReport(
            project_id=project_id, year=2024, report_type=FinancialReportType.balance_sheet,
            row_code="BS-002", row_name="货币资金", current_period_amount=Decimal("100.00"),
        ))
        await db_session.flush()
        gate = ConsistencyGate(db_session)
        result = await gate.check_notes_completeness(project_id, 2024)
        assert (result.status, result.passed) == ("failed", False)
        assert result.reason == result.details == "报表有 1 个有数据行次，但附注尚未生成"

    async def test_data_freshness_no_stale_passes(self, db_session, project_id):
        """Data freshness check passes when no stale records exist."""
        gate = ConsistencyGate(db_session)
        result = await gate.check_data_freshness(project_id, 2024)
        assert result.passed is True
        assert "最新状态" in result.details

    async def test_overall_logic_blocking_failure(self, db_session, project_id):
        """Property 10: If a blocking check fails, overall must be 'fail'."""
        gate = ConsistencyGate(db_session)
        # 无数据：阻断级检查未执行（不是通过）⇒ overall = fail（需求 16.2 / 16.5：不显示「通过」）
        result = await gate.run_all_checks(project_id, 2024)
        assert result.overall == "fail"

        # Manually verify the property
        # If we had a blocking failure, overall should be fail
        result.checks[0] = CheckItem(
            status="failed", check_name="试算平衡", passed=False, severity="blocking", details="test"
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
        item = CheckItem(status="passed", check_name="test", passed=True)
        assert item.severity == "warning"

    def test_blocking_severity(self):
        item = CheckItem(status="failed", check_name="test", passed=False, severity="blocking")
        assert item.severity == "blocking"

    def test_details_default_empty(self):
        item = CheckItem(status="passed", check_name="test", passed=True)
        assert item.details == ""
