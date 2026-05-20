"""Tests for B/C → cycle linkage cross_wp_references (CW-382 ~ CW-400)."""

import json
from pathlib import Path

import pytest

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "cross_wp_references.json"


@pytest.fixture(scope="module")
def all_references():
    """Load all references from the JSON file."""
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data["references"]


@pytest.fixture(scope="module")
def bc_linkage_refs(all_references):
    """Filter only the 19 new B/C linkage entries (CW-382 ~ CW-400)."""
    new_ids = {f"CW-{i}" for i in range(382, 401)}
    return [r for r in all_references if r["ref_id"] in new_ids]


class TestBCLinkageEntriesExist:
    """Verify all 19 new entries exist."""

    def test_total_count(self, bc_linkage_refs):
        assert len(bc_linkage_refs) == 19, (
            f"Expected 19 B/C linkage entries, got {len(bc_linkage_refs)}"
        )

    def test_all_ref_ids_present(self, bc_linkage_refs):
        expected_ids = {f"CW-{i}" for i in range(382, 401)}
        actual_ids = {r["ref_id"] for r in bc_linkage_refs}
        assert actual_ids == expected_ids


class TestB15MaterialityEntries:
    """Verify the 10 B15 materiality linkage entries (CW-382 ~ CW-391)."""

    @pytest.fixture
    def b15_refs(self, bc_linkage_refs):
        b15_ids = {f"CW-{i}" for i in range(382, 392)}
        return [r for r in bc_linkage_refs if r["ref_id"] in b15_ids]

    def test_count(self, b15_refs):
        assert len(b15_refs) == 10

    def test_source_wp(self, b15_refs):
        for ref in b15_refs:
            assert ref["source_wp"] == "B15", (
                f"{ref['ref_id']} source_wp should be B15, got {ref['source_wp']}"
            )

    def test_source_sheet(self, b15_refs):
        for ref in b15_refs:
            assert ref["source_sheet"] == "重要性计算表"

    def test_source_cell(self, b15_refs):
        for ref in b15_refs:
            assert ref["source_cell"] == "执行重要性"

    def test_category(self, b15_refs):
        for ref in b15_refs:
            assert ref["category"] == "materiality_linkage"

    def test_severity(self, b15_refs):
        for ref in b15_refs:
            assert ref["severity"] == "warning"

    def test_target_formula(self, b15_refs):
        expected_formula = "=WP('B15','重要性计算表','执行重要性')"
        for ref in b15_refs:
            assert ref["targets"][0]["formula"] == expected_formula

    def test_target_wp_codes(self, b15_refs):
        expected_targets = {"D4", "E1", "F2", "G7", "H1", "I1", "J1", "K8", "L1", "N2"}
        actual_targets = {ref["targets"][0]["wp_code"] for ref in b15_refs}
        assert actual_targets == expected_targets


class TestControlTestEntries:
    """Verify the 9 C control test linkage entries (CW-392 ~ CW-400)."""

    @pytest.fixture
    def c_refs(self, bc_linkage_refs):
        c_ids = {f"CW-{i}" for i in range(392, 401)}
        return [r for r in bc_linkage_refs if r["ref_id"] in c_ids]

    def test_count(self, c_refs):
        assert len(c_refs) == 9

    def test_source_wps(self, c_refs):
        expected_source_wps = {"C2", "C3", "C4", "C5", "C6", "C8", "C10", "C11", "C13"}
        actual_source_wps = {ref["source_wp"] for ref in c_refs}
        assert actual_source_wps == expected_source_wps

    def test_source_cell(self, c_refs):
        for ref in c_refs:
            assert ref["source_cell"] == "控制测试结论"

    def test_category(self, c_refs):
        for ref in c_refs:
            assert ref["category"] == "control_test_linkage"

    def test_severity(self, c_refs):
        for ref in c_refs:
            assert ref["severity"] == "warning"

    def test_target_formulas(self, c_refs):
        for ref in c_refs:
            src_wp = ref["source_wp"]
            src_sheet = ref["source_sheet"]
            expected_formula = f"=WP('{src_wp}','{src_sheet}','控制测试结论')"
            assert ref["targets"][0]["formula"] == expected_formula, (
                f"{ref['ref_id']} formula mismatch"
            )

    def test_target_wp_codes(self, c_refs):
        expected_targets = {"D4", "E1", "F2", "G7", "H1", "I1", "J1", "K8", "L1"}
        actual_targets = {ref["targets"][0]["wp_code"] for ref in c_refs}
        assert actual_targets == expected_targets


class TestNoDuplicateRefIds:
    """Verify no duplicate ref_ids globally."""

    def test_unique_ref_ids(self, all_references):
        ref_ids = [r["ref_id"] for r in all_references]
        duplicates = [rid for rid in ref_ids if ref_ids.count(rid) > 1]
        assert len(duplicates) == 0, f"Duplicate ref_ids found: {set(duplicates)}"


class TestCycleCoverage:
    """Verify target wp_codes cover all 10 cycles (D/E/F/G/H/I/J/K/L/N)."""

    def test_ten_cycles_covered(self, bc_linkage_refs):
        all_target_wps = set()
        for ref in bc_linkage_refs:
            for target in ref["targets"]:
                # Extract cycle letter from wp_code (first char)
                all_target_wps.add(target["wp_code"][0])
        expected_cycles = {"D", "E", "F", "G", "H", "I", "J", "K", "L", "N"}
        assert all_target_wps == expected_cycles, (
            f"Missing cycles: {expected_cycles - all_target_wps}"
        )
