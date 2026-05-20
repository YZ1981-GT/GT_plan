"""
Tests for M-cycle prefill extension (M-F6).

Validates: Requirements M-F6
- Total M-cycle cells ≥ 82
- Per-sheet minimums: M2≥6, M4≥6, M5≥4, M6≥8, M9≥4, M10≥2
- All AUX formulas use 4-arg format
- No duplicate (wp_code, sheet, cell_ref) tuples
- Idempotent: no duplicate entries across entire file
"""

import json
from pathlib import Path

import pytest

DATA_PATH = Path(__file__).parent.parent / "data" / "prefill_formula_mapping.json"


@pytest.fixture(scope="module")
def prefill_data():
    """Load the prefill formula mapping data."""
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def m_entries(prefill_data):
    """Extract all M-cycle entries."""
    return [e for e in prefill_data["mappings"] if e["wp_code"].startswith("M")]


@pytest.fixture(scope="module")
def m_cells_total(m_entries):
    """Total cell count across all M-cycle entries."""
    return sum(len(e["cells"]) for e in m_entries)


class TestMPrefillTotalCells:
    """Total M-cycle cells must be ≥ 82."""

    def test_total_cells_ge_82(self, m_cells_total):
        assert m_cells_total >= 82, (
            f"M-cycle total cells = {m_cells_total}, expected ≥ 82"
        )


class TestMPrefillPerSheetMinimums:
    """Per-sheet minimum cell counts."""

    def _cells_for_sheet(self, m_entries, sheet_pattern):
        """Sum cells for entries whose sheet contains the pattern."""
        total = 0
        for e in m_entries:
            if sheet_pattern in e["sheet"]:
                total += len(e["cells"])
        return total

    def test_m2_detail_ge_6(self, m_entries):
        """M2 明细表（非上市公司）M2-2 must have ≥ 6 cells."""
        count = self._cells_for_sheet(m_entries, "M2-2")
        assert count >= 6, f"M2 detail cells = {count}, expected ≥ 6"

    def test_m4_detail_ge_6(self, m_entries):
        """M4 明细表M4-2 must have ≥ 6 cells."""
        count = self._cells_for_sheet(m_entries, "M4-2")
        assert count >= 6, f"M4 detail cells = {count}, expected ≥ 6"

    def test_m5_detail_ge_4(self, m_entries):
        """M5 明细表M5-2 must have ≥ 4 cells."""
        count = self._cells_for_sheet(m_entries, "M5-2")
        assert count >= 4, f"M5 detail cells = {count}, expected ≥ 4"

    def test_m6_detail_ge_8(self, m_entries):
        """M6 明细表M6-2 must have ≥ 8 cells."""
        count = self._cells_for_sheet(m_entries, "M6-2")
        assert count >= 8, f"M6 detail cells = {count}, expected ≥ 8"

    def test_m9_detail_ge_4(self, m_entries):
        """M9 明细表M9-2 must have ≥ 4 cells."""
        count = self._cells_for_sheet(m_entries, "M9-2")
        assert count >= 4, f"M9 detail cells = {count}, expected ≥ 4"

    def test_m10_detail_ge_2(self, m_entries):
        """M10 明细表M10-2 must have ≥ 2 cells."""
        count = self._cells_for_sheet(m_entries, "M10-2")
        assert count >= 2, f"M10 detail cells = {count}, expected ≥ 2"


class TestMPrefillAUXFormat:
    """All AUX formulas must use 4-arg format: =AUX(account, aux_type, aux_code, column)."""

    def test_all_aux_formulas_have_4_args(self, m_entries):
        """Every =AUX formula in M-cycle must have exactly 4 arguments."""
        violations = []
        for entry in m_entries:
            for cell in entry["cells"]:
                if cell["formula_type"] == "AUX":
                    formula = cell["formula"]
                    # Extract args: =AUX('a','b','c','d')
                    inner = formula.replace("=AUX(", "").rstrip(")")
                    args = [a.strip() for a in inner.split(",")]
                    if len(args) != 4:
                        violations.append(
                            f"{entry['wp_code']}/{entry['sheet']}/{cell['cell_ref']}: "
                            f"{formula} has {len(args)} args"
                        )
        assert not violations, (
            f"AUX formulas with != 4 args:\n" + "\n".join(violations)
        )

    def test_aux_codes_are_real(self, m_entries):
        """AUX aux_code values must be non-empty real codes (not placeholders)."""
        # Real aux_codes from Sprint 0.X: 014021/606362/JTNB001/07120032/09280004/16400001/SHGD096/16400002/783604
        real_codes = {
            "014021", "606362", "JTNB001", "07120032", "09280004",
            "16400001", "SHGD096", "16400002", "783604",
        }
        for entry in m_entries:
            for cell in entry["cells"]:
                if cell["formula_type"] == "AUX":
                    formula = cell["formula"]
                    inner = formula.replace("=AUX(", "").rstrip(")")
                    args = [a.strip().strip("'") for a in inner.split(",")]
                    aux_code = args[2]
                    assert aux_code in real_codes, (
                        f"AUX code '{aux_code}' in {entry['wp_code']}/{cell['cell_ref']} "
                        f"not in real aux_codes from Sprint 0.X"
                    )


class TestMPrefillNoDuplicates:
    """No duplicate (wp_code, sheet, cell_ref) tuples."""

    def test_no_duplicate_cells(self, m_entries):
        """Each (wp_code, sheet, cell_ref) must be unique."""
        seen = set()
        duplicates = []
        for entry in m_entries:
            for cell in entry["cells"]:
                key = (entry["wp_code"], entry["sheet"], cell["cell_ref"])
                if key in seen:
                    duplicates.append(key)
                seen.add(key)
        assert not duplicates, (
            f"Duplicate cells found: {duplicates}"
        )

    def test_no_duplicate_entries_global(self, prefill_data):
        """No duplicate (wp_code, sheet) pairs in the entire file (idempotent append)."""
        seen = set()
        duplicates = []
        for entry in prefill_data["mappings"]:
            key = (entry["wp_code"], entry["sheet"])
            if key in seen:
                duplicates.append(key)
            seen.add(key)
        assert not duplicates, (
            f"Duplicate (wp_code, sheet) entries found: {duplicates}"
        )


class TestMPrefillNewCellsCount:
    """Verify that new cells added are ≥ 30 beyond baseline 52."""

    def test_new_cells_ge_30(self, m_cells_total):
        """New cells = total - baseline(52) must be ≥ 30."""
        baseline = 52
        new_cells = m_cells_total - baseline
        assert new_cells >= 30, (
            f"New M cells = {new_cells} (total={m_cells_total} - baseline={baseline}), "
            f"expected ≥ 30"
        )
