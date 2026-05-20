"""Tests for F-cycle cross_wp_references entries (≥35 new entries)

Validates: Requirements F-F7, F-F8
- 总条目 ≥ 210 (175 baseline + 35 new F-cycle entries)
- F-cycle 条目 ≥ 43 (8 baseline + 35 new)
- 所有 ref_id 全局唯一 (Property 3)
- 新增条目 schema 完整 (ref_id / source_wp / targets / category / severity)
- 6 个分组覆盖完整 (F0 internal / F2 internal / F-cross / F→A / F→T1 IPE / F→note)
- F-F8 反向回填: F0→F2 data_flow_reverse 至少 1 条且 trigger=eventBus

Spec: workpaper-f-purchase-inventory / Sprint 2 / Tasks 2.16, 2.19
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
def f_cycle_refs(references) -> list[dict]:
    """F-cycle 条目: source_wp 以 F 开头 OR 任一 target wp_code 以 F 开头"""
    out: list[dict] = []
    for r in references:
        src = (r.get("source_wp") or "")
        tgt_codes = [(t.get("wp_code") or "") for t in r.get("targets", [])]
        if src.startswith("F") or any(t.startswith("F") for t in tgt_codes):
            out.append(r)
    return out


@pytest.fixture(scope="module")
def new_entries(references) -> list[dict]:
    """新追加 F-cycle 条目: ref_id 在 CW-176~CW-210 区间且属于 F-cycle"""
    pattern = re.compile(r"^CW-(\d+)$")
    out = []
    for r in references:
        m = pattern.match(r.get("ref_id") or "")
        if not m:
            continue
        n = int(m.group(1))
        if not (176 <= n <= 210):
            continue
        # F-cycle membership: source_wp 或任一 target wp_code 以 F 开头
        src = r.get("source_wp") or ""
        tgt_codes = [(t.get("wp_code") or "") for t in r.get("targets", [])]
        if src.startswith("F") or any(t.startswith("F") for t in tgt_codes):
            out.append(r)
    return out


# ─── Test 1: 总数与 F-cycle 数 ────────────────────────────────────────────────


class TestCounts:
    def test_total_at_least_210(self, references):
        """总条目数 >= 210 (175 baseline + 35 new)"""
        assert len(references) >= 210, (
            f"Expected ≥210 total references, got {len(references)}"
        )

    def test_f_cycle_at_least_43(self, f_cycle_refs):
        """F-cycle 条目 >= 43 (8 baseline + 35 new)"""
        assert len(f_cycle_refs) >= 43, (
            f"Expected ≥43 F-cycle references, got {len(f_cycle_refs)}"
        )

    def test_at_least_35_new_entries(self, new_entries):
        """新增 (CW-176+) 条目 >= 35"""
        assert len(new_entries) >= 35, (
            f"Expected ≥35 new entries (CW-176+), got {len(new_entries)}"
        )

    def test_stats_consistent(self, cwr_data, references):
        """stats.total_references 与实际 references 数量一致"""
        stats = cwr_data.get("stats", {})
        assert stats.get("total_references") == len(references)


# ─── Test 2: ref_id 全局唯一性 (Property 3) ──────────────────────────────────


class TestRefIdUniqueness:
    def test_all_ref_ids_unique(self, references):
        """所有 ref_id 全局唯一 (含原 175 条 + 新增 35 条)"""
        ids = [r.get("ref_id") for r in references]
        assert len(ids) == len(set(ids)), (
            f"Duplicate ref_ids found: total {len(ids)}, unique {len(set(ids))}"
        )

    def test_ref_id_format_valid(self, references):
        """ref_id 格式为 CW-NNN"""
        pattern = re.compile(r"^CW-\d+$")
        for r in references:
            ref_id = r.get("ref_id", "")
            assert pattern.match(ref_id), f"Invalid ref_id format: {ref_id}"

    def test_new_entries_start_above_175(self, new_entries):
        """新增条目 CW-NNN 的 NNN 全部 > 175 (基于 max(ref_id)+1 起编规则)"""
        pattern = re.compile(r"^CW-(\d+)$")
        for r in new_entries:
            m = pattern.match(r["ref_id"])
            assert m and int(m.group(1)) > 175


# ─── Test 3: 新增条目 schema 完整 ─────────────────────────────────────────────


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

    def test_required_fields_present(self, new_entries):
        for r in new_entries:
            missing = self.REQUIRED_FIELDS - set(r.keys())
            assert not missing, (
                f"{r.get('ref_id')} missing fields: {missing}"
            )

    def test_targets_non_empty(self, new_entries):
        for r in new_entries:
            assert isinstance(r["targets"], list) and len(r["targets"]) >= 1, (
                f"{r['ref_id']} has empty targets"
            )

    def test_target_fields_present(self, new_entries):
        for r in new_entries:
            for t in r["targets"]:
                missing = self.REQUIRED_TARGET_FIELDS - set(t.keys())
                assert not missing, (
                    f"{r['ref_id']} target missing fields: {missing}"
                )

    def test_severity_enum(self, new_entries):
        valid = {"blocking", "warning", "info"}
        for r in new_entries:
            assert r["severity"] in valid, (
                f"{r['ref_id']} invalid severity: {r['severity']}"
            )

    def test_formula_uses_wp_syntax(self, new_entries):
        for r in new_entries:
            for t in r["targets"]:
                assert t["formula"].startswith("=WP("), (
                    f"{r['ref_id']} formula not using =WP() syntax: {t['formula']}"
                )


# ─── Test 4: 6 个分组覆盖 ─────────────────────────────────────────────────────


class TestGroupCoverage:
    """根据 design.md §4.3, 35 条按 6 分组分布"""

    def test_f0_internal_present(self, new_entries):
        """F0 内部联动 ≥ 5 条 (含反向回填 F0→F2)"""
        f0_internal = [
            r for r in new_entries
            if r.get("source_wp") == "F0"
            and (
                any(t.get("wp_code", "").startswith("F0") for t in r.get("targets", []))
                or r.get("category") == "data_flow_reverse"
            )
        ]
        assert len(f0_internal) >= 5, (
            f"Expected ≥5 F0 internal entries, got {len(f0_internal)}"
        )

    def test_f2_internal_present(self, new_entries):
        """F2 内部联动 ≥ 4 条"""
        f2_internal = [
            r for r in new_entries
            if r.get("source_wp") == "F2"
            and all(t.get("wp_code", "").startswith("F2") for t in r.get("targets", []))
        ]
        assert len(f2_internal) >= 4, (
            f"Expected ≥4 F2 internal entries, got {len(f2_internal)}"
        )

    def test_f_cross_workpapers_present(self, new_entries):
        """F 循环跨底稿 ≥ 8 条 (F2/F4/F5 三角等)"""
        f_cross = [
            r for r in new_entries
            if (r.get("source_wp") or "").startswith("F")
            and any(
                (t.get("wp_code") or "").startswith("F")
                and (t.get("wp_code") or "")[:2] != (r.get("source_wp") or "")[:2]
                for t in r.get("targets", [])
            )
        ]
        assert len(f_cross) >= 8, (
            f"Expected ≥8 F-cross workpaper entries, got {len(f_cross)}"
        )

    def test_f_to_a_cross_cycle_present(self, new_entries):
        """F → A 跨循环 ≥ 8 条"""
        f_to_a = [
            r for r in new_entries
            if (r.get("source_wp") or "").startswith("F")
            and any(
                (t.get("wp_code") or "").startswith("A")
                for t in r.get("targets", [])
            )
        ]
        assert len(f_to_a) >= 8, (
            f"Expected ≥8 F→A entries, got {len(f_to_a)}"
        )

    def test_f_to_t1_ipe_present(self, new_entries):
        """F → T1 IPE ≥ 4 条"""
        f_to_t1 = [
            r for r in new_entries
            if (r.get("source_wp") or "").startswith("F")
            and any(
                (t.get("wp_code") or "") == "T1"
                for t in r.get("targets", [])
            )
        ]
        assert len(f_to_t1) >= 4, (
            f"Expected ≥4 F→T1 IPE entries, got {len(f_to_t1)}"
        )

    def test_f_to_note_or_report_present(self, new_entries):
        """F → 附注/报表 ≥ 6 条"""
        f_to_note = [
            r for r in new_entries
            if (r.get("source_wp") or "").startswith("F")
            and any(
                (t.get("wp_code") or "") in ("NOTE", "REPORT")
                for t in r.get("targets", [])
            )
        ]
        assert len(f_to_note) >= 6, (
            f"Expected ≥6 F→note/report entries, got {len(f_to_note)}"
        )


# ─── Test 5: F-F8 反向回填 (F0→F2 data_flow_reverse) ──────────────────────────


class TestF0ToF2ReverseBackfill:
    """F-F8: F0 函证回函 → F2 反向回填.
    Validates Requirements F-F8.1: cross_wp_references 含 F0→F2 data_flow_reverse 条目.
    """

    def test_reverse_entry_exists(self, new_entries):
        """至少存在 1 条 F0→F2 且 category=data_flow_reverse"""
        reverse = [
            r for r in new_entries
            if r.get("source_wp") == "F0"
            and r.get("category") == "data_flow_reverse"
            and any(
                (t.get("wp_code") or "") == "F2"
                for t in r.get("targets", [])
            )
        ]
        assert len(reverse) >= 1, (
            "F-F8 反向回填条目缺失: 需至少 1 条 F0→F2 且 category=data_flow_reverse"
        )

    def test_reverse_entry_has_trigger(self, new_entries):
        """反向回填条目应携带 trigger 字段 (eventBus confirmation:received)"""
        reverse = [
            r for r in new_entries
            if r.get("source_wp") == "F0"
            and r.get("category") == "data_flow_reverse"
            and any(
                (t.get("wp_code") or "") == "F2"
                for t in r.get("targets", [])
            )
        ]
        for r in reverse:
            trig = (r.get("trigger") or "").lower()
            assert "confirmation" in trig, (
                f"{r['ref_id']} trigger 字段缺失或不含 'confirmation': {r.get('trigger')}"
            )
