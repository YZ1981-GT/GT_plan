"""G12 净敞口套期收益 — 后端 PBT 与 service 测试."""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._g12_net_hedge_gains_service import (
    G12NetHedgeGainsService,
)

svc = G12NetHedgeGainsService()


@given(
    unadjusted=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    adjustment=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p1_adjusted_amount(unadjusted: float, adjustment: float) -> None:
    """Property 1: 审定数 = 未审 + 调整."""
    assert svc.calc_adjusted(unadjusted, adjustment) == pytest.approx(unadjusted + adjustment)


@given(
    opening=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    closing=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p2_fv_change(opening: float, closing: float) -> None:
    """Property 2: FV变动 = 期末 - 期初."""
    assert svc.calc_fv_change(opening, closing) == pytest.approx(closing - opening)


@given(
    instrument=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    item=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p3_hedge_ineffectiveness_abs_diff(instrument: float, item: float) -> None:
    """Property 3: 套期无效部分 = |工具变动 - 项目变动|."""
    assert svc.calc_hedge_ineffectiveness(instrument, item) == pytest.approx(abs(instrument - item))


@given(
    instrument=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    item=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p4_hedge_ineffectiveness_non_negative(instrument: float, item: float) -> None:
    """Property 4: 套期无效部分非负."""
    assert svc.calc_hedge_ineffectiveness(instrument, item) >= 0


@given(
    current=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p5_change_rate_zero_prior(current: float) -> None:
    """Property 5: prior=0 时变动率为 null."""
    assert svc.calc_change_rate(0, current) is None


@given(
    debits=st.lists(
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=20,
    ),
    credits=st.lists(
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=20,
    ),
)
@settings(max_examples=50)
def test_p6_debit_credit_balance(debits: list[float], credits: list[float]) -> None:
    """Property 6: 借贷平衡恒等."""
    d = sum(debits)
    c = sum(credits)
    assert svc.is_debit_credit_balanced(debits, credits) == (abs(d - c) < 0.01)


@given(
    raw=st.one_of(
        st.none(),
        st.just(""),
        st.just("  "),
        st.just("abc"),
        st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
        st.integers(min_value=-10**8, max_value=10**8),
    ),
)
@settings(max_examples=50)
def test_p7_parse_num_robustness(raw) -> None:
    """Property 7: parseNum 健壮性."""
    result = svc.parse_num(raw)
    if raw is None or raw == "" or raw == "  " or raw == "abc":
        assert result == 0.0
    elif isinstance(raw, float):
        assert result == pytest.approx(raw)
    elif isinstance(raw, int):
        assert result == pytest.approx(float(raw))


def test_validate_fv_reconciliation_balanced() -> None:
    rows = [
        {
            "hedgeRelationId": "HR-1",
            "instrumentOpeningFV": 100,
            "instrumentClosingFV": 150,
            "instrumentFVChange": 50,
            "itemOpeningFV": 200,
            "itemClosingFV": 180,
            "itemFVChange": -20,
        }
    ]
    assert svc.validate_fv_reconciliation(rows) == []


def test_validate_fv_reconciliation_unbalanced() -> None:
    rows = [
        {
            "hedgeRelationId": "HR-1",
            "instrumentOpeningFV": 100,
            "instrumentClosingFV": 150,
            "instrumentFVChange": 40,
            "itemOpeningFV": 200,
            "itemClosingFV": 180,
            "itemFVChange": -20,
        }
    ]
    errors = svc.validate_fv_reconciliation(rows)
    assert len(errors) == 1
    assert errors[0].side == "instrument"


def test_validate_hedge_rows_balanced() -> None:
    rows = [
        {
            "hedgeRelationId": "HR-1",
            "instrumentFVChange": 50,
            "itemFVChange": -20,
            "ineffectiveness": 70,
        }
    ]
    assert svc.validate_hedge_rows(rows) == []


def test_validate_hedge_rows_unbalanced() -> None:
    rows = [
        {
            "hedgeRelationId": "HR-1",
            "instrumentFVChange": 50,
            "itemFVChange": -20,
            "ineffectiveness": 60,
        }
    ]
    errors = svc.validate_hedge_rows(rows)
    assert len(errors) == 1
    assert errors[0].row_id == "HR-1"


def test_renderer_dispatch_registered() -> None:
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert "g12-net-hedge-gains" in RENDERER_DISPATCH
