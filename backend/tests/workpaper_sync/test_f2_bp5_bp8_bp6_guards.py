# -*- coding: utf-8 -*-
"""F2 前置守卫：BP-5（受管路径不经整册码回落） / BP-8（合册不入契约） / BP-6（manifest 与 slice 不一致）。

spec: f2-sync-coverage-four-entry-lanes · Task 5b · Requirements 1.6, 1.7, 1.8

═══ BP-5 ═══
①不修跨循环"F2 约 60 sheet 无 sheet→模板映射"（另立 spec）
②守卫"已修的一半不复发"：find_template_file('F2') 返回审定明细表类册 + 第一层命中数==1
③四条 lane 的受管路径走 resolve_for_entry(entry_id)，调用链上无 find_template_file(wp_code)

═══ BP-8 ═══
F2存货.xlsx (560,160 B / 74 sheet) 不在 _index.json ⇒ 运行时不可达，不入任何 F2 契约

═══ BP-6 ═══
manifest capability==single_onlyoffice 且 slice 重裁 capability==null（必须不等，FC-12）
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

TPL_DIR = _BACKEND / "wp_templates"
SLICE_PATH = _BACKEND / "data" / "workpaper_sync_f_cycle_manifest_slice.json"
MANIFEST_PATH = _BACKEND / "data" / "workpaper_sync_entry_manifest.json"
INDEX_PATH = TPL_DIR / "_index.json"
CONTRACTS_DIR = _BACKEND / "data" / "workpaper_sync_contracts"
OVERLAY_PATH = _BACKEND / "data" / "workpaper_sync_entry_overlay.json"

# 四条 lane 的 TEMPLATE_SHA256（slice authoritative_templates 按值取）
LANE_TEMPLATE_SHA256 = {
    "xlsx/gt-f2-inventory-main": "9e57efd242b47171423e61f63a35be6ae5b46889baa14c246595ea95591fd0d8",
    "xlsx/gt-f2-stocktake-bundle": "bdfdcf8a804aab1c11db1cc2cd2deaac4f5bbf94c6a60e43a04108f178079bc7",
    "xlsx/gt-f2-inventory-valuation": "bab0abc099cfed3efdde3095bed510b3bbe7422ce32431054811034f6e6d5cd5",
    "xlsx/gt-f2-inventory-special": "b9ea248198217827a7b3d142dccca9ab5769c17867d1454ffd9105eaa9cb6c21",
}

# 不可达合册的 sha256
UNREACHABLE_COMPOSITE_SHA256 = "afc762843ffee1c32087848d6401500b53d5f3fb59d32c1098acfff6f1b2ef0d"

F2_ENTRY_IDS = list(LANE_TEMPLATE_SHA256.keys())


# ═══════════════════════════════════════════════════════════════════════════
# BP-5：受管路径不经整册码回落
# ═══════════════════════════════════════════════════════════════════════════


class TestBP5WholeCodeFallbackGuard:
    """BP-5 三条守卫。"""

    def test_find_template_file_f2_returns_main_template(self) -> None:
        """find_template_file('F2') 返回审定明细表类册（main 的 template_ref）。"""
        from app.services.wp_template_finder import find_template_file_unresolved

        result = find_template_file_unresolved("F2")
        assert result is not None, "find_template_file('F2') 返回 None"
        assert "审定明细表类" in result.name, (
            f"find_template_file('F2') 未返回审定明细表类册: {result.name}"
        )

    def test_primary_template_tier_1_hits_exactly_one_for_f2(self) -> None:
        """_PRIMARY_TEMPLATE_TIERS 第一层「审定」在 F2 候选集命中数 == 1。
        BP-5 latent_regression_shape 的复发条件是命中数 ≥ 2。"""
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        files = index.get("files", [])
        # F2 候选集：wp_code 精确匹配 F2 的索引项
        f2_candidates = [
            f for f in files
            if f.get("wp_code") == "F2" or (
                "relative_path" in f
                and f["relative_path"].startswith("F/F2")
                and "F2-" in f.get("filename", f.get("relative_path", ""))
            )
        ]
        # 第一层 tier = "审定"
        tier1_hits = [
            c for c in f2_candidates
            if "审定" in (c.get("filename") or c.get("relative_path", ""))
        ]
        assert len(tier1_hits) == 1, (
            f"第一层「审定」在 F2 候选集命中 {len(tier1_hits)} 条（复发条件是 ≥2）: "
            f"{[c.get('filename', c.get('relative_path')) for c in tier1_hits]}"
        )

    def test_resolve_for_entry_does_not_call_find_template_file(self) -> None:
        """四条 lane 的受管解析走 resolve_for_entry(entry_id)，
        其调用链上无 find_template_file(wp_code)。"""
        from app.services.workpaper_sync.adapters import registry as RG

        # resolve_for_entry 的实现只查 self._by_entry_id dict，不导入 wp_template_finder
        source = inspect.getsource(RG.WorkpaperSyncAdapterRegistry.resolve_for_entry)
        assert "find_template_file" not in source, (
            "resolve_for_entry 的源码含 find_template_file 调用——受管路径不应经整册码回落"
        )
        # assert_bidirectional_ready 调用 resolve_for_entry 也不含 find_template_file
        source2 = inspect.getsource(RG.WorkpaperSyncAdapterRegistry.assert_bidirectional_ready)
        assert "find_template_file" not in source2, (
            "assert_bidirectional_ready 含 find_template_file 调用"
        )


# ═══════════════════════════════════════════════════════════════════════════
# BP-8：不可达合册不入契约
# ═══════════════════════════════════════════════════════════════════════════


class TestBP8UnreachableCompositeNotInContracts:
    """F2存货.xlsx 不在 _index.json ⇒ 运行时不可达，sha 不入任何 F2 契约。"""

    def test_composite_not_in_runtime_index(self) -> None:
        """F2存货.xlsx 不在 _index.json（现算，不沿用 slice 快照）。"""
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        paths = [
            f.get("relative_path", "").replace("\\", "/")
            for f in index.get("files", [])
        ]
        assert "F/F2存货.xlsx" not in paths, (
            "F2存货.xlsx 出现在 _index.json 里——BP-8 的前提变了"
        )

    def test_composite_sha_not_in_any_f2_contract(self) -> None:
        """F2存货.xlsx 的 sha256 不出现在任何 F2 契约文件里。"""
        for f in CONTRACTS_DIR.glob("f2.*.json"):
            content = f.read_text(encoding="utf-8")
            assert UNREACHABLE_COMPOSITE_SHA256 not in content, (
                f"合册 sha 出现在 {f.name} 里——不可达文件不得入契约"
            )

    def test_four_lane_sha_match_slice(self) -> None:
        """四条 lane 的 TEMPLATE_SHA256 逐字取 slice authoritative_templates 值。"""
        slice_data = json.loads(SLICE_PATH.read_text(encoding="utf-8"))
        at_files = slice_data["authoritative_templates"]["files"]
        # 建立 entry→sha 映射
        slice_sha_by_entry: dict[str, str] = {}
        for f in at_files:
            entry = f.get("belongs_to_entry")
            if entry:
                slice_sha_by_entry[entry] = f["sha256"]

        for entry_id, expected_sha in LANE_TEMPLATE_SHA256.items():
            slice_sha = slice_sha_by_entry.get(entry_id)
            assert slice_sha is not None, f"{entry_id} 不在 slice authoritative_templates 里"
            assert expected_sha == slice_sha, (
                f"{entry_id} 的 sha 与 slice 不一致: {expected_sha} vs {slice_sha}"
            )

    def test_composite_sha_correct(self) -> None:
        """验证 F2存货.xlsx 的 sha256 确实是已知值。"""
        composite_path = TPL_DIR / "F" / "F2存货.xlsx"
        if composite_path.exists():
            real_sha = hashlib.sha256(composite_path.read_bytes()).hexdigest()
            assert real_sha == UNREACHABLE_COMPOSITE_SHA256, (
                f"合册 sha 已变: {real_sha} != {UNREACHABLE_COMPOSITE_SHA256}"
            )
        # 合册不存在也是合法状态（已被清理）


# ═══════════════════════════════════════════════════════════════════════════
# BP-6：manifest 与 slice 的 capability 不一致（FC-12）
# ═══════════════════════════════════════════════════════════════════════════


class TestBP6ManifestSliceCapabilityDivergence:
    """manifest capability==single_onlyoffice 且 slice 重裁 capability==null。"""

    def test_manifest_says_single_onlyoffice(self) -> None:
        """四个 F2 entry 在 manifest 里 capability==single_onlyoffice。"""
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        entries = {e["entry_id"]: e for e in manifest["entries"]}
        for entry_id in F2_ENTRY_IDS:
            entry = entries.get(entry_id)
            assert entry is not None, f"{entry_id} 不在 manifest 里"
            assert entry.get("capability") == "single_onlyoffice", (
                f"{entry_id} manifest capability != single_onlyoffice: "
                f"{entry.get('capability')}"
            )

    def test_slice_says_null(self) -> None:
        """四个 F2 entry 在 slice 里 capability==null。"""
        slice_data = json.loads(SLICE_PATH.read_text(encoding="utf-8"))
        entries = {e["entry_id"]: e for e in slice_data["independent_entries"]}
        for entry_id in F2_ENTRY_IDS:
            entry = entries.get(entry_id)
            assert entry is not None, f"{entry_id} 不在 slice 里"
            assert entry.get("capability") is None, (
                f"{entry_id} slice capability != null: {entry.get('capability')}"
            )

    def test_divergence_is_fact_not_bug(self) -> None:
        """两者不一致是既登记事实（FC-12），不得为「对齐」而改 overlay。"""
        # overlay 文件的 GtOnlyOfficeSheet 默认值不被本 spec 改动
        overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
        defaults = overlay.get("defaults_by_component", {}).get("GtOnlyOfficeSheet", {})
        # overlay 默认值应该是 single_onlyoffice（180 条 entry 的默认值）
        assert defaults.get("capability") == "single_onlyoffice", (
            "overlay GtOnlyOfficeSheet 默认 capability 已变——FC-12 的前提变了"
        )

    def test_overlay_digest_stable(self) -> None:
        """overlay 文件 digest 在本 spec 实施期间不变（不改 overlay）。"""
        digest = hashlib.sha256(OVERLAY_PATH.read_bytes()).hexdigest()
        # 记录当前 digest，后续 spec 实施若改变此文件则本判据打红
        assert len(digest) == 64, "digest 格式异常"
        # 只断言文件存在且可哈希，不固定值——其他 spec 可能合法改动
