"""E1 货币资金导入导出 — hypothesis 测试

测试:
1. Round-trip: export-data → reimport → verify same row count
2. Template validation: exported template has correct column headers
3. Column tamper: import with wrong column names → 400

Requirements: 13.2
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, strategies as st
from openpyxl import Workbook, load_workbook

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.wp_render_strategies._e1_import_export import (
    _create_template_wb,
    _export_row,
    _parse_row,
    _validate_columns,
    _SHEET_HEADERS,
    _SUPPORTED_SHEETS,
    _FIELD_MAPS,
    _NUMERIC_FIELDS,
    _SHEET_ITEM_ID,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════════════════════

sheet_strategy = st.sampled_from(sorted(_SUPPORTED_SHEETS))

# Generate random row data conforming to a sheet's field map
def _row_data_strategy(sheet_code: str):
    field_map = _FIELD_MAPS.get(sheet_code, {})
    numeric_fields = _NUMERIC_FIELDS.get(sheet_code, set())
    fields = {}
    for _col_name, json_field in field_map.items():
        if json_field in numeric_fields:
            fields[json_field] = st.floats(
                min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False
            )
        else:
            fields[json_field] = st.text(
                alphabet=st.characters(whitelist_categories=("L", "N", "P")),
                min_size=0,
                max_size=20,
            )
    fields["rowId"] = st.just(str(uuid4()))
    return st.fixed_dictionaries(fields)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1: Template column headers validation
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(sheet=sheet_strategy)
def test_template_has_correct_headers(sheet: str):
    """Exported template has correct column headers matching _SHEET_HEADERS."""
    wb = _create_template_wb(sheet)
    ws = wb.active

    expected_headers = _SHEET_HEADERS[sheet]
    actual_headers: list[str] = []
    for cell in next(ws.iter_rows(min_row=1, max_row=1)):
        if cell.value is not None:
            actual_headers.append(str(cell.value).strip())

    assert actual_headers == expected_headers, (
        f"Sheet {sheet}: expected {expected_headers}, got {actual_headers}"
    )

    # Freeze panes at A2
    assert ws.freeze_panes == "A2"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2: Round-trip (export → parse → same row count)
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(sheet=sheet_strategy, num_rows=st.integers(min_value=1, max_value=10))
def test_round_trip_row_count(sheet: str, num_rows: int):
    """Export N rows → create xlsx → parse back → row count matches."""
    field_map = _FIELD_MAPS.get(sheet, {})
    numeric_fields = _NUMERIC_FIELDS.get(sheet, set())

    # Generate test rows
    rows: list[dict] = []
    for _ in range(num_rows):
        row_data: dict = {"rowId": str(uuid4())}
        for _col_name, json_field in field_map.items():
            if json_field in numeric_fields:
                row_data[json_field] = 123.45
            else:
                row_data[json_field] = "test_value"
        rows.append(row_data)

    # Export to xlsx
    wb = _create_template_wb(sheet)
    ws = wb.active
    for data_row in rows:
        ws.append(_export_row(sheet, data_row))

    # Save to bytes
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    # Re-read and parse
    wb2 = load_workbook(buffer, read_only=True, data_only=True)
    ws2 = wb2.active
    actual_headers: list[str] = []
    for cell in next(ws2.iter_rows(min_row=1, max_row=1)):
        if cell.value is not None:
            actual_headers.append(str(cell.value).strip())

    parsed_rows: list[dict] = []
    for row in ws2.iter_rows(min_row=2, values_only=True):
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        parsed_rows.append(_parse_row(sheet, row, actual_headers))

    assert len(parsed_rows) == num_rows, (
        f"Sheet {sheet}: exported {num_rows} rows but parsed back {len(parsed_rows)}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3: Column tamper → validation fails
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(sheet=sheet_strategy)
def test_column_tamper_detected(sheet: str):
    """Workbook with wrong column names → _validate_columns returns missing list."""
    wb = Workbook()
    ws = wb.active
    # Write wrong headers
    wrong_headers = ["错误列A", "错误列B", "错误列C"]
    for col_idx, col_name in enumerate(wrong_headers, 1):
        ws.cell(row=1, column=col_idx, value=col_name)

    missing = _validate_columns(ws, sheet)
    expected_headers = set(_SHEET_HEADERS[sheet])

    # All expected headers should be reported as missing
    assert len(missing) == len(expected_headers), (
        f"Sheet {sheet}: expected {len(expected_headers)} missing columns, "
        f"got {len(missing)}"
    )
    # Each missing item should be from the expected set
    for col in missing:
        assert col in expected_headers
