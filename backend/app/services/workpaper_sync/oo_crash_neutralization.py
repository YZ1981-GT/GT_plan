# -*- coding: utf-8 -*-
"""OO 加载期崩溃中性化函数的**解析层** —— 注册表声明 → 可调用对象。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 13（原实现）
      `h2-h6-h10-pilot-cross-reference-lanes`（本模块：根因修复 + 从 adapters/excel 抽出）

═══ 🔴 原实现是「声明绿、运行时死」════════════════════════════════════════════════

原实现在 `adapters/excel.py` 里只查 provider 模块并 `getattr(..., None)` **软跳过**：

    return getattr(module, plan.oo_crash_neutralization_fn, None)

而 `neutralize_oo_crash_if_formulas` 只定义在 `g7_oo_crash_if_neutralize`，
只有 `pilot_g7_two_level_dynamic` re-export 了它。逐 adapter 实测：注册表里
**21 条声明中 20 条解析结果是 `None`**（G 循环 11 条 + H 循环 9 条），只有 G7 自己能
解析到 ⇒ **中性化对那 20 册从未执行过**，而注册表、契约、判据全绿。

后果不是性能问题：带裸 `IF(` 的册子在 OnlyOffice 9.4 加载期崩（`editor_error_-82`），
用户看到的是「打开就白屏」。最重的一册 `H1 固定资产.xlsx` 有 **496 个**含 IF 公式格。

═══ 修法：两段解析 + fail-closed ═════════════════════════════════════════════════

* **没声明** ⇒ 返回 `None`（语义是「这家不需要中性化」）；
* **声明了** ⇒ 先查 provider 模块（保住 G7 的既有形态），取不到则回落到**唯一定义模块**；
* 两处都取不到 ⇒ **抛** `OoCrashNeutralizationFnUnresolvedError`。

🔴 为什么回落而不是要求 20 个 provider 各写一行 re-export：那是 20 个漂移面，且漏一个
   又会静默退化成 `None`（正是本缺陷的复发路径）。回落让「声明即生效」。
🔴 为什么仍要 fail-closed：回落之后唯一取不到的情形就是**函数名写错**（或定义模块改名）。
   软跳过会把它继续变成静默无中性化；抛错让它在第一次 materialize 就暴露。

守护：`backend/tests/workpaper_sync/test_oo_crash_neutralization_resolves.py`
逐 adapter 断言「声明 ⇔ 解析得到」，并含「去掉回落分支即打红」的变异判据。
"""
from __future__ import annotations

import importlib
from typing import Any, Callable, Final

from app.services.workpaper_sync.adapters.base import AdapterProtocolError

__all__ = [
    "OO_CRASH_FN_DEFINING_MODULE",
    "OoCrashNeutralizationFnUnresolvedError",
    "resolve_oo_crash_neutralization_fn",
]


class OoCrashNeutralizationFnUnresolvedError(AdapterProtocolError):
    """注册表声明了 OO 崩溃中性化函数，但两条解析路径都取不到它。

    基类取 `AdapterProtocolError`（与 `adapters/excel.ExcelAdapterIdentityError` 一致）——
    这是**声明与实现不一致**的部署期缺陷，不是用户输入问题。
    """

    error_code = "excel_oo_crash_neutralization_fn_unresolved"


#: 中性化函数的**唯一定义模块**（`pilot_g7_two_level_dynamic` 只是从它 re-export）。
OO_CRASH_FN_DEFINING_MODULE: Final[str] = (
    "app.services.workpaper_sync.g7_oo_crash_if_neutralize"
)


def resolve_oo_crash_neutralization_fn(adapter_id: str) -> Callable[..., Any] | None:
    """按注册表声明取该 adapter 的 OO 崩溃中性化函数。

    :raises OoCrashNeutralizationFnUnresolvedError: 声明了却两条路径都取不到。
    """
    from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

    plan = STORE_MERGE_REGISTRY.get(adapter_id)
    if plan is None or not plan.oo_crash_neutralization_fn:
        return None

    fn_name = plan.oo_crash_neutralization_fn
    provider_path = f"app.services.workpaper_sync.{plan.provider_module}"
    for module_path in (provider_path, OO_CRASH_FN_DEFINING_MODULE):
        try:
            module = importlib.import_module(module_path)
        except ImportError:  # provider 模块名写错也要可归因，不静默
            continue
        fn = getattr(module, fn_name, None)
        if fn is not None:
            return fn

    raise OoCrashNeutralizationFnUnresolvedError(
        f"adapter {adapter_id!r} 声明了 oo_crash_neutralization_fn={fn_name!r}，"
        f"但 provider 模块 {plan.provider_module!r} 与唯一定义模块 "
        f"{OO_CRASH_FN_DEFINING_MODULE.rsplit('.', 1)[-1]!r} 都没有导出这个名字 —— "
        "带裸 IF( 的册子会在 OnlyOffice 9.4 加载期崩（editor_error_-82）。"
        "要么修正函数名，要么把该声明从注册表里去掉（若这家确实不需要中性化）。"
    )
