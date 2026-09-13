# -*- coding: utf-8 -*-
"""Task 5 守卫：D4-9 curated entry 的**接线**——真实 build_manifest 重生 +1 + registry attach。

spec: `workpaper-sync-curated-entry-facility` / Task 5
Requirements 4.1, 4.3
Property 5（Registry compatibility）

## 这个文件证明什么

Task 5 有两半，本文件各给一条**真实代码**判据（无 stub、无字符串存在性）：

### 半边 A —— 重生成产出 +1 entry（对拍 pinned discovery fixture）

真实磁盘 `--apply` 在本分支被**既有 mount-inventory 漂移**堵死（`discover_source()`
的 sourceDigest = `a18a531d…` ≠ reviewed `approved_source_digest` = `d9fddb64…`，
`build_manifest` 的 digest 门按设计 fail closed；这与 curated facility 无关，属 Req 3.4
明确划出的物理挂载清单正交面）。所以 Task 1 定影了一份 discovery fixture，其 sourceDigest
恰等于 overlay 的 approved_source_digest，可喂给真实 `build_manifest` 复现结构。

本半边把**真实 overlay（现已带 D4-9 curated 声明）** + 那份 pinned discovery fixture 喂给
真实 `build_manifest`，断言：
- `entry_count == baseline + 1`（唯一的增量正是 D4-9）；
- `xlsx/gt-d4-customer-structure` 存在，`adapter_id == d4.customer_structure`、
  `capability == bidirectional`、`independent_entry is True`、`mounts == []`；
- `stats.curated_entry_count == 1`、`curated_source_digest` 出现且参与 manifest_digest。

这证明 overlay 声明合法、重生成**会**产出 +1 entry —— 唯一被堵的只是「用漂移的活源
`--apply` 写盘」，而那是既有漂移、不是 curated facility 的缺陷。

### 半边 B —— registry attach（Req 4.1 / 4.3 / Property 5）

对**真实 build_manifest 产出的那条 curated entry**，驱动**真实** registry 代码：

- Req 4.1：curated bidirectional entry **可选中**（`assert_bidirectional_ready` 经
  `capability_of` 判定 + `resolve_for_entry` 取到 adapter）且真实 `register()` 挂上
  `d4.customer_structure`；RG-4 唯一性保留 —— 同一 entry_id 再注册第二个 adapter 抛
  `RegistrationError`（curated id 与 discovery id 天然不相交，故不撞 discovery）。
- Req 4.3：非 bidirectional 的 curated entry **attach 关闭失败**——`assert_bidirectional_ready`
  抛 `FakeBidirectionalError`；且声明 bidirectional 的 adapter 注册到非双向 entry 上时
  `register()` 以 `FakeBidirectionalError`（RG-18）拒绝。

registry 不被 stub：用真实 `WorkpaperSyncAdapterRegistry` + 真实磁盘契约
`d4.customer_structure`（RG-10/RG-11 双漂移门真跑）+ 与 D4-9 profile 一致的
descriptor/room 事实。bundle 用 frozen snapshot（contract slot digest 锁到真实契约的
canonical digest），这是唯一的测试脚手架，registry 判据本身全走生产代码。

## 环境阻塞（实测，非假设）

见 `--apply` 失败实证：本分支 `python backend/scripts/gen/generate_workpaper_sync_manifest.py
--apply` 抛 `source mounts changed since the reviewed overlay: approved='d9fddb64…'
current='a18a531d…'`。这是既有的 approved_source_digest 漂移（宿主挂载清单变了），
与 D4-9 curated 声明正交（Req 3.4）。故本文件用 pinned fixture 证明「重生成逻辑正确」，
磁盘写盘阻塞记为 pre-existing drift，不 bump approved_source_digest 强推。
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
_BASELINE_MANIFEST = _FIXTURE_DIR / "curated_baseline_manifest.json"

_CURATED_ID = "xlsx/gt-d4-customer-structure"
_ADAPTER_ID = "d4.customer_structure"
_D4_9_HOST = "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    return _load_module(_GENERATOR_PATH, "curated_d4_9_generator")


@pytest.fixture(scope="module")
def discovery() -> dict[str, Any]:
    if not _DISCOVERY_FIXTURE.is_file():
        pytest.fail(
            f"缺少 discovery 定影 {_DISCOVERY_FIXTURE.name}；"
            "先跑 python backend/tests/workpaper_sync/data/_capture_curated_baseline.py"
        )
    return json.loads(_DISCOVERY_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def real_overlay() -> dict[str, Any]:
    """真实 reviewed overlay —— Task 5 之后**必须**已带 D4-9 curated 声明。"""
    value = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    curated = value.get("curated_entries")
    assert isinstance(curated, list) and curated, (
        "真实 overlay 未带 curated_entries ⇒ Task 5 的 D4-9 curated 声明丢失"
    )
    d4_9 = [e for e in curated if e.get("entry_id") == _CURATED_ID]
    assert len(d4_9) == 1, f"real overlay 缺 D4-9 curated 声明（{_CURATED_ID}）"
    return value


@pytest.fixture(scope="module")
def curated_free_overlay(real_overlay: dict[str, Any]) -> dict[str, Any]:
    """把真实 overlay 的 curated 段剥掉一份副本，用来算「baseline」entry_count。"""
    stripped = copy.deepcopy(real_overlay)
    stripped.pop("curated_entries", None)
    return stripped


# ═══════════════════════════════════════════════════════════════════════════
# 半边 A：真实 build_manifest 重生成产出 +1 entry
# ═══════════════════════════════════════════════════════════════════════════


class TestRegenerationEmitsD49Entry:
    def test_entry_count_is_baseline_plus_one(
        self,
        gen: ModuleType,
        discovery: dict[str, Any],
        real_overlay: dict[str, Any],
        curated_free_overlay: dict[str, Any],
    ) -> None:
        """真实 overlay（带 D4-9 curated）重生成 ⇒ entry_count == curated-free baseline + 1。"""
        baseline = gen.build_manifest(discovery, curated_free_overlay)
        with_curated = gen.build_manifest(discovery, real_overlay)
        assert (
            with_curated["stats"]["entry_count"] == baseline["stats"]["entry_count"] + 1
        ), "带 D4-9 curated 声明后 entry_count 未 +1"
        # 反重言式：baseline 里不含该 entry，with_curated 里含。
        base_ids = {e["entry_id"] for e in baseline["entries"]}
        cur_ids = {e["entry_id"] for e in with_curated["entries"]}
        assert _CURATED_ID not in base_ids
        assert _CURATED_ID in cur_ids
        assert cur_ids - base_ids == {_CURATED_ID}, "增量必须恰好只有 D4-9 一条"

    def test_d4_9_entry_shape(
        self, gen: ModuleType, discovery: dict[str, Any], real_overlay: dict[str, Any]
    ) -> None:
        """D4-9 entry 的关键字段与 discovery entry 同构且携带 d4.customer_structure adapter。"""
        built = gen.build_manifest(discovery, real_overlay)
        entry = next(e for e in built["entries"] if e["entry_id"] == _CURATED_ID)
        assert not (gen._REQUIRED_ENTRY_FIELDS - entry.keys()), "curated entry schema 不同构"
        assert entry["adapter_id"] == _ADAPTER_ID
        assert entry["capability"] == "bidirectional"
        assert entry["independent_entry"] is True
        assert entry["mounts"] == []
        assert entry["host_path"] == _D4_9_HOST
        assert entry["editability"] == "editable"
        assert entry["room_model"] == "shared"

    def test_curated_count_and_digest_present(
        self, gen: ModuleType, discovery: dict[str, Any], real_overlay: dict[str, Any]
    ) -> None:
        """stats.curated_entry_count==1 且 curated_source_digest 出现并参与 manifest_digest。"""
        built = gen.build_manifest(discovery, real_overlay)
        assert built["stats"]["curated_entry_count"] == 1
        assert "curated_source_digest" in built
        assert isinstance(built["curated_source_digest"], str) and built["curated_source_digest"]
        # curated_source_digest 真在 manifest_digest 预映像里。
        preimage = copy.deepcopy(built)
        recomputed = preimage.pop("manifest_digest")
        assert gen._sha256_bytes(gen._stable_json(preimage).encode("utf-8")) == recomputed
        assert "curated_source_digest" in preimage

    def test_baseline_fixture_entry_count_matches_frozen(
        self,
        gen: ModuleType,
        discovery: dict[str, Any],
        curated_free_overlay: dict[str, Any],
    ) -> None:
        """反空集：curated-free baseline entry_count 必须等于 Task 1 冻结基线（非平凡）。"""
        baseline = gen.build_manifest(discovery, curated_free_overlay)
        frozen = json.loads(_BASELINE_MANIFEST.read_text(encoding="utf-8"))
        assert baseline["stats"]["entry_count"] == frozen["stats"]["entry_count"]
        assert baseline["stats"]["entry_count"] >= 100, "baseline entry 数远少于生产 ⇒ 定影可疑"


# ═══════════════════════════════════════════════════════════════════════════
# 半边 B：registry attach（Req 4.1 / 4.3 / Property 5）
# ═══════════════════════════════════════════════════════════════════════════


def _manifest_of(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_digest": "0" * 64,
        "entries": [entry],
    }


def _real_d4_9_entry(gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """从真实 build_manifest 取出那条 curated D4-9 entry（registry 消费的真实形状）。"""
    built = gen.build_manifest(discovery, overlay)
    return next(e for e in built["entries"] if e["entry_id"] == _CURATED_ID)


class _StubAdapter:
    """满足 protocol 形态的最小 adapter（不继承基类：形态判据靠属性+可调用方法）。"""

    def __init__(self, adapter_id: str, document_type: str = "xlsx") -> None:
        self.adapter_id = adapter_id
        self.document_type = document_type
        self.contract_version = "1.0.0"

    async def read_current_projection(self, ctx: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def stage_projection_mutation(
        self, ctx: Any, merged: Any, *, expected_revision: int
    ) -> Any:  # pragma: no cover
        raise NotImplementedError

    def materialize(self, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def extract(self, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def verify_unmanaged_regions(self, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


def _def_slot(slot: BundleSlot, digest: str):
    """真实 definition slot spec（type=definition + ref=definition:<uuid> + digest）。"""
    return D.definition_slot_spec(slot, definition_id=uuid.uuid4(), definition_sha256=digest)


def _bundle_for(contract: C.SyncContract) -> DefinitionBundleSnapshot:
    """frozen bundle，三 slot digest 全锁到**真实契约**声明的 digest。

    RG-10：contract slot digest == contract.canonical_sha256；
    `assert_matches_bundle_slots`：template/instrumentation slot digest 必须等于契约声明的
    `template_definition_sha256` / `instrumentation_definition_sha256`（否则 ContractDrift）。
    全部从真实加载的契约取值 —— bundle 是唯一脚手架，但它锁死到真实契约字节。
    """
    import hashlib

    def _fake(label: str) -> str:
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    slots = {
        BundleSlot.template: _def_slot(
            BundleSlot.template, contract.template_definition_sha256
        ),
        BundleSlot.instrumentation: _def_slot(
            BundleSlot.instrumentation, contract.instrumentation_definition_sha256
        ),
        BundleSlot.contract: _def_slot(BundleSlot.contract, contract.canonical_sha256),
    }
    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_fake("d4-9-bundle"),
        schema_version=D.BUNDLE_SCHEMA_VERSION,
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_fake("d4-9-authority"),
        slots=slots,
    )


# D4-9 profile = editable/shared/bidirectional ⇒ descriptor bidirectional + shared room。
_D4_9_DESCRIPTOR = EP.DescriptorFacts(
    mode=EP.DescriptorMode.bidirectional, exposes_mode_switch=True
)
_D4_9_ROOM = EP.RoomFacts(
    shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=True
)


def _registration(
    contract: C.SyncContract,
    *,
    entry_id: str = _CURATED_ID,
    adapter_id: str = _ADAPTER_ID,
    declared: EP.Capability = EP.Capability.bidirectional,
) -> RG.AdapterRegistration:
    return RG.AdapterRegistration(
        adapter=_StubAdapter(adapter_id),
        entry_id=entry_id,
        matcher=RG.EntryMatcher(
            document_type="xlsx",
            wp_codes=frozenset({"D4O"}),
            sheet_keys=frozenset({"d49-managed"}),
        ),
        bundle=_bundle_for(contract),
        descriptor=_D4_9_DESCRIPTOR,
        room=_D4_9_ROOM,
        declared_capability=declared,
        contract=contract,
    )


@pytest.fixture(scope="module")
def real_contract() -> C.SyncContract:
    """真实磁盘 per-entry contract d4.customer_structure（RG-11 磁盘漂移门真跑）。"""
    return C.load_contract(_ADAPTER_ID)


class TestReq41CuratedBidirectionalSelectableAndAttaches:
    """Req 4.1：curated bidirectional entry 可选中 + 挂 d4.customer_structure（RG-4 保留）。"""

    def test_curated_entry_is_selectable_as_bidirectional(
        self, gen: ModuleType, discovery: dict[str, Any], real_overlay: dict[str, Any]
    ) -> None:
        """`assert_bidirectional_ready` 之前的**可选中**判据：capability + profile 一致。

        走真实 registry 代码：`capability_of` 判 bidirectional、`extract_entry_profile` +
        `assert_profile_consistent_with_capability` 证明 profile 与 capability 不冲突（这是
        `assert_bidirectional_ready` 里对 entry 的第一道门，attach 前必须先过）。
        """
        entry = _real_d4_9_entry(gen, discovery, real_overlay)
        assert EP.capability_of(entry) is EP.Capability.bidirectional
        profile = EP.extract_entry_profile(entry)
        # 不抛即为「可选中」：curated entry 的 profile 与 bidirectional 能力自洽。
        EP.assert_profile_consistent_with_capability(profile, EP.Capability.bidirectional)

    def test_register_attaches_adapter_and_resolves_by_entry_id(
        self,
        gen: ModuleType,
        discovery: dict[str, Any],
        real_overlay: dict[str, Any],
        real_contract: C.SyncContract,
    ) -> None:
        """真实 registry.register() 把 d4.customer_structure 挂到 curated entry 上并可解析。"""
        entry = _real_d4_9_entry(gen, discovery, real_overlay)
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=_manifest_of(entry))
        registry.register(_registration(real_contract))
        resolved = registry.resolve_for_entry(_CURATED_ID)
        assert resolved.adapter_id == _ADAPTER_ID
        # bidirectional 验收链路：走完 assert_bidirectional_ready 不抛。
        ready = registry.assert_bidirectional_ready(_CURATED_ID)
        assert ready.adapter_id == _ADAPTER_ID
        # 也可经 matcher 解析（selectable by wp_code+sheet_key）。
        by_matcher = registry.resolve(
            wp_code="D4O", document_type="xlsx", sheet_key="d49-managed"
        )
        assert by_matcher.adapter_id == _ADAPTER_ID

    def test_rg4_uniqueness_preserved_second_adapter_on_same_entry_fails(
        self,
        gen: ModuleType,
        discovery: dict[str, Any],
        real_overlay: dict[str, Any],
        real_contract: C.SyncContract,
    ) -> None:
        """RG-4：curated entry_id 已被 d4.customer_structure 占用后，第二个 adapter 注册必拒。

        证明 curated entry 未削弱 RG-4「一个独立 entry 只解析到唯一 adapter」的硬约束。
        """
        entry = _real_d4_9_entry(gen, discovery, real_overlay)
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=_manifest_of(entry))
        registry.register(_registration(real_contract))
        # 第二个 adapter（不同 adapter_id，但同 entry_id）—— RG-4 拒。
        second = RG.AdapterRegistration(
            adapter=_StubAdapter("d4.customer_structure_dup"),
            entry_id=_CURATED_ID,
            matcher=RG.EntryMatcher(
                document_type="xlsx",
                wp_codes=frozenset({"D4O"}),
                sheet_keys=frozenset({"d49-other"}),
            ),
            bundle=_bundle_for(real_contract),
            descriptor=_D4_9_DESCRIPTOR,
            room=_D4_9_ROOM,
            declared_capability=EP.Capability.bidirectional,
            contract=None,  # 触发 RG-4（entry_id 已注册）先于 contract 校验
        )
        with pytest.raises(RG.RegistrationError, match="一个独立 entry 只能"):
            registry.register(second)

    def test_curated_id_disjoint_from_discovery_ids(
        self, gen: ModuleType, discovery: dict[str, Any], real_overlay: dict[str, Any]
    ) -> None:
        """RG-4 保留的前提：curated id 与全部 discovery id 天然不相交（generator 已 gate）。"""
        built = gen.build_manifest(discovery, real_overlay)
        curated_ids = {
            e["entry_id"] for e in built["entries"] if not e["mounts"]
        }
        discovery_ids = {e["entry_id"] for e in built["entries"] if e["mounts"]}
        assert _CURATED_ID in curated_ids
        assert not (curated_ids & discovery_ids), "curated id 与 discovery id 相交 ⇒ RG-4 前提破"


class TestReq43NonBidirectionalCuratedFailsAttachClosed:
    """Req 4.3：非 bidirectional 的 curated entry attach 关闭失败。"""

    def test_non_bidirectional_entry_fails_bidirectional_ready(
        self, gen: ModuleType, discovery: dict[str, Any], real_overlay: dict[str, Any]
    ) -> None:
        """把 curated entry 的 capability 降级为 single_onlyoffice ⇒ assert_bidirectional_ready 抛。"""
        entry = _real_d4_9_entry(gen, discovery, real_overlay)
        downgraded = copy.deepcopy(entry)
        downgraded["capability"] = "single_onlyoffice"
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=_manifest_of(downgraded))
        with pytest.raises(RG.FakeBidirectionalError):
            registry.assert_bidirectional_ready(_CURATED_ID)

    def test_rg18_declared_bidirectional_on_non_bidirectional_entry_fails(
        self,
        gen: ModuleType,
        discovery: dict[str, Any],
        real_overlay: dict[str, Any],
        real_contract: C.SyncContract,
    ) -> None:
        """RG-18：非 bidirectional entry 上注册 declared=bidirectional adapter ⇒ FakeBidirectionalError。

        这正是 Req 4.3「非双向 curated entry attach 关闭失败」的注册链路形态：
        「仅能打开 OO」不得伪装成双向同步。descriptor mode 与 manifest capability 一致
        （都 single_onlyoffice，故 RG-16 profile/descriptor 门先过），仅 adapter 的
        `declared_capability=bidirectional` 与 manifest 的 single_onlyoffice 冲突 ⇒ 最终由
        RG-18 伪双向门拒 —— 证明拦截来自伪双向门而非 descriptor 门。single_onlyoffice 允许
        editable/shared，故 profile/room 门也都过。
        """
        entry = _real_d4_9_entry(gen, discovery, real_overlay)
        downgraded = copy.deepcopy(entry)
        downgraded["capability"] = "single_onlyoffice"
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=_manifest_of(downgraded))
        # descriptor 与 manifest capability 一致（single_onlyoffice，不暴露模式切换），
        # 让 RG-16 先过，从而把拦截点精确落在 RG-18 伪双向门。
        so_descriptor = EP.DescriptorFacts(
            mode=EP.DescriptorMode.single_onlyoffice, exposes_mode_switch=False
        )
        registration = RG.AdapterRegistration(
            adapter=_StubAdapter(_ADAPTER_ID),
            entry_id=_CURATED_ID,
            matcher=RG.EntryMatcher(
                document_type="xlsx",
                wp_codes=frozenset({"D4O"}),
                sheet_keys=frozenset({"d49-managed"}),
            ),
            bundle=_bundle_for(real_contract),
            descriptor=so_descriptor,
            room=_D4_9_ROOM,
            declared_capability=EP.Capability.bidirectional,
            contract=real_contract,
        )
        with pytest.raises(RG.FakeBidirectionalError):
            registry.register(registration)
