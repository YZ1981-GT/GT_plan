# -*- coding: utf-8 -*-
"""Task 6 守卫：D4-9 manifest entry + reviewed overlay 裁决 capability + attach fail-closed。

spec: d4-9-customer-structure-bidirectional-writeback / Task 6
Requirements 1.1, 1.2, 4.6

## 这个文件证明什么（全部行为级判据，非「符号/字符串存在」）

Task 6 的三条可交付：

(a) **manifest 增 `xlsx/gt-d4-customer-structure` entry**
    真实 `build_manifest`（真实 reviewed overlay + pinned discovery fixture）产出的 entry
    携带 `document_type=xlsx` / `independent_entry=True` / `adapter_id=d4.customer_structure`
    / `capability=bidirectional` / wp_match sheet_literals。

(b) **reviewed overlay 裁决 capability=bidirectional**
    真实 overlay 的 curated 声明 capability==bidirectional；本 entry 经 build_manifest 后
    capability 仍为 bidirectional（裁决落到 manifest）。

(c) **capability 未裁决时 attach fail-closed（守卫断言，行为级）**
    驱动 **D4-9 bridge 的真实** `assert_manifest_capability_enabled` /
    `manifest_capability_enabled` / `attach_adapters`：
    - manifest 里 D4-9 capability=bidirectional + adapter_id 匹配 ⇒ 门**通过**、
      `manifest_capability_enabled()` True；
    - 把 capability 变异为 single_onlyoffice / 改错 adapter_id / 抽掉 entry ⇒ 门**抛
      `EntrySelectionError`**、`manifest_capability_enabled()` False、`attach_adapters`
      **不注册**（返回空 tuple 且 registry 无该 adapter）。

## 为什么用 pinned discovery fixture 而非磁盘 manifest（实测阻塞，非假设）

`python backend/scripts/gen/generate_workpaper_sync_manifest.py --apply` 在本分支被
**既有 `approved_source_digest` 漂移**堵死（reviewed=`d9fddb64…` vs 活源=`a18a531d…`，
276→274 mounts，因并发会话正在编辑 D4/D1-D7 宿主 `.vue` 使挂载 id churn）。该漂移与
D4-9 curated 声明正交（Req 3.4：物理挂载清单是独立复核面），故本文件用 sourceDigest 恰等
reviewed 的 pinned discovery fixture 喂真实 `build_manifest` 复现结构，不 bump digest 强推
写盘。磁盘写盘记 UNVERIFIABLE（见 spec Task 6 报告）。
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
from app.services.workpaper_sync.adapters.registry import (  # noqa: E402
    WorkpaperSyncAdapterRegistry,
)

_GENERATOR_PATH = _BACKEND / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"
_OVERLAY_PATH = _BACKEND / "data" / "workpaper_sync_entry_overlay.json"
_DISCOVERY_FIXTURE = (
    Path(__file__).resolve().parent / "data" / "curated_baseline_discovery.json"
)

_CURATED_ID = "xlsx/gt-d4-customer-structure"
_ADAPTER_ID = "d4.customer_structure"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("d4_9_task6_generator", _GENERATOR_PATH)
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
    assert isinstance(curated, list) and curated, "真实 overlay 未带 curated_entries"
    return value


@pytest.fixture(scope="module")
def manifest(gen: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """真实 build_manifest（真实 overlay + pinned discovery）的完整 manifest。"""
    return gen.build_manifest(discovery, overlay)


@pytest.fixture()
def d4_9_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    hits = [e for e in manifest["entries"] if e["entry_id"] == _CURATED_ID]
    assert len(hits) == 1, f"manifest 未产出唯一 D4-9 entry {_CURATED_ID}"
    return hits[0]


def _manifest_with(entry: dict[str, Any]) -> dict[str, Any]:
    """构造只含一条 entry 的 in-memory manifest（喂 bridge 的 manifest= seam）。"""
    return {"schema_version": 1, "manifest_digest": "0" * 64, "entries": [entry]}


# ═══════════════════════════════════════════════════════════════════════════
# (a) manifest 增 xlsx/gt-d4-customer-structure entry
# ═══════════════════════════════════════════════════════════════════════════


class TestManifestEntryEmitted:
    def test_overlay_curated_declaration_is_bidirectional(self, overlay: dict[str, Any]) -> None:
        """(b) reviewed overlay 已把 D4-9 裁决为 capability=bidirectional。"""
        curated = [e for e in overlay["curated_entries"] if e["entry_id"] == _CURATED_ID]
        assert len(curated) == 1
        decl = curated[0]
        assert decl["capability"] == "bidirectional"
        assert decl["adapter_id"] == _ADAPTER_ID
        assert decl["document_type"] == "xlsx"
        assert decl["evidence"]["review_status"], "curated 声明必须已复核"

    def test_manifest_emits_d4_9_entry_with_adapter_and_capability(
        self, d4_9_entry: dict[str, Any]
    ) -> None:
        """(a)+(b) build_manifest 产出的 entry 落 adapter_id + bidirectional + independent。"""
        assert d4_9_entry["document_type"] == "xlsx"
        assert d4_9_entry["adapter_id"] == _ADAPTER_ID
        assert d4_9_entry["capability"] == "bidirectional"
        assert d4_9_entry["independent_entry"] is True
        assert d4_9_entry["mounts"] == []  # curated 无 template_ast mount
        assert "重要客户结构分析D4-9" in d4_9_entry["wp_match"]["sheet_literals"]

    def test_manifest_entry_matches_bridge_frozen_identity(
        self, d4_9_entry: dict[str, Any]
    ) -> None:
        """entry_id / adapter_id 与 bridge 模块冻结常量一致（防两处漂移）。"""
        assert d4_9_entry["entry_id"] == bridge.ENTRY_ID
        assert d4_9_entry["adapter_id"] == bridge.ADAPTER_ID


# ═══════════════════════════════════════════════════════════════════════════
# (c) capability 门通过 / fail-closed —— 驱动 bridge 真实函数
# ═══════════════════════════════════════════════════════════════════════════


class TestCapabilityGatePasses:
    def test_assert_passes_when_bidirectional(self, d4_9_entry: dict[str, Any]) -> None:
        """capability=bidirectional + adapter_id 匹配 ⇒ 门不抛。"""
        m = _manifest_with(d4_9_entry)
        bridge.assert_manifest_capability_enabled(manifest=m)  # 不抛即通过
        assert bridge.manifest_capability_enabled(manifest=m) is True


class TestCapabilityGateFailsClosed:
    """Req 1.2 / 4.6：capability 未裁决 bidirectional 时 attach fail-closed。"""

    def test_downgraded_capability_fails_closed(self, d4_9_entry: dict[str, Any]) -> None:
        """capability 变异 single_onlyoffice ⇒ 门抛 + 布尔封装 False。"""
        downgraded = copy.deepcopy(d4_9_entry)
        downgraded["capability"] = "single_onlyoffice"
        m = _manifest_with(downgraded)
        with pytest.raises(bridge.EntrySelectionError):
            bridge.assert_manifest_capability_enabled(manifest=m)
        assert bridge.manifest_capability_enabled(manifest=m) is False

    def test_single_html_capability_fails_closed(self, d4_9_entry: dict[str, Any]) -> None:
        downgraded = copy.deepcopy(d4_9_entry)
        downgraded["capability"] = "single_html"
        m = _manifest_with(downgraded)
        with pytest.raises(bridge.EntrySelectionError):
            bridge.assert_manifest_capability_enabled(manifest=m)
        assert bridge.manifest_capability_enabled(manifest=m) is False

    def test_wrong_adapter_id_fails_closed(self, d4_9_entry: dict[str, Any]) -> None:
        """capability 对但 adapter_id 不符 ⇒ 门抛（防挂错 adapter）。"""
        wrong = copy.deepcopy(d4_9_entry)
        wrong["adapter_id"] = "d4.revenue_detail"
        m = _manifest_with(wrong)
        with pytest.raises(bridge.EntrySelectionError):
            bridge.assert_manifest_capability_enabled(manifest=m)
        assert bridge.manifest_capability_enabled(manifest=m) is False

    def test_missing_entry_fails_closed(self) -> None:
        """manifest 里根本没有 D4-9 entry（未重生成）⇒ 门抛。"""
        other = {
            "entry_id": "xlsx/gt-some-other",
            "capability": "bidirectional",
            "adapter_id": "x.y",
        }
        m = _manifest_with(other)
        with pytest.raises(bridge.EntrySelectionError):
            bridge.assert_manifest_capability_enabled(manifest=m)
        assert bridge.manifest_capability_enabled(manifest=m) is False


class TestAttachFailsClosedBehaviorally:
    """attach_adapters 在 capability 未裁决 bidirectional 时**不注册**（行为级，非 stub）。

    attach_adapters 的 DB-runtime 尾部（representation/bundle/observation）无法在无
    DB/OO 的单测环境驱动；但 **fail-closed 前置门**（capability 未 bidirectional 即
    return () 不注册）是纯 in-process 判据，可完全真跑：把 bridge 的 manifest 读取指向
    一个非 bidirectional 的 in-memory manifest（monkeypatch `load_entry_manifest`），
    断言 attach_adapters 返回空且 registry 无 d4.customer_structure。
    """

    @pytest.mark.asyncio
    async def test_attach_returns_empty_when_not_bidirectional(
        self, monkeypatch: pytest.MonkeyPatch, d4_9_entry: dict[str, Any]
    ) -> None:
        downgraded = copy.deepcopy(d4_9_entry)
        downgraded["capability"] = "single_onlyoffice"
        m = _manifest_with(downgraded)
        # bridge.manifest_capability_enabled() 无参走磁盘 load_entry_manifest；重定向到降级 manifest。
        monkeypatch.setattr(bridge, "load_entry_manifest", lambda: m)
        registry = WorkpaperSyncAdapterRegistry(manifest=m)

        attached = await bridge.attach_adapters(registry, session=object())

        assert attached == (), "capability 未裁决 bidirectional 时 attach 必须不注册"
        assert _ADAPTER_ID not in {r.adapter_id for r in registry.registrations()}

    @pytest.mark.asyncio
    async def test_attach_returns_empty_when_entry_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        m = _manifest_with(
            {"entry_id": "xlsx/gt-some-other", "capability": "bidirectional", "adapter_id": "x.y"}
        )
        monkeypatch.setattr(bridge, "load_entry_manifest", lambda: m)
        registry = WorkpaperSyncAdapterRegistry(manifest=m)

        attached = await bridge.attach_adapters(registry, session=object())

        assert attached == ()
        assert _ADAPTER_ID not in {r.adapter_id for r in registry.registrations()}
