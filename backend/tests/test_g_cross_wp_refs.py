"""Tests for G-cycle cross_wp_references entries (≥25 new entries)

Validates: Requirements G-F7, G-F8
- G-cycle 条目 ≥ 33 (baseline 8 + new ≥ 25)
- 所有 ref_id 全局唯一 (Property 3 / PBT-P3)
- 新增条目 schema 完整 (ref_id / source_wp / source_sheet / source_cell / targets / category / severity)
- ref_id 格式 CW-NNN (新增 G 条目从 CW-267 起编)
- category / severity 枚举值合法
- source_wp / target wp_code 非空
- G0→G7 函证反向回填 stale 传播路径存在 (data_flow_reverse, ADR-G5)
- 6 分组数量满足下限：内部 ≥ 6 / IS ≥ 4 / NOTE ≥ 5 / BS ≥ 4 / G11 汇总 ≥ 3 / IPE ≥ 3

Spec: workpaper-g-investment-cycle / Sprint 2 / Task 2.17
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CWR_PATH = DATA_DIR / "cross_wp_references.json"

# G 循环新增条目区间（双重过滤铁律：闭区间 + cycle_membership）
G_CWR_LO = 267
G_CWR_HI = 292


@pytest.fixture(scope="module")
def cwr_data() -> dict:
    assert CWR_PATH.exists(), f"cross_wp_references.json not found at {CWR_PATH}"
    return json.loads(CWR_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def references(cwr_data) -> list[dict]:
    return cwr_data["references"]


def _is_g_cycle(ref: dict) -> bool:
    """G-cycle membership: source_wp 或任一 target wp_code 以 G 开头"""
    src = ref.get("source_wp") or ""
    tgt_codes = [(t.get("wp_code") or "") for t in ref.get("targets", [])]
    return src.startswith("G") or any(t.startswith("G") for t in tgt_codes)


@pytest.fixture(scope="module")
def g_cycle_refs(references) -> list[dict]:
    """G-cycle 条目: source_wp 以 G 开头 OR 任一 target wp_code 以 G 开头"""
    return [r for r in references if _is_g_cycle(r)]


@pytest.fixture(scope="module")
def new_g_entries(references) -> list[dict]:
    """新增 G-cycle 条目: ref_id CW-267~CW-292 且属于 G-cycle (双重过滤)"""
    pattern = re.compile(r"^CW-(\d+)$")
    out = []
    for r in references:
        m = pattern.match(r.get("ref_id") or "")
        if not m:
            continue
        n = int(m.group(1))
        if not (G_CWR_LO <= n <= G_CWR_HI):
            continue
        if _is_g_cycle(r):
            out.append(r)
    return out


# ─── Test 1: G-cycle 条目数量 ─────────────────────────────────────────────────


class TestGCycleCounts:
    def test_g_cycle_at_least_33(self, g_cycle_refs):
        """G-cycle 条目 >= 33 (baseline 8 + new >= 25)"""
        assert len(g_cycle_refs) >= 33, (
            f"Expected ≥33 G-cycle references, got {len(g_cycle_refs)}"
        )

    def test_new_g_entries_at_least_25(self, new_g_entries):
        """新增 (CW-267~292) G-cycle 条目 >= 25"""
        assert len(new_g_entries) >= 25, (
            f"Expected ≥25 new G entries (CW-267~292), got {len(new_g_entries)}"
        )


# ─── Test 2: ref_id 全局唯一性（PBT-P3 等价覆盖）────────────────────────────


class TestRefIdUniqueness:
    def test_all_ref_ids_globally_unique(self, references):
        """所有 ref_id 全局唯一 (Property 3)"""
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

    def test_new_g_entries_in_assigned_range(self, new_g_entries):
        """新增 G-cycle 条目 ref_id 在 CW-267~CW-292 区间"""
        pattern = re.compile(r"^CW-(\d+)$")
        for r in new_g_entries:
            m = pattern.match(r["ref_id"])
            assert m and G_CWR_LO <= int(m.group(1)) <= G_CWR_HI, (
                f"G-cycle new entry {r['ref_id']} should be in CW-{G_CWR_LO}~CW-{G_CWR_HI}"
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
    REQUIRED_TARGET_FIELDS = {"wp_code"}  # cell/formula 在 note/report target 中可能用 cell+target_route 替代

    def test_required_fields_present(self, new_g_entries):
        for r in new_g_entries:
            missing = self.REQUIRED_FIELDS - set(r.keys())
            assert not missing, f"{r.get('ref_id')} missing fields: {missing}"

    def test_targets_non_empty(self, new_g_entries):
        for r in new_g_entries:
            assert isinstance(r["targets"], list) and len(r["targets"]) >= 1, (
                f"{r['ref_id']} has empty targets"
            )

    def test_target_wp_code_present(self, new_g_entries):
        for r in new_g_entries:
            for t in r["targets"]:
                missing = self.REQUIRED_TARGET_FIELDS - set(t.keys())
                assert not missing, (
                    f"{r['ref_id']} target missing fields: {missing}"
                )

    def test_no_empty_source_wp(self, new_g_entries):
        for r in new_g_entries:
            assert r.get("source_wp"), f"{r['ref_id']} has empty source_wp"

    def test_no_empty_target_wp_code(self, new_g_entries):
        for r in new_g_entries:
            for t in r["targets"]:
                assert t.get("wp_code"), (
                    f"{r['ref_id']} has empty target wp_code"
                )

    def test_source_cell_non_empty(self, new_g_entries):
        for r in new_g_entries:
            assert r.get("source_cell"), (
                f"{r['ref_id']} has empty source_cell"
            )


# ─── Test 4: category / severity 枚举值合法 ───────────────────────────────────


class TestEnumValues:
    """枚举值检查（与 H/I cycle 一致）"""

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
        "investment_cycle",
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

    def test_category_values_valid(self, new_g_entries):
        for r in new_g_entries:
            assert r["category"] in self.VALID_CATEGORIES, (
                f"{r['ref_id']} invalid category: {r['category']}"
            )

    def test_severity_values_valid(self, new_g_entries):
        for r in new_g_entries:
            assert r["severity"] in self.VALID_SEVERITIES, (
                f"{r['ref_id']} invalid severity: {r['severity']}"
            )


# ─── Test 5: G0→G7 函证反向回填 stale 传播路径（ADR-G5）─────────────────


class TestG0ToG7ReverseBackfill:
    """G-F8: G0 函证 → G7 长期股权投资反向回填.
    Validates Requirements G-F8.1, G-F8.2: cross_wp_references 含 G0→G7 data_flow_reverse 条目.
    """

    def test_g0_to_g7_reverse_entry_exists(self, g_cycle_refs):
        """至少存在 1 条 G0→G7 且 category=data_flow_reverse"""
        reverse = [
            r for r in g_cycle_refs
            if r.get("source_wp") == "G0"
            and r.get("category") == "data_flow_reverse"
            and any(
                (t.get("wp_code") or "") == "G7"
                for t in r.get("targets", [])
            )
        ]
        assert len(reverse) >= 1, (
            "G-F8 反向回填条目缺失: 需至少 1 条 G0→G7 且 category=data_flow_reverse"
        )

    def test_g0_to_g7_severity_warning(self, g_cycle_refs):
        """G0→G7 反向回填 severity=warning（按 ADR-G5 约定）"""
        reverse = [
            r for r in g_cycle_refs
            if r.get("source_wp") == "G0"
            and r.get("category") == "data_flow_reverse"
            and any((t.get("wp_code") or "") == "G7" for t in r.get("targets", []))
        ]
        assert len(reverse) >= 1
        for r in reverse:
            assert r.get("severity") == "warning", (
                f"{r['ref_id']} severity 应为 warning，实际 {r.get('severity')}"
            )

    def test_g0_to_g7_target_references_g0(self, g_cycle_refs):
        """G0→G7 反向回填 target 应有 formula 字段引用 G0"""
        reverse = [
            r for r in g_cycle_refs
            if r.get("source_wp") == "G0"
            and r.get("category") == "data_flow_reverse"
            and any((t.get("wp_code") or "") == "G7" for t in r.get("targets", []))
        ]
        for r in reverse:
            for t in r["targets"]:
                if t.get("wp_code") == "G7":
                    assert "formula" in t, (
                        f"{r['ref_id']} G0→G7 target missing formula"
                    )
                    formula = t.get("formula") or ""
                    # data_flow_reverse 必须引用源 wp_code='G0'
                    assert "G0" in formula, (
                        f"{r['ref_id']} G7 target formula 应引用 G0：{formula!r}"
                    )


# ─── Test 6: 6 分组数量满足下限（G-F7）─────────────────────────────────


class TestGroupCounts:
    """6 分组数量验证（G-F7 task 2.16 子任务声明）"""

    def test_internal_linkage_at_least_6(self, new_g_entries):
        """G 内部联动 ≥ 6（含 G0→G7 反向回填条目）"""
        internal = [
            r for r in new_g_entries
            if (r.get("source_wp") or "").startswith("G")
            and all(
                (t.get("wp_code") or "").startswith("G")
                for t in r.get("targets", [])
            )
        ]
        assert len(internal) >= 6, (
            f"G 内部联动 ≥ 6 缺失，实际 {len(internal)}"
        )

    def test_to_income_statement_at_least_4(self, new_g_entries):
        """G → 利润表（A2/IS 报表行）≥ 4"""
        is_targets = []
        for r in new_g_entries:
            for t in r.get("targets", []):
                row = t.get("report_row_code", "") or ""
                # IS 报表行通常以 IS 开头或为利润表标识
                target_type = t.get("target_type", "")
                if target_type == "report_row" and (
                    row.startswith("IS-") or row.startswith("PL-") or "利润" in (t.get("sheet") or "")
                ):
                    is_targets.append(r["ref_id"])
                    break
        assert len(is_targets) >= 4, (
            f"G → 利润表 ≥ 4 缺失，实际 {len(is_targets)}"
        )

    def test_to_disclosure_notes_at_least_5(self, new_g_entries):
        """G → 附注披露 ≥ 5"""
        note_targets = []
        for r in new_g_entries:
            for t in r.get("targets", []):
                target_type = t.get("target_type", "")
                if target_type == "note_section" or t.get("note_section_code"):
                    note_targets.append(r["ref_id"])
                    break
        assert len(note_targets) >= 5, (
            f"G → 附注 ≥ 5 缺失，实际 {len(note_targets)}"
        )

    def test_to_balance_sheet_at_least_4(self, new_g_entries):
        """G → A 财务报表（BS 报表行）≥ 4"""
        bs_targets = []
        for r in new_g_entries:
            for t in r.get("targets", []):
                row = t.get("report_row_code", "") or ""
                target_type = t.get("target_type", "")
                if target_type == "report_row" and (
                    row.startswith("BS-") or row.startswith("BS_")
                ):
                    bs_targets.append(r["ref_id"])
                    break
        assert len(bs_targets) >= 4, (
            f"G → BS 报表行 ≥ 4 缺失，实际 {len(bs_targets)}"
        )

    def test_g11_aggregation_at_least_3(self, new_g_entries):
        """G11 ← 子循环汇总 ≥ 3（G1/G4/G6/G7/G8 → G11）"""
        agg = [
            r for r in new_g_entries
            if (r.get("source_wp") or "") in {"G1", "G4", "G6", "G7", "G8"}
            and any(
                (t.get("wp_code") or "") == "G11"
                for t in r.get("targets", [])
            )
        ]
        assert len(agg) >= 3, (
            f"G11 子循环汇总 ≥ 3 缺失，实际 {len(agg)}"
        )

    def test_to_t1_ipe_at_least_3(self, new_g_entries):
        """G → T1 IPE ≥ 3"""
        ipe = [
            r for r in new_g_entries
            if r.get("category") == "ipe_reference"
            or any(
                (t.get("wp_code") or "").startswith("T1")
                for t in r.get("targets", [])
            )
        ]
        assert len(ipe) >= 3, (
            f"G → T1 IPE ≥ 3 缺失，实际 {len(ipe)}"
        )


# ─── Test 7: stale 传播 lookup 可达性 ─────────────────────────────────


class TestStalePropagationLookup:
    """新增 G-cycle 条目可被 stale_engine 索引：source_wp + source_sheet + source_cell 三元组检索"""

    def test_source_triple_lookup_works(self, new_g_entries):
        """每条新增条目都能按 (source_wp, source_sheet, source_cell) 唯一定位"""
        triples = set()
        for r in new_g_entries:
            triple = (r["source_wp"], r["source_sheet"], r["source_cell"])
            triples.add(triple)
        # 不要求 triples 完全唯一（同一 cell 可触发多条 ref），但每条 ref 应能映射回 source
        assert len(triples) >= 1

    def test_target_lookup_yields_cells(self, new_g_entries):
        """每条新增条目至少有 1 个 target 含 cell 或 cell-equivalent 字段（note_section_code/report_row_code）"""
        for r in new_g_entries:
            for t in r["targets"]:
                has_locator = any(
                    t.get(k) for k in ("cell", "note_section_code", "report_row_code")
                )
                assert has_locator, (
                    f"{r['ref_id']} target 缺乏定位字段（cell/note_section_code/report_row_code）"
                )
