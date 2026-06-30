"""Property 11: 导入导出 Round-Trip — D5 应收款项融资

Feature: d5-receivables-financing, Property 11: 导入导出Round-Trip

Generate random DetailRow[]/FairValueRow[] → export → import → verify equivalent.
Uses hypothesis with max_examples=5 (per project convention for PBT).

Tests _export_d5_2_row / _parse_d5_2_row and _export_d5_4_row / _parse_d5_4_row
as pure function round-trip pairs.

**Validates: Requirements 5.5, 12.6**
"""

from __future__ import annotations

import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure the backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.wp_render_strategies._d5_import_export import (
    _export_d5_2_row,
    _export_d5_4_row,
    _parse_d5_2_row,
    _parse_d5_4_row,
    _SHEET_HEADERS,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════════════════════

_amount_st = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)
_positive_amount_st = st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False)
_rate_st = st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False)
_days_st = st.floats(min_value=0, max_value=365, allow_nan=False, allow_infinity=False)
_category_st = st.sampled_from(["应收票据", "应收账款"])
_text_st = st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N")))

_d5_2_row_st = st.fixed_dictionaries({
    "rowId": st.uuids().map(str),
    "category": _category_st,
    "itemName": _text_st,
    "priorUnadjusted": _amount_st,
    "priorAje": _amount_st,
    "priorRje": _amount_st,
    "priorAudited": _amount_st,
    "ociImpairment": _amount_st,
    "periodIncrease": _amount_st,
    "periodDecrease": _amount_st,
    "endBalance": _amount_st,
    "entityReclass": _amount_st,
    "endUnadjusted": _amount_st,
    "endAje": _amount_st,
    "endRje": _amount_st,
    "endAudited": _amount_st,
    "endOciImpairment": _amount_st,
    # Use pre-stripped text since _safe_str does .strip() — round-trip normalizes whitespace
    "remark": st.text(max_size=30).map(str.strip),
})

_d5_4_row_st = st.fixed_dictionaries({
    "rowId": st.uuids().map(str),
    "category": _category_st,
    "itemName": _text_st,
    "billNo": st.text(min_size=1, max_size=15, alphabet=st.characters(categories=("L", "N"))),
    "faceValue": _positive_amount_st,
    "measurementDate": st.just("2026-06-30"),
    "maturityDate": st.just("2026-12-31"),
    "remainingDays": _days_st,
    "discountRate": _rate_st,
    "discountInterest": _positive_amount_st,
    "discountAmount": _positive_amount_st,
    "fairValue": _positive_amount_st,
    "fvHierarchy": st.sampled_from(["第二层次", "第三层次"]),
    # Use pre-stripped text since _safe_str does .strip() — round-trip normalizes whitespace
    "remark": st.text(max_size=30).map(str.strip),
})

_d5_2_rows_st = st.lists(_d5_2_row_st, min_size=1, max_size=5)
_d5_4_rows_st = st.lists(_d5_4_row_st, min_size=1, max_size=5)


# ═══════════════════════════════════════════════════════════════════════════════
# Property Tests
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(rows=_d5_2_rows_st)
def test_d5_2_export_import_round_trip(rows: list[dict]) -> None:
    """D5-2 明细表 export → import round-trip preserves key fields.

    **Validates: Requirements 5.5, 12.6**
    """
    headers = _SHEET_HEADERS["D5-2"]

    for original in rows:
        # Export: dict → list (xlsx row values)
        exported = _export_d5_2_row(original)
        assert len(exported) == len(headers)

        # Import: tuple (simulating xlsx row) → dict
        imported = _parse_d5_2_row(tuple(exported), headers)

        # Verify key fields match
        assert imported["category"] == original["category"]
        assert imported["itemName"] == original["itemName"]
        assert imported["remark"] == original["remark"]

        # Verify numeric fields (float round-trip fidelity)
        assert abs(imported["priorUnadjusted"] - float(original["priorUnadjusted"])) < 1e-6
        assert abs(imported["priorAje"] - float(original["priorAje"])) < 1e-6
        assert abs(imported["priorRje"] - float(original["priorRje"])) < 1e-6
        assert abs(imported["ociImpairment"] - float(original["ociImpairment"])) < 1e-6
        assert abs(imported["periodIncrease"] - float(original["periodIncrease"])) < 1e-6
        assert abs(imported["periodDecrease"] - float(original["periodDecrease"])) < 1e-6
        assert abs(imported["endBalance"] - float(original["endBalance"])) < 1e-6
        assert abs(imported["entityReclass"] - float(original["entityReclass"])) < 1e-6
        assert abs(imported["endUnadjusted"] - float(original["endUnadjusted"])) < 1e-6
        assert abs(imported["endAje"] - float(original["endAje"])) < 1e-6
        assert abs(imported["endRje"] - float(original["endRje"])) < 1e-6
        assert abs(imported["endOciImpairment"] - float(original["endOciImpairment"])) < 1e-6

        # rowId is regenerated (new UUID), so we just check it's non-empty
        assert imported["rowId"] != ""


@settings(max_examples=5)
@given(rows=_d5_4_rows_st)
def test_d5_4_export_import_round_trip(rows: list[dict]) -> None:
    """D5-4 公允价值测算表 export → import round-trip preserves key fields.

    **Validates: Requirements 5.5, 12.6**
    """
    headers = _SHEET_HEADERS["D5-4"]

    for original in rows:
        # Export: dict → list (xlsx row values)
        exported = _export_d5_4_row(original)
        assert len(exported) == len(headers)

        # Import: tuple (simulating xlsx row) → dict
        imported = _parse_d5_4_row(tuple(exported), headers)

        # Verify string fields
        assert imported["category"] == original["category"]
        assert imported["itemName"] == original["itemName"]
        assert imported["billNo"] == original["billNo"]
        assert imported["measurementDate"] == original["measurementDate"]
        assert imported["maturityDate"] == original["maturityDate"]
        assert imported["fvHierarchy"] == original["fvHierarchy"]
        assert imported["remark"] == original["remark"]

        # Verify numeric fields
        assert abs(imported["faceValue"] - float(original["faceValue"])) < 1e-6
        assert abs(imported["remainingDays"] - float(original["remainingDays"])) < 1e-6
        assert abs(imported["discountRate"] - float(original["discountRate"])) < 1e-6

        # discountInterest / fairValue may be recomputed during import if conditions match,
        # but when explicitly provided (non-zero), they should round-trip
        if original["discountInterest"] != 0.0:
            assert abs(imported["discountInterest"] - float(original["discountInterest"])) < 1e-6

        # rowId is regenerated (new UUID)
        assert imported["rowId"] != ""
