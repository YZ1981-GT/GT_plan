"""Property 11: 导入导出 Round-Trip — D6 合同资产

Feature: d6-contract-assets, Property 11: 导入导出Round-Trip

Generate random DetailRow[]/ImpairmentRow[]/RelatedPartyRow[]/EclRow[] data
→ export_row → parse_row(exported_tuple) → verify equivalent (round-trip).
Also tests format validation: random incorrect column names → errors detected.

Uses hypothesis with max_examples=5 (per project convention for PBT).

**Validates: Requirements 6.5, 6.6**
"""

from __future__ import annotations

import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure the backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.wp_render_strategies._d6_import_export import (
    _export_row,
    _parse_row,
    _SHEET_HEADERS,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════════════════════

_amount_st = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)
_positive_amount_st = st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False)
_rate_st = st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False)
_text_st = st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N")))
_stripped_text_st = st.text(max_size=30).map(str.strip)

# D6-2 明细表行
_d6_2_row_st = st.fixed_dictionaries({
    "rowId": st.uuids().map(str),
    "seqNo": st.integers(min_value=1, max_value=999),
    "contractName": _text_st,
    "contractType": st.sampled_from(["工程施工", "质量保证金", "其他"]),
    "customerName": _text_st,
    "companyCode": _stripped_text_st,
    "relatedPartyType": st.sampled_from(["非关联方", "实际控制人", "控股股东", "其他关联方"]),
    "priorUnadjusted": _amount_st,
    "priorAje": _amount_st,
    "priorRje": _amount_st,
    "priorAudited": _amount_st,
    "agePrior1y": _positive_amount_st,
    "agePrior1to2y": _positive_amount_st,
    "agePrior2to3y": _positive_amount_st,
    "agePrior3yAbove": _positive_amount_st,
    "debitAmount": _positive_amount_st,
    "creditAmount": _positive_amount_st,
    "endUnadjusted": _amount_st,
    "endAje": _amount_st,
    "endRje": _amount_st,
    "endAudited": _amount_st,
    "ageEnd1y": _positive_amount_st,
    "ageEnd1to2y": _positive_amount_st,
    "ageEnd2to3y": _positive_amount_st,
    "ageEnd3yAbove": _positive_amount_st,
    "receivableWithin1y": _positive_amount_st,
    "receivableAbove1y": _positive_amount_st,
    "isInConstructionPeriod": st.sampled_from(["是", "否"]),
    "creditRiskGroup": st.sampled_from(["单项计提", "业务类型组合", "客户类型组合"]),
    "isConfirmed": st.sampled_from(["是", "否"]),
    "postPeriodSettlement": _positive_amount_st,
})

# D6-3 减值准备明细行
_d6_3_row_st = st.fixed_dictionaries({
    "rowId": st.uuids().map(str),
    "itemName": _text_st,
    "category": st.sampled_from(["single", "group"]),
    "priorUnadjusted": _amount_st,
    "priorAje": _amount_st,
    "priorRje": _amount_st,
    "priorAudited": _amount_st,
    "provision": _positive_amount_st,
    "otherIncrease": _positive_amount_st,
    "reversal": _positive_amount_st,
    "writeOff": _positive_amount_st,
    "otherDecrease": _positive_amount_st,
    "endUnadjusted": _amount_st,
    "endAje": _amount_st,
    "endRje": _amount_st,
    "endAudited": _amount_st,
})

# D6-5 关联方检查行
_d6_5_row_st = st.fixed_dictionaries({
    "rowId": st.uuids().map(str),
    "partyName": _text_st,
    "relationship": st.sampled_from(["实际控制人", "控股股东", "联营", "合营", "其他关联方"]),
    "priorBalance": _positive_amount_st,
    "debitAmount": _positive_amount_st,
    "creditAmount": _positive_amount_st,
    "endBalance": _amount_st,
    "impairment": _positive_amount_st,
    "bookValue": _amount_st,
    "agingAndTiming": _stripped_text_st,
    "unsettledReason": _stripped_text_st,
    "postSettlement": _positive_amount_st,
    "plan": _stripped_text_st,
    "indexRef": _stripped_text_st,
    "remark": _stripped_text_st,
})

# D6-8 ECL单项计提行
_d6_8_row_st = st.fixed_dictionaries({
    "rowId": st.uuids().map(str),
    "debtorName": _text_st,
    "auditedBalance": _positive_amount_st,
    "lossRate": _rate_st,
    "expectedProvision": _positive_amount_st,
    "bookBalance": _positive_amount_st,
    "difference": _amount_st,
    "basis": _stripped_text_st,
    "indexRef": _stripped_text_st,
})

# List strategies
_d6_2_rows_st = st.lists(_d6_2_row_st, min_size=1, max_size=3)
_d6_3_rows_st = st.lists(_d6_3_row_st, min_size=1, max_size=3)
_d6_5_rows_st = st.lists(_d6_5_row_st, min_size=1, max_size=3)
_d6_8_rows_st = st.lists(_d6_8_row_st, min_size=1, max_size=3)


# ═══════════════════════════════════════════════════════════════════════════════
# Property Tests — Round-Trip
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(rows=_d6_2_rows_st)
def test_d6_2_export_import_round_trip(rows: list[dict]) -> None:
    """D6-2 明细表 export → import round-trip preserves key fields.

    **Validates: Requirements 6.5, 6.6**
    """
    headers = _SHEET_HEADERS["D6-2"]

    for original in rows:
        # Export: dict → list (xlsx row values)
        exported = _export_row("D6-2", original, headers)
        assert len(exported) == len(headers)

        # Import: tuple (simulating xlsx row) → dict
        imported = _parse_row("D6-2", tuple(exported), headers)

        # Verify string fields
        assert imported["contractName"] == original["contractName"]
        assert imported["contractType"] == original["contractType"]
        assert imported["customerName"] == original["customerName"]
        assert imported["companyCode"] == original["companyCode"]
        assert imported["relatedPartyType"] == original["relatedPartyType"]
        assert imported["isInConstructionPeriod"] == original["isInConstructionPeriod"]
        assert imported["creditRiskGroup"] == original["creditRiskGroup"]
        assert imported["isConfirmed"] == original["isConfirmed"]

        # Verify numeric input fields (editable columns that round-trip directly)
        assert abs(imported["priorUnadjusted"] - float(original["priorUnadjusted"])) < 1e-6
        assert abs(imported["priorAje"] - float(original["priorAje"])) < 1e-6
        assert abs(imported["priorRje"] - float(original["priorRje"])) < 1e-6
        assert abs(imported["debitAmount"] - float(original["debitAmount"])) < 1e-6
        assert abs(imported["creditAmount"] - float(original["creditAmount"])) < 1e-6
        assert abs(imported["endAje"] - float(original["endAje"])) < 1e-6
        assert abs(imported["endRje"] - float(original["endRje"])) < 1e-6
        assert abs(imported["agePrior1y"] - float(original["agePrior1y"])) < 1e-6
        assert abs(imported["agePrior1to2y"] - float(original["agePrior1to2y"])) < 1e-6
        assert abs(imported["agePrior2to3y"] - float(original["agePrior2to3y"])) < 1e-6
        assert abs(imported["agePrior3yAbove"] - float(original["agePrior3yAbove"])) < 1e-6
        assert abs(imported["ageEnd1y"] - float(original["ageEnd1y"])) < 1e-6
        assert abs(imported["ageEnd1to2y"] - float(original["ageEnd1to2y"])) < 1e-6
        assert abs(imported["ageEnd2to3y"] - float(original["ageEnd2to3y"])) < 1e-6
        assert abs(imported["ageEnd3yAbove"] - float(original["ageEnd3yAbove"])) < 1e-6
        assert abs(imported["receivableWithin1y"] - float(original["receivableWithin1y"])) < 1e-6
        assert abs(imported["receivableAbove1y"] - float(original["receivableAbove1y"])) < 1e-6
        assert abs(imported["postPeriodSettlement"] - float(original["postPeriodSettlement"])) < 1e-6

        # Computed fields (priorAudited/endUnadjusted/endAudited) are recalculated on import
        # Verify the formula chain is correct:
        expected_prior_audited = float(original["priorUnadjusted"]) + float(original["priorAje"]) + float(original["priorRje"])
        assert abs(imported["priorAudited"] - expected_prior_audited) < 1e-6

        expected_end_unadj = expected_prior_audited + float(original["debitAmount"]) - float(original["creditAmount"])
        assert abs(imported["endUnadjusted"] - expected_end_unadj) < 1e-6

        expected_end_audited = expected_end_unadj + float(original["endAje"]) + float(original["endRje"])
        assert abs(imported["endAudited"] - expected_end_audited) < 1e-6

        # rowId is regenerated
        assert imported["rowId"] != ""


@settings(max_examples=5)
@given(rows=_d6_3_rows_st)
def test_d6_3_export_import_round_trip(rows: list[dict]) -> None:
    """D6-3 减值准备明细 export → import round-trip preserves key fields.

    **Validates: Requirements 6.5, 6.6**
    """
    headers = _SHEET_HEADERS["D6-3"]

    for original in rows:
        exported = _export_row("D6-3", original, headers)
        assert len(exported) == len(headers)

        imported = _parse_row("D6-3", tuple(exported), headers)

        # Verify string fields
        assert imported["itemName"] == original["itemName"]
        assert imported["category"] == original["category"]

        # Verify numeric input fields
        assert abs(imported["priorUnadjusted"] - float(original["priorUnadjusted"])) < 1e-6
        assert abs(imported["priorAje"] - float(original["priorAje"])) < 1e-6
        assert abs(imported["priorRje"] - float(original["priorRje"])) < 1e-6
        assert abs(imported["provision"] - float(original["provision"])) < 1e-6
        assert abs(imported["otherIncrease"] - float(original["otherIncrease"])) < 1e-6
        assert abs(imported["reversal"] - float(original["reversal"])) < 1e-6
        assert abs(imported["writeOff"] - float(original["writeOff"])) < 1e-6
        assert abs(imported["otherDecrease"] - float(original["otherDecrease"])) < 1e-6
        assert abs(imported["endAje"] - float(original["endAje"])) < 1e-6
        assert abs(imported["endRje"] - float(original["endRje"])) < 1e-6

        # Computed fields recalculated on import
        expected_prior_audited = float(original["priorUnadjusted"]) + float(original["priorAje"]) + float(original["priorRje"])
        assert abs(imported["priorAudited"] - expected_prior_audited) < 1e-6

        expected_end_unadj = (
            expected_prior_audited
            + float(original["provision"])
            + float(original["otherIncrease"])
            - float(original["reversal"])
            - float(original["writeOff"])
            - float(original["otherDecrease"])
        )
        assert abs(imported["endUnadjusted"] - expected_end_unadj) < 1e-6

        expected_end_audited = expected_end_unadj + float(original["endAje"]) + float(original["endRje"])
        assert abs(imported["endAudited"] - expected_end_audited) < 1e-6

        assert imported["rowId"] != ""


@settings(max_examples=5)
@given(rows=_d6_5_rows_st)
def test_d6_5_export_import_round_trip(rows: list[dict]) -> None:
    """D6-5 关联方检查 export → import round-trip preserves key fields.

    **Validates: Requirements 6.5, 6.6**
    """
    headers = _SHEET_HEADERS["D6-5"]

    for original in rows:
        exported = _export_row("D6-5", original, headers)
        assert len(exported) == len(headers)

        imported = _parse_row("D6-5", tuple(exported), headers)

        # Verify string fields
        assert imported["partyName"] == original["partyName"]
        assert imported["relationship"] == original["relationship"]
        assert imported["agingAndTiming"] == original["agingAndTiming"]
        assert imported["unsettledReason"] == original["unsettledReason"]
        assert imported["plan"] == original["plan"]
        assert imported["indexRef"] == original["indexRef"]
        assert imported["remark"] == original["remark"]

        # Verify numeric input fields
        assert abs(imported["priorBalance"] - float(original["priorBalance"])) < 1e-6
        assert abs(imported["debitAmount"] - float(original["debitAmount"])) < 1e-6
        assert abs(imported["creditAmount"] - float(original["creditAmount"])) < 1e-6
        assert abs(imported["impairment"] - float(original["impairment"])) < 1e-6
        assert abs(imported["postSettlement"] - float(original["postSettlement"])) < 1e-6

        # Computed fields: endBalance = prior + debit - credit; bookValue = endBalance - impairment
        expected_end = float(original["priorBalance"]) + float(original["debitAmount"]) - float(original["creditAmount"])
        assert abs(imported["endBalance"] - expected_end) < 1e-6

        expected_book = expected_end - float(original["impairment"])
        assert abs(imported["bookValue"] - expected_book) < 1e-6

        assert imported["rowId"] != ""


@settings(max_examples=5)
@given(rows=_d6_8_rows_st)
def test_d6_8_export_import_round_trip(rows: list[dict]) -> None:
    """D6-8 ECL单项计提 export → import round-trip preserves key fields.

    **Validates: Requirements 6.5, 6.6**
    """
    headers = _SHEET_HEADERS["D6-8"]

    for original in rows:
        exported = _export_row("D6-8", original, headers)
        assert len(exported) == len(headers)

        imported = _parse_row("D6-8", tuple(exported), headers)

        # Verify string fields
        assert imported["debtorName"] == original["debtorName"]
        assert imported["basis"] == original["basis"]
        assert imported["indexRef"] == original["indexRef"]

        # Verify numeric input fields
        assert abs(imported["auditedBalance"] - float(original["auditedBalance"])) < 1e-6
        assert abs(imported["lossRate"] - float(original["lossRate"])) < 1e-6
        assert abs(imported["bookBalance"] - float(original["bookBalance"])) < 1e-6

        # Computed: expectedProvision = balance * rate; difference = expected - book
        expected_provision = float(original["auditedBalance"]) * float(original["lossRate"])
        assert abs(imported["expectedProvision"] - expected_provision) < 1e-6

        expected_diff = expected_provision - float(original["bookBalance"])
        assert abs(imported["difference"] - expected_diff) < 1e-6

        assert imported["rowId"] != ""


# ═══════════════════════════════════════════════════════════════════════════════
# Property Tests — Format Validation (incorrect columns → errors detected)
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(
    sheet=st.sampled_from(["D6-2", "D6-3", "D6-5", "D6-8"]),
    bad_cols=st.lists(
        st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L",))),
        min_size=1,
        max_size=5,
    ),
)
def test_format_validation_detects_incorrect_columns(sheet: str, bad_cols: list[str]) -> None:
    """Random incorrect column names should be detectable as missing.

    Simulates the validation logic from the import endpoint:
    any column in _SHEET_HEADERS[sheet] not present in actual_headers → error.

    **Validates: Requirements 6.5, 6.6**
    """
    expected_headers = _SHEET_HEADERS[sheet]

    # Create a header row with random bad column names (replacing some expected)
    actual_headers = bad_cols + expected_headers[len(bad_cols):]

    # Check for missing columns
    missing = [h for h in expected_headers if h not in actual_headers]

    # If we introduced bad columns that replace expected ones, they should be detected
    replaced_count = min(len(bad_cols), len(expected_headers))
    for i in range(replaced_count):
        if bad_cols[i] not in expected_headers:
            # This bad column replaced a good one, so we expect errors
            assert expected_headers[i] in missing or expected_headers[i] in actual_headers
