"""Tests for L-cycle cross_wp_references (CW-333 ~ CW-352).

Validates: Requirements L-F4
- 闭区间 + cycle membership 双重过滤铁律
- ≥ 20 new entries
- 5-group coverage
- severity distribution (info < 25%)
- ref_id uniqueness within interval
"""

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "cross_wp_references.json"

# L spec 闭区间: CW-333 ~ CW-352
L_INTERVAL_LO = 333
L_INTERVAL_HI = 352


@pytest.fixture(scope="module")
def all_references():
    """Load all cross_wp_references."""
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["references"]


@pytest.fixture(scope="module")
def l_cycle_new_refs(all_references):
    """Filter by closed interval AND cycle membership (双重过滤铁律).

    Closed interval: L_INTERVAL_LO <= ref_id_num <= L_INTERVAL_HI
    Cycle membership: source_wp starts with 'L' OR any target wp_code starts with 'L'
    """
    filtered = []
    for r in all_references:
        ref_num = int(r["ref_id"].replace("CW-", ""))
        # 闭区间过滤
        if not (L_INTERVAL_LO <= ref_num <= L_INTERVAL_HI):
            continue
        # cycle membership 过滤
        is_l_source = r["source_wp"].startswith("L")
        is_l_target = any(
            t.get("wp_code", "").startswith("L") for t in r.get("targets", [])
        )
        if is_l_source or is_l_target:
            filtered.append(r)
    return filtered


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLCrossWpRefsCount:
    """Verify ≥ 20 new L-cycle entries in closed interval."""

    def test_new_entries_count_gte_20(self, l_cycle_new_refs):
        """L-F4 AC2: ≥ 20 new entries."""
        assert len(l_cycle_new_refs) >= 20, (
            f"Expected ≥ 20 new L-cycle entries, got {len(l_cycle_new_refs)}"
        )

    def test_total_l_related_gte_26(self, all_references):
        """L-F4 量化指标: total L-related ≥ 26 (baseline 6 + new ≥ 20)."""
        l_related = []
        for r in all_references:
            is_l_source = r["source_wp"].startswith("L")
            is_l_target = any(
                t.get("wp_code", "").startswith("L") for t in r.get("targets", [])
            )
            if is_l_source or is_l_target:
                l_related.append(r)
        assert len(l_related) >= 26, (
            f"Expected total L-related ≥ 26, got {len(l_related)}"
        )


class TestLCrossWpRefsGroupCoverage:
    """Verify 5-group distribution meets minimums."""

    def _classify_groups(self, refs):
        """Classify refs into 5 groups."""
        groups = {
            "L内部": [],
            "L→报表": [],
            "L→附注": [],
            "L→H循环": [],
            "L→M/N循环": [],
        }
        for r in refs:
            src = r["source_wp"]
            tgt = r["targets"][0].get("wp_code", "") if r.get("targets") else ""
            if src.startswith("L") and tgt.startswith("L"):
                groups["L内部"].append(r["ref_id"])
            elif tgt in ("BS", "PL"):
                groups["L→报表"].append(r["ref_id"])
            elif tgt == "NOTE":
                groups["L→附注"].append(r["ref_id"])
            elif tgt.startswith("H"):
                groups["L→H循环"].append(r["ref_id"])
            elif tgt.startswith("M") or tgt.startswith("N"):
                groups["L→M/N循环"].append(r["ref_id"])
        return groups

    def test_l_internal_gte_5(self, l_cycle_new_refs):
        """L内部联动 ≥ 5."""
        groups = self._classify_groups(l_cycle_new_refs)
        assert len(groups["L内部"]) >= 5, (
            f"L内部 expected ≥ 5, got {len(groups['L内部'])}: {groups['L内部']}"
        )

    def test_l_to_report_gte_4(self, l_cycle_new_refs):
        """L→报表 ≥ 4."""
        groups = self._classify_groups(l_cycle_new_refs)
        assert len(groups["L→报表"]) >= 4, (
            f"L→报表 expected ≥ 4, got {len(groups['L→报表'])}: {groups['L→报表']}"
        )

    def test_l_to_notes_gte_4(self, l_cycle_new_refs):
        """L→附注 ≥ 4."""
        groups = self._classify_groups(l_cycle_new_refs)
        assert len(groups["L→附注"]) >= 4, (
            f"L→附注 expected ≥ 4, got {len(groups['L→附注'])}: {groups['L→附注']}"
        )

    def test_l_to_h_cycle_gte_3(self, l_cycle_new_refs):
        """L→H循环 ≥ 3."""
        groups = self._classify_groups(l_cycle_new_refs)
        assert len(groups["L→H循环"]) >= 3, (
            f"L→H循环 expected ≥ 3, got {len(groups['L→H循环'])}: {groups['L→H循环']}"
        )

    def test_l_to_mn_cycle_gte_4(self, l_cycle_new_refs):
        """L→M/N循环 ≥ 4."""
        groups = self._classify_groups(l_cycle_new_refs)
        assert len(groups["L→M/N循环"]) >= 4, (
            f"L→M/N循环 expected ≥ 4, got {len(groups['L→M/N循环'])}: {groups['L→M/N循环']}"
        )


class TestLCrossWpRefsSeverity:
    """Verify severity distribution: info < 25%."""

    def test_info_ratio_below_25_percent(self, l_cycle_new_refs):
        """CWR severity 健康度铁律: info < 25%."""
        total = len(l_cycle_new_refs)
        assert total > 0, "No L-cycle entries found"
        info_count = sum(1 for r in l_cycle_new_refs if r["severity"] == "info")
        ratio = info_count / total
        assert ratio < 0.25, (
            f"info ratio {ratio:.2%} >= 25% "
            f"(info={info_count}, total={total})"
        )

    def test_severity_values_valid(self, l_cycle_new_refs):
        """All severity values must be one of blocking/warning/info."""
        valid = {"blocking", "warning", "info"}
        for r in l_cycle_new_refs:
            assert r["severity"] in valid, (
                f"{r['ref_id']} has invalid severity: {r['severity']}"
            )


class TestLCrossWpRefsUniqueness:
    """Verify ref_id uniqueness within interval."""

    def test_ref_id_unique_in_interval(self, l_cycle_new_refs):
        """No duplicate ref_ids within L-cycle closed interval."""
        ids = [r["ref_id"] for r in l_cycle_new_refs]
        assert len(ids) == len(set(ids)), (
            f"Duplicate ref_ids found: {[x for x in ids if ids.count(x) > 1]}"
        )

    def test_ref_id_format(self, l_cycle_new_refs):
        """All ref_ids follow CW-NNN format."""
        import re
        pattern = re.compile(r"^CW-\d+$")
        for r in l_cycle_new_refs:
            assert pattern.match(r["ref_id"]), (
                f"Invalid ref_id format: {r['ref_id']}"
            )

    def test_ref_id_within_closed_interval(self, l_cycle_new_refs):
        """All filtered entries are within [333, 352]."""
        for r in l_cycle_new_refs:
            num = int(r["ref_id"].replace("CW-", ""))
            assert L_INTERVAL_LO <= num <= L_INTERVAL_HI, (
                f"{r['ref_id']} outside interval [{L_INTERVAL_LO}, {L_INTERVAL_HI}]"
            )


class TestLCrossWpRefsSchema:
    """Verify schema completeness of new entries."""

    REQUIRED_FIELDS = {"ref_id", "description", "source_wp", "source_sheet",
                       "source_cell", "targets", "category", "severity"}
    TARGET_FIELDS = {"wp_code", "sheet", "cell", "formula"}

    def test_all_required_fields_present(self, l_cycle_new_refs):
        """Each entry has all required top-level fields."""
        for r in l_cycle_new_refs:
            missing = self.REQUIRED_FIELDS - set(r.keys())
            assert not missing, (
                f"{r['ref_id']} missing fields: {missing}"
            )

    def test_targets_have_required_fields(self, l_cycle_new_refs):
        """Each target has wp_code, sheet, cell, formula."""
        for r in l_cycle_new_refs:
            for t in r.get("targets", []):
                missing = self.TARGET_FIELDS - set(t.keys())
                assert not missing, (
                    f"{r['ref_id']} target missing fields: {missing}"
                )

    def test_source_wp_starts_with_l(self, l_cycle_new_refs):
        """All new entries have source_wp starting with L (L-cycle origin)."""
        for r in l_cycle_new_refs:
            assert r["source_wp"].startswith("L"), (
                f"{r['ref_id']} source_wp={r['source_wp']} doesn't start with L"
            )
