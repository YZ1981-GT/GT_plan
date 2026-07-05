"""G13 公允价值变动收益 — 后端 PBT 与 service 测试."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._g13_fair_value_changes_service import (
    G13FairValueChangesService,
)

svc = G13FairValueChangesService()


@given(
    unadjusted=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    adjustment=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p1_adjusted_amount(unadjusted: float, adjustment: float) -> None:
    assert svc.calc_adjusted(unadjusted, adjustment) == pytest.approx(unadjusted + adjustment)


@given(
    opening=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    closing=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_p2_fv_change(opening: float, closing: float) -> None:
    assert svc.calc_fv_change(opening, closing) == pytest.approx(closing - opening)


def test_validate_fv_reconciliation_balanced() -> None:
    rows = [
        {
            "rowId": "r1",
            "openingFairValue": 100,
            "closingFairValue": 150,
            "currentUnadjusted": 50,
            "adjustment": 0,
        },
    ]
    assert svc.validate_fv_reconciliation(rows) == []


def test_validate_fv_reconciliation_mismatch() -> None:
    rows = [
        {
            "rowId": "r1",
            "openingFairValue": 100,
            "closingFairValue": 150,
            "currentUnadjusted": 40,
            "adjustment": 0,
        },
    ]
    errors = svc.validate_fv_reconciliation(rows)
    assert len(errors) == 1
    assert errors[0].row_id == "r1"


def test_g13_renderer_dispatch() -> None:
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert "g13-fair-value-changes" in RENDERER_DISPATCH
