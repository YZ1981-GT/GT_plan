# -*- coding: utf-8 -*-
"""pending entry 的生效能力：`effective_capability` / `is_pending_entry`。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · 1.1（pending schema）的消费方
Requirements: 1.3, 12.1

Task 1.1 把「还没裁决」写成 manifest 里的 `capability: null` + pending 标记。`capability_of()`
对它照旧抛（pending 不是第五种能力态），而好几处生产代码问的其实是「现在是不是
bidirectional」：pilot 评估一遇 pending 就整体抛异常，B60 pilot 的启用门把「还没启用」报成
「capability 未登记」。这里守两件事：pending 的判定本身可伪证，以及那几处调用方不再因为
pending 抛。
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import pilot_harness as PH  # noqa: E402
from app.services.workpaper_sync import pilot_simple_checklist as P  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402
from app.services.workpaper_sync.entry_profile import (  # noqa: E402
    Capability,
    EntryProfileError,
    capability_of,
    effective_capability,
    is_pending_entry,
    load_entry_manifest,
    manifest_entries_by_id,
)


def _entry(**fields: Any) -> dict[str, Any]:
    return {"entry_id": "xlsx/demo", **fields}


def test_the_two_pending_shapes_and_nothing_else() -> None:
    independent = _entry(capability=None, adjudication_state="pending")
    inherited = _entry(
        capability=None,
        adjudication_state="inherited",
        capability_verdict_stage="inherited_parent_pending",
    )
    assert is_pending_entry(independent) and effective_capability(independent) is None
    assert is_pending_entry(inherited) and effective_capability(inherited) is None

    # 反例：null 却不带 pending 标记 ⇒ 是清册坏了，不许被当成 pending 吞掉
    broken = _entry(capability=None, adjudication_state="terminal")
    assert not is_pending_entry(broken)
    with pytest.raises(EntryProfileError):
        effective_capability(broken)
    inherited_from_decided = _entry(
        capability=None, adjudication_state="inherited", capability_verdict_stage="inherited"
    )
    assert not is_pending_entry(inherited_from_decided)

    # 已裁决的 entry 与 capability_of 同答案；pending 只影响 effective_capability
    decided = _entry(capability="bidirectional", adjudication_state="terminal")
    assert effective_capability(decided) is Capability.bidirectional is capability_of(decided)
    with pytest.raises(EntryProfileError):
        capability_of(independent)


def test_every_null_capability_in_the_real_manifest_is_a_declared_pending() -> None:
    entries = manifest_entries_by_id(load_entry_manifest())
    nulls = [eid for eid, entry in entries.items() if entry.get("capability") is None]
    assert nulls, "manifest 里一条 pending 都没有 ⇒ 本文件的判据在空集上恒绿"
    for eid in nulls:
        assert effective_capability(entries[eid]) is None, eid


def test_pilot_assessment_no_longer_raises_on_pending_candidates() -> None:
    entries = manifest_entries_by_id(load_entry_manifest())
    assessments = PH.assess_pilot_classes()
    candidates = {eid for item in assessments.values() for eid in item.candidate_entry_ids}
    assert any(effective_capability(entries[eid]) is None for eid in candidates), (
        "候选里没有 pending entry ⇒ 这条回归判据没覆盖到原来抛异常的那条路"
    )
    for item in assessments.values():
        for eid in item.bidirectional_entry_ids:
            assert effective_capability(entries[eid]) is Capability.bidirectional, eid


def test_b60_enable_gate_says_pending_through_the_narrow_error() -> None:
    entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
    assert is_pending_entry(entry), "B60 已不是 pending —— 本判据的前提变了"
    with pytest.raises(P.PilotSelectionError, match="capability=pending"):
        P.assert_manifest_capability_enabled()
    assert P.manifest_capability_enabled() is False


def test_registry_rejects_pending_as_not_bidirectional_and_not_registrable() -> None:
    manifest = load_entry_manifest()
    registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)
    entries = manifest_entries_by_id(manifest)
    pending = next(
        eid for eid, entry in sorted(entries.items())
        if entry.get("independent_entry") and is_pending_entry(entry)
    )
    with pytest.raises(RG.FakeBidirectionalError, match="capability=pending"):
        registry.assert_bidirectional_ready(pending)

    # 对照：把同一条改成已裁决的非双向值，答案仍是 FakeBidirectionalError（判据不是只认 pending）
    decided = copy.deepcopy(dict(manifest))
    for item in decided["entries"]:
        if item["entry_id"] == pending:
            item["capability"] = Capability.single_onlyoffice.value
            item["adjudication_state"] = "terminal"
    with pytest.raises(RG.FakeBidirectionalError, match="capability=single_onlyoffice"):
        RG.WorkpaperSyncAdapterRegistry(manifest=decided).assert_bidirectional_ready(pending)
