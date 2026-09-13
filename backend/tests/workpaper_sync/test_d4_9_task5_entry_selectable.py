# -*- coding: utf-8 -*-
"""Task 5 守卫：D4-9 bridge `assert_entry_selectable`（design §3 交付物，行为级）。

spec: d4-9-customer-structure-bidirectional-writeback / Task 5
Requirements: 1.1, 1.4, 1.5

## 这个文件证明什么，以及为什么这样证明

design §3 把 `assert_entry_selectable` 列为本 bridge 的 Task-5 交付物（镜像 D4-2 sibling
`phase5_d4_revenue_detail.assert_entry_selectable`）。它是冻结 curated entry 的 **fail-closed
选型门**：entry 缺失 / document_type 非 xlsx / 非 independent_entry / profile 不符 /
wp_code_patterns 不符 逐条 raise，通过则返回 entry 映射。

本守卫**不 stub、不重言式**：直接调用 **D4-9 bridge 的真实** `assert_entry_selectable`，喂
**内存里现建**的真实 manifest（真实生成器 `build_manifest` + 真实 reviewed overlay + pinned
discovery fixture，与 `test_curated_entry_cross_spec_closure.py` / `test_d4_9_task6_*.py` 同一
接线法），无 DB、无 OnlyOffice。

- PASS：真实 in-memory manifest + 真实 D4-9 模板 resolution ⇒ 门通过、返回 D4-9 entry，
  且 entry_id / adapter_id / document_type=xlsx / independent_entry=True / profile / codes 齐备。
- FAIL-CLOSED（对 in-memory entry 的 deepcopy 逐项变异）：missing entry / document_type!=xlsx
  / independent_entry falsy / 错 profile_id / 错 wp_code_patterns 各自 raise `EntrySelectionError`。
  这些变异证明门**绑定 manifest 内容**（非恒真重言式）。

## 为什么用 pinned discovery fixture 而非磁盘 manifest

`generate_workpaper_sync_manifest.py --apply` 在本分支被既有 `approved_source_digest` 漂移
堵死（与 D4-9 curated 声明正交），故用 sourceDigest 恰等 reviewed 的 pinned discovery fixture
喂真实 `build_manifest` 复现结构。磁盘写盘记 UNVERIFIABLE（见 Task 6/13 报告）。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import (  # noqa: E402
    phase5_d4_customer_structure as bridge,
)

_GENERATOR_PATH = _BACKEND / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"
_OVERLAY_PATH = _BACKEND / "data" / "workpaper_sync_entry_overlay.json"
_DISCOVERY_FIXTURE = (
    Path(__file__).resolve().parent / "data" / "curated_baseline_discovery.json"
)

_CURATED_ID = bridge.ENTRY_ID  # xlsx/gt-d4-customer-structure（读本体常量，不硬编码）
_ADAPTER_ID = bridge.ADAPTER_ID  # d4.customer_structure


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("d4_9_task5_generator", _GENERATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    return _load_generator()


@pytest.fixture(scope="module")
def discovery() -> dict[str, Any]:
    if not _DISCOVERY_FIXTURE.is_file():
        pytest.fail(
            f"缺少 discovery 定影 {_DISCOVERY_FIXTURE.name}；"
            "先跑 backend/tests/workpaper_sync/data/_capture_curated_baseline.py"
        )
    return json.loads(_DISCOVERY_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def overlay() -> dict[str, Any]:
    value = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    curated = value.get("curated_entries")
    assert isinstance(curated, list) and any(
        e.get("entry_id") == _CURATED_ID for e in curated
    ), "真实 overlay 未带 D4-9 curated 声明 ⇒ Task 5 接线丢失"
    return value


@pytest.fixture(scope="module")
def in_memory_manifest(
    gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """真实 build_manifest（真实 overlay(带 D4-9 curated) + pinned discovery）。"""
    return gen.build_manifest(discovery, overlay)


@pytest.fixture()
def real_resolution() -> bridge.TemplateResolutionFacts:
    """真实 D4-9 模板 resolution：wp_code 全零命中 + 父码落权威模板。

    `parent_resolved_path` 用 bridge 自己的 `authoritative_template_path()`（D4-9 权威模板
    `D/D4收入底稿.xlsx`），使 `assert_no_implicit_template_fallback` 对 happy path 通过。
    """
    return bridge.TemplateResolutionFacts(
        by_wp_code={code: () for code in bridge.WP_CODES},
        parent_code="D4",
        parent_resolved_path=bridge.authoritative_template_path(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# PASS —— 真实 in-memory manifest + 真实 resolution ⇒ 门通过返回 D4-9 entry
# ═══════════════════════════════════════════════════════════════════════════


class TestAssertEntrySelectablePass:
    def test_returns_d4_9_entry(
        self,
        in_memory_manifest: dict[str, Any],
        real_resolution: bridge.TemplateResolutionFacts,
    ) -> None:
        entry = bridge.assert_entry_selectable(
            resolution=real_resolution, manifest=in_memory_manifest
        )
        assert entry["entry_id"] == _CURATED_ID
        assert entry["adapter_id"] == _ADAPTER_ID
        assert str(entry.get("document_type")) == "xlsx"
        assert entry.get("independent_entry") is True
        assert (entry.get("scenario_profile") or {}).get(
            "profile_id"
        ) == bridge.EXPECTED_PROFILE_ID
        codes = {
            str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()
        }
        assert codes == set(bridge.WP_CODES)

    def test_returned_entry_is_the_manifest_entry(
        self,
        in_memory_manifest: dict[str, Any],
        real_resolution: bridge.TemplateResolutionFacts,
    ) -> None:
        """门返回的正是 manifest 里那条 entry（不是另造对象）。"""
        from app.services.workpaper_sync.entry_profile import manifest_entries_by_id

        entry = bridge.assert_entry_selectable(
            resolution=real_resolution, manifest=in_memory_manifest
        )
        assert entry is manifest_entries_by_id(in_memory_manifest)[_CURATED_ID]


# ═══════════════════════════════════════════════════════════════════════════
# FAIL-CLOSED —— 对 in-memory entry 的 deepcopy 逐项变异，各自 raise
#   证明门绑定 manifest 内容（非恒真重言式）。
# ═══════════════════════════════════════════════════════════════════════════


def _single_entry_manifest(entry: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "manifest_digest": "0" * 64, "entries": [entry]}


class TestAssertEntrySelectableFailClosed:
    @pytest.fixture()
    def d4_9_entry(self, in_memory_manifest: dict[str, Any]) -> dict[str, Any]:
        from app.services.workpaper_sync.entry_profile import manifest_entries_by_id

        return copy.deepcopy(manifest_entries_by_id(in_memory_manifest)[_CURATED_ID])

    def test_missing_entry_fails(
        self, real_resolution: bridge.TemplateResolutionFacts
    ) -> None:
        empty = {"schema_version": 1, "manifest_digest": "0" * 64, "entries": []}
        with pytest.raises(bridge.EntrySelectionError, match="不在 source-backed manifest"):
            bridge.assert_entry_selectable(resolution=real_resolution, manifest=empty)

    def test_wrong_document_type_fails(
        self,
        d4_9_entry: dict[str, Any],
        real_resolution: bridge.TemplateResolutionFacts,
    ) -> None:
        d4_9_entry["document_type"] = "word"
        with pytest.raises(bridge.EntrySelectionError, match="document_type"):
            bridge.assert_entry_selectable(
                resolution=real_resolution,
                manifest=_single_entry_manifest(d4_9_entry),
            )

    def test_not_independent_entry_fails(
        self,
        d4_9_entry: dict[str, Any],
        real_resolution: bridge.TemplateResolutionFacts,
    ) -> None:
        d4_9_entry["independent_entry"] = False
        with pytest.raises(bridge.EntrySelectionError, match="independent_entry"):
            bridge.assert_entry_selectable(
                resolution=real_resolution,
                manifest=_single_entry_manifest(d4_9_entry),
            )

    def test_wrong_profile_id_fails(
        self,
        d4_9_entry: dict[str, Any],
        real_resolution: bridge.TemplateResolutionFacts,
    ) -> None:
        d4_9_entry.setdefault("scenario_profile", {})["profile_id"] = "xlsx.some.other.v9"
        with pytest.raises(bridge.EntrySelectionError, match="profile_id"):
            bridge.assert_entry_selectable(
                resolution=real_resolution,
                manifest=_single_entry_manifest(d4_9_entry),
            )

    def test_wrong_wp_code_patterns_fails(
        self,
        d4_9_entry: dict[str, Any],
        real_resolution: bridge.TemplateResolutionFacts,
    ) -> None:
        d4_9_entry.setdefault("wp_match", {})["wp_code_patterns"] = ["WRONG-CODE"]
        with pytest.raises(bridge.EntrySelectionError, match="wp_code_patterns"):
            bridge.assert_entry_selectable(
                resolution=real_resolution,
                manifest=_single_entry_manifest(d4_9_entry),
            )

    def test_leaked_template_fallback_fails(
        self, in_memory_manifest: dict[str, Any]
    ) -> None:
        """零回退判据反向自检：wp_code 在 finder 解析到文件 ⇒ raise（否则空集恒真）。"""
        polluted = bridge.TemplateResolutionFacts(
            by_wp_code={code: (str(bridge.authoritative_template_path()),) for code in bridge.WP_CODES},
            parent_code="D4",
            parent_resolved_path=bridge.authoritative_template_path(),
        )
        with pytest.raises(bridge.EntrySelectionError, match="零回退判据"):
            bridge.assert_entry_selectable(
                resolution=polluted, manifest=in_memory_manifest
            )
