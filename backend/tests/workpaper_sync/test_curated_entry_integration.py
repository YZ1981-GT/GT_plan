# -*- coding: utf-8 -*-
"""Task 3 守卫：curated-entry facility 在真实 build_manifest 中的集成行为。

spec: `workpaper-sync-curated-entry-facility`
Requirements 1.1, 3.1, 3.2, 3.3, 3.4, 4.2

Task 1 的基线守卫（test_curated_entry_facility_baseline.py）已证明「空/缺省 curated_entries
⇒ 字节不变」（Property 1 / Requirement 1.3）。本文件补 Task 3 的集成正向路径：把一条
**合成** curated 声明（挂在一个真实 discovered host 上）喂给真实 `build_manifest`，断言：

- (a) 空/缺省 curated ⇒ manifest 不含 `curated_source_digest` / `stats.curated_entry_count`
  键，且与纯 discovery 基线字节一致（omit-when-zero，Requirement 1.3）。
- (b) 一条 populated curated 声明 ⇒ entry 被追加、`entry_count` +1、`curated_entry_count`
  出现且 = 1、`curated_source_digest` 出现并**参与** `manifest_digest`（改声明 → 两个 digest
  都变，Requirement 3.1/3.3）、`manifest_mount_ids == source_mount_ids` 仍成立（curated
  `mounts=[]` 被 template_ast 过滤排除，Requirement 4.2）。
- `source_digest` 不受 curated 影响（Requirement 3.4：curated 与物理挂载清单正交）。
- 前端投影里 curated entry 与 discovery entry 同构（含 roomServiceState，Requirement 4.2）。

用 Task 1 定影的 discovery fixture（活源在本分支漂移，见基线守卫 docstring）+ 一个挂在真实
host `GtD4OperatingRevenue.vue` 上的合成 curated 声明。
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

_GENERATOR_PATH = _BACKEND / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"
_OVERLAY_PATH = _BACKEND / "data" / "workpaper_sync_entry_overlay.json"
_FIXTURE_DIR = Path(__file__).resolve().parent / "data"
_DISCOVERY_FIXTURE = _FIXTURE_DIR / "curated_baseline_discovery.json"

# 真实 discovered host（基线 discovery fixture 里确实产出它）。
_D4_9_HOST = "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    return _load(_GENERATOR_PATH, "curated_integration_generator")


@pytest.fixture(scope="module")
def discovery() -> dict[str, Any]:
    if not _DISCOVERY_FIXTURE.is_file():
        pytest.fail(
            f"缺少 discovery 定影 {_DISCOVERY_FIXTURE.name}；"
            "先跑 python backend/tests/workpaper_sync/data/_capture_curated_baseline.py"
        )
    return json.loads(_DISCOVERY_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def overlay() -> dict[str, Any]:
    """『纯 discovery』overlay —— 把真实 overlay 的 `curated_entries` 段剥掉一份副本。

    Task 5 之后 reviewed overlay 已带 D4-9 curated 声明。本文件用一条**合成** curated 声明
    喂 build_manifest 做集成正向路径判据，前提是从「无 curated 段」的干净基线出发，因此剥掉
    真实 overlay 的 curated 段得到 curated-free 副本（语义等同 Task 5 之前），再叠加合成声明。
    仍反向断言真实 overlay 必须已带 curated_entries（Task 5 声明不得丢）。
    """
    value = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    assert "curated_entries" in value, (
        "真实 overlay 未带 curated_entries ⇒ Task 5 的 D4-9 curated 声明丢失"
    )
    stripped = copy.deepcopy(value)
    stripped.pop("curated_entries", None)
    return stripped


def _curated_declaration() -> dict[str, Any]:
    """合成 curated 声明：bidirectional + 全证据，挂在真实 host（design §2.2 D4-9 形状）。"""
    return {
        "entry_id": "xlsx/gt-d4-customer-structure",
        "host_path": _D4_9_HOST,
        "curated_reason": (
            "one dynamic GtOnlyOfficeSheet host backs D4-1/2/3/9; "
            "D4-9 needs its own contract+adapter"
        ),
        "document_type": "xlsx",
        "wp_match": {
            "wp_code_patterns": ["D4-9"],
            "component_types": [],
            "sheet_literals": ["重要客户结构分析D4-9"],
            "sheet_expressions": [],
            "source_host": _D4_9_HOST,
        },
        "html_store": "D4-9-data",
        "canonical_resolver": "d4_customer_structure_projection",
        "adapter_id": "d4.customer_structure",
        "capability": "bidirectional",
        "migration_state": "curated_bidirectional",
        "expected_profile": {
            "editability": ["editable"],
            "room_model": ["shared"],
            "scenario_profile_ids": ["xlsx.editable.shared.single.room_service_wired.v1"],
        },
        "profile": {
            "editability": "editable",
            "room_model": "shared",
            "scenario_profile_id": "xlsx.editable.shared.single.room_service_wired.v1",
        },
        "evidence": {
            "review_status": "curated_reviewed",
            "contract_test": "backend/tests/workpaper_sync/test_d4_9_task3_contract.py",
            "browser_case": None,
            "legacy_reasons": [],
        },
    }


def _overlay_with_curated(overlay: dict[str, Any], declarations: list[dict[str, Any]]) -> dict[str, Any]:
    merged = copy.deepcopy(overlay)
    merged["curated_entries"] = copy.deepcopy(declarations)
    return merged


class TestEmptyCaseOmitsCuratedKeys:
    def test_absent_curated_omits_digest_and_count(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """(a) 缺省 curated ⇒ manifest 不含 curated_source_digest / stats.curated_entry_count。"""
        built = gen.build_manifest(discovery, overlay)
        assert "curated_source_digest" not in built
        assert "curated_entry_count" not in built["stats"]

    def test_empty_list_omits_digest_and_count(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """(a) 显式空列表也 omit（与缺省同 —— omit-when-zero，Requirement 1.3）。"""
        built = gen.build_manifest(discovery, _overlay_with_curated(overlay, []))
        assert "curated_source_digest" not in built
        assert "curated_entry_count" not in built["stats"]

    def test_empty_list_manifest_bytes_equal_absent(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """(a) `[]` 与缺省两条路径 manifest+前端字节完全一致（overlay_digest 规范化）。"""
        absent = gen.build_manifest(discovery, overlay)
        empty = gen.build_manifest(discovery, _overlay_with_curated(overlay, []))
        assert gen.render_manifest(absent) == gen.render_manifest(empty)
        assert gen.render_frontend(absent) == gen.render_frontend(empty)


class TestPopulatedEmission:
    def test_curated_entry_appended_and_counts(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """(b) populated ⇒ entry 被追加、entry_count +1、curated_entry_count=1、digest 出现。"""
        base = gen.build_manifest(discovery, overlay)
        populated = gen.build_manifest(
            discovery, _overlay_with_curated(overlay, [_curated_declaration()])
        )

        # entry_count +1，且追加的正是那条 curated entry。
        assert populated["stats"]["entry_count"] == base["stats"]["entry_count"] + 1
        ids = {entry["entry_id"] for entry in populated["entries"]}
        assert "xlsx/gt-d4-customer-structure" in ids
        assert "xlsx/gt-d4-customer-structure" not in {
            entry["entry_id"] for entry in base["entries"]
        }

        # curated_entry_count 出现且 = 1；curated_source_digest 出现。
        assert populated["stats"]["curated_entry_count"] == 1
        assert "curated_source_digest" in populated
        assert isinstance(populated["curated_source_digest"], str) and populated[
            "curated_source_digest"
        ]

    def test_curated_entry_schema_matches_discovery(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """(b) curated entry 与 discovery entry 同构（含被 stamp 的 room_service_state）。"""
        populated = gen.build_manifest(
            discovery, _overlay_with_curated(overlay, [_curated_declaration()])
        )
        curated = next(
            e for e in populated["entries"] if e["entry_id"] == "xlsx/gt-d4-customer-structure"
        )
        assert not (gen._REQUIRED_ENTRY_FIELDS - curated.keys())
        assert curated["capability"] == "bidirectional"
        assert curated["adapter_id"] == "d4.customer_structure"
        assert curated["independent_entry"] is True
        assert curated["mounts"] == []
        # 关键：room_service_state 被从 discovery 的单一全局值 stamp 上来（否则 render_frontend KeyError）。
        assert (
            curated["scenario_profile"]["room_service_state"]
            == populated["stats"]["room_service_state"]
        )

    def test_curated_source_digest_participates_in_manifest_digest(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """(b) Requirement 3.1/3.3：改 curated 声明 ⇒ curated_source_digest 与 manifest_digest 都变。"""
        first = gen.build_manifest(
            discovery, _overlay_with_curated(overlay, [_curated_declaration()])
        )
        edited = _curated_declaration()
        edited["curated_reason"] = edited["curated_reason"] + " (edited)"
        second = gen.build_manifest(discovery, _overlay_with_curated(overlay, [edited]))

        assert first["curated_source_digest"] != second["curated_source_digest"]
        assert first["manifest_digest"] != second["manifest_digest"]

        # 反重言式：populated 的 manifest_digest 必然 != 空/缺省的 manifest_digest。
        absent = gen.build_manifest(discovery, overlay)
        assert first["manifest_digest"] != absent["manifest_digest"]

        # 精确断言：manifest_digest 是对「含 curated_source_digest 的 manifest 内容」现算的。
        # 这排除「curated_source_digest 只是挂在旁边、没进 digest 预映像」的假绿（把它移到
        # manifest_digest 计算之后就会被这条 assert 抓到）。
        preimage = copy.deepcopy(first)
        recomputed = preimage.pop("manifest_digest")
        assert (
            gen._sha256_bytes(gen._stable_json(preimage).encode("utf-8")) == recomputed
        ), "manifest_digest 与其内容不自洽"
        assert "curated_source_digest" in preimage, (
            "curated_source_digest 未进入 manifest_digest 预映像 ⇒ 未真正参与 digest（Requirement 3.1）"
        )
        # 移除 curated_source_digest 后重算必然改变 ⇒ 证明它确实被 digest 覆盖。
        without = copy.deepcopy(preimage)
        without.pop("curated_source_digest")
        assert (
            gen._sha256_bytes(gen._stable_json(without).encode("utf-8")) != recomputed
        ), "移除 curated_source_digest 后 digest 不变 ⇒ 它没被 digest 覆盖"

    def test_source_digest_unaffected_by_curated(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """(b) Requirement 3.4：source_digest 是物理挂载清单 digest，与 curated 正交、不变。"""
        absent = gen.build_manifest(discovery, overlay)
        populated = gen.build_manifest(
            discovery, _overlay_with_curated(overlay, [_curated_declaration()])
        )
        assert absent["source_digest"] == populated["source_digest"]

    def test_mount_id_check_still_holds_with_curated(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """(b) Requirement 4.2：curated mounts=[] 不破坏 manifest_mount_ids == source_mount_ids。

        build_manifest 内部若 mount 集不匹配会 raise；能成功产出即证明该检查通过。这里再显式
        重算一遍：所有 template_ast mount_id 集合应等于 discovery 物理 mount_id 集合，curated
        的 mounts=[] 贡献为空。
        """
        populated = gen.build_manifest(
            discovery, _overlay_with_curated(overlay, [_curated_declaration()])
        )
        source_mount_ids = {item["mountId"] for item in discovery["mounts"]}
        manifest_mount_ids = {
            item["mountId"]
            for entry in populated["entries"]
            for item in entry["mounts"]
            if item.get("sourceKind") == "template_ast"
        }
        assert manifest_mount_ids == source_mount_ids

    def test_frontend_projection_includes_curated_uniformly(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """(b) Requirement 4.2：前端投影里 curated entry 与 discovery entry 同形（无特判、无 KeyError）。"""
        populated = gen.build_manifest(
            discovery, _overlay_with_curated(overlay, [_curated_declaration()])
        )
        # render_frontend 读 scenario_profile.room_service_state；curated 无该字段会 KeyError。
        frontend = gen.render_frontend(populated)
        assert "xlsx/gt-d4-customer-structure" in frontend
        assert '"d4.customer_structure"' not in frontend  # adapter_id 不进前端投影
        # 前端投影的 stats 也带 curated_entry_count。
        assert '"curated_entry_count": 1' in frontend
