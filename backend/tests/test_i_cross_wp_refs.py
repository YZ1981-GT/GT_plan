"""Tests for I-cycle cross_wp_references entries (≥20 new entries)

Validates: Requirements I-F7, I-F8
- I-cycle 条目 ≥ 25 (baseline 5 + new ≥ 20)
- 所有 ref_id 全局唯一 (Property 3)
- 新增条目 schema 完整 (ref_id / source_wp / source_sheet / source_cell / targets / category / severity / description)
- ref_id 格式 CW-NNN (新增 I 条目从 max(existing)+1 起编)
- category / severity 枚举值合法
- source_wp / target wp_code 非空
- I2↔I6 反向回填 stale 传播路径存在 (data_flow_reverse 双向)

Spec: workpaper-i-intangible-assets-cycle / Sprint 2 / Task 2.17
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
def i_cycle_refs(references) -> list[dict]:
    """I-cycle 条目: source_wp 以 I 开头 OR 任一 target wp_code 以 I 开头"""
    out: list[dict] = []
    for r in references:
        src = r.get("source_wp") or ""
        tgt_codes = [(t.get("wp_code") or "") for t in r.get("targets", [])]
        if src.startswith("I") or any(t.startswith("I") for t in tgt_codes):
            out.append(r)
    return out


@pytest.fixture(scope="module")
def new_i_entries(i_cycle_refs) -> list[dict]:
    """新增 I-cycle 条目: ref_id 在 CW-243~CW-266 闭区间（Sprint 2 Task 2.16 起编）

    使用闭区间避免被后续 spec（J/K/L 等）的新条目污染。
    跨 spec ref_id 区间铁律：闭区间 + cycle membership 双重过滤。
    """
    pattern = re.compile(r"^CW-(\d+)$")
    out = []
    for r in i_cycle_refs:
        m = pattern.match(r.get("ref_id") or "")
        if m and 243 <= int(m.group(1)) <= 266:
            out.append(r)
    return out


# ─── Test 1: I-cycle 条目数量 ─────────────────────────────────────────────────


class TestICycleCounts:
    def test_i_cycle_at_least_25(self, i_cycle_refs):
        """I-cycle 条目 >= 25 (baseline 5 + new >= 20)"""
        assert len(i_cycle_refs) >= 25, (
            f"Expected ≥25 I-cycle references, got {len(i_cycle_refs)}"
        )

    def test_new_i_entries_at_least_20(self, new_i_entries):
        """新增 (CW-243+) I-cycle 条目 >= 20"""
        assert len(new_i_entries) >= 20, (
            f"Expected ≥20 new I entries (CW-243+), got {len(new_i_entries)}"
        )

    def test_grouping_coverage(self, new_i_entries):
        """5 分组覆盖：内部联动 ≥ 5 / 报表 ≥ 3 / 附注 ≥ 4 / K 期间费用 ≥ 4 / A 报表 ≥ 4"""
        internal = [r for r in new_i_entries if r.get("category") == "internal"]
        to_report = [
            r for r in new_i_entries
            if any((t.get("wp_code") or "") == "REPORT" for t in r.get("targets", []))
        ]
        to_note = [
            r for r in new_i_entries
            if any((t.get("wp_code") or "") == "NOTE" for t in r.get("targets", []))
        ]
        to_k = [
            r for r in new_i_entries
            if any(
                (t.get("wp_code") or "").startswith("K")
                or (t.get("wp_code") or "") == "D5"  # K 期间费用包含 D5 营业成本（生产用摊销分摊）
                for t in r.get("targets", [])
            )
        ]
        to_a = [
            r for r in new_i_entries
            if any(
                (t.get("wp_code") or "").startswith("A")
                for t in r.get("targets", [])
            )
        ]
        assert len(internal) >= 5, f"internal links < 5: {len(internal)}"
        assert len(to_report) >= 3, f"to-report links < 3: {len(to_report)}"
        assert len(to_note) >= 4, f"to-note links < 4: {len(to_note)}"
        assert len(to_k) >= 4, f"to-K links < 4: {len(to_k)}"
        assert len(to_a) >= 4, f"to-A links < 4: {len(to_a)}"


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

    def test_new_i_entries_in_range(self, new_i_entries):
        """新增 I-cycle 条目 ref_id 在 CW-243~CW-266 闭区间（紧接 H 循环最后 CW-242，预留至 CW-266）"""
        pattern = re.compile(r"^CW-(\d+)$")
        for r in new_i_entries:
            m = pattern.match(r["ref_id"])
            assert m and 243 <= int(m.group(1)) <= 266, (
                f"I-cycle new entry {r['ref_id']} should be in CW-243~CW-266"
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

    def test_required_fields_present(self, new_i_entries):
        """每条新增 I 条目必须包含所有必填字段"""
        for r in new_i_entries:
            missing = self.REQUIRED_FIELDS - set(r.keys())
            assert not missing, (
                f"{r.get('ref_id')} missing fields: {missing}"
            )

    def test_targets_non_empty(self, new_i_entries):
        """每条新增 I 条目的 targets 非空"""
        for r in new_i_entries:
            assert isinstance(r["targets"], list) and len(r["targets"]) >= 1, (
                f"{r['ref_id']} has empty targets"
            )

    def test_target_fields_present(self, new_i_entries):
        """每个 target 必须包含 wp_code / sheet / cell / formula"""
        for r in new_i_entries:
            for t in r["targets"]:
                missing = self.REQUIRED_TARGET_FIELDS - set(t.keys())
                assert not missing, (
                    f"{r['ref_id']} target missing fields: {missing}"
                )

    def test_no_empty_source_wp(self, new_i_entries):
        """source_wp 不能为空字符串"""
        for r in new_i_entries:
            assert r.get("source_wp"), (
                f"{r['ref_id']} has empty source_wp"
            )

    def test_no_empty_target_wp_code(self, new_i_entries):
        """target wp_code 不能为空字符串"""
        for r in new_i_entries:
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
        "intangible_cycle",
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

    def test_category_values_valid(self, new_i_entries):
        """所有新增 I 条目的 category 值在合法枚举内"""
        for r in new_i_entries:
            assert r["category"] in self.VALID_CATEGORIES, (
                f"{r['ref_id']} invalid category: {r['category']}"
            )

    def test_severity_values_valid(self, new_i_entries):
        """所有新增 I 条目的 severity 值在合法枚举内"""
        for r in new_i_entries:
            assert r["severity"] in self.VALID_SEVERITIES, (
                f"{r['ref_id']} invalid severity: {r['severity']}"
            )


# ─── Test 5: I2↔I6 反向回填 stale 传播路径（双向） ────────────────────────────


class TestI2I6ReverseBackfill:
    """I-F8: I2 开发支出 ↔ I6 研发费用反向回填.
    Validates Requirements I-F8.1: cross_wp_references 含 I2↔I6 data_flow_reverse 双向条目.
    """

    def test_i2_to_i6_reverse_entry_exists(self, i_cycle_refs):
        """至少存在 1 条 I2→I6 且 category=data_flow_reverse"""
        reverse = [
            r for r in i_cycle_refs
            if r.get("source_wp") == "I2"
            and r.get("category") == "data_flow_reverse"
            and any(
                (t.get("wp_code") or "") == "I6"
                for t in r.get("targets", [])
            )
        ]
        assert len(reverse) >= 1, (
            "I-F8 反向回填条目缺失: 需至少 1 条 I2→I6 且 category=data_flow_reverse"
        )

    def test_i6_to_i2_reverse_entry_exists(self, i_cycle_refs):
        """至少存在 1 条 I6→I2 且 category=data_flow_reverse"""
        reverse = [
            r for r in i_cycle_refs
            if r.get("source_wp") == "I6"
            and r.get("category") == "data_flow_reverse"
            and any(
                (t.get("wp_code") or "") == "I2"
                for t in r.get("targets", [])
            )
        ]
        assert len(reverse) >= 1, (
            "I-F8 反向回填条目缺失: 需至少 1 条 I6→I2 且 category=data_flow_reverse"
        )

    def test_reverse_entries_have_trigger(self, i_cycle_refs):
        """I2↔I6 反向回填条目应有 trigger 字段（workpaper:saved:I2 / I6）"""
        reverse = [
            r for r in i_cycle_refs
            if r.get("category") == "data_flow_reverse"
            and r.get("source_wp") in {"I2", "I6"}
        ]
        assert len(reverse) >= 2, (
            f"Expected ≥2 I2/I6 data_flow_reverse entries, got {len(reverse)}"
        )
        for r in reverse:
            trigger = (r.get("trigger") or "").lower()
            assert trigger.startswith("workpaper:saved:"), (
                f"{r['ref_id']} trigger 字段缺失或格式错误: {r.get('trigger')}"
            )
            wp = r["source_wp"].lower()
            assert wp in trigger, (
                f"{r['ref_id']} trigger 不含 source_wp '{wp}': {trigger}"
            )

    def test_reverse_entries_severity_warning(self, i_cycle_refs):
        """I2↔I6 反向回填 severity = warning（非阻断，仅 stale 提示）"""
        reverse = [
            r for r in i_cycle_refs
            if r.get("category") == "data_flow_reverse"
            and r.get("source_wp") in {"I2", "I6"}
        ]
        for r in reverse:
            assert r.get("severity") == "warning", (
                f"{r['ref_id']} severity 应为 warning, got {r.get('severity')}"
            )

    def test_reverse_target_has_formula(self, i_cycle_refs):
        """I2↔I6 反向回填 target 应有 formula 字段（=WP 语法）"""
        reverse = [
            r for r in i_cycle_refs
            if r.get("category") == "data_flow_reverse"
            and r.get("source_wp") in {"I2", "I6"}
        ]
        for r in reverse:
            for t in r["targets"]:
                assert "formula" in t, (
                    f"{r['ref_id']} target missing formula field"
                )
                assert (t.get("formula") or "").startswith("=WP("), (
                    f"{r['ref_id']} formula 应使用 =WP(...) 语法: {t.get('formula')}"
                )
