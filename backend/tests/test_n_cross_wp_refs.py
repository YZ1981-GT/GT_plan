"""Tests for N-cycle cross_wp_references (CW-370 ~ CW-381).

Validates: Requirements N-F4
- 闭区间 + cycle membership 双重过滤铁律
- ≥ 10 new entries (actual: 12)
- 4-group coverage: N内部(≥2) / N→报表(≥3) / N→跨循环(≥3) / N→附注(≥2)
- severity distribution (info < 25%)
- ref_id uniqueness within interval and globally
- Total N-related ≥ 24 (baseline 14 + new ≥ 10)
"""

import json
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "cross_wp_references.json"

# N spec 闭区间: CW-370 ~ CW-381
N_INTERVAL_LO = 370
N_INTERVAL_HI = 381

# N cycle wp_codes
N_WP_CODES = {"N1", "N2", "N3", "N4", "N5"}


def _is_n_cycle(wp_code: str) -> bool:
    """Check if wp_code belongs to N cycle."""
    if wp_code in N_WP_CODES:
        return True
    # Match N followed by digit(s) for any future N-cycle codes
    return bool(re.match(r"^N\d+$", wp_code))


@pytest.fixture(scope="module")
def all_references():
    """Load all cross_wp_references."""
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["references"]


@pytest.fixture(scope="module")
def n_cycle_new_refs(all_references):
    """Filter by closed interval AND cycle membership (双重过滤铁律).

    Closed interval: N_INTERVAL_LO <= ref_id_num <= N_INTERVAL_HI
    Cycle membership: source_wp is N-cycle OR any target wp_code is N-cycle
    """
    filtered = []
    for r in all_references:
        ref_num = int(r["ref_id"].replace("CW-", ""))
        # 闭区间过滤
        if not (N_INTERVAL_LO <= ref_num <= N_INTERVAL_HI):
            continue
        # cycle membership 过滤
        is_n_source = _is_n_cycle(r["source_wp"])
        is_n_target = any(
            _is_n_cycle(t.get("wp_code", "")) for t in r.get("targets", [])
        )
        if is_n_source or is_n_target:
            filtered.append(r)
    return filtered


@pytest.fixture(scope="module")
def all_n_related(all_references):
    """All N-cycle related entries (any ref_id, cycle membership only)."""
    related = []
    for r in all_references:
        is_n_source = _is_n_cycle(r["source_wp"])
        is_n_target = any(
            _is_n_cycle(t.get("wp_code", "")) for t in r.get("targets", [])
        )
        if is_n_source or is_n_target:
            related.append(r)
    return related


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNCrossWpRefsCount:
    """Verify ≥ 10 new N-cycle entries in closed interval."""

    def test_new_entries_count_gte_10(self, n_cycle_new_refs):
        """N-F4: ≥ 10 new entries in closed interval [370, 381]."""
        assert len(n_cycle_new_refs) >= 10, (
            f"Expected ≥ 10 new N-cycle entries, got {len(n_cycle_new_refs)}"
        )

    def test_total_n_related_gte_24(self, all_n_related):
        """N-F4 量化指标: total N-related ≥ 24 (baseline 14 + new ≥ 10)."""
        assert len(all_n_related) >= 24, (
            f"Expected total N-related ≥ 24, got {len(all_n_related)}"
        )


class TestNCrossWpRefsGroupCoverage:
    """Verify 4-group distribution meets minimums."""

    def _classify_groups(self, refs):
        """Classify refs into 4 groups per N-F4 spec."""
        groups = {
            "N内部": [],
            "N→报表": [],
            "N→附注": [],
            "N→跨循环": [],
        }
        for r in refs:
            src = r["source_wp"]
            targets = r.get("targets", [])
            tgt_wp = targets[0].get("wp_code", "") if targets else ""

            if _is_n_cycle(src) and _is_n_cycle(tgt_wp):
                # Both source and target are N-cycle
                groups["N内部"].append(r["ref_id"])
            elif tgt_wp in ("REPORT", "BS", "PL"):
                groups["N→报表"].append(r["ref_id"])
            elif tgt_wp == "NOTE":
                groups["N→附注"].append(r["ref_id"])
            else:
                # Cross-cycle: target is non-N, non-report, non-note
                groups["N→跨循环"].append(r["ref_id"])
        return groups

    def test_n_internal_gte_2(self, n_cycle_new_refs):
        """N内部联动 ≥ 2."""
        groups = self._classify_groups(n_cycle_new_refs)
        assert len(groups["N内部"]) >= 2, (
            f"N内部 expected ≥ 2, got {len(groups['N内部'])}: {groups['N内部']}"
        )

    def test_n_to_report_gte_3(self, n_cycle_new_refs):
        """N→报表 ≥ 3."""
        groups = self._classify_groups(n_cycle_new_refs)
        assert len(groups["N→报表"]) >= 3, (
            f"N→报表 expected ≥ 3, got {len(groups['N→报表'])}: {groups['N→报表']}"
        )

    def test_n_to_notes_gte_2(self, n_cycle_new_refs):
        """N→附注 ≥ 2."""
        groups = self._classify_groups(n_cycle_new_refs)
        assert len(groups["N→附注"]) >= 2, (
            f"N→附注 expected ≥ 2, got {len(groups['N→附注'])}: {groups['N→附注']}"
        )

    def test_n_to_cross_cycle_gte_3(self, n_cycle_new_refs):
        """N→跨循环 ≥ 3."""
        groups = self._classify_groups(n_cycle_new_refs)
        assert len(groups["N→跨循环"]) >= 3, (
            f"N→跨循环 expected ≥ 3, got {len(groups['N→跨循环'])}: {groups['N→跨循环']}"
        )


class TestNCrossWpRefsSeverity:
    """Verify severity distribution: info < 25%."""

    def test_info_ratio_below_25_percent(self, n_cycle_new_refs):
        """CWR severity 健康度铁律: info < 25%."""
        total = len(n_cycle_new_refs)
        assert total > 0, "No N-cycle entries found"
        info_count = sum(1 for r in n_cycle_new_refs if r["severity"] == "info")
        ratio = info_count / total
        assert ratio < 0.25, (
            f"info ratio {ratio:.2%} >= 25% "
            f"(info={info_count}, total={total})"
        )

    def test_severity_values_valid(self, n_cycle_new_refs):
        """All severity values must be one of blocking/warning/info."""
        valid = {"blocking", "warning", "info"}
        for r in n_cycle_new_refs:
            assert r["severity"] in valid, (
                f"{r['ref_id']} has invalid severity: {r['severity']}"
            )


class TestNCrossWpRefsUniqueness:
    """Verify ref_id uniqueness within interval and globally."""

    def test_ref_id_unique_in_interval(self, n_cycle_new_refs):
        """No duplicate ref_ids within N-cycle closed interval."""
        ids = [r["ref_id"] for r in n_cycle_new_refs]
        assert len(ids) == len(set(ids)), (
            f"Duplicate ref_ids found: {[x for x in ids if ids.count(x) > 1]}"
        )

    def test_ref_id_format(self, n_cycle_new_refs):
        """All ref_ids follow CW-NNN format."""
        pattern = re.compile(r"^CW-\d+$")
        for r in n_cycle_new_refs:
            assert pattern.match(r["ref_id"]), (
                f"Invalid ref_id format: {r['ref_id']}"
            )

    def test_ref_id_within_closed_interval(self, n_cycle_new_refs):
        """All filtered entries are within [370, 381]."""
        for r in n_cycle_new_refs:
            num = int(r["ref_id"].replace("CW-", ""))
            assert N_INTERVAL_LO <= num <= N_INTERVAL_HI, (
                f"{r['ref_id']} outside interval [{N_INTERVAL_LO}, {N_INTERVAL_HI}]"
            )

    def test_ref_id_globally_unique(self, all_references):
        """ref_ids are globally unique across all entries."""
        all_ids = [r["ref_id"] for r in all_references]
        duplicates = [x for x in all_ids if all_ids.count(x) > 1]
        assert not duplicates, (
            f"Global duplicate ref_ids found: {set(duplicates)}"
        )


class TestNCrossWpRefsSchema:
    """Verify schema completeness of new entries."""

    REQUIRED_FIELDS = {"ref_id", "description", "source_wp", "source_sheet",
                       "source_cell", "targets", "category", "severity"}
    TARGET_FIELDS = {"wp_code", "sheet", "cell", "formula"}

    def test_all_required_fields_present(self, n_cycle_new_refs):
        """Each entry has all required top-level fields."""
        for r in n_cycle_new_refs:
            missing = self.REQUIRED_FIELDS - set(r.keys())
            assert not missing, (
                f"{r['ref_id']} missing fields: {missing}"
            )

    def test_targets_have_required_fields(self, n_cycle_new_refs):
        """Each target has wp_code, sheet, cell, formula."""
        for r in n_cycle_new_refs:
            for t in r.get("targets", []):
                missing = self.TARGET_FIELDS - set(t.keys())
                assert not missing, (
                    f"{r['ref_id']} target missing fields: {missing}"
                )

    def test_cycle_membership_holds(self, n_cycle_new_refs):
        """All new entries have N-cycle involvement (source or target)."""
        for r in n_cycle_new_refs:
            is_n_source = _is_n_cycle(r["source_wp"])
            is_n_target = any(
                _is_n_cycle(t.get("wp_code", "")) for t in r.get("targets", [])
            )
            assert is_n_source or is_n_target, (
                f"{r['ref_id']} has no N-cycle involvement: "
                f"source={r['source_wp']}, targets="
                f"{[t.get('wp_code') for t in r.get('targets', [])]}"
            )
