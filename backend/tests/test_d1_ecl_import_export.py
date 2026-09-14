"""Property 13 (backend): D1-15 ECL坏账准备测算表 导入导出 Round-Trip + 模板格式校验

Feature: d1-ecl-provision, Property 13: D1-15导入导出集成测试

Tests:
1. Round-trip: generate random row data → _export_d1_15_row → _parse_d1_15_row → verify user fields match
2. Template format validation: verify _create_template_wb("D1-15") produces 8 headers + 2 section markers
3. Section marker detection: _is_section_marker correctly identifies section rows
4. Column validation: _validate_columns rejects wrong column count and missing headers

Uses hypothesis with max_examples=5 (per project convention for PBT).

**Validates: Requirements 13.2, 13.3**
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure the backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.wp_render_strategies._d1_import_export import (
    _create_template_wb,
    _export_d1_15_row,
    _parse_d1_15_row,
    _is_section_marker,
    _validate_columns,
    _SHEET_HEADERS,
    _D1_15_SECTION_PORTFOLIO,
    _D1_15_SECTION_INDIVIDUAL,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Property-Based Test: D1-15 Export → Import Round-Trip
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(
    debtor=st.text(min_size=0, max_size=20),
    balance=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False),
    loss_rate=st.floats(min_value=0, max_value=1, allow_nan=False),
    actual_provision=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False),
    basis=st.text(min_size=0, max_size=20),
    index_ref=st.text(min_size=0, max_size=10),
)
def test_d1_15_export_import_round_trip(
    debtor: str,
    balance: float,
    loss_rate: float,
    actual_provision: float,
    basis: str,
    index_ref: str,
) -> None:
    """D1-15 ECL测算表 export → import round-trip preserves user-input fields.

    Computed columns D (shouldProvision=B×C) and F (difference=E-D) are
    ignored on import since they are recalculated from user inputs.

    **Validates: Requirements 13.2, 13.3**
    """
    headers = _SHEET_HEADERS["D1-15"]

    # Build input row data matching the expected dict format
    original = {
        "debtor": debtor,
        "balance": balance,
        "lossRate": loss_rate,
        "actualProvision": actual_provision,
        "basis": basis,
        "indexRef": index_ref,
    }

    # Export: dict → list of 8 cell values
    exported = _export_d1_15_row(original)
    assert len(exported) == len(headers), f"Expected {len(headers)} columns, got {len(exported)}"

    # Import: tuple of cell values → dict (simulating reading from xlsx row)
    imported = _parse_d1_15_row(tuple(exported), headers)

    # Verify user-input fields survive the round-trip
    assert imported["debtor"] == debtor.strip()
    assert abs(imported["balance"] - balance) < 1e-6
    assert abs(imported["lossRate"] - loss_rate) < 1e-6
    # actualProvision is stored in column E (账面余额)
    assert abs(imported["actualProvision"] - actual_provision) < 1e-6
    assert imported["basis"] == basis.strip()
    assert imported["indexRef"] == index_ref.strip()

    # id is regenerated (new UUID) on import
    assert imported["id"] != ""


# ═══════════════════════════════════════════════════════════════════════════════
# Standard pytest tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_d1_15_template_has_correct_structure() -> None:
    """Verify D1-15 template workbook has 8 column headers + 2 section marker rows.

    **Validates: Requirements 13.2**
    """
    wb = _create_template_wb("D1-15")
    ws = wb.active

    # Verify 8 column headers in row 1
    actual_headers = [
        cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))
        if cell.value is not None
    ]
    expected = _SHEET_HEADERS["D1-15"]
    assert actual_headers == expected, f"Headers mismatch: {actual_headers}"
    assert len(actual_headers) == 8, f"Expected 8 headers, got {len(actual_headers)}"

    # Verify 2 section marker rows exist
    section_markers_found = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        first_cell = row[0] if row else None
        if first_cell and isinstance(first_cell, str):
            if "按组合计提" in first_cell:
                section_markers_found.append("portfolio")
            elif "按单项计提" in first_cell:
                section_markers_found.append("individual")

    assert "portfolio" in section_markers_found, "Missing '按组合计提' section marker"
    assert "individual" in section_markers_found, "Missing '按单项计提' section marker"
    assert len(section_markers_found) == 2, f"Expected 2 section markers, found {len(section_markers_found)}"


def test_is_section_marker_detects_portfolio() -> None:
    """_is_section_marker correctly detects portfolio section marker."""
    row = (_D1_15_SECTION_PORTFOLIO, None, None, None, None, None, None, None)
    assert _is_section_marker(row) == "portfolio"


def test_is_section_marker_detects_individual() -> None:
    """_is_section_marker correctly detects individual section marker."""
    row = (_D1_15_SECTION_INDIVIDUAL, None, None, None, None, None, None, None)
    assert _is_section_marker(row) == "individual"


def test_is_section_marker_returns_none_for_data_row() -> None:
    """_is_section_marker returns None for normal data rows."""
    row = ("客户A", 100000, 0.05, 5000, 4500, -500, "账龄法", "D1-1")
    assert _is_section_marker(row) is None


def test_is_section_marker_returns_none_for_empty_row() -> None:
    """_is_section_marker returns None for empty rows."""
    assert _is_section_marker(()) is None
    assert _is_section_marker((None, None, None)) is None


def test_validate_columns_accepts_correct_headers() -> None:
    """_validate_columns returns empty list when headers are correct."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for col_idx, col_name in enumerate(_SHEET_HEADERS["D1-15"], 1):
        ws.cell(row=1, column=col_idx, value=col_name)

    missing = _validate_columns(ws, "D1-15")
    assert missing == [], f"Unexpected missing columns: {missing}"


def test_validate_columns_rejects_wrong_column_count() -> None:
    """_validate_columns detects wrong column count (not 8)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    # Only put 5 columns instead of required 8
    for col_idx, col_name in enumerate(_SHEET_HEADERS["D1-15"][:5], 1):
        ws.cell(row=1, column=col_idx, value=col_name)

    missing = _validate_columns(ws, "D1-15")
    assert len(missing) > 0, "Should detect column count mismatch"
    # The error message should mention column count
    assert any("列数" in msg for msg in missing), f"Expected column count error, got: {missing}"


def test_validate_columns_rejects_missing_headers() -> None:
    """_validate_columns detects missing header names when count is 8."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    # Put 8 columns but with some wrong names
    tampered_headers = list(_SHEET_HEADERS["D1-15"])
    tampered_headers[0] = "错误列名A"
    tampered_headers[2] = "错误列名C"
    for col_idx, col_name in enumerate(tampered_headers, 1):
        ws.cell(row=1, column=col_idx, value=col_name)

    missing = _validate_columns(ws, "D1-15")
    assert "债务人名称" in missing, f"Should detect missing '债务人名称', got: {missing}"
    assert "预期信用损失率" in missing, f"Should detect missing '预期信用损失率', got: {missing}"


def test_export_d1_15_row_computes_d_and_f_columns() -> None:
    """_export_d1_15_row correctly computes D (shouldProvision=B×C) and F (difference=E-D)."""
    data = {
        "debtor": "客户甲",
        "balance": 100000.0,
        "lossRate": 0.05,
        "actualProvision": 4500.0,
        "basis": "账龄法",
        "indexRef": "D1-1",
    }
    exported = _export_d1_15_row(data)

    # D = B × C = 100000 × 0.05 = 5000
    assert abs(exported[3] - 5000.0) < 1e-6, f"D column should be 5000, got {exported[3]}"
    # F = E - D = 4500 - 5000 = -500
    assert abs(exported[5] - (-500.0)) < 1e-6, f"F column should be -500, got {exported[5]}"


def test_parse_d1_15_row_ignores_computed_columns() -> None:
    """_parse_d1_15_row ignores D and F columns (computed on import)."""
    headers = _SHEET_HEADERS["D1-15"]
    # Row with D=9999 and F=8888 (should be ignored)
    row = ("债务人B", 200000.0, 0.10, 9999.0, 18000.0, 8888.0, "个别认定", "D1-4")

    parsed = _parse_d1_15_row(tuple(row), headers)

    assert parsed["debtor"] == "债务人B"
    assert abs(parsed["balance"] - 200000.0) < 1e-6
    assert abs(parsed["lossRate"] - 0.10) < 1e-6
    # actualProvision reads from E column (账面余额)
    assert abs(parsed["actualProvision"] - 18000.0) < 1e-6
    assert parsed["basis"] == "个别认定"
    assert parsed["indexRef"] == "D1-4"
