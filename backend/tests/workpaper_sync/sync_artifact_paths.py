# -*- coding: utf-8 -*-
"""workpaper_sync 守卫共用的产物定位（spec 目录 / 契约归属）—— 不含任何循环特有事实。

放在这里而不是某条循环的事实层：两件事都是**平台级**的，各循环守卫都会用到，各写一份就是 N 个
漂移面（本仓方法论铁律：同一判据写两份，变异只改一份、守卫照绿）。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPECS = ROOT / ".kiro" / "specs"


def spec_dir(name: str) -> pathlib.Path:
    """spec 目录：活跃目录优先，归档后到 `_archive/*/<name>` 找。

    🔴 2026-11-05：K 的三份 spec 已归档到 `_archive/26-workpaper-sync-cycle-lanes-kln/`，而 6 个
    守卫把活跃路径写死 ⇒ `evidence/superseded-candidate-contracts/` 整目录「不存在」，102 个用例在
    setup 阶段就 ERROR，报的是「草案阶段交付证据丢了」这个**错结论**（证据一直在，只是随 spec 归档
    换了位置）。归档不改变证据存在性 ⇒ 路径解析必须两处都看。
    返回值即使不存在也给活跃路径，让调用方自己的「不存在」断言照旧报它自己的话。
    """
    active = SPECS / name
    if active.is_dir():
        return active
    hits = sorted(p for p in SPECS.glob(f"_archive/*/{name}") if p.is_dir())
    assert len(hits) <= 1, f"{name} 在 _archive 下有多份：{[str(p) for p in hits]}"
    return hits[0] if hits else active


#: reviewed 契约里**没写** `review` 元数据块的 contract_id（归属只能按 contract_id 查交付台账）。
#: 🔴 只许变短，且不许在守卫里顺手补 `review` 块：它在 canonical payload 里，补上就改了契约的
#:    definition_sha256 ⇒ 已发布底稿的冻结身份与生产契约脱钩、必须重发布（归该循环的 lane）。
CONTRACTS_WITHOUT_REVIEW_BLOCK = frozenset({"a51.cashflow_audit"})


def contract_owner(name: str, doc: dict) -> str | None:
    """契约的归属 entry_id：优先读 `review.entry_id`；登记的例外按 `contract_id` 查交付台账。"""
    declared = (doc.get("review") or {}).get("entry_id")
    if declared:
        return str(declared)
    contract_id = str(doc.get("contract_id") or "")
    if doc.get("review_status") != "reviewed" or contract_id not in CONTRACTS_WITHOUT_REVIEW_BLOCK:
        return None
    from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )

    ledger = {str(row["contract_id"]): str(row["entry_id"]) for row in DELIVERED_PER_ENTRY_CONTRACTS}
    assert contract_id in ledger, f"{name}: 既没写 review 块、交付台账里也没有 {contract_id}"
    return ledger[contract_id]
