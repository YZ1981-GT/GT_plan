"""H8-H9 联动集成测试 — CAS21配对底稿一致性验证

Spec: .kiro/specs/h8-right-of-use-assets/ Task 7.2
Validates: Requirements 11.1-11.4

使用 hypothesis PBT (max_examples=5) 测试:
- P9: CAS21 linkage: H8初始 - directCost + incentive ≈ H9初始 (±1元容差)
- validate_h9_linkage 逻辑 (mock DB)
- validate_simplified_processing 逻辑 (mock DB)
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.h8_right_of_use_assets_service import (
    H8RightOfUseAssetsService,
    calc_initial_measurement,
    is_short_term_lease,
    is_low_value_lease,
    check_simplified_eligibility,
    LINKAGE_TOLERANCE,
    SHORT_TERM_THRESHOLD_MONTHS,
    LOW_VALUE_THRESHOLD_DEFAULT,
)


# ═══════════════════════════════════════════════════════════════════════════════
# P9: CAS21联动公式 PBT
# H8初始 - directCost + incentive ≈ H9初始 (±1元容差)
# Validates: Requirements 11.1-11.4
# ═══════════════════════════════════════════════════════════════════════════════


class TestCAS21LinkageFormula:
    """CAS21联动公式验证: H8初始-直接费用+激励 ≈ H9初始"""

    @given(
        h9_initial=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
        direct_cost=st.floats(min_value=0, max_value=1e7, allow_nan=False, allow_infinity=False),
        incentive=st.floats(min_value=0, max_value=1e7, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=5)
    def test_linkage_formula_consistency(
        self, h9_initial: float, direct_cost: float, incentive: float
    ):
        """**Validates: Requirements 11.1-11.4**

        CAS21: H8 = H9 + 直接费用 - 激励
        反向: H8 - 直接费用 + 激励 = H9
        差额应在±1元容差内
        """
        # 计算H8初始值
        h8_initial = calc_initial_measurement(h9_initial, direct_cost, incentive)

        # 反向推导H9: H8 - 直接费用 + 激励 应约等于 H9初始
        h9_derived = h8_initial - direct_cost + incentive

        # 验证容差
        diff = abs(h9_derived - h9_initial)
        assert diff <= LINKAGE_TOLERANCE, (
            f"联动公式不一致: H9初始={h9_initial}, "
            f"反推H9={h9_derived}, 差额={diff}"
        )

    @given(
        h9_initial=st.floats(min_value=1000, max_value=1e8, allow_nan=False, allow_infinity=False),
        direct_cost=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
        incentive=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=5)
    def test_linkage_bidirectional_identity(
        self, h9_initial: float, direct_cost: float, incentive: float
    ):
        """**Validates: Requirements 11.2**

        双向恒等: calcInitialMeasurement(h9, dc, inc) - dc + inc == h9
        """
        h8 = calc_initial_measurement(h9_initial, direct_cost, incentive)
        # H8 = H9 + dc - inc → H8 - dc + inc = H9
        h9_back = h8 - direct_cost + incentive
        assert abs(h9_back - h9_initial) < 1e-6

    def test_linkage_exact_example(self):
        """具体数值验证: 租赁负债100万, 直接费用5万, 激励2万"""
        h9 = 1_000_000.0
        dc = 50_000.0
        inc = 20_000.0

        h8 = calc_initial_measurement(h9, dc, inc)
        assert h8 == pytest.approx(1_030_000.0)

        # 反向
        h9_back = h8 - dc + inc
        assert abs(h9_back - h9) <= LINKAGE_TOLERANCE


# ═══════════════════════════════════════════════════════════════════════════════
# validate_h9_linkage 逻辑测试 (mock DB)
# Validates: Requirements 11.1-11.4
# ═══════════════════════════════════════════════════════════════════════════════


def _make_mock_row(remark: str):
    """构造 fetchone 返回的 mock row"""
    row = MagicMock()
    row.remark = remark
    return row


class TestValidateH9Linkage:
    """validate_h9_linkage — mock DB 测试"""

    @pytest.mark.asyncio
    async def test_consistent_single_contract(self):
        """单笔合同H8与H9一致"""
        svc = H8RightOfUseAssetsService()

        h8_details = [
            {"contractNo": "LC-001", "entryValue": 103000, "directCost": 5000, "incentive": 2000}
        ]
        h9_initial = [
            {"contractNo": "LC-001", "initialAmount": 100000}
        ]

        mock_db = AsyncMock()
        # 第一次调用返回 H8 明细
        # 第二次调用返回 H9 初始
        mock_result_h8 = MagicMock()
        mock_result_h8.fetchone.return_value = _make_mock_row(json.dumps(h8_details))
        mock_result_h9 = MagicMock()
        mock_result_h9.fetchone.return_value = _make_mock_row(json.dumps(h9_initial))

        mock_db.execute = AsyncMock(side_effect=[mock_result_h8, mock_result_h9])

        result = await svc.validate_h9_linkage(mock_db, "proj-1", "wp-h8-1")

        assert result["is_consistent"] is True
        assert abs(result["difference"]) <= LINKAGE_TOLERANCE
        assert "一致" in result["message"]

    @pytest.mark.asyncio
    async def test_inconsistent_single_contract(self):
        """单笔合同H8与H9不一致 (差额>1元)"""
        svc = H8RightOfUseAssetsService()

        # H8入账值105000, 直接5000, 激励2000 → H8中负债部分=105000-5000+2000=102000
        # H9初始=100000 → 差额2000
        h8_details = [
            {"contractNo": "LC-002", "entryValue": 105000, "directCost": 5000, "incentive": 2000}
        ]
        h9_initial = [
            {"contractNo": "LC-002", "initialAmount": 100000}
        ]

        mock_db = AsyncMock()
        mock_result_h8 = MagicMock()
        mock_result_h8.fetchone.return_value = _make_mock_row(json.dumps(h8_details))
        mock_result_h9 = MagicMock()
        mock_result_h9.fetchone.return_value = _make_mock_row(json.dumps(h9_initial))
        mock_db.execute = AsyncMock(side_effect=[mock_result_h8, mock_result_h9])

        result = await svc.validate_h9_linkage(mock_db, "proj-1", "wp-h8-1")

        assert result["is_consistent"] is False
        assert abs(result["difference"]) > LINKAGE_TOLERANCE
        assert "不一致" in result["message"]

    @pytest.mark.asyncio
    async def test_multiple_contracts_mixed(self):
        """多笔合同：部分一致部分不一致"""
        svc = H8RightOfUseAssetsService()

        h8_details = [
            {"contractNo": "LC-A", "entryValue": 103000, "directCost": 5000, "incentive": 2000},
            {"contractNo": "LC-B", "entryValue": 250000, "directCost": 10000, "incentive": 5000},
        ]
        h9_initial = [
            {"contractNo": "LC-A", "initialAmount": 100000},  # 一致
            {"contractNo": "LC-B", "initialAmount": 240000},  # H8-B负债部分=250000-10000+5000=245000, 差5000
        ]

        mock_db = AsyncMock()
        mock_result_h8 = MagicMock()
        mock_result_h8.fetchone.return_value = _make_mock_row(json.dumps(h8_details))
        mock_result_h9 = MagicMock()
        mock_result_h9.fetchone.return_value = _make_mock_row(json.dumps(h9_initial))
        mock_db.execute = AsyncMock(side_effect=[mock_result_h8, mock_result_h9])

        result = await svc.validate_h9_linkage(mock_db, "proj-1", "wp-h8-1")

        # 总差额=5000, 不一致
        assert result["is_consistent"] is False
        assert len(result["details"]) == 2
        # LC-A 一致
        lc_a = next(d for d in result["details"] if d["contract_no"] == "LC-A")
        assert lc_a["is_consistent"] is True
        # LC-B 不一致
        lc_b = next(d for d in result["details"] if d["contract_no"] == "LC-B")
        assert lc_b["is_consistent"] is False

    @pytest.mark.asyncio
    async def test_empty_h8_details(self):
        """H8明细为空时"""
        svc = H8RightOfUseAssetsService()

        mock_db = AsyncMock()
        mock_result_h8 = MagicMock()
        mock_result_h8.fetchone.return_value = _make_mock_row("[]")
        mock_result_h9 = MagicMock()
        mock_result_h9.fetchone.return_value = _make_mock_row("[]")
        mock_db.execute = AsyncMock(side_effect=[mock_result_h8, mock_result_h9])

        result = await svc.validate_h9_linkage(mock_db, "proj-1", "wp-h8-1")

        assert result["is_consistent"] is True
        assert result["difference"] == 0

    @pytest.mark.asyncio
    async def test_h9_data_not_found(self):
        """H9数据不存在时"""
        svc = H8RightOfUseAssetsService()

        h8_details = [
            {"contractNo": "LC-X", "entryValue": 103000, "directCost": 5000, "incentive": 2000}
        ]

        mock_db = AsyncMock()
        mock_result_h8 = MagicMock()
        mock_result_h8.fetchone.return_value = _make_mock_row(json.dumps(h8_details))
        # H9 返回 None (底稿未创建)
        mock_result_h9 = MagicMock()
        mock_result_h9.fetchone.return_value = None
        mock_db.execute = AsyncMock(side_effect=[mock_result_h8, mock_result_h9])

        result = await svc.validate_h9_linkage(mock_db, "proj-1", "wp-h8-1")

        # H8有数据但H9没有 → 不一致
        assert result["is_consistent"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# validate_simplified_processing 逻辑测试 (mock DB)
# Validates: Requirements 8.1-8.4
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateSimplifiedProcessing:
    """validate_simplified_processing — mock DB 测试"""

    @pytest.mark.asyncio
    async def test_all_eligible(self):
        """全部符合简化条件"""
        svc = H8RightOfUseAssetsService()

        rows = [
            {"contractNo": "S-1", "termMonths": 6, "newAssetValue": 20000, "annualRent": 5000},
            {"contractNo": "S-2", "termMonths": 10, "newAssetValue": 35000, "annualRent": 8000},
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = _make_mock_row(json.dumps(rows))
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await svc.validate_simplified_processing(mock_db, "wp-h8-1")

        assert result["total_count"] == 2
        assert result["eligible_count"] == 2
        assert result["ineligible_count"] == 0
        assert result["total_annual_rent"] == pytest.approx(13000)

    @pytest.mark.asyncio
    async def test_some_ineligible(self):
        """部分不符合简化条件"""
        svc = H8RightOfUseAssetsService()

        rows = [
            {"contractNo": "S-A", "termMonths": 6, "newAssetValue": 20000, "annualRent": 5000},  # 短期✓
            {"contractNo": "S-B", "termMonths": 24, "newAssetValue": 80000, "annualRent": 40000},  # 都不满足✗
            {"contractNo": "S-C", "termMonths": 18, "newAssetValue": 30000, "annualRent": 12000},  # 低价值✓
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = _make_mock_row(json.dumps(rows))
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await svc.validate_simplified_processing(mock_db, "wp-h8-1")

        assert result["total_count"] == 3
        assert result["eligible_count"] == 2
        assert result["ineligible_count"] == 1
        assert len(result["ineligible_items"]) == 1
        assert result["ineligible_items"][0]["contract_no"] == "S-B"
        assert "不符合简化条件" in result["ineligible_items"][0]["reason"]

    @pytest.mark.asyncio
    async def test_empty_rows(self):
        """无简化处理行"""
        svc = H8RightOfUseAssetsService()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = _make_mock_row("[]")
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await svc.validate_simplified_processing(mock_db, "wp-h8-1")

        assert result["total_count"] == 0
        assert result["eligible_count"] == 0
        assert result["total_annual_rent"] == 0

    @given(
        term_months=st.integers(min_value=1, max_value=60),
        new_value=st.floats(min_value=1000, max_value=200000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=5)
    def test_simplified_eligibility_pbt(self, term_months: int, new_value: float):
        """**Validates: Requirements 8.2-8.3**

        PBT: check_simplified_eligibility 与独立判断结果一致
        """
        result = check_simplified_eligibility(term_months, new_value)

        expected_short = term_months <= SHORT_TERM_THRESHOLD_MONTHS
        expected_low = new_value <= LOW_VALUE_THRESHOLD_DEFAULT
        expected_eligible = expected_short or expected_low

        assert result["is_short_term"] == expected_short
        assert result["is_low_value"] == expected_low
        assert result["eligible"] == expected_eligible
