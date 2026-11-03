"""DashboardAggregatorService._aggregate_vr_summary 单元测试（自 test_dashboard_aggregator_service.py 拆出）

Validates: Requirements 3.1, 9.5
拆出原因：原文件 HEAD 已 841 行、超行数门 800 且未登记；本次随 spec formula-hub-integrity-closure 任务 39（项目审计年度
改由 fetch_project_audit_year 统一解析、去掉日历年兜底）改这一节，按行数门「先抽伴生模块」拆到本文件，不扩白名单。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dashboard_aggregator_service import DashboardAggregatorService


@pytest.fixture
def mock_db():
    """Create a mock AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def service(mock_db):
    """Create a DashboardAggregatorService with mock db."""
    return DashboardAggregatorService(mock_db)

# ===========================================================================
# Tests: _aggregate_vr_summary
# ===========================================================================


@dataclass
class _MockCheckItem:
    """Mock CheckItem for testing."""
    check_name: str
    passed: bool
    details: str = ""
    severity: str = "warning"


@dataclass
class _MockConsistencyResult:
    """Mock ConsistencyResult for testing."""
    overall: str = "pass"
    checks: list = field(default_factory=list)


def _audit_year(mock_project):
    """项目审计年度改由 ``fetch_project_audit_year`` 统一解析（spec formula-hub-integrity-closure 任务 39：去掉日历年兜底）。

    mock_db 不能真跑 SQL ⇒ 在被调模块上替换它，按夹具的 ``audit_period_end`` 给出年度（为空 ⇒ None）。
    """
    end = mock_project.audit_period_end
    return patch(
        "app.services.project_audit_year.fetch_project_audit_year",
        new=AsyncMock(return_value=end.year if end else None),
    )


class TestAggregateVRSummary:
    """测试 _aggregate_vr_summary 方法。

    Validates: Requirements 3.1, 9.5
    """

    @pytest.mark.asyncio
    async def test_all_passed(self, mock_db, service):
        """全通过 — blocking_failed=0, all_passed=True。"""
        mock_result = _MockConsistencyResult(
            overall="pass",
            checks=[
                _MockCheckItem(check_name="d4_revenue_reconciliation", passed=True, severity="blocking"),
                _MockCheckItem(check_name="f5_triangle", passed=True, severity="blocking"),
                _MockCheckItem(check_name="tb_balance", passed=True, severity="warning"),
            ],
        )

        # Mock project with audit_period_end
        mock_project = MagicMock()
        mock_project.audit_period_end = date(2025, 12, 31)

        with patch(
            "app.services.dashboard_aggregator_service.ConsistencyGate"
        ) as MockGate, _audit_year(mock_project):
            gate_instance = MockGate.return_value
            gate_instance.run_all_checks = AsyncMock(return_value=mock_result)

            project_id = uuid.uuid4()
            result = await service._aggregate_vr_summary(project_id, mock_project)

        assert result["total_rules"] == 3
        assert result["blocking_failed"] == 0
        assert result["all_passed"] is True
        assert result["by_cycle"] == []

    @pytest.mark.asyncio
    async def test_partial_blocking(self, mock_db, service):
        """部分 blocking 未通过 — 正确统计 blocking_failed 和 by_cycle。"""
        mock_result = _MockConsistencyResult(
            overall="fail",
            checks=[
                _MockCheckItem(check_name="d4_revenue_reconciliation", passed=False, severity="blocking", details="mismatch"),
                _MockCheckItem(check_name="d4_revenue_completeness", passed=False, severity="blocking", details="incomplete"),
                _MockCheckItem(check_name="f5_triangle", passed=True, severity="blocking"),
                _MockCheckItem(check_name="h1_fixed_asset", passed=False, severity="blocking", details="gap"),
                _MockCheckItem(check_name="tb_balance", passed=False, severity="warning"),  # warning, not blocking
            ],
        )

        mock_project = MagicMock()
        mock_project.audit_period_end = date(2025, 12, 31)

        with patch(
            "app.services.dashboard_aggregator_service.ConsistencyGate"
        ) as MockGate, _audit_year(mock_project):
            gate_instance = MockGate.return_value
            gate_instance.run_all_checks = AsyncMock(return_value=mock_result)

            project_id = uuid.uuid4()
            result = await service._aggregate_vr_summary(project_id, mock_project)

        assert result["total_rules"] == 5
        assert result["blocking_failed"] == 3  # 2 D + 1 H
        assert result["all_passed"] is False

        # Verify by_cycle grouping
        by_cycle_map = {item["cycle"]: item for item in result["by_cycle"]}
        assert "D" in by_cycle_map
        assert by_cycle_map["D"]["blocking_failed"] == 2
        assert len(by_cycle_map["D"]["failed_rules"]) == 2
        assert "H" in by_cycle_map
        assert by_cycle_map["H"]["blocking_failed"] == 1

    @pytest.mark.asyncio
    async def test_consistency_gate_exception_propagates(self, mock_db, service):
        """ConsistencyGate 异常 — 异常向上传播（由 _safe_call 捕获降级）。"""
        mock_project = MagicMock()
        mock_project.audit_period_end = date(2025, 12, 31)

        with patch(
            "app.services.dashboard_aggregator_service.ConsistencyGate"
        ) as MockGate, _audit_year(mock_project):
            gate_instance = MockGate.return_value
            gate_instance.run_all_checks = AsyncMock(
                side_effect=RuntimeError("ConsistencyGate timeout")
            )

            project_id = uuid.uuid4()
            with pytest.raises(RuntimeError, match="ConsistencyGate timeout"):
                await service._aggregate_vr_summary(project_id, mock_project)

    @pytest.mark.asyncio
    async def test_project_without_audit_period_end(self, mock_db, service):
        """项目解析不出审计年度时不跑一致性检查、返回 unavailable（原先按当前日历年跑 —— 年度兜底已去掉，
        spec formula-hub-integrity-closure 任务 39 / 年度棘轮）。"""
        mock_result = _MockConsistencyResult(
            overall="pass",
            checks=[
                _MockCheckItem(check_name="tb_balance", passed=True, severity="blocking"),
            ],
        )

        mock_project = MagicMock()
        mock_project.audit_period_end = None

        with patch(
            "app.services.dashboard_aggregator_service.ConsistencyGate"
        ) as MockGate, _audit_year(mock_project):
            gate_instance = MockGate.return_value
            gate_instance.run_all_checks = AsyncMock(return_value=mock_result)

            project_id = uuid.uuid4()
            result = await service._aggregate_vr_summary(project_id, mock_project)

        # 第 2 轮 D-3：无年度分支补 all_passed=False（缺它时看板响应模型校验失败、整个看板 500，见
        # formula_hub/test_consistency_display_snapshots.py）与五态计数（全 0）/ 非通过项（空）
        assert result == {
            "unavailable": True,
            "reason": "项目未设置审计年度，未运行一致性检查",
            "total_rules": 0,
            "blocking_failed": 0,
            "all_passed": False,
            "by_cycle": [],
            "status_counts": {"passed": 0, "failed": 0, "not_executed": 0, "not_applicable": 0, "error": 0},
            "not_passed_checks": [],
        }
        # 不按日历年兜底：一致性检查根本没跑
        gate_instance.run_all_checks.assert_not_awaited()
