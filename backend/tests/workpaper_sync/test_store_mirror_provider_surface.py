# -*- coding: utf-8 -*-
"""镜像路径对 provider **硬取**的属性，注册表里每个 plan 都必须真有 —— spec d2-online-edit-platform-closure · R11。

═══ 锁的是什么缺陷 ═══

2026-10-11 和平药房 D2 在线编辑：OO 保存后 content version 已前进，镜像进 checklist 时抛
``AttributeError: module 'd2_bidirectional_bridge' has no attribute 'STORE_ITEM_IDS'``。
``store_item_registry`` 把 ``d2.receivable_detail`` 的 provider 登记成 bridge 模块（多 store
item 型，``dual_store_fn``），而 ``store_mirror._mirror_dual_stores`` 对 provider 硬取
``all_store_item_ids()``（缺则回退 ``STORE_ITEM_IDS``）—— bridge 两个都没有，只有 pilot 有。
注册表、bridge、镜像三处各自都「看起来对」，只有真跑一次 OO 保存才炸，而且炸在 durable
提交**之后**（OO 侧编辑已落库、HTML 永远看不到）。

既有守卫只验「plan 能 resolve」与少数几家的单个符号，没有逐 plan 验镜像会解引用的**全部**属性。

═══ 判据 ═══

1. 逐 plan：镜像在该 plan 形态下会无保护解引用的属性，provider 全都有（参数化 = 全注册表）。
2. 模型完整性：``store_mirror`` 里对 provider 的无保护解引用点集合与本文件的模型逐项相等 ——
   镜像新增一个硬取点而模型没跟上，这里先红（否则判据 1 会静默变成不完整的检查）。
3. 变异证明：R11 的形态（多 store 型 provider 缺 item 清单 / 缺整体 merge 函数）判据 1 必报。
"""
from __future__ import annotations

import ast
import importlib
import types
from pathlib import Path
from typing import Any

import pytest

from app.services.workpaper_sync import store_item_registry as REG
from app.services.workpaper_sync import store_mirror

_DEFAULT_MERGE_ALL = "merge_projection_into_all_d4_stores"


def _missing_hard_attrs(plan: Any, module: Any) -> list[str]:
    """``store_mirror.mirror_projection_into_store`` 在本 plan 形态下会无保护解引用、而 module 缺的属性。"""
    missing: list[str] = []
    if plan.dual_store_fn:
        # _mirror_dual_stores：item 清单（all_store_item_ids() 优先，缺则 STORE_ITEM_IDS）+ 整体 merge
        if not callable(getattr(module, "all_store_item_ids", None)) and not hasattr(
            module, "STORE_ITEM_IDS"
        ):
            missing.append("all_store_item_ids()|STORE_ITEM_IDS")
        merge_all = getattr(plan, "merge_all_fn", None) or _DEFAULT_MERGE_ALL
        if not callable(getattr(module, merge_all, None)):
            missing.append(merge_all)
        return missing
    if not hasattr(module, "STORE_ITEM_ID"):
        missing.append("STORE_ITEM_ID")
    merge_name = plan.merge_state_fn or plan.merge_rows_fn
    if not merge_name or not callable(getattr(module, merge_name, None)):
        missing.append(f"merge fn {merge_name!r}")
    return missing


def _mirrorable_plans() -> list[str]:
    # mirror_unavailable_reason 非空的 plan 在 store_merge_plan_or_skip 里就被拒，走不到解引用。
    return sorted(
        adapter_id
        for adapter_id, plan in REG.STORE_MERGE_REGISTRY.items()
        if not getattr(plan, "mirror_unavailable_reason", "")
    )


@pytest.mark.parametrize("adapter_id", _mirrorable_plans())
def test_provider_exposes_every_attribute_the_mirror_dereferences(adapter_id: str) -> None:
    plan = REG.STORE_MERGE_REGISTRY[adapter_id]
    module = importlib.import_module(f"app.services.workpaper_sync.{plan.provider_module}")
    assert _missing_hard_attrs(plan, module) == [], (
        f"{adapter_id} 的 provider {plan.provider_module} 缺镜像会硬取的属性 —— "
        "OO 保存会在 durable 提交之后才抛 AttributeError（HTML 永远看不到 OO 侧编辑）"
    )


def test_registry_is_not_vacuous() -> None:
    assert len(_mirrorable_plans()) >= 60, "注册表规模骤降 ⇒ 判据 1 的覆盖面可能被意外收窄"
    assert "d2.receivable_detail" in _mirrorable_plans()


# ═══════════════════════════════════════════════════════════════════════════
# 判据 2：模型完整性（store_mirror 的无保护解引用点 ≡ 本文件模型 + 已知受 hasattr 保护的点）
# ═══════════════════════════════════════════════════════════════════════════

#: 直接 ``bridge.<attr>``：前两项是硬取（判据 1 已建模），其余六项都在 ``if hasattr(bridge, …)`` 分支内。
_BRIDGE_ATTRS = frozenset({
    "STORE_ITEM_ID",
    "STORE_ITEM_IDS",
    "STORE_ITEM_IDS_D45_FIXED", "merge_d45_fixed_from_projection",
    "STORE_ITEM_IDS_D413_FIXED", "merge_d413_fixed_from_projection",
    "STORE_ITEM_IDS_D47_DEDICATED", "merge_d47_from_projection",
})
#: 无默认值的 ``getattr(bridge|module, X)``：前三项判据 1 已建模；dedicated 两项在 hasattr 软跳过之后。
_GETATTR_NO_DEFAULT = frozenset({
    "bridge:plan.merge_state_fn",
    "bridge:plan.merge_rows_fn",
    "bridge:_merge_all_fn_name",
    "module:dedicated.item_id_const",
    "module:dedicated.merge_fn",
})


def _mirror_dereference_surface() -> tuple[frozenset[str], frozenset[str]]:
    tree = ast.parse(Path(store_mirror.__file__).read_bytes().decode("utf-8"))
    attrs: set[str] = set()
    getattrs: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "bridge"
        ):
            attrs.add(node.attr)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) == 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in ("bridge", "module")
        ):
            getattrs.add(f"{node.args[0].id}:{ast.unparse(node.args[1])}")
    return frozenset(attrs), frozenset(getattrs)


def test_mirror_dereference_surface_matches_the_model() -> None:
    attrs, getattrs = _mirror_dereference_surface()
    assert attrs == _BRIDGE_ATTRS, (
        "store_mirror 对 provider 的 `bridge.<attr>` 解引用点变了 —— 先更新本文件的模型"
        f"（新增 {sorted(attrs - _BRIDGE_ATTRS)} / 消失 {sorted(_BRIDGE_ATTRS - attrs)}），"
        "否则判据 1 会静默变成不完整的检查"
    )
    assert getattrs == _GETATTR_NO_DEFAULT, (
        "store_mirror 的无默认值 getattr 点变了 —— 先更新本文件的模型"
        f"（新增 {sorted(getattrs - _GETATTR_NO_DEFAULT)} / 消失 {sorted(_GETATTR_NO_DEFAULT - getattrs)}）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 3：变异证明（R11 的真实形态必须被判据 1 报出来）
# ═══════════════════════════════════════════════════════════════════════════


def _fake_module(**attrs: Any) -> types.ModuleType:
    module = types.ModuleType("fake_provider")
    for name, value in attrs.items():
        setattr(module, name, value)
    return module


def test_r11_shape_dual_provider_without_item_list_is_reported() -> None:
    plan = REG.STORE_MERGE_REGISTRY["d2.receivable_detail"]
    assert plan.dual_store_fn, "前提：D2 是多 store item 型"
    fake = _fake_module(merge_projection_into_all_d2_stores=lambda **_: {})
    assert _missing_hard_attrs(plan, fake) == ["all_store_item_ids()|STORE_ITEM_IDS"]


def test_dual_provider_without_whole_merge_fn_is_reported() -> None:
    plan = REG.STORE_MERGE_REGISTRY["d2.receivable_detail"]
    fake = _fake_module(all_store_item_ids=lambda: ("D2-detail-rows",))
    assert _missing_hard_attrs(plan, fake) == [plan.merge_all_fn]


def test_single_provider_without_store_item_id_is_reported() -> None:
    adapter_id = next(
        a for a in _mirrorable_plans() if not REG.STORE_MERGE_REGISTRY[a].dual_store_fn
    )
    plan = REG.STORE_MERGE_REGISTRY[adapter_id]
    merge_name = plan.merge_state_fn or plan.merge_rows_fn
    fake = _fake_module(**{merge_name: lambda **_: None})
    assert _missing_hard_attrs(plan, fake) == ["STORE_ITEM_ID"]
