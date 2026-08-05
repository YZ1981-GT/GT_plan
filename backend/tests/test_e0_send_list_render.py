"""Unit tests for E0 send list render strategies.

Tests _initial_data, migrate_legacy_grid_payload, and render functions.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies._e0_send_list import (
    _initial_data,
    _render_send_list,
    migrate_legacy_grid_payload,
    render_e0_send_list_e03,
    render_e0_send_list_e04,
    render_e0_send_list_e05,
)
from app.services.e0_send_list.send_list_specs import (
    ALL_SHEETS,
    FORMAT_VERSION,
    SHEET_E03,
    SHEET_E04,
    SHEET_E05,
    SHEET_E06,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_ctx(html_data=None):
    """Build a minimal RenderContext-like object for testing."""
    ctx = MagicMock()
    ctx.sheet_html_data = html_data
    return ctx


# ─── Test 1: _initial_data returns rows==[] with correct _format ──────────────


@pytest.mark.parametrize("sheet", ALL_SHEETS)
def test_initial_data_returns_empty_rows_and_correct_format(sheet):
    result = _initial_data(sheet)
    assert result["rows"] == []
    assert result["_format"] == FORMAT_VERSION[sheet]
    assert "conclusion" in result
    assert result["conclusion"]["audit_explanation"] == ""
    assert result["conclusion"]["overall_conclusion"] == ""
    assert result["conclusion"]["remarks"] == ""


# ─── Test 2: Serialized initial data does NOT contain sample values ───────────


@pytest.mark.parametrize("sheet", [SHEET_E03, SHEET_E04, SHEET_E05])
def test_initial_data_no_sample_bank_names(sheet):
    """Initial data must not contain template example values."""
    result = _initial_data(sheet)
    serialized = json.dumps(result, ensure_ascii=False)
    assert "XX银行" not in serialized
    assert "XX财务公司" not in serialized


def test_fixture_with_sample_values_would_be_detected():
    """Reverse check: a fixture WITH sample values must be detectable."""
    polluted = {
        "_format": "send-list-e03-v1",
        "rows": [{"bank_name": "XX银行"}, {"bank_name": "XX财务公司"}],
        "conclusion": {"audit_explanation": "", "overall_conclusion": "", "remarks": ""},
    }
    serialized = json.dumps(polluted, ensure_ascii=False)
    assert "XX银行" in serialized
    assert "XX财务公司" in serialized


# ─── Test 3: migrate_legacy_grid_payload is idempotent ────────────────────────


def test_migrate_idempotent():
    """Applying migration twice yields the same result."""
    legacy = {
        "cells": {"A6": {"v": "基本存款账户"}, "B6": {"v": "IDX-001"}},
        "column_meta": {},
        "header_rows": 1,
    }
    first = migrate_legacy_grid_payload(SHEET_E03, legacy)
    second = migrate_legacy_grid_payload(SHEET_E03, first)
    assert first == second


# ─── Test 4: Migration preserves _row_id ──────────────────────────────────────


def test_migrate_preserves_row_ids():
    """Output row IDs are a superset of input row IDs."""
    legacy = {
        "cells": {"A6": {"v": "val1"}, "A7": {"v": "val2"}},
        "column_meta": {},
        "rows": [
            {"_row_id": "existing-id-1"},
            {"_row_id": "existing-id-2"},
        ],
    }
    result = migrate_legacy_grid_payload(SHEET_E03, legacy)
    output_ids = {r.get("_row_id") for r in result["rows"]}
    input_ids = {"existing-id-1", "existing-id-2"}
    assert input_ids.issubset(output_ids)


# ─── Test 5: Migration preserves conclusion three keys ────────────────────────


def test_migrate_preserves_conclusion():
    legacy = {
        "cells": {"A6": {"v": "test"}},
        "column_meta": {},
        "conclusion": {
            "audit_explanation": "说明内容",
            "overall_conclusion": "结论内容",
            "remarks": "备注内容",
        },
    }
    result = migrate_legacy_grid_payload(SHEET_E03, legacy)
    assert result["conclusion"]["audit_explanation"] == "说明内容"
    assert result["conclusion"]["overall_conclusion"] == "结论内容"
    assert result["conclusion"]["remarks"] == "备注内容"


# ─── Test 6: Unmapped cells go to _unmapped_cells ─────────────────────────────


def test_unmapped_cells_preserved():
    """Columns not in manifest go to _unmapped_cells, not silently lost."""
    legacy = {
        "cells": {
            "A6": {"v": "基本存款账户"},  # A is in E03 column_map
            "Z6": {"v": "unexpected_value"},  # Z is NOT in any column_map
        },
        "column_meta": {},
    }
    result = migrate_legacy_grid_payload(SHEET_E03, legacy)
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert "_unmapped_cells" in row
    assert row["_unmapped_cells"]["Z"] == "unexpected_value"


# ─── Test 7: Already-migrated data passes through unchanged ───────────────────


def test_already_migrated_passes_through():
    """Data with correct _format is returned unchanged."""
    migrated = {
        "_format": FORMAT_VERSION[SHEET_E04],
        "rows": [{"bank_name": "测试银行", "_row_id": "r1"}],
        "conclusion": {
            "audit_explanation": "已审",
            "overall_conclusion": "无异常",
            "remarks": "",
        },
    }
    result = migrate_legacy_grid_payload(SHEET_E04, migrated)
    assert result is migrated  # same object, not copy


# ─── Test 8: Empty input returns initial data ─────────────────────────────────


@pytest.mark.parametrize("empty_input", [{}, None])
def test_empty_input_returns_initial(empty_input):
    """Empty or None-equivalent input returns initial data."""
    if empty_input is None:
        # migrate_legacy_grid_payload expects a dict, but _render_send_list
        # handles None before calling it. Test via render path.
        ctx = _make_ctx(html_data=None)
        result = _render_send_list(SHEET_E03, ctx)
    else:
        result = migrate_legacy_grid_payload(SHEET_E03, empty_input)
    assert result["_format"] == FORMAT_VERSION[SHEET_E03]
    assert result["rows"] == []


# ─── Test 9: render functions with None ctx return initial data ───────────────


@pytest.mark.parametrize(
    "render_fn,sheet",
    [
        (render_e0_send_list_e03, SHEET_E03),
        (render_e0_send_list_e04, SHEET_E04),
        (render_e0_send_list_e05, SHEET_E05),
    ],
)
def test_render_with_none_html_data_returns_initial(render_fn, sheet):
    ctx = _make_ctx(html_data=None)
    result = asyncio.run(render_fn(ctx))
    assert result["_format"] == FORMAT_VERSION[sheet]
    assert result["rows"] == []


# ─── Test 10: Source code does NOT contain extract_grid or data_only ──────────


def test_source_code_no_extract_grid_or_data_only():
    """Property 3: render strategy source must not contain extract_grid or data_only."""
    source_path = Path(__file__).resolve().parents[1] / (
        "app/routers/wp_render_strategies/_e0_send_list.py"
    )
    source = source_path.read_text(encoding="utf-8")
    # Strip comments (lines starting with #) and docstrings
    lines = []
    in_docstring = False
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            if stripped.count('"""') == 1 or stripped.count("'''") == 1:
                in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if stripped.startswith("#"):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    assert "extract_grid" not in cleaned
    assert "data_only" not in cleaned


# ─── Test 11: PBT — random legacy payload → idempotent + _row_id superset ────


try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    _cell_ref_st = st.from_regex(r"[A-P][6-9]|[A-P]1[0-9]|[A-P]2[0-4]", fullmatch=True)
    _cell_value_st = st.one_of(
        st.fixed_dictionaries({"v": st.one_of(st.text(min_size=1, max_size=20), st.integers(0, 99999))}),
        st.text(min_size=1, max_size=20),
    )

    @settings(max_examples=5)
    @given(
        cells=st.dictionaries(_cell_ref_st, _cell_value_st, min_size=0, max_size=10),
        row_ids=st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=5),
    )
    def test_pbt_migrate_idempotent_and_row_id_superset(cells, row_ids):
        """PBT: random legacy → idempotent + _row_id superset."""
        legacy = {
            "cells": cells,
            "column_meta": {},
            "rows": [{"_row_id": rid} for rid in row_ids],
        }
        first = migrate_legacy_grid_payload(SHEET_E03, legacy)
        second = migrate_legacy_grid_payload(SHEET_E03, first)

        # Idempotent
        assert first == second

        # _row_id superset: output IDs ⊇ input IDs (for rows that were migrated)
        output_ids = {r.get("_row_id") for r in first.get("rows", [])}
        input_ids = set(row_ids[: len(first.get("rows", []))])
        assert input_ids.issubset(output_ids)

except ImportError:
    pass  # hypothesis not installed — skip PBT
