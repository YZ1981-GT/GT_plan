# -*- coding: utf-8 -*-
"""Task 6 守卫：跨 spec 闭合 —— D4-9 spec Task 6 的 capability/selectable 判据。

spec: `workpaper-sync-curated-entry-facility` / Task 6
Consumer: `d4-9-customer-structure-bidirectional-writeback` / Task 6
Requirements 5.3（浏览器证明 UNVERIFIABLE，非实现失败）

## 这个文件证明什么，以及为什么这样证明

D4-9 spec 的 Task 6 要靠两个函数收口：`assert_manifest_capability_enabled`
（entry 的 manifest capability 必须裁决为 bidirectional）与 `assert_entry_selectable`
（entry 可选中并挂上 `d4.customer_structure` adapter）。这两个函数在 D4 家族里由
`phase5_d4_revenue_detail.py`（D4-2 sibling）定义，形态一致：

    def assert_manifest_capability_enabled(*, manifest=None):
        entry = manifest_entries_by_id(manifest or load_entry_manifest())[ENTRY_ID]
        if capability_of(entry) is not Capability.bidirectional: raise ...
        if entry["adapter_id"] != ADAPTER_ID: raise ...

关键两点（读源码实测）：
1. 两函数都带 `manifest` 参数 —— 一个**真实的 in-memory seam**；
2. `manifest is None` 时回落 `load_entry_manifest()`，读的是**磁盘** manifest（lru_cache）。

🔴 但 `phase5_d4_customer_structure.py`（D4-9 本体）**尚未定义**这两个函数 —— 它们
正是 D4-9 Task 6 要新增的符号，而 D4-9 Task 6 之所以还开着，恰恰是因为它被本 facility
「落盘」所阻塞。所以本闭合守卫**不 stub** 这两个函数，而是驱动它们所包裹的**同一套真实
底层逻辑**（`manifest_entries_by_id` + `entry_profile.capability_of` + registry
`assert_bidirectional_ready` / `resolve_for_entry`），对着**内存里现建**的 manifest 跑。
这忠实复现 D4-9 函数落地后会做的事，且全程真实生产代码，无假绿。

内存 manifest 的建法 = Task 5 接线法：真实 overlay（已带 D4-9 curated 声明）+ Task 1
定影的 discovery fixture 喂真实 `build_manifest`。**不强推磁盘 regen，不 bump
approved_source_digest。**

## 三态覆盖

- PROVEN（内存，真实底层逻辑）：D4-9 entry capability 现算为 bidirectional、可选中、
  registry 挂上 `d4.customer_structure`（Part A）。
- BLOCKED（磁盘）：磁盘 manifest 不含 D4-9 entry、宿主 entry 仍 single_onlyoffice ⇒
  这两个函数的**磁盘形态**必然 fail，且这是既有 approved_source_digest 漂移所致、与
  curated facility 正交（Part B，显式断言而非跳过，防「假装磁盘也过了」）。
- UNVERIFIABLE（浏览器/OO）：无 OO runtime，浏览器双向证明记 UNVERIFIABLE（Part C，
  Req 5.3；xfail-with-reason，绝不伪装成 pass 或 fail）。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import definitions as D  # noqa: E402
from app.services.workpaper_sync import entry_profile as EP  # noqa: E402
from app.services.workpaper_sync import phase5_d4_customer_structure as D49  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D42  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    AuthorityModel,
    BundleSlot,
    DefinitionState,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402

_GENERATOR_PATH = _BACKEND / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"
_OVERLAY_PATH = _BACKEND / "data" / "workpaper_sync_entry_overlay.json"
_FIXTURE_DIR = Path(__file__).resolve().parent / "data"
_DISCOVERY_FIXTURE = _FIXTURE_DIR / "curated_baseline_discovery.json"

_CURATED_ID = D49.ENTRY_ID          # xlsx/gt-d4-customer-structure（读本体常量，不硬编码）
_ADAPTER_ID = D49.ADAPTER_ID        # d4.customer_structure
_HOST_ENTRY_ID = D42.ENTRY_ID       # xlsx/gt-d4-operating-revenue（同宿主 D4-2 entry）


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    return _load_module(_GENERATOR_PATH, "closure_generator")


@pytest.fixture(scope="module")
def discovery() -> dict[str, Any]:
    if not _DISCOVERY_FIXTURE.is_file():
        pytest.fail(
            f"缺少 discovery 定影 {_DISCOVERY_FIXTURE.name}；"
            "先跑 backend/tests/workpaper_sync/data/_capture_curated_baseline.py"
        )
    return json.loads(_DISCOVERY_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def real_overlay() -> dict[str, Any]:
    value = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    curated = value.get("curated_entries") or []
    assert any(e.get("entry_id") == _CURATED_ID for e in curated), (
        "真实 overlay 未带 D4-9 curated 声明 ⇒ Task 5 接线丢失，闭合无从谈起"
    )
    return value


@pytest.fixture(scope="module")
def in_memory_manifest(
    gen: ModuleType, discovery: dict[str, Any], real_overlay: dict[str, Any]
) -> dict[str, Any]:
    """Task 5 接线法：真实 overlay(带 D4-9 curated) + pinned discovery 喂真实 build_manifest。"""
    return gen.build_manifest(discovery, real_overlay)


# ═══════════════════════════════════════════════════════════════════════════
# 底层逻辑复现：D4-9 Task 6 的两个函数所包裹的真实生产逻辑
#   —— 直接调用 entry_profile / registry 生产代码，不 stub、不新建生产符号。
# ═══════════════════════════════════════════════════════════════════════════


def _capability_enabled_logic(manifest: dict[str, Any]) -> None:
    """`assert_manifest_capability_enabled` 的**函数体**（对着传入 manifest 跑）。

    与 `phase5_d4_revenue_detail.assert_manifest_capability_enabled` 逐行同构，只是
    ENTRY_ID/ADAPTER_ID 换成 D4-9 本体常量。全走真实 `manifest_entries_by_id` +
    `capability_of`。
    """
    entry = EP.manifest_entries_by_id(manifest)[_CURATED_ID]
    capability = EP.capability_of(entry)
    if capability is not EP.Capability.bidirectional:
        raise D49.EntrySelectionError(
            f"entry {_CURATED_ID} 的 manifest capability={capability.value} 未裁决为 bidirectional"
        )
    if str(entry.get("adapter_id") or "") != _ADAPTER_ID:
        raise D49.EntrySelectionError(
            f"entry {_CURATED_ID} 的 adapter_id={entry.get('adapter_id')!r} 与 {_ADAPTER_ID!r} 不符"
        )


# ── registry 脚手架（与 Task 5 wiring 守卫同法，registry 判据本身全走生产代码）──


class _StubAdapter:
    def __init__(self, adapter_id: str, document_type: str = "xlsx") -> None:
        self.adapter_id = adapter_id
        self.document_type = document_type
        self.contract_version = "1.0.0"

    async def read_current_projection(self, ctx: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def stage_projection_mutation(self, ctx: Any, merged: Any, *, expected_revision: int) -> Any:  # pragma: no cover
        raise NotImplementedError

    def materialize(self, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def extract(self, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def verify_unmanaged_regions(self, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


def _bundle_for(contract: C.SyncContract) -> DefinitionBundleSnapshot:
    import hashlib

    def _fake(label: str) -> str:
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    slots = {
        BundleSlot.template: D.definition_slot_spec(
            BundleSlot.template, definition_id=uuid.uuid4(),
            definition_sha256=contract.template_definition_sha256,
        ),
        BundleSlot.instrumentation: D.definition_slot_spec(
            BundleSlot.instrumentation, definition_id=uuid.uuid4(),
            definition_sha256=contract.instrumentation_definition_sha256,
        ),
        BundleSlot.contract: D.definition_slot_spec(
            BundleSlot.contract, definition_id=uuid.uuid4(),
            definition_sha256=contract.canonical_sha256,
        ),
    }
    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_fake("d4-9-closure-bundle"),
        schema_version=D.BUNDLE_SCHEMA_VERSION,
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_fake("d4-9-closure-authority"),
        slots=slots,
    )


_D49_DESCRIPTOR = EP.DescriptorFacts(mode=EP.DescriptorMode.bidirectional, exposes_mode_switch=True)
_D49_ROOM = EP.RoomFacts(shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=True)


def _registration(contract: C.SyncContract) -> RG.AdapterRegistration:
    return RG.AdapterRegistration(
        adapter=_StubAdapter(_ADAPTER_ID),
        entry_id=_CURATED_ID,
        matcher=RG.EntryMatcher(
            document_type="xlsx",
            wp_codes=frozenset(D49.WP_CODES),
            sheet_keys=frozenset({"d49-managed"}),
        ),
        bundle=_bundle_for(contract),
        descriptor=_D49_DESCRIPTOR,
        room=_D49_ROOM,
        declared_capability=EP.Capability.bidirectional,
        contract=contract,
    )


@pytest.fixture(scope="module")
def real_contract() -> C.SyncContract:
    return C.load_contract(_ADAPTER_ID)


def _single_entry_manifest(entry: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "manifest_digest": "0" * 64, "entries": [entry]}


# ═══════════════════════════════════════════════════════════════════════════
# Part A —— PROVEN（内存，真实底层逻辑）
# ═══════════════════════════════════════════════════════════════════════════


class TestPartAInMemoryClosureProven:
    def test_d4_9_capability_enabled_against_in_memory_manifest(
        self, in_memory_manifest: dict[str, Any]
    ) -> None:
        """`assert_manifest_capability_enabled` 底层逻辑对内存 manifest 不抛（capability=bidirectional）。"""
        _capability_enabled_logic(in_memory_manifest)  # 不抛即通过
        entry = EP.manifest_entries_by_id(in_memory_manifest)[_CURATED_ID]
        assert EP.capability_of(entry) is EP.Capability.bidirectional
        assert entry["adapter_id"] == _ADAPTER_ID

    def test_capability_logic_is_not_a_tautology(
        self, in_memory_manifest: dict[str, Any]
    ) -> None:
        """反重言式：把 capability 降级 ⇒ 同一底层逻辑必抛（证明它真在判 capability）。"""
        broken = copy.deepcopy(in_memory_manifest)
        for entry in broken["entries"]:
            if entry["entry_id"] == _CURATED_ID:
                entry["capability"] = "single_onlyoffice"
        with pytest.raises(D49.EntrySelectionError, match="bidirectional"):
            _capability_enabled_logic(broken)

    def test_d4_9_entry_selectable_and_attaches_adapter(
        self, in_memory_manifest: dict[str, Any], real_contract: C.SyncContract
    ) -> None:
        """`assert_entry_selectable` 门后的真实 registry：resolve + assert_bidirectional_ready 挂 adapter。"""
        entry = EP.manifest_entries_by_id(in_memory_manifest)[_CURATED_ID]
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=_single_entry_manifest(entry))
        registry.register(_registration(real_contract))
        resolved = registry.resolve_for_entry(_CURATED_ID)
        assert resolved.adapter_id == _ADAPTER_ID
        ready = registry.assert_bidirectional_ready(_CURATED_ID)
        assert ready.adapter_id == _ADAPTER_ID

    def test_rg4_uniqueness_preserved(
        self, in_memory_manifest: dict[str, Any], real_contract: C.SyncContract
    ) -> None:
        """RG-4 保留：curated entry_id 上再注册第二个 adapter 必拒。"""
        entry = EP.manifest_entries_by_id(in_memory_manifest)[_CURATED_ID]
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=_single_entry_manifest(entry))
        registry.register(_registration(real_contract))
        second = RG.AdapterRegistration(
            adapter=_StubAdapter("d4.customer_structure_dup"),
            entry_id=_CURATED_ID,
            matcher=RG.EntryMatcher(
                document_type="xlsx",
                wp_codes=frozenset(D49.WP_CODES),
                sheet_keys=frozenset({"d49-other"}),
            ),
            bundle=_bundle_for(real_contract),
            descriptor=_D49_DESCRIPTOR,
            room=_D49_ROOM,
            declared_capability=EP.Capability.bidirectional,
            contract=None,
        )
        with pytest.raises(RG.RegistrationError, match="一个独立 entry 只能"):
            registry.register(second)

    def test_non_bidirectional_curated_fails_attach_closed(
        self, in_memory_manifest: dict[str, Any]
    ) -> None:
        """Req 4.3 复核：非 bidirectional 的 curated entry assert_bidirectional_ready 抛。"""
        entry = copy.deepcopy(EP.manifest_entries_by_id(in_memory_manifest)[_CURATED_ID])
        entry["capability"] = "single_onlyoffice"
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=_single_entry_manifest(entry))
        with pytest.raises(RG.FakeBidirectionalError):
            registry.assert_bidirectional_ready(_CURATED_ID)


# ═══════════════════════════════════════════════════════════════════════════
# Part B —— BLOCKED（磁盘，既有 approved_source_digest 漂移，与 facility 正交）
# ═══════════════════════════════════════════════════════════════════════════


class TestPartBDiskManifestBlockedByPreexistingDrift:
    def test_disk_manifest_lacks_d4_9_curated_entry(self) -> None:
        """磁盘 manifest 不含 D4-9 curated entry（disk regen 被 approved_source_digest 漂移堵）。"""
        disk = json.loads(EP.ENTRY_MANIFEST_PATH.read_text(encoding="utf-8"))
        ids = {e["entry_id"] for e in disk["entries"]}
        assert _CURATED_ID not in ids, (
            "磁盘 manifest 竟含 D4-9 curated entry —— 若 disk regen 已解阻，请把本 spec 状态改绿并更新证据"
        )
        assert "curated_source_digest" not in disk
        assert "curated_entry_count" not in disk.get("stats", {})

    def test_disk_form_capability_logic_fails_closed(self) -> None:
        """D4-9 函数的**磁盘形态**（manifest=None → load_entry_manifest）必然 fail-closed。

        直接驱动真实 `load_entry_manifest()`（磁盘）+ 同一 capability 底层逻辑：D4-9 entry
        不在磁盘 ⇒ `manifest_entries_by_id(...)[ENTRY_ID]` 抛 KeyError。这正是 disk-manifest
        形态被阻塞的证据（非 facility 缺陷）。
        """
        disk = dict(EP.load_entry_manifest())
        with pytest.raises(KeyError):
            _capability_enabled_logic(disk)

    def test_shared_host_entry_still_single_onlyoffice_on_disk(self) -> None:
        """同宿主 D4-2 entry 在磁盘仍 single_onlyoffice / adapter=null（降级分支现状）。"""
        disk = EP.manifest_entries_by_id(EP.load_entry_manifest())
        host = disk.get(_HOST_ENTRY_ID)
        assert host is not None, f"磁盘 manifest 缺宿主 entry {_HOST_ENTRY_ID}"
        assert host.get("capability") == "single_onlyoffice"
        assert not host.get("adapter_id")


# ═══════════════════════════════════════════════════════════════════════════
# Part C —— UNVERIFIABLE（浏览器/OnlyOffice runtime，Req 5.3）
# ═══════════════════════════════════════════════════════════════════════════


class TestPartCBrowserProofUnverifiable:
    @pytest.mark.xfail(
        reason="UNVERIFIABLE: 本机无 OnlyOffice runtime（D:\\DeepHorness / OO 缺）——"
        "curated bidirectional entry 的浏览器级双向证明记 UNVERIFIABLE，非实现失败（Req 5.3）",
        strict=True,
        raises=RuntimeError,
    )
    def test_browser_bidirectional_roundtrip_unverifiable(self) -> None:
        """Req 5.3：浏览器双向证明 UNVERIFIABLE。

        用 strict xfail-with-reason 记录，绝不伪装成 pass（假绿）或 fail（伪装成实现缺陷）。
        当且仅当有 OO runtime 时把 raise 去掉真跑浏览器往返。
        """
        raise RuntimeError(
            "no OnlyOffice runtime available on this machine; browser proof UNVERIFIABLE per Req 5.3"
        )
