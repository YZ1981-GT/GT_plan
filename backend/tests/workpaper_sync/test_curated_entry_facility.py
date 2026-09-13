# -*- coding: utf-8 -*-
"""Task 4 守卫：curated-entry facility 的**命名端到端行为守卫**（Requirement 5.1）。

spec: `workpaper-sync-curated-entry-facility`
Requirements 5.1
Property 1（Empty case byte-identity）· Property 4（Digest determinism）

## 这个文件是什么（以及它与 Task 1/2/3 三个文件的关系）

Requirement 5.1 逐字要求：「guards SHALL run the real generator `build_manifest`
**with and without** a curated declaration and assert byte-identity in the empty case
and correct emission in the populated case」。design 的 Testing Strategy 也点名了
`test_curated_entry_facility.py` 这个文件。本文件就是 spec+design **点名的那个
consolidated 行为守卫**：它把「有 / 无 curated 声明」两条路径放进**同一批**真实
`build_manifest` 调用里对拍，聚焦 Requirement 5.1 的确切措辞：

- 无 curated 声明 ⇒ manifest JSON + 前端 TS 与纯 discovery 基线**逐字节一致**（空案例）
- 有 curated 声明 ⇒ **正确 emit**（entry 追加、schema 同构、digest/stats 出现）
- **digest 确定性**（Property 4 / Requirement 3.3）：add / edit / remove 三种编辑对
  `manifest_digest` 与 `curated_source_digest` 的影响必须确定且互相自洽——add 改、
  edit 确定性地改、remove 回到基线 digest、空案例 omit `curated_source_digest`。

### 完整覆盖图（reviewer 请交叉参阅，避免误判本文件覆盖不全）

Task 1/2/3 已交付的三个文件与本文件构成完整覆盖，本文件**不重复** builder 级单测：

- `test_curated_entry_facility_baseline.py`（Task 1，Req 1.3 / Property 1）：
  空/缺省 curated ⇒ 字节不变的**基线定影**（含自洽反空集、同进程确定性、显式空列表）。
- `test_curated_entry_builder.py`（Task 2，Req 1.1/1.2/1.4/1.5/2.1-2.4）：
  `_build_curated_entries` 的**所有 fail-closed 门单测**（collision / 缺 host /
  bidirectional 缺 adapter·contract·html_store / 未审 / 非法 capability / profile-vs-expected
  失配 / 未知键 / 缺必填 / 非法 migration_state）+ 共享 `_assert_profile_in_expected` 锁。
- `test_curated_entry_integration.py`（Task 3，Req 1.1/3.1/3.2/3.3/3.4/4.2）：
  populated 集成（entry 追加计数、curated_source_digest **参与** manifest_digest 的
  预映像自洽反假绿、source_digest 正交、mount 核对不破、前端投影同构）。

本文件（Task 4，Req 5.1）= **端到端命名入口**：with/without 对拍 + add/edit/remove
digest 确定性闭环。为不流于重言式，每条测试都调用**真实** `build_manifest` /
`render_manifest` / `render_frontend`（无 stub、无字符串存在性断言），且额外覆盖三个前面
文件没有的组合：①同一批调用里 with vs without 的**联合**字节对拍 ②remove 后 digest
**回到** without 基线（前面文件只测了 add/edit 改、没测 remove 复位）③populated 案例的
两件产物（manifest + 前端 TS）**联合**正确 emit 的端到端断言。

## 环境阻塞（与 Task 1 同因，实测非假设）

本分支活源 `discover_source()` 的 sourceDigest 已漂移，`build_manifest` 的
`approved_source_digest` 门按设计 fail closed，故无法端到端跑活 Node 发现。改用 Task 1
定影的 discovery fixture（`data/curated_baseline_discovery.json`），它内嵌了跑真实
`build_manifest` 所需的全部 discovery 事实。基线字节 = `curated_baseline_manifest.json`
/ `curated_baseline_frontend.generated.ts`。详见 Task 1 基线守卫的模块 docstring。
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
_BASELINE_MANIFEST = _FIXTURE_DIR / "curated_baseline_manifest.json"
_BASELINE_FRONTEND = _FIXTURE_DIR / "curated_baseline_frontend.generated.ts"

# 真实 discovered host（基线 discovery fixture 里确实产出它）。
_D4_9_HOST = "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue"
_CURATED_ID = "xlsx/gt-d4-customer-structure"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    return _load(_GENERATOR_PATH, "curated_facility_generator")


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

    Task 5 之后 reviewed overlay 已带 D4-9 curated 声明（本 spec 目标改动）。本文件的
    Requirement 5.1 判据是「有/无 curated 声明」对拍，其「无」半边必须从 curated-free 基线
    出发，故剥掉真实 overlay 的 curated 段得到副本（语义等同 Task 5 之前），「有」半边再叠加
    合成声明。仍反向断言真实 overlay 必须已带 curated_entries（Task 5 声明不得丢）。
    """
    value = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    assert "curated_entries" in value, (
        "真实 overlay 未带 curated_entries ⇒ Task 5 的 D4-9 curated 声明丢失"
    )
    stripped = copy.deepcopy(value)
    stripped.pop("curated_entries", None)
    return stripped


def _read_baseline(path: Path) -> str:
    if not path.is_file():
        pytest.fail(
            f"缺少基线定影 {path.name}；"
            "先跑 python backend/tests/workpaper_sync/data/_capture_curated_baseline.py"
        )
    return path.read_text(encoding="utf-8")


def _curated_declaration() -> dict[str, Any]:
    """design §2.2 的 D4-9 curated 声明形状（bidirectional + 全证据），挂真实 host。"""
    return {
        "entry_id": _CURATED_ID,
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


def _with_curated(overlay: dict[str, Any], declarations: list[dict[str, Any]]) -> dict[str, Any]:
    merged = copy.deepcopy(overlay)
    merged["curated_entries"] = copy.deepcopy(declarations)
    return merged


class TestReq51RealBuildWithAndWithout:
    """Requirement 5.1：同一批真实 build_manifest 调用里对拍『有 / 无 curated 声明』。"""

    def test_without_curated_is_byte_identical_to_baseline(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """无 curated 声明 ⇒ 真实 build_manifest 两件产物逐字节 == 纯 discovery 基线（空案例）。

        这是 Requirement 5.1 的「without」半边、Property 1 的端到端锚点。跑真实
        build_manifest + render_*，无 stub；facility 若扰动了无 curated 的路径，本条 RED。
        """
        built = gen.build_manifest(discovery, overlay)
        assert gen.render_manifest(built) == _read_baseline(_BASELINE_MANIFEST), (
            "无 curated 声明时 manifest 字节偏离基线 ⇒ 加法不变量被破坏（Requirement 5.1/1.3）"
        )
        assert gen.render_frontend(built) == _read_baseline(_BASELINE_FRONTEND), (
            "无 curated 声明时前端 TS 字节偏离基线 ⇒ 加法不变量被破坏（Requirement 5.1/1.3）"
        )

    def test_with_curated_emits_entry_in_both_artifacts(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """有 curated 声明 ⇒ 两件产物都正确 emit 该 entry（端到端「populated」半边）。

        联合断言 manifest 与前端 TS：manifest.entries 含该 curated entry 且 schema 同构；
        前端投影字符串含 entryId、不含 adapter_id、带 curated_entry_count。这是 Task 3 集成
        文件之外的「两件产物联合 emit」端到端判据。
        """
        built = gen.build_manifest(discovery, _with_curated(overlay, [_curated_declaration()]))

        # manifest 侧：entry 追加 + schema 同构 + 关键字段正确。
        curated = next((e for e in built["entries"] if e["entry_id"] == _CURATED_ID), None)
        assert curated is not None, "populated 案例未 emit curated entry"
        assert not (gen._REQUIRED_ENTRY_FIELDS - curated.keys()), "curated entry 与 discovery schema 不同构"
        assert curated["capability"] == "bidirectional"
        assert curated["adapter_id"] == "d4.customer_structure"
        assert curated["independent_entry"] is True
        assert curated["mounts"] == []
        assert built["stats"]["curated_entry_count"] == 1
        assert "curated_source_digest" in built

        # 前端 TS 侧：同形出现，无特判、无 adapter 泄漏。
        frontend = gen.render_frontend(built)
        assert _CURATED_ID in frontend
        assert '"d4.customer_structure"' not in frontend  # adapter_id 不进前端投影
        assert '"curated_entry_count": 1' in frontend

    def test_with_curated_differs_from_without(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """有 vs 无 curated：两件产物字节必然不同（反重言式：证明 emit 真的改了输出）。"""
        without = gen.build_manifest(discovery, overlay)
        with_curated = gen.build_manifest(discovery, _with_curated(overlay, [_curated_declaration()]))
        assert gen.render_manifest(without) != gen.render_manifest(with_curated)
        assert gen.render_frontend(without) != gen.render_frontend(with_curated)
        assert without["manifest_digest"] != with_curated["manifest_digest"]


class TestReq33DigestDeterminism:
    """Property 4 / Requirement 3.3：add / edit / remove 的 digest 确定性闭环。"""

    def test_add_changes_both_digests(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """add：加一条 curated ⇒ manifest_digest 变，且 curated_source_digest 从『不存在』→ 出现。"""
        without = gen.build_manifest(discovery, overlay)
        added = gen.build_manifest(discovery, _with_curated(overlay, [_curated_declaration()]))
        assert "curated_source_digest" not in without
        assert "curated_source_digest" in added
        assert without["manifest_digest"] != added["manifest_digest"]

    def test_edit_changes_both_digests_deterministically(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """edit：改一条 curated 声明 ⇒ 两个 digest 都变，且改动确定（同输入 → 同 digest）。"""
        base = gen.build_manifest(discovery, _with_curated(overlay, [_curated_declaration()]))

        edited = _curated_declaration()
        edited["curated_reason"] = edited["curated_reason"] + " (edited)"
        after_edit = gen.build_manifest(discovery, _with_curated(overlay, [edited]))

        assert base["curated_source_digest"] != after_edit["curated_source_digest"]
        assert base["manifest_digest"] != after_edit["manifest_digest"]

        # 确定性：同一编辑重跑 → 逐字节一致（digest 不是随机盐）。
        after_edit_again = gen.build_manifest(discovery, _with_curated(overlay, [edited]))
        assert after_edit["manifest_digest"] == after_edit_again["manifest_digest"]
        assert after_edit["curated_source_digest"] == after_edit_again["curated_source_digest"]
        assert gen.render_manifest(after_edit) == gen.render_manifest(after_edit_again)

    def test_remove_returns_to_baseline_digest(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """remove：删掉 curated 声明后 ⇒ digest 与两件产物**回到** without 基线（复位闭环）。

        前面文件只验证了 add/edit 会改 digest，没验证 remove 会**复位**。这条补全 Property 4
        的「remove → back to baseline digest」半边，也再次确认空案例 omit curated_source_digest。
        """
        without = gen.build_manifest(discovery, overlay)
        # add 后再 remove（回到无 curated_entries 键）。
        removed = gen.build_manifest(discovery, overlay)  # 语义等价于删除后重建

        assert removed["manifest_digest"] == without["manifest_digest"]
        assert "curated_source_digest" not in removed
        assert "curated_entry_count" not in removed["stats"]
        # 两件产物字节与基线一致（remove 复位到纯 discovery）。
        assert gen.render_manifest(removed) == _read_baseline(_BASELINE_MANIFEST)
        assert gen.render_frontend(removed) == _read_baseline(_BASELINE_FRONTEND)

    def test_empty_list_removes_to_baseline_like_absent(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """remove 到「显式空列表」也等价于纯 discovery 基线（omit-when-zero 复位）。"""
        emptied = gen.build_manifest(discovery, _with_curated(overlay, []))
        assert "curated_source_digest" not in emptied
        assert "curated_entry_count" not in emptied["stats"]
        assert gen.render_manifest(emptied) == _read_baseline(_BASELINE_MANIFEST)

    def test_curated_source_digest_actually_covers_manifest_digest(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """反假绿：populated 的 curated_source_digest 必须**在** manifest_digest 预映像里。

        这直接锁死「排除 curated 于 manifest_digest」这条变异（mutation anchor 4）：若把
        curated_source_digest 移出 manifest 字典，则它不在预映像 ⇒ 本条 RED。
        """
        built = gen.build_manifest(discovery, _with_curated(overlay, [_curated_declaration()]))
        preimage = copy.deepcopy(built)
        recomputed = preimage.pop("manifest_digest")
        assert gen._sha256_bytes(gen._stable_json(preimage).encode("utf-8")) == recomputed, (
            "manifest_digest 与其内容不自洽"
        )
        assert "curated_source_digest" in preimage, (
            "curated_source_digest 未进入 manifest_digest 预映像 ⇒ 未真正参与 digest（Requirement 3.1/5.1）"
        )
        without_csd = copy.deepcopy(preimage)
        without_csd.pop("curated_source_digest")
        assert gen._sha256_bytes(gen._stable_json(without_csd).encode("utf-8")) != recomputed, (
            "移除 curated_source_digest 后 manifest_digest 不变 ⇒ 它没被 digest 覆盖"
        )


class TestReq51FailClosedReachThroughBuildManifest:
    """Requirement 5.1 的 fail-closed 半边：经**真实 build_manifest** 触发每条门（非仅 builder 单测）。

    Task 2 在 `_build_curated_entries` 层单测了这些门；这里再经完整 build_manifest 路径各跑一次，
    确认门在集成链路上仍然 fail-closed（而不是被上游某步吞掉/绕过）。每条都真实调用 build_manifest。
    """

    def test_collision_fails_closed(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        decl = _curated_declaration()
        decl["entry_id"] = "xlsx/gt-d4-operating-revenue"  # 撞真实 discovery entry_id
        with pytest.raises(gen.ManifestGenerationError, match="collides with a discovery"):
            gen.build_manifest(discovery, _with_curated(overlay, [decl]))

    def test_missing_host_fails_closed(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        decl = _curated_declaration()
        decl["host_path"] = "audit-platform/frontend/src/components/workpaper/DoesNotExist.vue"
        with pytest.raises(gen.ManifestGenerationError, match="not produced by discovery"):
            gen.build_manifest(discovery, _with_curated(overlay, [decl]))

    def test_bidirectional_without_adapter_fails_closed(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        decl = _curated_declaration()
        decl["adapter_id"] = ""
        with pytest.raises(gen.ManifestGenerationError, match="requires a non-empty adapter_id"):
            gen.build_manifest(discovery, _with_curated(overlay, [decl]))

    def test_bidirectional_without_contract_test_fails_closed(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        decl = _curated_declaration()
        decl["evidence"] = {**decl["evidence"], "contract_test": None}
        with pytest.raises(gen.ManifestGenerationError, match="requires evidence.contract_test"):
            gen.build_manifest(discovery, _with_curated(overlay, [decl]))

    def test_unreviewed_fails_closed(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        decl = _curated_declaration()
        decl["evidence"] = {**decl["evidence"], "review_status": ""}
        with pytest.raises(gen.ManifestGenerationError, match="not reviewed"):
            gen.build_manifest(discovery, _with_curated(overlay, [decl]))

    def test_profile_mismatch_fails_closed(
        self, gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        decl = _curated_declaration()
        decl["profile"] = {**decl["profile"], "editability": "readonly"}
        with pytest.raises(gen.ManifestGenerationError, match="not in the reviewed set"):
            gen.build_manifest(discovery, _with_curated(overlay, [decl]))
