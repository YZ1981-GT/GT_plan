"""G14 信用减值损失 — 后端 PBT 与 service 测试."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._g14_credit_impairment_loss_service import (
    G14CreditImpairmentLossService,
)


svc = G14CreditImpairmentLossService()


@given(
    unadjusted=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    adjustment=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p1_adjusted_amount(unadjusted: float, adjustment: float) -> None:
    assert svc.calc_adjusted(unadjusted, adjustment) == pytest.approx(unadjusted + adjustment)


@given(
    provision=st.floats(min_value=0, max_value=1e8, allow_nan=False, allow_infinity=False),
    reversal=st.floats(min_value=0, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p2_net_impairment(provision: float, reversal: float) -> None:
    assert svc.calc_profit_loss(provision, reversal) == pytest.approx(provision - reversal)


@given(
    opening=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    provision=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    reversal_signed=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    writeoff=st.floats(min_value=0, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p3_roll_forward(opening: float, provision: float, reversal_signed: float, writeoff: float) -> None:
    expected = opening + provision + reversal_signed - writeoff
    assert svc.calc_roll_forward(opening, provision, reversal_signed, writeoff) == pytest.approx(expected)


def test_validate_roll_forward_balanced() -> None:
    rows = [
        {
            "rowKey": "ar",
            "openingProvision": 100,
            "currentProvision": 30,
            "currentReversal": -5,
            "currentWriteoff": 2,
            "closingProvision": 123,
        }
    ]
    assert svc.validate_roll_forward_rows(rows) == []


def test_validate_roll_forward_unbalanced() -> None:
    rows = [
        {
            "rowKey": "ar",
            "openingProvision": 100,
            "currentProvision": 30,
            "currentReversal": -5,
            "currentWriteoff": 2,
            "closingProvision": 200,
        }
    ]
    errors = svc.validate_roll_forward_rows(rows)
    assert len(errors) == 1
    assert errors[0].row_key == "ar"


def test_renderer_dispatch_registered() -> None:
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert "g14-credit-impairment-loss" in RENDERER_DISPATCH
