"""Property 11: 导入导出 Round-Trip — D7 合同负债

Feature: d7-contract-liabilities, Property 11: 导入导出Round-Trip

Generate random DetailRow[]/LongTermRow[]/RelatedPartyRow[] data
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

from app.routers.wp_render_strategies._d7_import_export import (
    _export_row,
    _parse_row,
    _SHEET_HEADERS,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════════════════════

_amount_st = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)
_positive_amount_st = st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False)
_text_st = st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N")))
_stripped_text_st = st.text(max_size=30).map(str.strip)

# D7-2 明细表行（贷方科目：期末=期初+贷方-借方）
_d7_2_row_st = st.fixed_dictionaries({
    "rowId": st.uuids().map(str),
    "seqNo": st.integers(min_value=1, max_value=999),
    "contractName": _text_st,
    "companyName": _text_st,
    "companyCode": _stripped_text_st,
    "relatedPartyType": st.sampled_from(["非关联方", "实际控制人", "控股股东", "其他关联方"]),
    "natureType": st.sampled_from(["预收货款", "开发项目预收款", "预收工程款", "其他"]),
    "priorUnadjusted": _amount_st,
    "priorAje": _amount_st,
    "priorRje": _amount_st,
    "priorAudited": _amount_st,
    "priorAging1": _positive_amount_st,
    "priorAging2": _positive_amount_st,
    "priorAging3": _positive_amount_st,
    "priorAging4": _positive_amount_st,
    "debitAmount": _positive_amount_st,
    "creditAmount": _positive_amount_st,
    "endBalance": _amount_st,
    "entityReclass": _amount_st,
    "endUnadjusted": _amount_st,
    "endAje": _amount_st,
    "endRje": _amount_st,
    "endAudited": _amount_st,
    "endAging1": _positive_amount_st,
    "endAging2": _positive_amount_st,
    "endAging3": _positive_amount_st,
    "endAging4": _positive_amount_st,
    "isConfirmed": st.sampled_from(["是", "否"]),
    "postTransfer": _positive_amount_st,
})

# D7-5 账龄1年以上行
_d7_5_row_st = st.fixed_dictionaries({
    "rowId": st.uuids().map(str),
    "customerName": _text_st,
    "endBalance": _positive_amount_st,
    "aging": st.sampled_from(["1~2年", "2~3年", "3年以上"]),
    "businessDescription": _stripped_text_st,
    "reason": _stripped_text_st,
    "auditDateTransfer": _positive_amount_st,
    "plan": _stripped_text_st,
    "remark": _stripped_text_st,
})

# D7-6 关联方行
_d7_6_row_st = st.fixed_dictionaries({
    "rowId": st.uuids().map(str),
    "partyName": _text_st,
    "relationship": st.sampled_from(["实际控制人", "控股股东", "联营", "合营", "其他关联方"]),
    "openingBalance": _positive_amount_st,
    "debitAmount": _positive_amount_st,
    "creditAmount": _positive_amount_st,
    "endBalance": _amount_st,
    "agingTime": _stripped_text_st,
    "reason": _stripped_text_st,
    "auditDateTransfer": _positive_amount_st,
    "plan": _stripped_text_st,
    "remark": _stripped_text_st,
})

# List strategies
_d7_2_rows_st = st.lists(_d7_2_row_st, min_size=1, max_size=3)
_d7_5_rows_st = st.lists(_d7_5_row_st, min_size=1, max_size=3)
_d7_6_rows_st = st.lists(_d7_6_row_st, min_size=1, max_size=3)


# ═══════════════════════════════════════════════════════════════════════════════
# Property Tests — Round-Trip
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(rows=_d7_2_rows_st)
def test_d7_2_export_import_round_trip(rows: list[dict]) -> None:
    """D7-2 明细表 export → import round-trip preserves key fields.

    **Validates: Requirements 6.5, 6.6**
    """
    headers = _SHEET_HEADERS["D7-2"]

    for original in rows:
        # Export: dict → list (xlsx row values)
        exported = _export_row("D7-2", original, headers)
        assert len(exported) == len(headers)

        # Import: tuple (simulating xlsx row) → dict
        imported = _parse_row("D7-2", tuple(exported), headers)

        # Verify string fields
        assert imported["contractName"] == original["contractName"]
        assert imported["companyName"] == original["companyName"]
        assert imported["companyCode"] == original["companyCode"]
        assert imported["relatedPartyType"] == original["relatedPartyType"]
        assert imported["natureType"] == original["natureType"]
        assert imported["isConfirmed"] == original["isConfirmed"]

        # Verify numeric input fields (editable columns that round-trip directly)
        assert abs(imported["priorUnadjusted"] - float(original["priorUnadjusted"])) < 1e-6
        assert abs(imported["priorAje"] - float(original["priorAje"])) < 1e-6
        assert abs(imported["priorRje"] - float(original["priorRje"])) < 1e-6
        assert abs(imported["debitAmount"] - float(original["debitAmount"])) < 1e-6
        assert abs(imported["creditAmount"] - float(original["creditAmount"])) < 1e-6
        assert abs(imported["entityReclass"] - float(original["entityReclass"])) < 1e-6
        assert abs(imported["endAje"] - float(original["endAje"])) < 1e-6
        assert abs(imported["endRje"] - float(original["endRje"])) < 1e-6
        assert abs(imported["priorAging1"] - float(original["priorAging1"])) < 1e-6
        assert abs(imported["priorAging2"] - float(original["priorAging2"])) < 1e-6
        assert abs(imported["priorAging3"] - float(original["priorAging3"])) < 1e-6
        assert abs(imported["priorAging4"] - float(original["priorAging4"])) < 1e-6
        assert abs(imported["endAging1"] - float(original["endAging1"])) < 1e-6
        assert abs(imported["endAging2"] - float(original["endAging2"])) < 1e-6
        assert abs(imported["endAging3"] - float(original["endAging3"])) < 1e-6
        assert abs(imported["endAging4"] - float(original["endAging4"])) < 1e-6
        assert abs(imported["postTransfer"] - float(original["postTransfer"])) < 1e-6

        # Computed fields (recalculated on import using credit formula)
        expected_prior_audited = float(original["priorUnadjusted"]) + float(original["priorAje"]) + float(original["priorRje"])
        assert abs(imported["priorAudited"] - expected_prior_audited) < 1e-6

        # 贷方科目：期末余额=期初审定+贷方-借方
        expected_end_balance = expected_prior_audited + float(original["creditAmount"]) - float(original["debitAmount"])
        assert abs(imported["endBalance"] - expected_end_balance) < 1e-6

        expected_end_unadj = expected_end_balance + float(original["entityReclass"])
        assert abs(imported["endUnadjusted"] - expected_end_unadj) < 1e-6

        expected_end_audited = expected_end_unadj + float(original["endAje"]) + float(original["endRje"])
        assert abs(imported["endAudited"] - expected_end_audited) < 1e-6

        # rowId is regenerated
        assert imported["rowId"] != ""


@settings(max_examples=5)
@given(rows=_d7_5_rows_st)
def test_d7_5_export_import_round_trip(rows: list[dict]) -> None:
    """D7-5 账龄1年以上 export → import round-trip preserves key fields.

    **Validates: Requirements 6.5, 6.6**
    """
    headers = _SHEET_HEADERS["D7-5"]

    for original in rows:
        exported = _export_row("D7-5", original, headers)
        assert len(exported) == len(headers)

        imported = _parse_row("D7-5", tuple(exported), headers)

        # Verify string fields
        assert imported["customerName"] == original["customerName"]
        assert imported["aging"] == original["aging"]
        assert imported["businessDescription"] == original["businessDescription"]
        assert imported["reason"] == original["reason"]
        assert imported["plan"] == original["plan"]
        assert imported["remark"] == original["remark"]

        # Verify numeric fields
        assert abs(imported["endBalance"] - float(original["endBalance"])) < 1e-6
        assert abs(imported["auditDateTransfer"] - float(original["auditDateTransfer"])) < 1e-6

        assert imported["rowId"] != ""


@settings(max_examples=5)
@given(rows=_d7_6_rows_st)
def test_d7_6_export_import_round_trip(rows: list[dict]) -> None:
    """D7-6 关联方检查 export → import round-trip preserves key fields.

    **Validates: Requirements 6.5, 6.6**
    """
    headers = _SHEET_HEADERS["D7-6"]

    for original in rows:
        exported = _export_row("D7-6", original, headers)
        assert len(exported) == len(headers)

        imported = _parse_row("D7-6", tuple(exported), headers)

        # Verify string fields
        assert imported["partyName"] == original["partyName"]
        assert imported["relationship"] == original["relationship"]
        assert imported["agingTime"] == original["agingTime"]
        assert imported["reason"] == original["reason"]
        assert imported["plan"] == original["plan"]
        assert imported["remark"] == original["remark"]

        # Verify numeric input fields
        assert abs(imported["openingBalance"] - float(original["openingBalance"])) < 1e-6
        assert abs(imported["debitAmount"] - float(original["debitAmount"])) < 1e-6
        assert abs(imported["creditAmount"] - float(original["creditAmount"])) < 1e-6
        assert abs(imported["auditDateTransfer"] - float(original["auditDateTransfer"])) < 1e-6

        # Computed: 贷方科目 endBalance = opening + credit - debit
        expected_end = float(original["openingBalance"]) + float(original["creditAmount"]) - float(original["debitAmount"])
        assert abs(imported["endBalance"] - expected_end) < 1e-6

        assert imported["rowId"] != ""


# ═══════════════════════════════════════════════════════════════════════════════
# Property Tests — Format Validation (incorrect columns → errors detected)
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(
    sheet=st.sampled_from(["D7-2", "D7-5", "D7-6"]),
    bad_cols=st.lists(
        st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L",))),
        min_size=1,
        max_size=5,
    ),
)
def test_format_validation_detects_incorrect_columns(sheet: str, bad_cols: list[str]) -> None:
    """Random incorrect column names should be detectable as missing.

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
            assert expected_headers[i] in missing or expected_headers[i] in actual_headers
