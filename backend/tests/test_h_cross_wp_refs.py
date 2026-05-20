"""Tests for H-cycle cross_wp_references entries (≥30 new entries)

Validates: Requirements H-F7, H-F8
- H-cycle 条目 ≥ 39 (baseline 9 + new ≥ 30)
- 所有 ref_id 全局唯一 (Property 3)
- 新增条目 schema 完整 (ref_id / source_wp / source_sheet / source_cell / targets / category / severity / description)
- ref_id 格式 CW-NNN (新增 H 条目从 CW-211 起编)
- category / severity 枚举值合法
- source_wp / target wp_code 非空
- H9→H8 反向回填 stale 传播路径存在 (data_flow_reverse)

Spec: workpaper-h-fixed-assets-cycle / Sprint 2 / Task 2.15
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CWR_PATH = DATA_DIR / "cross_wp_references.json"


@pytest.fixture(scope="module")
def cwr_data() -> dict:
    assert CWR_PATH.exists(), f"cross_wp_references.json not found at {CWR_PATH}"
    return json.loads(CWR_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def references(cwr_data) -> list[dict]:
    return cwr_data["references"]


@pytest.fixture(scope="module")
def h_cycle_refs(references) -> list[dict]:
    """H-cycle 条目: source_wp 以 H 开头 OR 任一 target wp_code 以 H 开头"""
    out: list[dict] = []
    for r in references:
        src = r.get("source_wp") or ""
        tgt_codes = [(t.get("wp_code") or "") for t in r.get("targets", [])]
        if src.startswith("H") or any(t.startswith("H") for t in tgt_codes):
            out.append(r)
    return out


@pytest.fixture(scope="module")
def new_h_entries(references) -> list[dict]:
    """新增 H-cycle 条目: ref_id CW-211~CW-242 且属于 H-cycle (source_wp 或 target 以 H 开头)"""
    pattern = re.compile(r"^CW-(\d+)$")
    out = []
    for r in references:
        m = pattern.match(r.get("ref_id") or "")
        if not m:
            continue
        n = int(m.group(1))
        if not (211 <= n <= 242):
            continue
        # H-cycle membership check: source_wp 或任一 target wp_code 以 H 开头
        src = r.get("source_wp") or ""
        tgt_codes = [(t.get("wp_code") or "") for t in r.get("targets", [])]
        if src.startswith("H") or any(t.startswith("H") for t in tgt_codes):
            out.append(r)
    return out


# ─── Test 1: H-cycle 条目数量 ─────────────────────────────────────────────────


class TestHCycleCounts:
    def test_h_cycle_at_least_39(self, h_cycle_refs):
        """H-cycle 条目 >= 39 (baseline 9 + new >= 30)"""
        assert len(h_cycle_refs) >= 39, (
            f"Expected ≥39 H-cycle references, got {len(h_cycle_refs)}"
        )

    def test_new_h_entries_at_least_30(self, new_h_entries):
        """新增 (CW-211+) H-cycle 条目 >= 30"""
        assert len(new_h_entries) >= 30, (
            f"Expected ≥30 new H entries (CW-211+), got {len(new_h_entries)}"
        )


# ─── Test 2: ref_id 全局唯一性 ────────────────────────────────────────────────


class TestRefIdUniqueness:
    def test_all_ref_ids_globally_unique(self, references):
        """所有 ref_id 全局唯一 (含全部条目，无重复)"""
        ids = [r.get("ref_id") for r in references]
        duplicates = [rid for rid in ids if ids.count(rid) > 1]
        assert len(ids) == len(set(ids)), (
            f"Duplicate ref_ids found: {set(duplicates)}"
        )

    def test_ref_id_format_cw_nnn(self, references):
        """所有 ref_id 格式为 CW-NNN (数字)"""
        pattern = re.compile(r"^CW-\d+$")
        for r in references:
            ref_id = r.get("ref_id", "")
            assert pattern.match(ref_id), f"Invalid ref_id format: {ref_id}"

    def test_new_h_entries_start_from_211(self, new_h_entries):
        """新增 H-cycle 条目 ref_id 在 CW-211~CW-242 区间"""
        pattern = re.compile(r"^CW-(\d+)$")
        for r in new_h_entries:
            m = pattern.match(r["ref_id"])
            assert m and 211 <= int(m.group(1)) <= 242, (
                f"H-cycle new entry {r['ref_id']} should be in CW-211~CW-242"
            )


# ─── Test 3: 新增条目 schema 完整性 ───────────────────────────────────────────


class TestNewEntrySchema:
    REQUIRED_FIELDS = {
        "ref_id",
        "description",
        "source_wp",
        "source_sheet",
        "source_cell",
        "targets",
        "category",
        "severity",
    }
    REQUIRED_TARGET_FIELDS = {"wp_code", "sheet", "cell", "formula"}

    def test_required_fields_present(self, new_h_entries):
        """每条新增 H 条目必须包含所有必填字段"""
        for r in new_h_entries:
            missing = self.REQUIRED_FIELDS - set(r.keys())
            assert not missing, (
                f"{r.get('ref_id')} missing fields: {missing}"
            )

    def test_targets_non_empty(self, new_h_entries):
        """每条新增 H 条目的 targets 非空"""
        for r in new_h_entries:
            assert isinstance(r["targets"], list) and len(r["targets"]) >= 1, (
                f"{r['ref_id']} has empty targets"
            )

    def test_target_fields_present(self, new_h_entries):
        """每个 target 必须包含 wp_code / sheet / cell / formula"""
        for r in new_h_entries:
            for t in r["targets"]:
                missing = self.REQUIRED_TARGET_FIELDS - set(t.keys())
                assert not missing, (
                    f"{r['ref_id']} target missing fields: {missing}"
                )

    def test_no_empty_source_wp(self, new_h_entries):
        """source_wp 不能为空字符串"""
        for r in new_h_entries:
            assert r.get("source_wp"), (
                f"{r['ref_id']} has empty source_wp"
            )

    def test_no_empty_target_wp_code(self, new_h_entries):
        """target wp_code 不能为空字符串"""
        for r in new_h_entries:
            for t in r["targets"]:
                assert t.get("wp_code"), (
                    f"{r['ref_id']} has empty target wp_code"
                )


# ─── Test 4: category / severity 枚举值合法 ───────────────────────────────────


class TestEnumValues:
    VALID_CATEGORIES = {
        "internal",
        "cross_cycle",
        "data_flow",
        "data_flow_reverse",
        "depreciation",
        "salary",
        "impairment",
        "interest",
        "profit",
        "tax",
        "other",
        "revenue_cycle",
        "inventory_cycle",
        "fixed_asset_cycle",
        "disclosure_reference",
        "ipe_reference",
        "review_traceback",
        "trigger",
        "prerequisite",
        "scope_driver",
        "feedback",
        "completion_check",
        "overlap_reference",
        "cash_cycle",
    }
    VALID_SEVERITIES = {"blocking", "warning", "info"}

    def test_category_values_valid(self, new_h_entries):
        """所有新增 H 条目的 category 值在合法枚举内"""
        for r in new_h_entries:
            assert r["category"] in self.VALID_CATEGORIES, (
                f"{r['ref_id']} invalid category: {r['category']}"
            )

    def test_severity_values_valid(self, new_h_entries):
        """所有新增 H 条目的 severity 值在合法枚举内"""
        for r in new_h_entries:
            assert r["severity"] in self.VALID_SEVERITIES, (
                f"{r['ref_id']} invalid severity: {r['severity']}"
            )


# ─── Test 5: H9→H8 反向回填 stale 传播路径 ────────────────────────────────────


class TestH9ToH8ReverseBackfill:
    """H-F8: H9 租赁负债 → H8 使用权资产反向回填.
    Validates Requirements H-F8.1: cross_wp_references 含 H9→H8 data_flow_reverse 条目.
    """

    def test_h9_to_h8_reverse_entry_exists(self, h_cycle_refs):
        """至少存在 1 条 H9→H8 且 category=data_flow_reverse"""
        reverse = [
            r for r in h_cycle_refs
            if r.get("source_wp") == "H9"
            and r.get("category") == "data_flow_reverse"
            and any(
                (t.get("wp_code") or "") == "H8"
                for t in r.get("targets", [])
            )
        ]
        assert len(reverse) >= 1, (
            "H-F8 反向回填条目缺失: 需至少 1 条 H9→H8 且 category=data_flow_reverse"
        )

    def test_h9_to_h8_target_has_formula(self, h_cycle_refs):
        """H9→H8 反向回填条目的 target 应有 formula 字段"""
        reverse = [
            r for r in h_cycle_refs
            if r.get("source_wp") == "H9"
            and r.get("category") == "data_flow_reverse"
            and any(
                (t.get("wp_code") or "") == "H8"
                for t in r.get("targets", [])
            )
        ]
        for r in reverse:
            for t in r["targets"]:
                if t.get("wp_code") == "H8":
                    # formula can be =WP(...) or null for some target types
                    # but for data_flow_reverse it should reference H9
                    assert "formula" in t, (
                        f"{r['ref_id']} H9→H8 target missing formula field"
                    )
