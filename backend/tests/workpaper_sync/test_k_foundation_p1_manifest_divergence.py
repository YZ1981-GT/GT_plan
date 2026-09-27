# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 0 Task 1：manifest 与 slice 分歧门（BP-9）。

spec: k-cycle-sync-foundation-and-first-canary
Task 1: manifest 与 slice 分歧门（BP-9），验证 13 条 entry 边界
Property: KF-P1, KF-P2, KF-P3, KF-P4

═══ 判据 ═══

KF-P1: 按 selection_rule 从 manifest 现算 K 前缀 xlsx 独立 entry == slice 的
       independent_entries，大小 **13**。
KF-P2: manifest 里 13 条 K entry 的 capability 全 `single_onlyoffice` /
       html_store 全 `unresolved` / adapter_id 全 null / **0 条有 capability_target**。
       🔴 这是 overlay 默认值机械展开的结果，不是裁决（KC-1）。
KF-P3: slice 现算 bidirectional 条数 == 0 且 capability_verdict_pending == 13；
       守卫断言 manifest 与 slice **不相等**并指向 BP-9。
KF-P4: parent_entry_id ∈ 13 条 == 0 ∧ overlay parent_rules 含 /k\\d 的 == 0 ∧
       slice 顶层无 parent_duplicate_summary 键。

═══ 与 test_task53 的关系 ═══

test_task53_k_cycle_migration.py 的 TestSliceScopeIsRecomputable 已覆盖
selection_rule 现算、scope counter、parent_duplicate 两侧验。本文件**聚焦
foundation spec 独有的精确判据**：KC-1 的 manifest 原值四字段逐条验、
slice 与 manifest 的不等式方向验、entry 全名等值。不重复 test_task53 的判据，
而是**加入它未覆盖的精确维度**。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
OVERLAY_PATH = DATA / "workpaper_sync_entry_overlay.json"

#: 13 条 entry 的全名（全名，无缩写，与 design.md 切分表等值）
K_ENTRY_IDS = frozenset({
    "xlsx/gt-k1-other-receivables",
    "xlsx/gt-k2-other-current-assets",
    "xlsx/gt-k3-other-payables",
    "xlsx/gt-k4-other-current-liabilities",
    "xlsx/gt-k5-provisions",
    "xlsx/gt-k6-held-for-sale",
    "xlsx/gt-k7-deferred-income",
    "xlsx/gt-k8-selling-expenses",
    "xlsx/gt-k9-admin-expenses",
    "xlsx/gt-k10-other-income",
    "xlsx/gt-k11-asset-impairment-loss",
    "xlsx/gt-k12-non-operating-income",
    "xlsx/gt-k13-non-operating-expense",
})


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _k_prefixed_xlsx_independent(full_manifest: dict) -> list[dict]:
    """按 slice 的 selection_rule 从 manifest 现算 K 前缀 xlsx 独立 entry。"""
    out = []
    for e in full_manifest["entries"]:
        pats = (e.get("wp_match") or {}).get("wp_code_patterns") or []
        if (
            any(str(p).startswith("K") for p in pats)
            and e["document_type"] == "xlsx"
            and e["independent_entry"]
        ):
            out.append(e)
    return out


# ════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def full_manifest() -> dict:
    return _load(FULL_MANIFEST_PATH)


@pytest.fixture(scope="module")
def overlay() -> dict:
    return _load(OVERLAY_PATH)


# ════════════════════════════════════════════════════════════════════════════
# KF-P1: entry 集合等值
# ════════════════════════════════════════════════════════════════════════════
class TestKFP1EntrySetEquality:
    """selection_rule 从 manifest 现算的集合与 slice 声明的集合等值。"""

    def test_selection_rule_recomputes_exactly_13(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        recomputed = {
            e["entry_id"] for e in _k_prefixed_xlsx_independent(full_manifest)
        }
        declared = {
            e["entry_id"] for e in manifest_slice["independent_entries"]
        }
        assert declared == recomputed, (
            f"多写 {sorted(declared - recomputed)}，漏写 {sorted(recomputed - declared)}"
        )
        assert len(recomputed) == 13

    def test_entry_ids_match_the_design_table(
        self, manifest_slice: dict
    ) -> None:
        """与 design.md 的切分表等值比对——13 条全名一个不多一个不少。"""
        actual = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert actual == K_ENTRY_IDS, (
            f"与 design 表不符：多 {sorted(actual - K_ENTRY_IDS)}，"
            f"缺 {sorted(K_ENTRY_IDS - actual)}"
        )

    def test_slice_scope_count_equals_13(self, manifest_slice: dict) -> None:
        assert manifest_slice["slice_scope"]["independent_entry_count"] == 13


# ════════════════════════════════════════════════════════════════════════════
# KF-P2: manifest 原值四字段（KC-1：overlay 默认值，非裁决）
# ════════════════════════════════════════════════════════════════════════════
class TestKFP2ManifestOriginalValues:
    """🔴 manifest 原值是 overlay 默认值机械展开的结果，不是逐 entry 裁决。"""

    def test_all_13_capability_is_single_onlyoffice_in_manifest(
        self, full_manifest: dict
    ) -> None:
        """manifest 原值 capability 全 single_onlyoffice。"""
        ks = _k_prefixed_xlsx_independent(full_manifest)
        assert len(ks) == 13
        for e in ks:
            assert e["capability"] == "single_onlyoffice", (
                f"{e['entry_id']}: manifest capability={e['capability']!r}"
            )

    def test_all_13_html_store_is_unresolved_in_manifest(
        self, full_manifest: dict
    ) -> None:
        ks = _k_prefixed_xlsx_independent(full_manifest)
        for e in ks:
            assert e["html_store"] == "unresolved", (
                f"{e['entry_id']}: manifest html_store={e['html_store']!r}"
            )

    def test_all_13_adapter_id_is_null_in_manifest(
        self, full_manifest: dict
    ) -> None:
        ks = _k_prefixed_xlsx_independent(full_manifest)
        for e in ks:
            assert e["adapter_id"] is None, (
                f"{e['entry_id']}: manifest adapter_id={e['adapter_id']!r}"
            )

    def test_zero_entries_have_capability_target_field_in_manifest(
        self, full_manifest: dict
    ) -> None:
        """🔴 KC-1 关键判据：manifest 原值里 0 条有 capability_target 字段。"""
        ks = _k_prefixed_xlsx_independent(full_manifest)
        has_ct = [
            e["entry_id"] for e in ks if "capability_target" in e
        ]
        assert has_ct == [], (
            f"manifest 原值里出现了 capability_target 字段：{has_ct}"
        )

    def test_these_values_come_from_overlay_defaults_not_per_entry_ruling(
        self, full_manifest: dict, overlay: dict
    ) -> None:
        """overlay 的 defaults_by_component.GtOnlyOfficeSheet 驱动了这些默认值。"""
        defaults = overlay.get("defaults_by_component", {}).get("GtOnlyOfficeSheet", {})
        assert defaults.get("capability") == "single_onlyoffice"
        assert defaults.get("html_store") == "unresolved"
        ks = _k_prefixed_xlsx_independent(full_manifest)
        for e in ks:
            assert e["capability"] == defaults["capability"]
            assert e["html_store"] == defaults["html_store"]


# ════════════════════════════════════════════════════════════════════════════
# KF-P3: slice 与 manifest 不相等（BP-9）
# ════════════════════════════════════════════════════════════════════════════
class TestKFP3SliceManifestDivergence:
    """守卫断言 manifest 与 slice 在 capability 上不相等并指向 BP-9。"""

    def test_slice_bidirectional_count_is_zero(
        self, manifest_slice: dict
    ) -> None:
        s = manifest_slice["honest_adjudication_summary"]
        assert s["adjudicated_as_bidirectional"] == 0

    def test_slice_capability_verdict_pending_is_13(
        self, manifest_slice: dict
    ) -> None:
        s = manifest_slice["honest_adjudication_summary"]
        assert s["capability_verdict_pending"] == 13

    def test_all_13_slice_entries_have_null_capability(
        self, manifest_slice: dict
    ) -> None:
        """slice 的 capability 全 null（待裁决），manifest 的是 single_onlyoffice。"""
        for e in manifest_slice["independent_entries"]:
            assert e["capability"] is None, (
                f"{e['entry_id']}: slice capability={e['capability']!r}，应为 null（待裁决）"
            )

    def test_manifest_and_slice_are_not_equal_and_point_to_bp9(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 断言两者不相等且分歧已登记为 BP-9。"""
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        diverged = 0
        for e in manifest_slice["independent_entries"]:
            live_cap = by_id[e["entry_id"]]["capability"]
            slice_cap = e["capability"]
            if live_cap != slice_cap:
                diverged += 1
        assert diverged == 13, (
            f"期望 13/13 不一致，实得 {diverged}/13 —— "
            "断言相等就是把 overlay 默认值当裁决（AP-3 明禁）"
        )
        # BP-9 必须存在于阻断项列表
        bp_ids = {b["id"] for b in manifest_slice["blocking_preconditions"]}
        assert "BP-9" in bp_ids, "BP-9 不在阻断项列表里"

    def test_manifest_mirror_documents_the_divergence(
        self, manifest_slice: dict
    ) -> None:
        """每条 entry 的 manifest_mirror 须指出 why_not_adopted 含 BP-9。"""
        for e in manifest_slice["independent_entries"]:
            mirror = e["manifest_mirror"]
            assert mirror["capability"] == "single_onlyoffice", (
                f"{e['entry_id']}: 镜像值期望 single_onlyoffice"
            )
            assert "BP-9" in mirror["why_not_adopted"], (
                f"{e['entry_id']}: why_not_adopted 不含 BP-9"
            )


# ════════════════════════════════════════════════════════════════════════════
# KF-P4: parent_duplicate 为 0（两侧都验）
# ════════════════════════════════════════════════════════════════════════════
class TestKFP4ParentDuplicateZero:
    """KD-5: parent_duplicate == 0，且 slice 顶层无 parent_duplicate_summary。"""

    def test_no_manifest_entry_has_parent_in_k_set(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        k_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        children = [
            e["entry_id"] for e in full_manifest["entries"]
            if e.get("parent_entry_id") in k_ids
        ]
        assert children == [], (
            f"manifest 里有 K 的 parent_duplicate 子入口：{children}"
        )

    def test_overlay_has_no_k_parent_rules(self, overlay: dict) -> None:
        k_rules = [
            r for r in overlay.get("parent_rules", [])
            if re.search(r"/k\d+/", str(r.get("file_glob", "")))
        ]
        assert k_rules == [], (
            f"overlay parent_rules 含 K 的 file_glob：{k_rules}"
        )

    def test_slice_scope_count_is_zero(self, manifest_slice: dict) -> None:
        assert manifest_slice["slice_scope"]["parent_duplicate_count"] == 0

    def test_no_parent_duplicate_summary_key_in_slice(
        self, manifest_slice: dict
    ) -> None:
        """🔴 触发条件不成立时写空节 = additive 死声明（KD-5）。"""
        assert "parent_duplicate_summary" not in manifest_slice

    def test_k0_has_template_but_no_entry(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 KD-4 / KF-P7: K0 有册但无 entry（与 J0 的都返 None 相反）。"""
        k0_hits = [
            e["entry_id"] for e in full_manifest["entries"]
            if "k0" in e["entry_id"].lower()
        ]
        assert k0_hits == [], f"manifest 出现 K0 entry：{k0_hits}"
        # K0 权威模板存在
        k_template_dir = ROOT / "backend" / "wp_templates" / "K"
        k0_file = k_template_dir / "K0 管理循环函证.xlsx"
        assert k0_file.exists(), "K0 册不存在 ⇒ 与 KD-4 登记矛盾"
        # slice 里 K0 被排除且有 excluded_reason
        at = manifest_slice["authoritative_templates"]
        k0_rec = next(
            (f for f in at["files"] if f["name"] == "K0 管理循环函证.xlsx"), None
        )
        assert k0_rec is not None, "slice 的 authoritative_templates 没有 K0 册"
        assert k0_rec["belongs_to_entry"] is None
        assert k0_rec.get("excluded_reason"), "K0 无 excluded_reason"
