"""
Tests for N-cycle prefill extension (N-F6).

Validates: Requirements N-F6
- N cycle total cells ≥ 53 (28 baseline + ≥25 new)
- N2 entries use =AUX(4-arg) format (4 commas = 4 args)
- N1/N3/N4/N5 entries use =TB or =WP format
- Sheet names match real template names (including trailing space for N4A)
- No duplicate (wp_code, sheet, cell_ref) combinations
- All formulas are syntactically valid
"""

import json
import re
from pathlib import Path

import pytest

DATA_PATH = Path(__file__).parent.parent / "data" / "prefill_formula_mapping.json"

# Real sheet names from Sprint 0x.2 (openpyxl extraction)
REAL_N_SHEET_NAMES = {
    "明细表N1-2",
    "明细表N2-2",
    "明细表N3-2",
    "明细表N4-2",
    "税金及附加审计程序表N4A ",  # trailing space!
    "明细表N5-2",
    "N5-4当期所得税费用计算表",
    "N5-8递延所得税费用核对表",
}

# Baseline sheets (existing before extension)
BASELINE_SHEETS = {
    "审定表N1-1",
    "应交税费审定表N2-1",
    "递延所得税负债审定表N3-1",
    "税金及附加审定表N4-1",
    "所得税费用审定表N5-1",
    "分析程序N1-3",
}

# Valid formula patterns
VALID_FORMULA_PATTERNS = [
    re.compile(r"^=TB\('.+','.+'\)$"),
    re.compile(r"^=TB_SUM\('.+','.+'\)$"),
    re.compile(r"^=ADJ\('.+','.+'\)$"),
    re.compile(r"^=PREV\('.+','.+','.+'\)$"),
    re.compile(r"^=WP\('.+','.+','.+'\)$"),
    re.compile(r"^=AUX\('.+','.+','.+','.+'\)$"),
    re.compile(r"^=LEDGER\('.+','.+','.+'\)$"),
    re.compile(r"^=LEDGER_DETAIL\('.+','.+','.+'\)$"),
]


@pytest.fixture(scope="module")
def prefill_data():
    """Load the prefill formula mapping data."""
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def n_entries(prefill_data):
    """Extract all N-cycle entries."""
    return [e for e in prefill_data["mappings"] if e["wp_code"].startswith("N")]


@pytest.fixture(scope="module")
def n_cells_total(n_entries):
    """Total cell count across all N-cycle entries."""
    return sum(len(e["cells"]) for e in n_entries)


@pytest.fixture(scope="module")
def n_new_entries(n_entries):
    """Extract only the new extension entries (non-baseline sheets)."""
    return [e for e in n_entries if e["sheet"] not in BASELINE_SHEETS]


class TestNPrefillTotalCells:
    """N cycle total cells must be ≥ 53 (28 baseline + ≥25 new)."""

    def test_total_cells_ge_53(self, n_cells_total):
        assert n_cells_total >= 53, (
            f"N-cycle total cells = {n_cells_total}, expected ≥ 53"
        )

    def test_new_cells_ge_25(self, n_new_entries):
        """New cells added must be ≥ 25."""
        new_cells = sum(len(e["cells"]) for e in n_new_entries)
        assert new_cells >= 25, (
            f"New N cells = {new_cells}, expected ≥ 25"
        )


class TestN2AUXFormat:
    """N2 entries must use =AUX(4-arg) format."""

    def test_n2_detail_uses_aux_4arg(self, n_entries):
        """N2 明细表N2-2 entries must use =AUX with exactly 4 arguments."""
        n2_detail_entries = [e for e in n_entries if e["sheet"] == "明细表N2-2"]
        assert len(n2_detail_entries) > 0, "No N2 明细表N2-2 entry found"

        violations = []
        for entry in n2_detail_entries:
            for cell in entry["cells"]:
                formula = cell["formula"]
                if not formula or not formula.startswith("=AUX("):
                    violations.append(
                        f"{cell['cell_ref']}: formula '{formula}' is not =AUX"
                    )
                    continue
                # Count commas inside AUX() - 3 commas = 4 args
                inner = formula[5:-1]  # strip =AUX( and )
                args = [a.strip() for a in inner.split(",")]
                if len(args) != 4:
                    violations.append(
                        f"{cell['cell_ref']}: {formula} has {len(args)} args, expected 4"
                    )
        assert not violations, (
            f"N2 AUX format violations:\n" + "\n".join(violations)
        )

    def test_n2_aux_has_tax_rate_type(self, n_entries):
        """N2 AUX formulas must use aux_type='税率'."""
        n2_detail_entries = [e for e in n_entries if e["sheet"] == "明细表N2-2"]
        for entry in n2_detail_entries:
            for cell in entry["cells"]:
                formula = cell["formula"]
                inner = formula[5:-1]
                args = [a.strip().strip("'") for a in inner.split(",")]
                assert args[0] == "2221", (
                    f"{cell['cell_ref']}: account_code should be '2221', got '{args[0]}'"
                )
                assert args[1] == "税率", (
                    f"{cell['cell_ref']}: aux_type should be '税率', got '{args[1]}'"
                )

    def test_n2_detail_ge_8_cells(self, n_entries):
        """N2 明细表N2-2 must have ≥ 8 cells."""
        n2_cells = sum(
            len(e["cells"]) for e in n_entries if e["sheet"] == "明细表N2-2"
        )
        assert n2_cells >= 8, f"N2 detail cells = {n2_cells}, expected ≥ 8"


class TestN1N3N4N5FormulaFormat:
    """N1/N3/N4/N5 entries must use =TB or =WP format (not =AUX)."""

    def test_n1_detail_uses_tb(self, n_entries):
        """N1 明细表N1-2 entries must use =TB format."""
        n1_entries = [e for e in n_entries if e["sheet"] == "明细表N1-2"]
        assert len(n1_entries) > 0, "No N1 明细表N1-2 entry found"
        for entry in n1_entries:
            for cell in entry["cells"]:
                formula = cell["formula"]
                assert formula.startswith("=TB("), (
                    f"N1/{cell['cell_ref']}: expected =TB, got '{formula}'"
                )

    def test_n1_detail_ge_6_cells(self, n_entries):
        """N1 明细表N1-2 must have ≥ 6 cells."""
        n1_cells = sum(
            len(e["cells"]) for e in n_entries if e["sheet"] == "明细表N1-2"
        )
        assert n1_cells >= 6, f"N1 detail cells = {n1_cells}, expected ≥ 6"

    def test_n3_detail_ge_4_cells(self, n_entries):
        """N3 明细表N3-2 must have ≥ 4 cells."""
        n3_cells = sum(
            len(e["cells"]) for e in n_entries if e["sheet"] == "明细表N3-2"
        )
        assert n3_cells >= 4, f"N3 detail cells = {n3_cells}, expected ≥ 4"

    def test_n4_detail_ge_4_cells(self, n_entries):
        """N4 sheets (明细表N4-2 + 审计程序表N4A) must have ≥ 4 cells total."""
        n4_cells = sum(
            len(e["cells"])
            for e in n_entries
            if e["wp_code"] == "N4" and e["sheet"] in REAL_N_SHEET_NAMES
        )
        assert n4_cells >= 4, f"N4 new cells = {n4_cells}, expected ≥ 4"

    def test_n5_new_sheets_ge_3_cells(self, n_entries):
        """N5 new sheets must have ≥ 3 cells total."""
        n5_new_sheets = {"明细表N5-2", "N5-4当期所得税费用计算表", "N5-8递延所得税费用核对表"}
        n5_cells = sum(
            len(e["cells"])
            for e in n_entries
            if e["wp_code"] == "N5" and e["sheet"] in n5_new_sheets
        )
        assert n5_cells >= 3, f"N5 new cells = {n5_cells}, expected ≥ 3"

    def test_n1_n3_n4_n5_no_aux(self, n_new_entries):
        """N1/N3/N4/N5 new entries must NOT use =AUX (only N2 uses AUX)."""
        violations = []
        for entry in n_new_entries:
            if entry["wp_code"] == "N2":
                continue  # N2 is allowed to use AUX
            for cell in entry["cells"]:
                formula = cell["formula"]
                if formula and formula.startswith("=AUX("):
                    violations.append(
                        f"{entry['wp_code']}/{entry['sheet']}/{cell['cell_ref']}: "
                        f"uses =AUX but should use =TB/=WP/=PREV"
                    )
        assert not violations, (
            f"Non-N2 entries using =AUX:\n" + "\n".join(violations)
        )


class TestSheetNames:
    """Sheet names must match real template names."""

    def test_new_sheets_are_real(self, n_new_entries):
        """All new entry sheet names must be in the real sheet name set."""
        for entry in n_new_entries:
            assert entry["sheet"] in REAL_N_SHEET_NAMES, (
                f"Sheet '{entry['sheet']}' (repr={repr(entry['sheet'])}) "
                f"not in real N sheet names"
            )

    def test_n4a_trailing_space(self, n_entries):
        """N4A sheet must have trailing space: '税金及附加审计程序表N4A '."""
        n4a_entries = [
            e for e in n_entries
            if "N4A" in e["sheet"]
        ]
        if n4a_entries:
            for entry in n4a_entries:
                assert entry["sheet"].endswith(" "), (
                    f"N4A sheet name must end with space: repr={repr(entry['sheet'])}"
                )


class TestNoDuplicates:
    """No duplicate (wp_code, sheet, cell_ref) combinations."""

    def test_no_duplicate_cells_in_n_cycle(self, n_entries):
        """Each (wp_code, sheet, cell_ref) must be unique within N-cycle."""
        seen = set()
        duplicates = []
        for entry in n_entries:
            for cell in entry["cells"]:
                key = (entry["wp_code"], entry["sheet"], cell["cell_ref"])
                if key in seen:
                    duplicates.append(key)
                seen.add(key)
        assert not duplicates, (
            f"Duplicate N-cycle cells found: {duplicates}"
        )

    def test_no_duplicate_wp_sheet_global(self, prefill_data):
        """No duplicate (wp_code, sheet) pairs in the entire file."""
        seen = set()
        duplicates = []
        for entry in prefill_data["mappings"]:
            key = (entry["wp_code"], entry["sheet"])
            if key in seen:
                duplicates.append(key)
            seen.add(key)
        assert not duplicates, (
            f"Duplicate (wp_code, sheet) entries found globally: {duplicates}"
        )


class TestFormulaSyntax:
    """All formulas must be syntactically valid."""

    def test_all_formulas_valid(self, n_entries):
        """Every formula in N-cycle must match a known valid pattern."""
        invalid = []
        for entry in n_entries:
            for cell in entry["cells"]:
                formula = cell["formula"]
                if formula is None:
                    continue  # PLACEHOLDER type allowed
                matched = any(p.match(formula) for p in VALID_FORMULA_PATTERNS)
                if not matched:
                    invalid.append(
                        f"{entry['wp_code']}/{entry['sheet']}/{cell['cell_ref']}: "
                        f"'{formula}' does not match any valid pattern"
                    )
        assert not invalid, (
            f"Invalid formula syntax:\n" + "\n".join(invalid)
        )

    def test_aux_formulas_have_exactly_4_args(self, n_entries):
        """Every =AUX formula must have exactly 4 arguments (3 commas)."""
        violations = []
        for entry in n_entries:
            for cell in entry["cells"]:
                formula = cell["formula"]
                if formula and formula.startswith("=AUX("):
                    inner = formula[5:-1]
                    args = [a.strip() for a in inner.split(",")]
                    if len(args) != 4:
                        violations.append(
                            f"{entry['wp_code']}/{entry['sheet']}/{cell['cell_ref']}: "
                            f"{formula} has {len(args)} args, expected 4"
                        )
        assert not violations, (
            f"AUX formulas with != 4 args:\n" + "\n".join(violations)
        )
