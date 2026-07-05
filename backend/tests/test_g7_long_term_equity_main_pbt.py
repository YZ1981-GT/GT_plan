"""G7 长期股权投资(main组) — 后端PBT公式验证(hypothesis).

9个property对应前端公式引擎 useG7FormulaEngine.ts 的后端校验。
测试 G7LongTermEquityMainService 中的8个纯函数+validate_formulas批量一致性。

hypothesis max_examples=5

**Validates: Requirements 6.2**
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings, strategies as st

from app.routers.wp_render_strategies._g7_long_term_equity_main_service import (
    G7LongTermEquityMainService,
)

svc = G7LongTermEquityMainService()

# ─── 公共 strategies ──────────────────────────────────────────────────────────

_finite_floats = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
_positive_floats = st.floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False)
_float_lists = st.lists(_finite_floats, min_size=1, max_size=10)


# ─── Property 1: parseNum 健壮性 ─────────────────────────────────────────────

@settings(max_examples=5)
@given(n=_finite_floats)
def test_property_1_parse_num_finite_returns_same(n: float):
    """Property 1a: parseNum(finite n) == n.

    **Validates: Requirements 6.2**
    """
    assert svc.parse_num(n) == n


@settings(max_examples=5)
@given(invalid=st.sampled_from([None, "", "  ", "abc", float("nan")]))
def test_property_1_parse_num_invalid_returns_zero(invalid):
    """Property 1b: parseNum(None/''/NaN) == 0.

    **Validates: Requirements 6.2**
    """
    result = svc.parse_num(invalid)
    assert result == 0.0


# ─── Property 2: 借方余额公式 ────────────────────────────────────────────────

@settings(max_examples=5)
@given(
    opening=_finite_floats,
    debit=_finite_floats,
    credit=_finite_floats,
)
def test_property_2_calc_debit_balance(opening: float, debit: float, credit: float):
    """Property 2: calcDebitBalance(opening, debit, credit) == opening + debit - credit.

    **Validates: Requirements 6.2**
    """
    result = svc.calc_debit_balance(opening, debit, credit)
    expected = opening + debit - credit
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 3: 审定数公式 ──────────────────────────────────────────────────

@settings(max_examples=5)
@given(
    unadjusted=_finite_floats,
    aje=_finite_floats,
    rje=_finite_floats,
)
def test_property_3_calc_adjusted_amount(unadjusted: float, aje: float, rje: float):
    """Property 3: calcAdjustedAmount(unadjusted, aje, rje) == unadjusted + aje + rje.

    **Validates: Requirements 6.2**
    """
    result = svc.calc_adjusted_amount(unadjusted, aje, rje)
    expected = unadjusted + aje + rje
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 4: 期末投资成本公式 ────────────────────────────────────────────

@settings(max_examples=5)
@given(
    opening=_finite_floats,
    increase=_finite_floats,
    decrease=_finite_floats,
)
def test_property_4_calc_ending_cost(opening: float, increase: float, decrease: float):
    """Property 4: calcEndingCost(opening, increase, decrease) == opening + increase - decrease.

    **Validates: Requirements 6.2**
    """
    result = svc.calc_ending_cost(opening, increase, decrease)
    expected = opening + increase - decrease
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 5: 期末权益法调整公式 ──────────────────────────────────────────

@settings(max_examples=5)
@given(
    opening=_finite_floats,
    eq_inc=_finite_floats,
    eq_dec=_finite_floats,
)
def test_property_5_calc_ending_equity_adj(opening: float, eq_inc: float, eq_dec: float):
    """Property 5: calcEndingEquityAdj(opening, eq_inc, eq_dec) == opening + eq_inc - eq_dec.

    **Validates: Requirements 6.2**
    """
    result = svc.calc_ending_equity_adj(opening, eq_inc, eq_dec)
    expected = opening + eq_inc - eq_dec
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 6: 账面价值公式 ────────────────────────────────────────────────

@settings(max_examples=5)
@given(
    subtotal=_finite_floats,
    impairment=_finite_floats,
)
def test_property_6_calc_book_value(subtotal: float, impairment: float):
    """Property 6: calcBookValue(subtotal, impairment) == subtotal - impairment.

    **Validates: Requirements 6.2**
    """
    result = svc.calc_book_value(subtotal, impairment)
    expected = subtotal - impairment
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9)


# ─── Property 7: 变动率方向性与除零保护 ──────────────────────────────────────

@settings(max_examples=5)
@given(current=_finite_floats)
def test_property_7a_change_rate_zero_prior_returns_none(current: float):
    """Property 7a: calcChangeRate(0, any) == None.

    **Validates: Requirements 6.2**
    """
    result = svc.calc_change_rate(0, current)
    assert result is None


@settings(max_examples=5)
@given(
    prior=_positive_floats,
    delta=_positive_floats,
)
def test_property_7b_change_rate_positive_direction(prior: float, delta: float):
    """Property 7b: current > prior > 0 → calcChangeRate > 0.

    **Validates: Requirements 6.2**
    """
    current = prior + delta  # current > prior
    result = svc.calc_change_rate(prior, current)
    assert result is not None
    assert result > 0


@settings(max_examples=5)
@given(
    prior=_positive_floats,
    delta=_positive_floats,
)
def test_property_7c_change_rate_negative_direction(prior: float, delta: float):
    """Property 7c: current < prior, prior > 0 → calcChangeRate < 0.

    **Validates: Requirements 6.2**
    """
    current = prior - delta  # current < prior (delta is positive)
    result = svc.calc_change_rate(prior, current)
    assert result is not None
    assert result < 0


# ─── Property 8: 借贷平衡恒等 ────────────────────────────────────────────────

@settings(max_examples=5)
@given(
    debits=_float_lists,
    credits=_float_lists,
)
def test_property_8_debit_credit_balanced(debits: list[float], credits: list[float]):
    """Property 8: isDebitCreditBalanced ↔ |SUM(debits) - SUM(credits)| < 0.01.

    **Validates: Requirements 6.2**
    """
    result = svc.is_debit_credit_balanced(debits, credits)
    diff = abs(sum(debits) - sum(credits))
    expected = diff < 0.01
    assert result == expected


# ─── Property 9: validate_formulas 批量一致性 ─────────────────────────────────

@settings(max_examples=5)
@given(
    opening=_finite_floats,
    debit=_finite_floats,
    credit=_finite_floats,
    unadjusted=_finite_floats,
    aje=_finite_floats,
    rje=_finite_floats,
    op_cost=_finite_floats,
    increase=_finite_floats,
    decrease=_finite_floats,
)
def test_property_9_validate_formulas_batch_consistency(
    opening: float,
    debit: float,
    credit: float,
    unadjusted: float,
    aje: float,
    rje: float,
    op_cost: float,
    increase: float,
    decrease: float,
):
    """Property 9: validate_formulas batch — 当所有字段按公式填充时无错误.

    **Validates: Requirements 6.2**
    """
    # 构建一个完全按公式正确填充的data包
    data = {
        "debit_balance_check": {
            "row_key": "test",
            "opening": opening,
            "debit": debit,
            "credit": credit,
            "balance": opening + debit - credit,
        },
        "adjusted_checks": [
            {
                "row_key": "adj1",
                "unadjusted": unadjusted,
                "aje": aje,
                "rje": rje,
                "adjusted": unadjusted + aje + rje,
            }
        ],
        "ending_cost_checks": [
            {
                "row_key": "cost1",
                "opening": op_cost,
                "increase": increase,
                "decrease": decrease,
                "ending": op_cost + increase - decrease,
            }
        ],
        "book_value_checks": [
            {
                "row_key": "bv1",
                "subtotal": op_cost + increase,
                "impairment": decrease,
                "book_value": (op_cost + increase) - decrease,
            }
        ],
        "debit_credit_balance": {
            "debits": [opening, debit],
            "credits": [opening, debit],  # balanced: sum equals
        },
    }
    errors = svc.validate_formulas(data)
    assert errors == [], f"Unexpected errors: {errors}"
