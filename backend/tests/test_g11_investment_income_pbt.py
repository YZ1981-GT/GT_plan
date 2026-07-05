"""G11 投资收益 — 后端 PBT 与 service 测试."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._g11_investment_income_service import (
    G11InvestmentIncomeService,
)

svc = G11InvestmentIncomeService()


@given(
    unadjusted=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    adjustment=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p1_adjusted_amount(unadjusted: float, adjustment: float) -> None:
    assert svc.calc_adjusted(unadjusted, adjustment) == pytest.approx(unadjusted + adjustment)


@given(
    opening=st.floats(min_value=0, max_value=1e8, allow_nan=False, allow_infinity=False),
    closing=st.floats(min_value=0, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p2_average_balance(opening: float, closing: float) -> None:
    assert svc.calc_average_balance(opening, closing) == pytest.approx((opening + closing) / 2)


@given(
    income=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    avg=st.floats(min_value=0.01, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p3_return_rate(income: float, avg: float) -> None:
    assert svc.calc_return_rate(income, avg) == pytest.approx(income / avg)


def test_p4_return_rate_zero() -> None:
    assert svc.calc_return_rate(100, 0) is None


@given(
    prior=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    current=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p5_change_rate(prior: float, current: float) -> None:
    if prior == 0:
        assert svc.calc_change_rate(prior, current) is None
    else:
        assert svc.calc_change_rate(prior, current) == pytest.approx((current - prior) / abs(prior))


def test_p6_debit_credit_balanced() -> None:
    assert svc.is_debit_credit_balanced([100, 50], [150]) is True
    assert svc.is_debit_credit_balanced([100], [90]) is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, 0.0),
        ("", 0.0),
        ("abc", 0.0),
        (42, 42.0),
    ],
)
def test_p7_parse_num(raw: object, expected: float) -> None:
    assert svc.parse_num(raw) == expected


def test_validate_adjudication_balanced() -> None:
    rows = [{"rowKey": "a", "currentUnadjusted": 100, "currentAdjustment": 10, "currentAudited": 110}]
    assert svc.validate_adjudication_rows(rows) == []


def test_validate_detail_reconciliation_mismatch() -> None:
    adj = [{"label": "权益法", "currentAudited": 100}]
    detail = [{"itemName": "权益法", "currentUnadjusted": 50, "currentAdjustment": 0}]
    errors = svc.validate_detail_reconciliation(adj, detail)
    assert len(errors) == 1


def test_renderer_dispatch_registered() -> None:
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert "g11-investment-income" in RENDERER_DISPATCH
