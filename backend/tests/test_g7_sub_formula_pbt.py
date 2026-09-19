"""G7 长期股权投资(子公司组) 公式引擎属性测试 (hypothesis PBT)

Properties:
- P1: calcSameControlCost(netAssets, ratio) == netAssets × ratio
- P2: calcNotSameControlCost(price, fees) == price（fees费用化）
- P3: calcGoodwill(cost, share) == cost - share; 正=商誉, 负=营业外收入
- P4: calcCostMethodIncome(dividend, ratio) == dividend × ratio
- P5: calcSubsequentBalance(opening, addition, impairment) == opening + addition - impairment
- P6: calcDisposalGain(price, bookValue, dividend, oci) == price - bookValue - dividend + oci
- P7: isDebitCreditBalanced(debits, credits) ↔ |sum(debits)-sum(credits)| < 0.01
- P8: parseNum(None/''/'abc'/NaN) == 0; parseNum(finite_number) == finite_number

**Validates: Requirements 3.3, 3.4, 4.2, 4.3, 5.3, 6.2, 7.1**

Tag: Feature: g7-long-term-equity-subsidiary
"""
from __future__ import annotations

import sys

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, "backend")

from app.routers.wp_render_strategies._g7_long_term_equity_subsidiary_service import (
    G7SubsidiaryService,
)

# ─── 共用策略 ─────────────────────────────────────────────────────────────────

finite_floats = st.floats(allow_nan=False, allow_infinity=False)
positive_floats = st.floats(min_value=0, max_value=1e12, allow_nan=False, allow_infinity=False)
ratio_floats = st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False)

svc = G7SubsidiaryService()


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1: 同一控制下企业合并初始投资成本 = 净资产 × 持股比例
# Tag: Feature: g7-long-term-equity-subsidiary, Property 1
# **Validates: Requirements 3.3**
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1SameControlCost:
    """Property 1: calcSameControlCost(netAssets, ratio) == netAssets × ratio."""

    @given(net_assets=finite_floats, ratio=finite_floats)
    @settings(max_examples=5)
    def test_same_control_cost_equals_product(self, net_assets: float, ratio: float):
        result = svc.calc_same_control_cost(net_assets, ratio)
        expected = net_assets * ratio
        assert result == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Property 2: 非同一控制下企业合并初始投资成本 = 合并对价公允价值
# Tag: Feature: g7-long-term-equity-subsidiary, Property 2
# **Validates: Requirements 3.4**
# ═══════════════════════════════════════════════════════════════════════════════


class TestP2NotSameControlCost:
    """Property 2: 直接费用费用化，旧fees参数不进入初始成本."""

    @given(price=finite_floats, fees=finite_floats)
    @settings(max_examples=5)
    def test_not_same_control_cost_equals_consideration(self, price: float, fees: float):
        result = svc.calc_not_same_control_cost(price, fees)
        expected = price
        assert result == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3: 商誉 = 初始投资成本 - 享有被购买方净资产公允价值份额
# Tag: Feature: g7-long-term-equity-subsidiary, Property 3
# **Validates: Requirements 3.4, 7.1**
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3Goodwill:
    """Property 3: calcGoodwill(cost, share) == cost - share; 正=商誉, 负=营业外收入."""

    @given(cost=finite_floats, share=finite_floats)
    @settings(max_examples=5)
    def test_goodwill_equals_difference(self, cost: float, share: float):
        result = svc.calc_goodwill(cost, share)
        expected = cost - share
        assert result == expected

    @given(cost=positive_floats, share=positive_floats)
    @settings(max_examples=5)
    def test_goodwill_sign_semantics(self, cost: float, share: float):
        """正值=商誉(资产), 负值=廉价购买利得(营业外收入)."""
        result = svc.calc_goodwill(cost, share)
        if cost > share:
            assert result > 0, "cost > share → 正商誉"
        elif cost < share:
            assert result < 0, "cost < share → 廉价购买利得(营业外收入)"
        else:
            assert result == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Property 4: 成本法投资收益 = 被投资方宣告股利 × 持股比例
# Tag: Feature: g7-long-term-equity-subsidiary, Property 4
# **Validates: Requirements 4.2**
# ═══════════════════════════════════════════════════════════════════════════════


class TestP4CostMethodIncome:
    """Property 4: calcCostMethodIncome(dividend, ratio) == dividend × ratio."""

    @given(dividend=finite_floats, ratio=finite_floats)
    @settings(max_examples=5)
    def test_cost_method_income_equals_product(self, dividend: float, ratio: float):
        result = svc.calc_cost_method_income(dividend, ratio)
        expected = dividend * ratio
        assert result == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Property 5: 成本法期末账面 = 期初 + 追加投资 - 减值
# Tag: Feature: g7-long-term-equity-subsidiary, Property 5
# **Validates: Requirements 4.3**
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5SubsequentBalance:
    """Property 5: calcSubsequentBalance(opening, addition, impairment) == opening + addition - impairment."""

    @given(opening=finite_floats, addition=finite_floats, impairment=finite_floats)
    @settings(max_examples=5)
    def test_subsequent_balance_formula(
        self, opening: float, addition: float, impairment: float
    ):
        result = svc.calc_subsequent_balance(opening, addition, impairment)
        expected = opening + addition - impairment
        assert result == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Property 6: 处置损益 = 处置对价 - 账面 - 应收股利 + 可转损益OCI
# Tag: Feature: g7-long-term-equity-subsidiary, Property 6
# **Validates: Requirements 5.3**
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6DisposalGain:
    """Property 6: calcDisposalGain(price, bookValue, dividend, oci) == price - bookValue - dividend + oci."""

    @given(
        price=finite_floats,
        book_value=finite_floats,
        dividend=finite_floats,
        oci=finite_floats,
    )
    @settings(max_examples=5)
    def test_disposal_gain_formula(
        self, price: float, book_value: float, dividend: float, oci: float
    ):
        result = svc.calc_disposal_gain(price, book_value, dividend, oci)
        expected = price - book_value - dividend + oci
        assert result == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Property 7: 借贷平衡 ↔ |SUM(debits) - SUM(credits)| < 0.01
# Tag: Feature: g7-long-term-equity-subsidiary, Property 7
# **Validates: Requirements 6.2, 7.1**
# ═══════════════════════════════════════════════════════════════════════════════


class TestP7DebitCreditBalance:
    """Property 7: isDebitCreditBalanced(debits, credits) ↔ |sum(debits)-sum(credits)| < 0.01."""

    @given(
        debits=st.lists(finite_floats, min_size=1, max_size=10),
        credits=st.lists(finite_floats, min_size=1, max_size=10),
    )
    @settings(max_examples=5)
    def test_balance_iff_tolerance(self, debits: list[float], credits: list[float]):
        result = svc.is_debit_credit_balanced(debits, credits)
        diff = abs(sum(debits) - sum(credits))
        expected = diff < 0.01
        assert result == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Property 8: parseNum 健壮性 — 无效输入→0, 有效有限数→原值
# Tag: Feature: g7-long-term-equity-subsidiary, Property 8
# **Validates: Requirements 7.1**
# ═══════════════════════════════════════════════════════════════════════════════


class TestP8ParseNum:
    """Property 8: parseNum(None/''/'abc'/NaN) == 0; parseNum(finite_number) == finite_number."""

    @given(n=finite_floats)
    @settings(max_examples=5)
    def test_finite_number_identity(self, n: float):
        """parseNum(finite_number) == finite_number."""
        result = svc.parse_num(n)
        assert result == n

    def test_none_returns_zero(self):
        assert svc.parse_num(None) == 0.0

    def test_empty_string_returns_zero(self):
        assert svc.parse_num("") == 0.0

    def test_non_numeric_string_returns_zero(self):
        assert svc.parse_num("abc") == 0.0

    def test_nan_returns_zero(self):
        assert svc.parse_num(float("nan")) == 0.0
