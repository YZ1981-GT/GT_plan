"""G7 长期股权投资(权益法组) — 后端PBT公式验证(hypothesis).

9个property对应前端公式引擎 useG7EquityMethodFormulaEngine.ts 的后端校验。
测试 G7LongTermEquityMethodService 中的9个纯函数+parseNum。

hypothesis max_examples=5

**Validates: Requirements 7.1**
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings, strategies as st

from app.routers.wp_render_strategies._g7_long_term_equity_method_service import (
    G7LongTermEquityMethodService,
)

svc = G7LongTermEquityMethodService()

# ─── 公共 strategies ──────────────────────────────────────────────────────────

_finite_floats = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
_positive_floats = st.floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False)
_ratio = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_direction = st.sampled_from(["downstream", "upstream"])


# ─── Property 1: calcInvestmentCost 初始投资成本 ─────────────────────────────

@settings(max_examples=5)
@given(consideration=_finite_floats, direct_costs=_finite_floats)
def test_property_1_calc_investment_cost(consideration: float, direct_costs: float):
    """Property 1: calcInvestmentCost(consideration, directCosts) == round(consideration + directCosts, 2).

    **Validates: Requirements 7.1**
    """
    result = svc.calc_investment_cost(consideration, direct_costs)
    expected = round(consideration + direct_costs, 2)
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 2: calcShareOfNetAssets 享有净资产份额 ──────────────────────────

@settings(max_examples=5)
@given(net_asset_fv=_finite_floats, ratio=_ratio)
def test_property_2_calc_share_of_net_assets(net_asset_fv: float, ratio: float):
    """Property 2: calcShareOfNetAssets(netAssetFV, ratio) == round(netAssetFV × ratio, 2).

    **Validates: Requirements 7.1**
    """
    result = svc.calc_share_of_net_assets(net_asset_fv, ratio)
    expected = round(net_asset_fv * ratio, 2)
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 3: calcGoodwill 商誉/营业外收入 ────────────────────────────────

@settings(max_examples=5)
@given(initial_cost=_finite_floats, share=_finite_floats)
def test_property_3_calc_goodwill(initial_cost: float, share: float):
    """Property 3: calcGoodwill(initialCost, share) == round(initialCost - share, 2).
    正=商誉性质，负=营业外收入性质。

    **Validates: Requirements 7.1**
    """
    result = svc.calc_goodwill(initial_cost, share)
    expected = round(initial_cost - share, 2)
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)
    # 符号性质验证
    if result > 0:
        assert initial_cost > share  # 商誉性质
    elif result < 0:
        assert initial_cost < share  # 营业外收入性质


# ─── Property 4: calcAdjustedNetProfit 调整后净利润 ──────────────────────────

@settings(max_examples=5)
@given(
    reported=_finite_floats,
    internal=_finite_floats,
    fv_dep=_finite_floats,
    policy=_finite_floats,
    other=_finite_floats,
)
def test_property_4_calc_adjusted_net_profit(
    reported: float, internal: float, fv_dep: float, policy: float, other: float
):
    """Property 4: calcAdjustedNetProfit(r, i, f, p, o) == round(r - i - f + p + o, 2).

    **Validates: Requirements 7.1**
    """
    result = svc.calc_adjusted_net_profit(reported, internal, fv_dep, policy, other)
    expected = round(reported - internal - fv_dep + policy + other, 2)
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 5: calcEquityShare 持股比例份额(通用乘法) ───────────────────────

@settings(max_examples=5)
@given(value=_finite_floats, ratio=_ratio)
def test_property_5_calc_equity_share(value: float, ratio: float):
    """Property 5: calcEquityShare(value, ratio) == round(value × ratio, 2).

    **Validates: Requirements 7.1**
    """
    result = svc.calc_equity_share(value, ratio)
    expected = round(value * ratio, 2)
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 6: calcEquityMethodBalance 权益法余额递推 ──────────────────────

@settings(max_examples=5)
@given(
    opening=_finite_floats,
    income=_finite_floats,
    oci=_finite_floats,
    equity_change=_finite_floats,
    dividend=_finite_floats,
)
def test_property_6_calc_equity_method_balance(
    opening: float, income: float, oci: float, equity_change: float, dividend: float
):
    """Property 6: calcEquityMethodBalance(o, i, oci, eq, d) == round(o + i + oci + eq - d, 2).

    **Validates: Requirements 7.1**
    """
    result = svc.calc_equity_method_balance(opening, income, oci, equity_change, dividend)
    expected = round(opening + income + oci + equity_change - dividend, 2)
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 7: calcUnrealizedProfit 未实现利润 ─────────────────────────────

@settings(max_examples=5)
@given(amount=_finite_floats, margin=_ratio)
def test_property_7_calc_unrealized_profit(amount: float, margin: float):
    """Property 7: calcUnrealizedProfit(amount, margin) == round(amount × margin, 2).

    **Validates: Requirements 7.1**
    """
    result = svc.calc_unrealized_profit(amount, margin)
    expected = round(amount * margin, 2)
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 8: calcEliminationAmount 顺流/逆流抵销 ─────────────────────────

@settings(max_examples=5)
@given(direction=_direction, profit=_finite_floats, ratio=_ratio)
def test_property_8_calc_elimination_amount(direction: str, profit: float, ratio: float):
    """Property 8: 顺流=round(profit, 2)全额; 逆流=round(profit×ratio, 2)按份额.

    **Validates: Requirements 7.1**
    """
    result = svc.calc_elimination_amount(direction, profit, ratio)
    if direction == 'downstream':
        expected = round(profit, 2)
    else:
        expected = round(profit * ratio, 2)
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 9: calcImpairmentAmount 减值非负+MAX语义 ───────────────────────

@settings(max_examples=5)
@given(book_value=_finite_floats, recoverable=_finite_floats)
def test_property_9_calc_impairment_amount(book_value: float, recoverable: float):
    """Property 9: calcImpairmentAmount(bv, ra) == round(MAX(0, bv-ra), 2) 且 ≥ 0.

    **Validates: Requirements 7.1**
    """
    result = svc.calc_impairment_amount(book_value, recoverable)
    expected = round(max(0.0, book_value - recoverable), 2)
    assert result >= 0, f"减值金额必须非负，got {result}"
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── parseNum 健壮性 ─────────────────────────────────────────────────────────

@settings(max_examples=5)
@given(n=_finite_floats)
def test_parse_num_finite_returns_same(n: float):
    """parseNum(finite n) == n.

    **Validates: Requirements 7.1**
    """
    assert svc.parse_num(n) == n


@settings(max_examples=5)
@given(invalid=st.sampled_from([None, "", "  ", "abc", float("nan")]))
def test_parse_num_invalid_returns_zero(invalid):
    """parseNum(None/''/NaN) == 0.

    **Validates: Requirements 7.1**
    """
    result = svc.parse_num(invalid)
    assert result == 0.0
