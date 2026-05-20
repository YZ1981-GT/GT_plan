"""DashboardAggregatorService 服务层单元测试

Validates: Requirements 2.2, 3.1, 4.2, 7.2, 9.5

测试覆盖：
- calc_progress_rate: 正常值 / total=0 / trimmed=total / completed > total-trimmed (clamp)
- sort_reviews: 多层级混合排序 / 同层级时间排序 / 空列表
- _aggregate_cycle_progress: 11 循环全覆盖 / 部分循环无数据
- _aggregate_vr_summary: 全通过 / 部分 blocking / ConsistencyGate 异常降级
- _aggregate_open_reviews: 有数据 / 无数据（空列表）/ summary 截断 80 字符
- _aggregate_timeline: 各阶段推断逻辑
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dashboard_aggregator_service import (
    CYCLES,
    CYCLE_NAMES,
    LAYER_PRIORITY,
    DashboardAggregatorService,
    calc_progress_rate,
    sort_reviews,
)


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------


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
# Tests: calc_progress_rate (pure function)
# ===========================================================================


class TestCalcProgressRate:
    """测试 calc_progress_rate 纯函数。

    Validates: Requirements 2.2
    """

    def test_normal_values(self):
        """正常值：total=10, completed=5, trimmed=2 → 62.5%"""
        result = calc_progress_rate(10, 5, 2)
        assert result == pytest.approx(62.5)

    def test_all_completed(self):
        """全部完成：completed == total - trimmed → 100.0%"""
        result = calc_progress_rate(10, 8, 2)
        assert result == 100.0

    def test_none_completed(self):
        """无完成：completed=0 → 0.0%"""
        result = calc_progress_rate(10, 0, 2)
        assert result == 0.0

    def test_total_zero(self):
        """total=0 → denominator <= 0 → 100.0%"""
        result = calc_progress_rate(0, 0, 0)
        assert result == 100.0

    def test_trimmed_equals_total(self):
        """trimmed=total → denominator=0 → 100.0%（全部裁剪视为完成）"""
        result = calc_progress_rate(10, 0, 10)
        assert result == 100.0

    def test_trimmed_greater_than_total(self):
        """trimmed > total → denominator < 0 → 100.0%"""
        result = calc_progress_rate(5, 0, 8)
        assert result == 100.0

    def test_completed_greater_than_denominator_clamp(self):
        """completed > (total - trimmed) → rate > 100 → clamp to 100.0"""
        # total=10, trimmed=5, denominator=5, completed=8 → 160% → clamp 100.0
        result = calc_progress_rate(10, 8, 5)
        assert result == 100.0

    def test_half_completed(self):
        """50% 完成率"""
        result = calc_progress_rate(20, 10, 0)
        assert result == pytest.approx(50.0)

    def test_large_numbers(self):
        """大数值正常计算"""
        result = calc_progress_rate(1000, 750, 0)
        assert result == pytest.approx(75.0)

    def test_one_procedure(self):
        """单个程序完成"""
        result = calc_progress_rate(1, 1, 0)
        assert result == 100.0

    def test_one_procedure_not_completed(self):
        """单个程序未完成"""
        result = calc_progress_rate(1, 0, 0)
        assert result == 0.0


# ===========================================================================
# Tests: sort_reviews (pure function)
# ===========================================================================


class TestSortReviews:
    """测试 sort_reviews 纯函数。

    Validates: Requirements 4.2
    """

    def test_multi_layer_mixed_sort(self):
        """多层级混合排序：L5 > L4 > L3 > L2 > L1"""
        items = [
            {"review_layer": "L1", "created_at": "2026-05-20T10:00:00"},
            {"review_layer": "L5", "created_at": "2026-05-20T09:00:00"},
            {"review_layer": "L3", "created_at": "2026-05-20T11:00:00"},
            {"review_layer": "L4", "created_at": "2026-05-20T08:00:00"},
            {"review_layer": "L2", "created_at": "2026-05-20T12:00:00"},
        ]
        result = sort_reviews(items)
        layers = [item["review_layer"] for item in result]
        assert layers == ["L5", "L4", "L3", "L2", "L1"]

    def test_same_layer_time_descending(self):
        """同层级内按创建时间降序排列"""
        items = [
            {"review_layer": "L3", "created_at": "2026-05-18T10:00:00"},
            {"review_layer": "L3", "created_at": "2026-05-20T10:00:00"},
            {"review_layer": "L3", "created_at": "2026-05-19T10:00:00"},
        ]
        result = sort_reviews(items)
        times = [item["created_at"] for item in result]
        assert times == [
            "2026-05-20T10:00:00",
            "2026-05-19T10:00:00",
            "2026-05-18T10:00:00",
        ]

    def test_empty_list(self):
        """空列表返回空列表"""
        result = sort_reviews([])
        assert result == []

    def test_single_item(self):
        """单个元素列表"""
        items = [{"review_layer": "L4", "created_at": "2026-05-20T10:00:00"}]
        result = sort_reviews(items)
        assert len(result) == 1
        assert result[0]["review_layer"] == "L4"

    def test_mixed_layers_and_times(self):
        """混合层级 + 同层级时间排序"""
        items = [
            {"review_layer": "L4", "created_at": "2026-05-18T10:00:00"},
            {"review_layer": "L5", "created_at": "2026-05-17T10:00:00"},
            {"review_layer": "L4", "created_at": "2026-05-20T10:00:00"},
            {"review_layer": "L5", "created_at": "2026-05-19T10:00:00"},
        ]
        result = sort_reviews(items)
        # L5 first (higher priority), then L4
        assert result[0]["review_layer"] == "L5"
        assert result[0]["created_at"] == "2026-05-19T10:00:00"
        assert result[1]["review_layer"] == "L5"
        assert result[1]["created_at"] == "2026-05-17T10:00:00"
        assert result[2]["review_layer"] == "L4"
        assert result[2]["created_at"] == "2026-05-20T10:00:00"
        assert result[3]["review_layer"] == "L4"
        assert result[3]["created_at"] == "2026-05-18T10:00:00"

    def test_unknown_layer_sorted_last(self):
        """未知层级（不在 LAYER_PRIORITY 中）排在最后"""
        items = [
            {"review_layer": "L1", "created_at": "2026-05-20T10:00:00"},
            {"review_layer": "unknown", "created_at": "2026-05-20T10:00:00"},
            {"review_layer": "L5", "created_at": "2026-05-20T10:00:00"},
        ]
        result = sort_reviews(items)
        layers = [item["review_layer"] for item in result]
        assert layers == ["L5", "L1", "unknown"]


# ===========================================================================
# Tests: _aggregate_cycle_progress
# ===========================================================================


class TestAggregateCycleProgress:
    """测试 _aggregate_cycle_progress 方法。

    Validates: Requirements 2.2, 9.5
    """

    @pytest.mark.asyncio
    async def test_all_11_cycles_covered(self, mock_db, service):
        """11 循环全覆盖 — 返回 D~N 所有循环的进度数据。"""
        # Mock db.execute to return a row for each cycle query
        mock_row = MagicMock()
        mock_row.total = 10
        mock_row.completed = 5
        mock_row.trimmed = 2

        mock_result = MagicMock()
        mock_result.one.return_value = mock_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await service._aggregate_cycle_progress(project_id)

        assert len(result) == 11
        cycle_codes = [item["cycle"] for item in result]
        assert cycle_codes == CYCLES

        # Verify each item has correct structure
        for item in result:
            assert item["cycle"] in CYCLES
            assert item["cycle_name"] == CYCLE_NAMES[item["cycle"]]
            assert item["total_procedures"] == 10
            assert item["completed_procedures"] == 5
            assert item["trimmed_procedures"] == 2
            assert item["progress_rate"] == pytest.approx(62.5)

    @pytest.mark.asyncio
    async def test_partial_cycles_no_data(self, mock_db, service):
        """部分循环无数据 — total=0 时 progress_rate=100.0。"""
        # First 3 cycles have data, rest have 0
        call_count = 0

        async def _mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            mock_row = MagicMock()
            if call_count <= 3:
                mock_row.total = 10
                mock_row.completed = 5
                mock_row.trimmed = 0
            else:
                mock_row.total = 0
                mock_row.completed = 0
                mock_row.trimmed = 0
            mock_result = MagicMock()
            mock_result.one.return_value = mock_row
            return mock_result

        mock_db.execute = _mock_execute

        project_id = uuid.uuid4()
        result = await service._aggregate_cycle_progress(project_id)

        assert len(result) == 11
        # First 3 cycles: 50%
        for item in result[:3]:
            assert item["progress_rate"] == pytest.approx(50.0)
        # Remaining cycles: total=0 → 100.0%
        for item in result[3:]:
            assert item["progress_rate"] == 100.0
            assert item["total_procedures"] == 0

    @pytest.mark.asyncio
    async def test_cycle_names_correct(self, mock_db, service):
        """验证循环名称映射正确。"""
        mock_row = MagicMock()
        mock_row.total = 5
        mock_row.completed = 3
        mock_row.trimmed = 0

        mock_result = MagicMock()
        mock_result.one.return_value = mock_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await service._aggregate_cycle_progress(project_id)

        # Verify specific cycle names
        cycle_name_map = {item["cycle"]: item["cycle_name"] for item in result}
        assert cycle_name_map["D"] == "销售收入"
        assert cycle_name_map["E"] == "货币资金"
        assert cycle_name_map["F"] == "采购存货"
        assert cycle_name_map["N"] == "税费"


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
        ) as MockGate:
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
        ) as MockGate:
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
        ) as MockGate:
            gate_instance = MockGate.return_value
            gate_instance.run_all_checks = AsyncMock(
                side_effect=RuntimeError("ConsistencyGate timeout")
            )

            project_id = uuid.uuid4()
            with pytest.raises(RuntimeError, match="ConsistencyGate timeout"):
                await service._aggregate_vr_summary(project_id, mock_project)

    @pytest.mark.asyncio
    async def test_project_without_audit_period_end(self, mock_db, service):
        """project.audit_period_end 为 None 时使用当前年份。"""
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
        ) as MockGate:
            gate_instance = MockGate.return_value
            gate_instance.run_all_checks = AsyncMock(return_value=mock_result)

            project_id = uuid.uuid4()
            result = await service._aggregate_vr_summary(project_id, mock_project)

        assert result["total_rules"] == 1
        assert result["all_passed"] is True
        # Verify run_all_checks was called with current year
        call_args = gate_instance.run_all_checks.call_args
        assert call_args[0][1] == datetime.now().year


# ===========================================================================
# Tests: _aggregate_open_reviews
# ===========================================================================


class TestAggregateOpenReviews:
    """测试 _aggregate_open_reviews 方法。

    Validates: Requirements 4.2, 9.5
    """

    @pytest.mark.asyncio
    async def test_with_data(self, mock_db, service):
        """有数据 — 正确返回 total, by_layer, items。"""
        # Create mock review records
        mock_rec1 = MagicMock()
        mock_rec1.id = uuid.uuid4()
        mock_rec1.review_layer = "L5"
        mock_rec1.comment_text = "需要补充审计证据"
        mock_rec1.created_at = datetime(2026, 5, 20, 10, 0, 0)
        mock_rec1.working_paper_id = uuid.uuid4()
        mock_rec1.target_sheet = "审定表"
        mock_rec1.target_cell = "B5"
        mock_rec1.cell_reference = None

        mock_rec2 = MagicMock()
        mock_rec2.id = uuid.uuid4()
        mock_rec2.review_layer = "L4"
        mock_rec2.comment_text = "金额核对有差异"
        mock_rec2.created_at = datetime(2026, 5, 19, 10, 0, 0)
        mock_rec2.working_paper_id = uuid.uuid4()
        mock_rec2.target_sheet = "明细表"
        mock_rec2.target_cell = None
        mock_rec2.cell_reference = "C10"

        # Mock the first query (review records)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_rec1, mock_rec2]
        mock_result1 = MagicMock()
        mock_result1.scalars.return_value = mock_scalars

        # Mock the second query (wp_code lookup)
        mock_result2 = MagicMock()
        mock_result2.all.return_value = [
            (mock_rec1.working_paper_id, "D4-1"),
            (mock_rec2.working_paper_id, "F2-1"),
        ]

        call_count = 0

        async def _mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result1
            return mock_result2

        mock_db.execute = _mock_execute

        project_id = uuid.uuid4()
        result = await service._aggregate_open_reviews(project_id)

        assert result["total"] == 2
        assert result["by_layer"] == {"L5": 1, "L4": 1}
        assert len(result["items"]) == 2
        # Sorted: L5 first (higher priority)
        assert result["items"][0]["review_layer"] == "L5"
        assert result["items"][1]["review_layer"] == "L4"

    @pytest.mark.asyncio
    async def test_no_data_empty_list(self, mock_db, service):
        """无数据 — 返回 total=0, items=[]。"""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await service._aggregate_open_reviews(project_id)

        assert result["total"] == 0
        assert result["by_layer"] == {}
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_summary_truncated_80_chars(self, mock_db, service):
        """summary 截断 80 字符 — 超过 80 字符的 comment_text 被截断。"""
        long_text = "A" * 200  # 200 characters

        mock_rec = MagicMock()
        mock_rec.id = uuid.uuid4()
        mock_rec.review_layer = "L3"
        mock_rec.comment_text = long_text
        mock_rec.created_at = datetime(2026, 5, 20, 10, 0, 0)
        mock_rec.working_paper_id = uuid.uuid4()
        mock_rec.target_sheet = "审定表"
        mock_rec.target_cell = "A1"
        mock_rec.cell_reference = None

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_rec]
        mock_result1 = MagicMock()
        mock_result1.scalars.return_value = mock_scalars

        mock_result2 = MagicMock()
        mock_result2.all.return_value = [
            (mock_rec.working_paper_id, "D4-1"),
        ]

        call_count = 0

        async def _mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result1
            return mock_result2

        mock_db.execute = _mock_execute

        project_id = uuid.uuid4()
        result = await service._aggregate_open_reviews(project_id)

        assert len(result["items"]) == 1
        assert len(result["items"][0]["summary"]) == 80
        assert result["items"][0]["summary"] == "A" * 80

    @pytest.mark.asyncio
    async def test_summary_exactly_80_chars(self, mock_db, service):
        """summary 恰好 80 字符 — 不截断。"""
        text_80 = "B" * 80

        mock_rec = MagicMock()
        mock_rec.id = uuid.uuid4()
        mock_rec.review_layer = "L2"
        mock_rec.comment_text = text_80
        mock_rec.created_at = datetime(2026, 5, 20, 10, 0, 0)
        mock_rec.working_paper_id = uuid.uuid4()
        mock_rec.target_sheet = "审定表"
        mock_rec.target_cell = "A1"
        mock_rec.cell_reference = None

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_rec]
        mock_result1 = MagicMock()
        mock_result1.scalars.return_value = mock_scalars

        mock_result2 = MagicMock()
        mock_result2.all.return_value = [
            (mock_rec.working_paper_id, "E1-1"),
        ]

        call_count = 0

        async def _mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result1
            return mock_result2

        mock_db.execute = _mock_execute

        project_id = uuid.uuid4()
        result = await service._aggregate_open_reviews(project_id)

        assert len(result["items"][0]["summary"]) == 80

    @pytest.mark.asyncio
    async def test_summary_short_text_not_truncated(self, mock_db, service):
        """summary 短文本 — 不截断。"""
        short_text = "短文本"

        mock_rec = MagicMock()
        mock_rec.id = uuid.uuid4()
        mock_rec.review_layer = "L1"
        mock_rec.comment_text = short_text
        mock_rec.created_at = datetime(2026, 5, 20, 10, 0, 0)
        mock_rec.working_paper_id = uuid.uuid4()
        mock_rec.target_sheet = "审定表"
        mock_rec.target_cell = "A1"
        mock_rec.cell_reference = None

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_rec]
        mock_result1 = MagicMock()
        mock_result1.scalars.return_value = mock_scalars

        mock_result2 = MagicMock()
        mock_result2.all.return_value = [
            (mock_rec.working_paper_id, "D4-1"),
        ]

        call_count = 0

        async def _mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result1
            return mock_result2

        mock_db.execute = _mock_execute

        project_id = uuid.uuid4()
        result = await service._aggregate_open_reviews(project_id)

        assert result["items"][0]["summary"] == "短文本"


# ===========================================================================
# Tests: _aggregate_timeline
# ===========================================================================


class TestAggregateTimeline:
    """测试 _aggregate_timeline 方法。

    Validates: Requirements 7.2, 9.5
    """

    @pytest.mark.asyncio
    async def test_planning_stage(self, mock_db, service):
        """项目处于 planning 阶段。"""
        mock_project = MagicMock()
        mock_project.status = MagicMock()
        mock_project.status.value = "planning"

        # Mock audit log query (empty)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await service._aggregate_timeline(project_id, mock_project)

        assert result["current_stage"] == "planning"
        assert len(result["stages"]) == 4
        assert result["stages"][0]["name"] == "planning"
        assert result["stages"][0]["status"] == "current"
        assert result["stages"][1]["status"] == "pending"
        assert result["stages"][2]["status"] == "pending"
        assert result["stages"][3]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_execution_stage(self, mock_db, service):
        """项目处于 execution 阶段 — planning 已完成。"""
        mock_project = MagicMock()
        mock_project.status = MagicMock()
        mock_project.status.value = "in_progress"

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await service._aggregate_timeline(project_id, mock_project)

        assert result["current_stage"] == "execution"
        assert result["stages"][0]["name"] == "planning"
        assert result["stages"][0]["status"] == "completed"
        assert result["stages"][1]["name"] == "execution"
        assert result["stages"][1]["status"] == "current"
        assert result["stages"][2]["status"] == "pending"
        assert result["stages"][3]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_review_stage(self, mock_db, service):
        """项目处于 review 阶段 — planning + execution 已完成。"""
        mock_project = MagicMock()
        mock_project.status = MagicMock()
        mock_project.status.value = "under_review"

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await service._aggregate_timeline(project_id, mock_project)

        assert result["current_stage"] == "review"
        assert result["stages"][0]["status"] == "completed"
        assert result["stages"][1]["status"] == "completed"
        assert result["stages"][2]["name"] == "review"
        assert result["stages"][2]["status"] == "current"
        assert result["stages"][3]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_reporting_stage(self, mock_db, service):
        """项目处于 reporting 阶段 — 前三阶段已完成。"""
        mock_project = MagicMock()
        mock_project.status = MagicMock()
        mock_project.status.value = "completed"

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await service._aggregate_timeline(project_id, mock_project)

        assert result["current_stage"] == "reporting"
        assert result["stages"][0]["status"] == "completed"
        assert result["stages"][1]["status"] == "completed"
        assert result["stages"][2]["status"] == "completed"
        assert result["stages"][3]["name"] == "reporting"
        assert result["stages"][3]["status"] == "current"

    @pytest.mark.asyncio
    async def test_created_status_maps_to_planning(self, mock_db, service):
        """created 状态映射到 planning 阶段。"""
        mock_project = MagicMock()
        mock_project.status = MagicMock()
        mock_project.status.value = "created"

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await service._aggregate_timeline(project_id, mock_project)

        assert result["current_stage"] == "planning"

    @pytest.mark.asyncio
    async def test_unknown_status_defaults_to_planning(self, mock_db, service):
        """未知状态默认映射到 planning。"""
        mock_project = MagicMock()
        mock_project.status = MagicMock()
        mock_project.status.value = "unknown_status"

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await service._aggregate_timeline(project_id, mock_project)

        assert result["current_stage"] == "planning"

    @pytest.mark.asyncio
    async def test_stages_always_four(self, mock_db, service):
        """始终返回 4 个阶段。"""
        mock_project = MagicMock()
        mock_project.status = MagicMock()
        mock_project.status.value = "execution"

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await service._aggregate_timeline(project_id, mock_project)

        assert len(result["stages"]) == 4
        stage_names = [s["name"] for s in result["stages"]]
        assert stage_names == ["planning", "execution", "review", "reporting"]

    @pytest.mark.asyncio
    async def test_stage_timestamps_from_audit_log(self, mock_db, service):
        """从 audit_log 获取阶段时间戳。"""
        mock_project = MagicMock()
        mock_project.status = MagicMock()
        mock_project.status.value = "in_progress"

        # Mock audit log entry
        mock_entry = MagicMock()
        mock_entry.payload = {"new_status": "planning"}
        mock_entry.ts = datetime(2026, 1, 15, 10, 0, 0)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_entry]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await service._aggregate_timeline(project_id, mock_project)

        # Planning stage should have entered_at from audit log
        planning_stage = result["stages"][0]
        assert planning_stage["entered_at"] == "2026-01-15T10:00:00"
