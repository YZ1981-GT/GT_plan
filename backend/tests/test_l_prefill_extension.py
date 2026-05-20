"""
Tests for L-cycle prefill extension (≥ 40 cells across 7 sheets).
Validates: Requirements L-F6

Verifies:
1. Total new L-cycle prefill cells ≥ 40
2. All AUX formulas are 4-arg (count commas == 3)
3. Sheet names match real openpyxl-extracted names (no trailing spaces)
4. Per-sheet minimums: L1-2≥8, L1-5≥6, L3-2≥8, L3-5≥6, L5-2≥4, L6-2≥4, L8-2≥4
"""
import json
from pathlib import Path

import pytest

MAPPING_FILE = Path(__file__).parent.parent / "data" / "prefill_formula_mapping.json"

# Real sheet names from Sprint 0.X openpyxl extraction (no trailing spaces)
REAL_SHEET_NAMES = {
    "明细表L1-2",
    "利息测算表L1-5",
    "明细表L3-2",
    "利息测算表L3-5",
    "明细表L5-2",
    "明细表L6-2",
    "明细表L8-2",
}

# Per-sheet minimum cell counts
SHEET_MINIMUMS = {
    "明细表L1-2": 8,
    "利息测算表L1-5": 6,
    "明细表L3-2": 8,
    "利息测算表L3-5": 6,
    "明细表L5-2": 4,
    "明细表L6-2": 4,
    "明细表L8-2": 4,
}


@pytest.fixture(scope="module")
def prefill_data():
    """Load prefill_formula_mapping.json."""
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def l_extension_entries(prefill_data):
    """Filter entries for the 7 L-cycle extension sheets."""
    return [
        m for m in prefill_data["mappings"]
        if m["sheet"] in REAL_SHEET_NAMES
    ]


class TestLPrefillExtensionCount:
    """Test total cell count meets ≥ 40 requirement."""

    def test_total_cells_ge_40(self, l_extension_entries):
        """Total new L-cycle prefill cells must be ≥ 40."""
        total_cells = sum(len(entry["cells"]) for entry in l_extension_entries)
        assert total_cells >= 40, (
            f"Expected ≥ 40 L-cycle prefill cells, got {total_cells}"
        )

    def test_entries_count_is_7(self, l_extension_entries):
        """Should have exactly 7 entries (one per target sheet)."""
        assert len(l_extension_entries) == 7, (
            f"Expected 7 L-cycle extension entries, got {len(l_extension_entries)}"
        )


class TestAuxFormulas4Arg:
    """All AUX formulas must be 4-arg: =AUX(account_code, aux_type, aux_code, column)."""

    def test_all_aux_formulas_have_4_args(self, l_extension_entries):
        """Every =AUX formula must have exactly 3 commas (4 arguments)."""
        violations = []
        for entry in l_extension_entries:
            for cell in entry["cells"]:
                formula = cell["formula"]
                if formula.startswith("=AUX("):
                    # Extract content between =AUX( and )
                    inner = formula[5:-1]  # strip =AUX( and )
                    comma_count = inner.count(",")
                    if comma_count != 3:
                        violations.append(
                            f"{entry['sheet']}/{cell['cell_ref']}: "
                            f"formula={formula} has {comma_count} commas (expected 3)"
                        )
        assert not violations, (
            f"AUX formulas with wrong arg count:\n" + "\n".join(violations)
        )

    def test_aux_formulas_exist(self, l_extension_entries):
        """At least some entries should use =AUX formulas (L1-2, L6-2, L8-2)."""
        aux_count = sum(
            1 for entry in l_extension_entries
            for cell in entry["cells"]
            if cell["formula"].startswith("=AUX(")
        )
        # L1-2 has ≥8 AUX + L6-2 has ≥4 AUX + L8-2 has ≥3 AUX = ≥15
        assert aux_count >= 15, (
            f"Expected ≥ 15 AUX formulas across L1-2/L6-2/L8-2, got {aux_count}"
        )


class TestSheetNames:
    """Sheet names must match real openpyxl-extracted names (no trailing spaces)."""

    def test_no_trailing_spaces(self, l_extension_entries):
        """No sheet name should have trailing whitespace."""
        for entry in l_extension_entries:
            sheet = entry["sheet"]
            assert sheet == sheet.rstrip(), (
                f"Sheet name has trailing space: repr={repr(sheet)}"
            )

    def test_sheet_names_match_real_names(self, l_extension_entries):
        """All sheet names must be in the known real sheet name set."""
        found_sheets = {entry["sheet"] for entry in l_extension_entries}
        assert found_sheets == REAL_SHEET_NAMES, (
            f"Sheet name mismatch.\n"
            f"  Expected: {REAL_SHEET_NAMES}\n"
            f"  Got: {found_sheets}"
        )


class TestPerSheetMinimums:
    """Each sheet must meet its minimum cell count."""

    @pytest.mark.parametrize("sheet_name,min_cells", list(SHEET_MINIMUMS.items()))
    def test_sheet_minimum(self, l_extension_entries, sheet_name, min_cells):
        """Each target sheet must have at least the specified minimum cells."""
        matching = [e for e in l_extension_entries if e["sheet"] == sheet_name]
        assert len(matching) == 1, (
            f"Expected exactly 1 entry for {sheet_name}, got {len(matching)}"
        )
        actual_cells = len(matching[0]["cells"])
        assert actual_cells >= min_cells, (
            f"{sheet_name}: expected ≥ {min_cells} cells, got {actual_cells}"
        )


class TestFormulaTypes:
    """Verify formula types are valid and consistent."""

    VALID_FORMULA_TYPES = {"TB", "TB_SUM", "AUX", "PREV", "LEDGER", "LEDGER_DETAIL", "ADJ", "WP"}

    def test_all_formula_types_valid(self, l_extension_entries):
        """All formula_type values must be in the known set."""
        for entry in l_extension_entries:
            for cell in entry["cells"]:
                assert cell["formula_type"] in self.VALID_FORMULA_TYPES, (
                    f"{entry['sheet']}/{cell['cell_ref']}: "
                    f"unknown formula_type={cell['formula_type']}"
                )

    def test_formula_prefix_matches_type(self, l_extension_entries):
        """Formula string prefix should be consistent with formula_type."""
        for entry in l_extension_entries:
            for cell in entry["cells"]:
                formula = cell["formula"]
                ftype = cell["formula_type"]
                if ftype == "AUX":
                    assert formula.startswith("=AUX("), (
                        f"formula_type=AUX but formula={formula}"
                    )
                elif ftype == "TB":
                    assert formula.startswith("=TB("), (
                        f"formula_type=TB but formula={formula}"
                    )
                elif ftype == "PREV":
                    assert formula.startswith("=PREV("), (
                        f"formula_type=PREV but formula={formula}"
                    )
                elif ftype in ("LEDGER", "LEDGER_DETAIL"):
                    assert formula.startswith("=LEDGER_DETAIL("), (
                        f"formula_type={ftype} but formula={formula}"
                    )


class TestIdempotency:
    """Verify (wp_code, sheet) uniqueness as idempotent key."""

    def test_no_duplicate_wp_code_sheet_pairs(self, prefill_data):
        """No duplicate (wp_code, sheet) pairs in the entire mapping file."""
        seen = set()
        duplicates = []
        for entry in prefill_data["mappings"]:
            key = (entry["wp_code"], entry["sheet"])
            if key in seen:
                duplicates.append(key)
            seen.add(key)
        assert not duplicates, (
            f"Duplicate (wp_code, sheet) pairs found: {duplicates}"
        )
