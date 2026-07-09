"""H8 使用权资产 — 服务层纯函数 PBT 测试.

Spec: .kiro/specs/h8-right-of-use-assets/ Task 5.3
Validates: Requirements 10.1-10.4, 11.1-11.4

使用 hypothesis PBT 验证 CAS21 计量引擎纯函数逻辑：
- P4: 初始计量 = lease_liability + direct_cost - incentive
- P5: 折旧期 = min(lease_term, useful_life)
- P6: 终止损益 = liability_balance - rou_net_value
- P7: 短期租赁判断 (≤12月)
- P8: 低价值租赁判断 (≤40000元)
- 重新计量 = old_rou + adjustment
- 简化处理综合判断
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.h8_right_of_use_assets_service import (
    calc_initial_measurement,
    calc_depreciation_period,
    calc_termination_gain_loss,
    calc_remeasurement,
    is_short_term_lease,
    is_low_value_lease,
    check_simplified_eligibility,
    SHORT_TERM_THRESHOLD_MONTHS,
    LOW_VALUE_THRESHOLD_DEFAULT,
    LINKAGE_TOLERANCE,
    H8RightOfUseAssetsService,
)


# ═══════════════════════════════════════════════════════════════════════════════
# P4: CAS21初始计量公式
# Validates: Requirements 10.1
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcInitialMeasurement:
    """CAS21初始计量：H8 = H9初始 + 直接费用 - 激励"""

    @given(
        lease_liability=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
        direct_cost=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
        incentive=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=5)
    def test_initial_measurement_formula(
        self, lease_liability: float, direct_cost: float, incentive: float
    ):
        """**Validates: Requirements 10.1**

        ∀ ll, dc, inc: calcInitialMeasurement(ll, dc, inc) == ll + dc - inc
        """
        result = calc_initial_measurement(lease_liability, direct_cost, incentive)
        expected = lease_liability + direct_cost - incentive
        assert result == pytest.approx(expected, abs=1e-10)

    def test_initial_measurement_zero_incentive(self):
        """无激励时：H8 = H9 + 直接费用"""
        assert calc_initial_measurement(100000, 5000, 0) == 105000

    def test_initial_measurement_all_zero(self):
        """全零输入"""
        assert calc_initial_measurement(0, 0, 0) == 0

    def test_static_method_delegation(self):
        """类静态方法委托给模块级函数"""
        svc = H8RightOfUseAssetsService()
        assert svc.calc_initial_measurement(100, 20, 5) == 115


# ═══════════════════════════════════════════════════════════════════════════════
# P5: 折旧期 = min(租赁期, 使用寿命)
# Validates: Requirements 10.2
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcDepreciationPeriod:
    """折旧期确定：min(租赁期, 使用寿命)"""

    @given(
        lease_term=st.integers(min_value=1, max_value=600),
        useful_life=st.integers(min_value=1, max_value=600),
    )
    @settings(max_examples=5)
    def test_depreciation_period_is_min(self, lease_term: int, useful_life: int):
        """**Validates: Requirements 10.2**

        ∀ lt, ul: calcDepreciationPeriod(lt, ul) == min(lt, ul)
        """
        result = calc_depreciation_period(lease_term, useful_life)
        assert result == min(lease_term, useful_life)

    def test_lease_term_shorter(self):
        """租赁期短于使用寿命"""
        assert calc_depreciation_period(36, 120) == 36

    def test_useful_life_shorter(self):
        """使用寿命短于租赁期"""
        assert calc_depreciation_period(120, 60) == 60

    def test_equal_term_and_life(self):
        """租赁期等于使用寿命"""
        assert calc_depreciation_period(60, 60) == 60


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 终止损益
# Validates: Requirements 10.3
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcTerminationGainLoss:
    """终止损益 = 租赁负债余额 - 使用权资产净值"""

    @given(
        liability_balance=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
        rou_net_value=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=5)
    def test_termination_gain_loss_formula(
        self, liability_balance: float, rou_net_value: float
    ):
        """**Validates: Requirements 10.3**

        ∀ lb, nv: calcTerminationGainLoss(lb, nv) == lb - nv
        """
        result = calc_termination_gain_loss(liability_balance, rou_net_value)
        expected = liability_balance - rou_net_value
        assert result == pytest.approx(expected, abs=1e-10)

    def test_gain_when_liability_greater(self):
        """负债>资产=收益"""
        assert calc_termination_gain_loss(100000, 80000) == 20000

    def test_loss_when_asset_greater(self):
        """资产>负债=损失"""
        assert calc_termination_gain_loss(80000, 100000) == -20000

    def test_zero_when_equal(self):
        """相等=无损益"""
        assert calc_termination_gain_loss(50000, 50000) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 重新计量
# Validates: Requirements 10.4
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcRemeasurement:
    """重新计量后ROU = 原值 + 调整"""

    @given(
        old_rou=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
        adjustment=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=5)
    def test_remeasurement_formula(self, old_rou: float, adjustment: float):
        """**Validates: Requirements 10.4**

        ∀ old, adj: calcRemeasurement(old, adj) == old + adj
        """
        result = calc_remeasurement(old_rou, adjustment)
        expected = old_rou + adjustment
        assert result == pytest.approx(expected, abs=1e-10)

    def test_positive_adjustment(self):
        """正向调整增加"""
        assert calc_remeasurement(100000, 20000) == 120000

    def test_negative_adjustment(self):
        """负向调整减少"""
        assert calc_remeasurement(100000, -30000) == 70000


# ═══════════════════════════════════════════════════════════════════════════════
# P7: 短期租赁判断
# Validates: Requirements 8.2
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsShortTermLease:
    """短期租赁：≤12个月"""

    @given(term_months=st.integers(min_value=1, max_value=36))
    @settings(max_examples=5)
    def test_short_term_boundary(self, term_months: int):
        """**Validates: Requirements 8.2**

        ∀ m: isShortTermLease(m) == (m <= 12)
        """
        result = is_short_term_lease(term_months)
        assert result == (term_months <= SHORT_TERM_THRESHOLD_MONTHS)

    def test_exactly_12_months(self):
        """12月=短期"""
        assert is_short_term_lease(12) is True

    def test_13_months_not_short(self):
        """13月≠短期"""
        assert is_short_term_lease(13) is False

    def test_1_month_short(self):
        """1月=短期"""
        assert is_short_term_lease(1) is True


# ═══════════════════════════════════════════════════════════════════════════════
# P8: 低价值租赁判断
# Validates: Requirements 8.2
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsLowValueLease:
    """低价值租赁：全新价值 ≤ 40000元"""

    @given(new_asset_value=st.floats(min_value=1, max_value=100000, allow_nan=False, allow_infinity=False))
    @settings(max_examples=5)
    def test_low_value_boundary(self, new_asset_value: float):
        """**Validates: Requirements 8.2**

        ∀ v: isLowValueLease(v) == (v <= 40000)
        """
        result = is_low_value_lease(new_asset_value)
        assert result == (new_asset_value <= LOW_VALUE_THRESHOLD_DEFAULT)

    def test_exactly_40000(self):
        """40000元=低价值"""
        assert is_low_value_lease(40000) is True

    def test_40001_not_low(self):
        """40001元≠低价值"""
        assert is_low_value_lease(40001) is False

    def test_custom_threshold(self):
        """自定义阈值"""
        assert is_low_value_lease(50000, threshold=60000) is True
        assert is_low_value_lease(70000, threshold=60000) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 简化处理综合判断
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckSimplifiedEligibility:
    """简化处理资格综合判断"""

    def test_short_term_only(self):
        """仅满足短期"""
        result = check_simplified_eligibility(10, 80000)
        assert result["eligible"] is True
        assert result["is_short_term"] is True
        assert result["is_low_value"] is False

    def test_low_value_only(self):
        """仅满足低价值"""
        result = check_simplified_eligibility(24, 30000)
        assert result["eligible"] is True
        assert result["is_short_term"] is False
        assert result["is_low_value"] is True

    def test_both_eligible(self):
        """同时满足"""
        result = check_simplified_eligibility(6, 20000)
        assert result["eligible"] is True
        assert result["is_short_term"] is True
        assert result["is_low_value"] is True
        assert "短期+低价值" in result["reason"]

    def test_neither_eligible(self):
        """都不满足"""
        result = check_simplified_eligibility(24, 80000)
        assert result["eligible"] is False
        assert "不符合简化条件" in result["reason"]
