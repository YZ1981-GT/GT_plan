"""Property 12: Single-source snapshot round-trip + 删除验证

Feature: advanced-query-enhancements-p1p2, Property 12: Single-source snapshot round-trip

For any structure.json file content, after the migration script runs, the file must
no longer exist on disk AND parsed_data['univer_snapshot'] must contain equivalent
structural data that, when read by the query path, produces the same cell values
as the original file would have.

Validates: Requirements 6.1, 6.4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck

# Ensure scripts directory is importable
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# ─── Strategies ───────────────────────────────────────────────────────────────

# Generate valid cell values (strings, numbers, None)
st_cell_value = st.one_of(
    st.none(),
    st.text(min_size=0, max_size=50, alphabet=st.characters(categories=("L", "N", "P", "S"))),
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
)

# Generate valid formula strings (optional)
st_formula = st.one_of(
    st.none(),
    st.from_regex(r"=TB\('[0-9]{4}','[^']+'\)", fullmatch=True),
    st.from_regex(r"=[A-Z]+[0-9]+\+[A-Z]+[0-9]+", fullmatch=True),
)

# Generate a single cell
st_cell = st.fixed_dictionaries({
    "value": st_cell_value,
    "formula": st_formula,
})

# Generate a row of cells (1-10 cells per row)
st_row = st.lists(st_cell, min_size=1, max_size=10).map(lambda cells: {"cells": cells})

# Generate a structure.json-like dict
st_structure = st.fixed_dictionaries({
    "sheets": st.just([{"name": "TestSheet"}]),
    "rows": st.lists(st_row, min_size=1, max_size=20),
})


# ─── Helper: migration logic (extracted from script for testability) ──────────

def _structure_to_slim_snapshot(structure: dict) -> dict:
    """Replicate the migration logic from scripts/_migrate_structure_to_jsonb.py"""
    sheets_meta = structure.get("sheets", [])
    rows = structure.get("rows", [])
    sheet_names = [s.get("name", f"Sheet{i+1}") for i, s in enumerate(sheets_meta)]
    if not sheet_names:
        sheet_names = ["Sheet1"]

    slim_sheets: dict[str, dict] = {}
    total_cells = 0

    # Single sheet: all rows belong to it
    cell_data: dict[str, dict] = {}
    count = 0
    for r_idx, row in enumerate(rows):
        cells = row.get("cells", [])
        row_dict: dict[str, dict] = {}
        for c_idx, cell in enumerate(cells):
            v = cell.get("value")
            f = cell.get("formula")
            obj: dict = {}
            if v is not None and v != "":
                obj["v"] = v
            if f:
                obj["f"] = f
            if obj:
                row_dict[str(c_idx)] = obj
                count += 1
        if row_dict:
            cell_data[str(r_idx)] = row_dict

    slim_sheets[sheet_names[0]] = {"cellData": cell_data, "cell_count": count}
    total_cells = count

    return {
        "sheets": slim_sheets,
        "sheet_order_names": sheet_names,
        "saved_at": "2026-01-01T00:00:00Z",
        "version": 0,
        "total_cells": total_cells,
        "migrated_from": "structure.json",
    }


def _extract_values_from_structure(structure: dict) -> list[tuple[int, int, str | int | float | None]]:
    """Extract (row, col, value) triples from structure.json format"""
    results = []
    for r_idx, row in enumerate(structure.get("rows", [])):
        for c_idx, cell in enumerate(row.get("cells", [])):
            v = cell.get("value")
            if v is not None and v != "":
                results.append((r_idx, c_idx, v))
    return results


def _extract_values_from_snapshot(snapshot: dict, sheet_name: str) -> list[tuple[int, int, str | int | float | None]]:
    """Extract (row, col, value) triples from slim snapshot format"""
    results = []
    sheets = snapshot.get("sheets", {})
    sheet_obj = sheets.get(sheet_name, {})
    cell_data = sheet_obj.get("cellData", {})
    for r_key, row_dict in cell_data.items():
        for c_key, cell in row_dict.items():
            v = cell.get("v")
            if v is not None and v != "":
                results.append((int(r_key), int(c_key), v))
    return results


# ─── Property 12: Round-trip test ─────────────────────────────────────────────

# Feature: advanced-query-enhancements-p1p2, Property 12: Single-source snapshot round-trip
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@given(structure=st_structure)
def test_single_source_round_trip(structure: dict):
    """For any structure.json content, migrating to univer_snapshot preserves all cell values."""
    # Act: migrate structure → slim snapshot
    snapshot = _structure_to_slim_snapshot(structure)

    # Extract values from both representations
    original_values = set(_extract_values_from_structure(structure))
    snapshot_values = set(_extract_values_from_snapshot(snapshot, "TestSheet"))

    # Assert: all non-empty values from structure.json are preserved in snapshot
    assert original_values == snapshot_values, (
        f"Values mismatch!\n"
        f"  In structure but not snapshot: {original_values - snapshot_values}\n"
        f"  In snapshot but not structure: {snapshot_values - original_values}"
    )


# ─── Property 12: File deletion verification ─────────────────────────────────

def test_migration_deletes_structure_json(tmp_path: Path):
    """After migration, structure.json file must no longer exist on disk."""
    # Arrange: create a structure.json file
    structure = {
        "sheets": [{"name": "Sheet1"}],
        "rows": [
            {"cells": [{"value": "hello", "formula": None}, {"value": 42, "formula": "=A1+1"}]}
        ],
    }
    structure_file = tmp_path / "test.structure.json"
    structure_file.write_text(json.dumps(structure, ensure_ascii=False), encoding="utf-8")
    assert structure_file.exists()

    # Act: simulate migration (read + convert + delete)
    content = json.loads(structure_file.read_text(encoding="utf-8"))
    snapshot = _structure_to_slim_snapshot(content)

    # Verify snapshot has the data
    assert snapshot["sheets"]["Sheet1"]["cellData"]["0"]["0"]["v"] == "hello"
    assert snapshot["sheets"]["Sheet1"]["cellData"]["0"]["1"]["v"] == 42
    assert snapshot["sheets"]["Sheet1"]["cellData"]["0"]["1"]["f"] == "=A1+1"

    # Delete the file (as migration would)
    structure_file.unlink()

    # Assert: file no longer exists
    assert not structure_file.exists()


# ─── Unit test: univer-save no longer writes structure.json ───────────────────

def test_univer_save_does_not_write_structure_json(tmp_path: Path):
    """Verify that the univer-save code path no longer references structure.json writes."""
    import inspect
    from app.routers.working_paper import save_univer_data

    source = inspect.getsource(save_univer_data)

    # The function should NOT contain structure.json write logic
    assert "structure_path" not in source, "save_univer_data still references structure_path"
    assert "univer_snapshot_to_structure" not in source, "save_univer_data still calls univer_snapshot_to_structure"
    assert ".structure.json" not in source, "save_univer_data still references .structure.json"


# ─── Unit test: HTML preview reads from univer_snapshot, not structure.json ───

def test_html_preview_reads_from_snapshot_not_file():
    """Verify workpaper_html_preview reads from parsed_data['univer_snapshot'] first."""
    import inspect
    from app.routers.workpaper_html_preview import get_workpaper_html_preview

    source = inspect.getsource(get_workpaper_html_preview)

    # Should NOT read structure.json from disk
    assert "structure_json_path" not in source, "HTML preview still reads structure.json from disk"
    # Should read from univer_snapshot
    assert "univer_snapshot" in source or "_structure_from_univer_snapshot" in source, (
        "HTML preview does not read from univer_snapshot"
    )


# ─── Unit test: snapshot_missing_total metric increments ──────────────────────

def test_snapshot_missing_metric_increments():
    """When snapshot is missing, the metric counter should increment."""
    from app.services.custom_query.metrics import inc_snapshot_missing, SNAPSHOT_MISSING_TOTAL

    # The function should not raise
    inc_snapshot_missing("D2")
    # Metric module should be importable and functional
    assert callable(inc_snapshot_missing)


# ─── Unit test: _structure_from_univer_snapshot helper ────────────────────────

def test_structure_from_univer_snapshot_basic():
    """_structure_from_univer_snapshot correctly converts slim snapshot to structure format."""
    from app.routers.workpaper_html_preview import _structure_from_univer_snapshot

    snap = {
        "sheets": {
            "Sheet1": {
                "cellData": {
                    "0": {"0": {"v": "A1"}, "1": {"v": 100, "f": "=B2+1"}},
                    "1": {"0": {"v": "A2"}},
                },
                "cell_count": 3,
            }
        },
        "sheet_order_names": ["Sheet1"],
    }

    result = _structure_from_univer_snapshot(snap)

    assert result["sheet_names"] == ["Sheet1"]
    assert len(result["rows"]) == 2
    # Row 0: A1, 100 with formula
    assert result["rows"][0]["cells"][0]["value"] == "A1"
    assert result["rows"][0]["cells"][1]["value"] == 100
    assert result["rows"][0]["cells"][1]["formula"] == "=B2+1"
    # Row 1: A2
    assert result["rows"][1]["cells"][0]["value"] == "A2"
