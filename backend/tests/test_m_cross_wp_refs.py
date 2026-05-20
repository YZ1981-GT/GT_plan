"""Tests for M-cycle cross_wp_references (CW-353 ~ CW-369).

Validates: Requirements M-F4
- 闭区间 + cycle membership 双重过滤铁律
- ≥ 15 new entries (actual: 17)
- 4-group coverage: M内部(≥3) / M→报表(≥4) / M→附注(≥4) / M→跨循环(≥4)
- severity distribution (info < 25%)
- ref_id uniqueness within interval
- Total M-related ≥ 23 (baseline 8 + new 15+)
"""

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "cross_wp_references.json"

# M spec 闭区间: CW-353 ~ CW-369
M_INTERVAL_LO = 353
M_INTERVAL_HI = 369

# M cycle wp_codes
M_WP_CODES = {"M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10"}


def _is_m_cycle(wp_code: str) -> bool:
    """Check if wp_code belongs to M cycle."""
    return wp_code in M_WP_CODES or wp_code.startswith("M")


@pytest.fixture(scope="module")
def all_references():
    """Load all cross_wp_references."""
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["references"]


@pytest.fixture(scope="module")
def m_cycle_new_refs(all_references):
    """Filter by closed interval AND cycle membership (双重过滤铁律).

    Closed interval: M_INTERVAL_LO <= ref_id_num <= M_INTERVAL_HI
    Cycle membership: source_wp is M-cycle OR any target wp_code is M-cycle
    """
    filtered = []
    for r in all_references:
        ref_num = int(r["ref_id"].replace("CW-", ""))
        # 闭区间过滤
        if not (M_INTERVAL_LO <= ref_num <= M_INTERVAL_HI):
            continue
        # cycle membership 过滤
        is_m_source = _is_m_cycle(r["source_wp"])
        is_m_target = any(
            _is_m_cycle(t.get("wp_code", "")) for t in r.get("targets", [])
        )
        if is_m_source or is_m_target:
            filtered.append(r)
    return filtered


@pytest.fixture(scope="module")
def all_m_related(all_references):
    """All M-cycle related entries (any ref_id, cycle membership only)."""
    related = []
    for r in all_references:
        is_m_source = _is_m_cycle(r["source_wp"])
        is_m_target = any(
            _is_m_cycle(t.get("wp_code", "")) for t in r.get("targets", [])
        )
        if is_m_source or is_m_target:
            related.append(r)
    return related


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMCrossWpRefsCount:
    """Verify ≥ 15 new M-cycle entries in closed interval."""

    def test_new_entries_count_gte_15(self, m_cycle_new_refs):
        """M-F4: ≥ 15 new entries in closed interval [353, 368]."""
        assert len(m_cycle_new_refs) >= 15, (
            f"Expected ≥ 15 new M-cycle entries, got {len(m_cycle_new_refs)}"
        )

    def test_total_m_related_gte_23(self, all_m_related):
        """M-F4 量化指标: total M-related ≥ 23 (baseline 8 + new ≥ 15)."""
        assert len(all_m_related) >= 23, (
            f"Expected total M-related ≥ 23, got {len(all_m_related)}"
        )


class TestMCrossWpRefsGroupCoverage:
    """Verify 4-group distribution meets minimums."""

    def _classify_groups(self, refs):
        """Classify refs into 4 groups per M-F4 spec."""
        groups = {
            "M内部": [],
            "M→报表": [],
            "M→附注": [],
            "M→跨循环": [],
        }
        for r in refs:
            src = r["source_wp"]
            targets = r.get("targets", [])
            tgt_wp = targets[0].get("wp_code", "") if targets else ""

            if _is_m_cycle(src) and _is_m_cycle(tgt_wp):
                # Both source and target are M-cycle
                groups["M内部"].append(r["ref_id"])
            elif tgt_wp in ("REPORT", "BS", "PL"):
                groups["M→报表"].append(r["ref_id"])
            elif tgt_wp == "NOTE":
                groups["M→附注"].append(r["ref_id"])
            else:
                # Cross-cycle: target is non-M, non-report, non-note
                groups["M→跨循环"].append(r["ref_id"])
        return groups

    def test_m_internal_gte_3(self, m_cycle_new_refs):
        """M内部联动 ≥ 3."""
        groups = self._classify_groups(m_cycle_new_refs)
        assert len(groups["M内部"]) >= 3, (
            f"M内部 expected ≥ 3, got {len(groups['M内部'])}: {groups['M内部']}"
        )

    def test_m_to_report_gte_4(self, m_cycle_new_refs):
        """M→报表 ≥ 4."""
        groups = self._classify_groups(m_cycle_new_refs)
        assert len(groups["M→报表"]) >= 4, (
            f"M→报表 expected ≥ 4, got {len(groups['M→报表'])}: {groups['M→报表']}"
        )

    def test_m_to_notes_gte_4(self, m_cycle_new_refs):
        """M→附注 ≥ 4."""
        groups = self._classify_groups(m_cycle_new_refs)
        assert len(groups["M→附注"]) >= 4, (
            f"M→附注 expected ≥ 4, got {len(groups['M→附注'])}: {groups['M→附注']}"
        )

    def test_m_to_cross_cycle_gte_4(self, m_cycle_new_refs):
        """M→跨循环 ≥ 4."""
        groups = self._classify_groups(m_cycle_new_refs)
        assert len(groups["M→跨循环"]) >= 4, (
            f"M→跨循环 expected ≥ 4, got {len(groups['M→跨循环'])}: {groups['M→跨循环']}"
        )


class TestMCrossWpRefsSeverity:
    """Verify severity distribution: info < 25%."""

    def test_info_ratio_below_25_percent(self, m_cycle_new_refs):
        """CWR severity 健康度铁律: info < 25%."""
        total = len(m_cycle_new_refs)
        assert total > 0, "No M-cycle entries found"
        info_count = sum(1 for r in m_cycle_new_refs if r["severity"] == "info")
        ratio = info_count / total
        assert ratio < 0.25, (
            f"info ratio {ratio:.2%} >= 25% "
            f"(info={info_count}, total={total})"
        )

    def test_blocking_gte_4(self, m_cycle_new_refs):
        """Blocking severity ≥ 4."""
        blocking = [r for r in m_cycle_new_refs if r["severity"] == "blocking"]
        assert len(blocking) >= 4, (
            f"Expected blocking ≥ 4, got {len(blocking)}"
        )

    def test_warning_gte_8(self, m_cycle_new_refs):
        """Warning severity ≥ 8."""
        warning = [r for r in m_cycle_new_refs if r["severity"] == "warning"]
        assert len(warning) >= 8, (
            f"Expected warning ≥ 8, got {len(warning)}"
        )

    def test_severity_values_valid(self, m_cycle_new_refs):
        """All severity values must be one of blocking/warning/info."""
        valid = {"blocking", "warning", "info"}
        for r in m_cycle_new_refs:
            assert r["severity"] in valid, (
                f"{r['ref_id']} has invalid severity: {r['severity']}"
            )


class TestMCrossWpRefsUniqueness:
    """Verify ref_id uniqueness within interval."""

    def test_ref_id_unique_in_interval(self, m_cycle_new_refs):
        """No duplicate ref_ids within M-cycle closed interval."""
        ids = [r["ref_id"] for r in m_cycle_new_refs]
        assert len(ids) == len(set(ids)), (
            f"Duplicate ref_ids found: {[x for x in ids if ids.count(x) > 1]}"
        )

    def test_ref_id_format(self, m_cycle_new_refs):
        """All ref_ids follow CW-NNN format."""
        import re
        pattern = re.compile(r"^CW-\d+$")
        for r in m_cycle_new_refs:
            assert pattern.match(r["ref_id"]), (
                f"Invalid ref_id format: {r['ref_id']}"
            )

    def test_ref_id_within_closed_interval(self, m_cycle_new_refs):
        """All filtered entries are within [353, 369]."""
        for r in m_cycle_new_refs:
            num = int(r["ref_id"].replace("CW-", ""))
            assert M_INTERVAL_LO <= num <= M_INTERVAL_HI, (
                f"{r['ref_id']} outside interval [{M_INTERVAL_LO}, {M_INTERVAL_HI}]"
            )

    def test_ref_id_globally_unique(self, all_references):
        """ref_ids are globally unique across all entries."""
        all_ids = [r["ref_id"] for r in all_references]
        duplicates = [x for x in all_ids if all_ids.count(x) > 1]
        assert not duplicates, (
            f"Global duplicate ref_ids found: {set(duplicates)}"
        )


class TestMCrossWpRefsSchema:
    """Verify schema completeness of new entries."""

    REQUIRED_FIELDS = {"ref_id", "description", "source_wp", "source_sheet",
                       "source_cell", "targets", "category", "severity"}
    TARGET_FIELDS = {"wp_code", "sheet", "cell", "formula"}

    def test_all_required_fields_present(self, m_cycle_new_refs):
        """Each entry has all required top-level fields."""
        for r in m_cycle_new_refs:
            missing = self.REQUIRED_FIELDS - set(r.keys())
            assert not missing, (
                f"{r['ref_id']} missing fields: {missing}"
            )

    def test_targets_have_required_fields(self, m_cycle_new_refs):
        """Each target has wp_code, sheet, cell, formula."""
        for r in m_cycle_new_refs:
            for t in r.get("targets", []):
                missing = self.TARGET_FIELDS - set(t.keys())
                assert not missing, (
                    f"{r['ref_id']} target missing fields: {missing}"
                )

    def test_cycle_membership_holds(self, m_cycle_new_refs):
        """All new entries have M-cycle involvement (source or target)."""
        for r in m_cycle_new_refs:
            is_m_source = _is_m_cycle(r["source_wp"])
            is_m_target = any(
                _is_m_cycle(t.get("wp_code", "")) for t in r.get("targets", [])
            )
            assert is_m_source or is_m_target, (
                f"{r['ref_id']} has no M-cycle involvement: "
                f"source={r['source_wp']}, targets={[t.get('wp_code') for t in r.get('targets', [])]}"
            )
