# -*- coding: utf-8 -*-
"""守卫：每个已交付 xlsx provider **真实发布链**冻结的 instrumentation 必须覆盖契约声明的全部 sheet。

spec: d2-online-edit-platform-closure · R2.3

═══ 为什么需要它 ═══

D2 契约声明了 `d22-managed` / `d23-managed` / `d21-managed` 三张受管 sheet，而发布链走编排工厂
内部的**单数** `instrumentation_spec()`，库里每一个 D2 bundle 冻结的 instrumentation 都只认识
`d22-managed`。注册期观测器按冻结 instrumentation 找 sheet ⇒ d23/d21 找不到 ⇒
`ContractDriftError` ⇒ D2 永远注册不上 ⇒ 用户点「在线编辑」毫无反应。模块自带的复数 payload
**从未进过发布链**，而所有离线判据都在测模块函数本身，没人看「发布链实际发布了什么」。

═══ 判据 ═══

用**记录型 publisher**（只记录、不入库）跑每个 provider 的 `publish_pilot_definitions`，取它
**实际**发布的 contract 与 instrumentation payload，按观测器同一口径（
`published_identity_observer._frozen_sheet_anchors`）算覆盖集：

    契约声明的 sheet_key − 冻结 instrumentation 覆盖的 sheet_key = 覆盖缺口

现算全域 88 个 xlsx provider 中有 **17 个**存在缺口（D3/D5/D6/D7/E1/G1~G3/G6/G8~G14/C 控制测试）。
其中 G6 已在注册日志里实报失败，其余是潜伏缺陷（manifest capability 未开到 bidirectional，
注册路径还没走到观测那一步）。它们不在本 spec 修复范围 ⇒ 冻结为**双向锁死的基线**：

* 出现基线外的缺口（或某条缺口变大）⇒ 打红；
* 基线里某条已修好（缺口变小或消失）⇒ 也打红，要求同步缩小基线 —— 基线不得退化成豁免名单。
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

#: 覆盖缺口基线（entry_id → 契约声明却未被冻结 instrumentation 覆盖的 sheet_key）。
#: 2026-10-10 现算；**只许变短**。修好一条就从这里删掉（或缩小它的集合）。
KNOWN_UNCOVERED: Mapping[str, frozenset[str]] = {
    "xlsx/gt-c-control-test": frozenset({"c2-summary-managed"}),
    "xlsx/gt-d3-prepaid-accounts": frozenset(
        {"d34-managed", "d35-managed", "d36-managed", "d37-managed"}
    ),
    "xlsx/gt-d5-receivables-financing": frozenset({"d51-managed", "d54-managed"}),
    "xlsx/gt-d6-contract-assets": frozenset(
        {"d61-managed", "d63-managed", "d65-managed", "d66-managed", "d68-managed", "d69-managed"}
    ),
    "xlsx/gt-d7-contract-liabilities": frozenset(
        {"d71-managed", "d74-managed", "d75-managed", "d76-managed", "d77-managed"}
    ),
    "xlsx/gt-e1-monetary-fund": frozenset({"e14-managed"}),
    "xlsx/gt-g1-trading-financial-assets": frozenset({"g11-managed"}),
    "xlsx/gt-g2-interest-receivable": frozenset({"g21-managed"}),
    "xlsx/gt-g3-dividend-receivable": frozenset({"g31-managed"}),
    "xlsx/gt-g6-other-bond-main": frozenset({"g61-managed"}),
    "xlsx/gt-g8-other-equity-instruments": frozenset({"g81-managed"}),
    "xlsx/gt-g9-other-noncurrent-financial": frozenset({"g91-managed"}),
    "xlsx/gt-g10-trading-financial-liabilities": frozenset({"g101-managed"}),
    "xlsx/gt-g11-investment-income": frozenset({"g111-managed"}),
    "xlsx/gt-g12-net-hedge-gains": frozenset({"g121-managed"}),
    "xlsx/gt-g13-fair-value-changes": frozenset({"g131-managed"}),
    "xlsx/gt-g14-credit-impairment-loss": frozenset({"g141-managed"}),
}

D2_ENTRY = "xlsx/gt-d2-accounts-receivable"


class _RecordingPublisher:
    """只记录、不入库的 publisher（`publish_definition` / `publish_bundle` 两个面）。"""

    def __init__(self) -> None:
        self.definitions: list[tuple[Any, dict[str, Any]]] = []

    async def publish_definition(self, *, kind: Any, payload: dict[str, Any], **_kw: Any) -> Any:
        from app.services.workpaper_sync.definitions import canonical_digest

        self.definitions.append((kind, payload))
        return SimpleNamespace(definition_id=uuid.uuid4(), sha256=canonical_digest(payload))

    async def publish_bundle(self, **_kw: Any) -> Any:
        return SimpleNamespace(bundle_id=uuid.uuid4(), canonical_sha256="0" * 64)


def uncovered_sheets(contract: Mapping[str, Any], instrumentation: Mapping[str, Any]) -> frozenset[str]:
    """契约声明 − 冻结 instrumentation 覆盖（观测器同口径）。"""
    from app.services.workpaper_sync.published_identity_observer import _frozen_sheet_anchors

    declared = {str(sheet["sheet_key"]) for sheet in contract.get("sheets") or ()}
    covered = {str(anchor["sheet_key"]) for anchor in _frozen_sheet_anchors(instrumentation)}
    return frozenset(declared - covered)


async def _observe_all() -> dict[str, Any]:
    from app.services.workpaper_sync.adapters.registry import DELIVERED_PER_ENTRY_CONTRACTS
    from app.services.workpaper_sync.models import DefinitionKind

    gaps: dict[str, frozenset[str]] = {}
    unobservable: dict[str, str] = {}
    observed = 0
    d2: dict[str, Any] = {}
    for row in DELIVERED_PER_ENTRY_CONTRACTS:
        if str(row.get("document_type")) != "xlsx":
            continue
        entry_id = str(row["entry_id"])
        module = importlib.import_module(str(row["provider_module"]))
        publish = getattr(module, "publish_pilot_definitions", None) or getattr(
            module, "publish_definitions", None
        )
        if publish is None:
            unobservable[entry_id] = "provider 没有发布函数"
            continue
        publisher = _RecordingPublisher()
        try:
            await publish(publisher)
        except Exception as exc:  # noqa: BLE001 - 记录不穿透，由判据断言为空
            unobservable[entry_id] = f"{type(exc).__name__}: {str(exc)[:200]}"
            continue
        instr = [p for k, p in publisher.definitions if k == DefinitionKind.instrumentation]
        contract = [p for k, p in publisher.definitions if k == DefinitionKind.contract]
        if not instr or not contract:
            unobservable[entry_id] = f"instrumentation={len(instr)} contract={len(contract)}"
            continue
        observed += 1
        missing = uncovered_sheets(contract[-1], instr[-1])
        if missing:
            gaps[entry_id] = missing
        if entry_id == D2_ENTRY:
            d2 = {"contract": contract[-1], "instrumentation": instr[-1]}
    return {"gaps": gaps, "unobservable": unobservable, "observed": observed, "d2": d2}


@pytest.fixture(scope="module")
def observed() -> dict[str, Any]:
    return asyncio.run(_observe_all())


def test_every_delivered_xlsx_provider_was_observed(observed: dict[str, Any]) -> None:
    """扫描面自检：每个 provider 的发布链都真跑通了（跑不通 = 判据对它失明）。"""
    assert observed["unobservable"] == {}, observed["unobservable"]
    assert observed["observed"] >= 80, f"只观测到 {observed['observed']} 个 provider —— 扫描面被掏空"


def test_no_new_coverage_gap(observed: dict[str, Any]) -> None:
    grown = {
        entry: sorted(missing - KNOWN_UNCOVERED.get(entry, frozenset()))
        for entry, missing in observed["gaps"].items()
        if missing - KNOWN_UNCOVERED.get(entry, frozenset())
    }
    assert not grown, (
        "以下 entry 的契约声明了受管 sheet，而发布链冻结的 instrumentation 不认识它 —— "
        "注册期必报 ContractDriftError（D2 事故同形）：\n  "
        + "\n  ".join(f"{e}: {s}" for e, s in sorted(grown.items()))
    )


def test_fixed_gaps_are_removed_from_the_baseline(observed: dict[str, Any]) -> None:
    """基线双向锁死：缺口变小或消失必须同步缩小基线（不得退化成豁免名单）。"""
    shrunk = {
        entry: sorted(baseline - observed["gaps"].get(entry, frozenset()))
        for entry, baseline in KNOWN_UNCOVERED.items()
        if baseline - observed["gaps"].get(entry, frozenset())
    }
    assert not shrunk, (
        "以下基线缺口已修复，请从 KNOWN_UNCOVERED 删掉对应 sheet：\n  "
        + "\n  ".join(f"{e}: {s}" for e, s in sorted(shrunk.items()))
    )


def test_d2_publishes_all_three_managed_sheets(observed: dict[str, Any]) -> None:
    """D2 正面判据：发布链冻结的 instrumentation 覆盖 d22 / d23 / d21 三张受管 sheet。"""
    from app.services.workpaper_sync.published_identity_observer import _frozen_sheet_anchors

    assert observed["d2"], (
        f"D2 发布链没跑通：{observed['unobservable'].get(D2_ENTRY)}"
    )
    assert D2_ENTRY not in observed["gaps"], observed["gaps"].get(D2_ENTRY)
    covered = {str(a["sheet_key"]) for a in _frozen_sheet_anchors(observed["d2"]["instrumentation"])}
    assert {"d22-managed", "d23-managed", "d21-managed"} <= covered, covered


def test_mutation_singular_instrumentation_is_caught(observed: dict[str, Any]) -> None:
    """变异：D2 退回编排工厂的**单数** instrumentation（事故形态）⇒ 判据必报 d23/d21 缺口。"""
    from app.services.workpaper_sync import pilot_d2_large_json as D2
    from app.services.workpaper_sync.definitions import canonical_digest
    from app.services.workpaper_sync.excel_instrumentation import build_instrumentation_payload

    assert observed["d2"], f"D2 发布链没跑通：{observed['unobservable'].get(D2_ENTRY)}"
    # 与编排工厂未注入钩子时的单数分支逐参数相同（`phase5_entry_orchestration`）。
    # 真实发布链上做同一变异（删掉 D2 的 `instrumentation_definition_payload_fn` 注入）时，
    # 链内「单向引用」校验先拦下（`46f3c617…` 与契约声明不一致）⇒ 由上面的「每个 provider
    # 都被观测到」判据打红 —— 2026-10-10 实测，两条路径各自可证伪。
    singular = build_instrumentation_payload(
        spec=D2.instrumentation_spec(),
        template_definition_sha256=canonical_digest(D2.template_definition_payload()),
        template_sha256=D2.TEMPLATE_SHA256,
        gate=D2.excel_carrier_gate(),
    )
    missing = uncovered_sheets(observed["d2"]["contract"], singular)
    assert missing == {"d23-managed", "d21-managed"}, missing
