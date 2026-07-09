"""H2 在建工程 — 利息资本化引擎 Property-Based Tests (hypothesis).

Spec: .kiro/specs/h2-construction-in-progress/ Task 7.2
Validates: Requirements 10.4, 10.5

测试利息资本化2分支纯函数：
- 无专门借款：加权资本化率 + 累计支出加权平均 + 资本化金额
- 有专门借款：专门借款资本化 + 一般借款补充 + 合计
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.wp_render_strategies._h2_interest_cap_engine import (
    calc_weighted_cap_rate,
    calc_weighted_expenditure,
    calc_cap_amount_no_borrow,
    calc_special_loan_cap,
    calc_general_loan_supp,
    calc_total_cap_with_borrow,
)


# ─── 加权资本化率 ────────────────────────────────────────────────────────────


class TestWeightedCapRatePBT:
    """**Validates: Requirements 10.4** — 加权资本化率公式正确性."""

    @settings(max_examples=5)
    @given(
        loans=st.lists(
            st.fixed_dictionaries({
                "principal": st.floats(min_value=1e4, max_value=1e9, allow_nan=False, allow_infinity=False),
                "rate": st.floats(min_value=0.01, max_value=0.2, allow_nan=False, allow_infinity=False),
                "days": st.integers(min_value=1, max_value=365),
            }),
            min_size=1,
            max_size=10,
        ),
    )
    def test_weighted_cap_rate_formula(self, loans):
        """加权资本化率 = Σ(principal×rate×days/365) / Σ(principal×days/365)."""
        result = calc_weighted_cap_rate(loans)
        # 手动计算期望
        numerator = sum(l["principal"] * l["days"] / 365 * l["rate"] for l in loans)
        denominator = sum(l["principal"] * l["days"] / 365 for l in loans)
        expected = numerator / denominator if denominator != 0 else 0.0
        assert abs(result - expected) < 1e-10

    @settings(max_examples=5)
    @given(
        principal=st.floats(min_value=1e4, max_value=1e9, allow_nan=False, allow_infinity=False),
        rate=st.floats(min_value=0.01, max_value=0.2, allow_nan=False, allow_infinity=False),
        days=st.integers(min_value=1, max_value=365),
    )
    def test_single_loan_rate_equals_loan_rate(self, principal, rate, days):
        """单笔借款时加权资本化率 = 该笔借款利率."""
        loans = [{"principal": principal, "rate": rate, "days": days}]
        result = calc_weighted_cap_rate(loans)
        assert abs(result - rate) < 1e-10

    def test_empty_loans_returns_zero(self):
        """无借款时加权资本化率为0."""
        assert calc_weighted_cap_rate([]) == 0.0


# ─── 累计支出加权平均数 ──────────────────────────────────────────────────────


class TestWeightedExpenditurePBT:
    """**Validates: Requirements 10.4** — 累计支出加权平均数公式."""

    @settings(max_examples=5)
    @given(
        expenditures=st.lists(
            st.fixed_dictionaries({
                "amount": st.floats(min_value=1, max_value=1e8, allow_nan=False, allow_infinity=False),
                "days": st.integers(min_value=1, max_value=365),
            }),
            min_size=1,
            max_size=12,
        ),
        total_days=st.integers(min_value=1, max_value=365),
    )
    def test_weighted_expenditure_formula(self, expenditures, total_days):
        """累计支出加权平均数 = Σ(amount×days/total_days)."""
        result = calc_weighted_expenditure(expenditures, total_days)
        expected = sum(e["amount"] * e["days"] / total_days for e in expenditures)
        # 使用相对误差容忍大数值浮点偏差
        if abs(expected) > 1:
            assert abs(result - expected) / abs(expected) < 1e-10
        else:
            assert abs(result - expected) < 1e-6

    def test_zero_total_days_returns_zero(self):
        """资本化期间为0时返回0."""
        result = calc_weighted_expenditure([{"amount": 1000000, "days": 180}], 0)
        assert result == 0.0


# ─── 无专门借款资本化金额 ────────────────────────────────────────────────────


class TestCapAmountNoBorrowPBT:
    """**Validates: Requirements 10.4** — 无专门借款资本化金额."""

    @settings(max_examples=5)
    @given(
        weighted_exp=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        cap_rate=st.floats(min_value=0.01, max_value=0.2, allow_nan=False, allow_infinity=False),
    )
    def test_cap_amount_equals_product(self, weighted_exp, cap_rate):
        """无专门借款资本化金额 = 累计支出加权平均 × 加权资本化率."""
        result = calc_cap_amount_no_borrow(weighted_exp, cap_rate)
        expected = weighted_exp * cap_rate
        assert abs(result - expected) < 1e-6


# ─── 专门借款资本化 ──────────────────────────────────────────────────────────


class TestSpecialLoanCapPBT:
    """**Validates: Requirements 10.5** — 专门借款资本化公式."""

    @settings(max_examples=5)
    @given(
        interest=st.floats(min_value=1, max_value=1e8, allow_nan=False, allow_infinity=False),
        idle_income=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    def test_special_loan_cap_formula(self, interest, idle_income):
        """专门借款资本化 = 利息 - 闲置收益."""
        result = calc_special_loan_cap(interest, idle_income)
        expected = interest - idle_income
        assert abs(result - expected) < 1e-6


# ─── 一般借款补充资本化 ──────────────────────────────────────────────────────


class TestGeneralLoanSuppPBT:
    """**Validates: Requirements 10.5** — 一般借款补充资本化."""

    @settings(max_examples=5)
    @given(
        excess=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        rate=st.floats(min_value=0.01, max_value=0.2, allow_nan=False, allow_infinity=False),
    )
    def test_general_supp_formula(self, excess, rate):
        """一般借款补充 = 超出额 × 一般借款加权资本化率."""
        result = calc_general_loan_supp(excess, rate)
        if excess <= 0:
            assert result == 0.0
        else:
            expected = excess * rate
            assert abs(result - expected) < 1e-6

    @settings(max_examples=5)
    @given(
        rate=st.floats(min_value=0.01, max_value=0.2, allow_nan=False, allow_infinity=False),
    )
    def test_negative_excess_returns_zero(self, rate):
        """超出额<=0时返回0."""
        result = calc_general_loan_supp(-100.0, rate)
        assert result == 0.0


# ─── 有专门借款合计资本化 ────────────────────────────────────────────────────


class TestTotalCapWithBorrowPBT:
    """**Validates: Requirements 10.5** — 有专门借款合计 = 专门 + 一般补充."""

    @settings(max_examples=5)
    @given(
        special_cap=st.floats(min_value=0.0, max_value=1e8, allow_nan=False, allow_infinity=False),
        general_supp=st.floats(min_value=0.0, max_value=1e8, allow_nan=False, allow_infinity=False),
    )
    def test_total_cap_with_borrow_sum(self, special_cap, general_supp):
        """有专门借款合计 = 专门借款资本化 + 一般借款补充."""
        result = calc_total_cap_with_borrow(special_cap, general_supp)
        expected = special_cap + general_supp
        assert abs(result - expected) < 1e-6
