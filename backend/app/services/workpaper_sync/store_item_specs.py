# -*- coding: utf-8 -*-
"""store item 的**声明类**（形态 + 缺省载荷 + 合并计划）—— 注册表本体的伴生模块。

spec: d1-sync-row-table-engine-and-d1-coverage（原属 `store_item_registry`）

═══ 为什么从 `store_item_registry.py` 抽出来 ═══════════════════════════════════

那个文件是**全平台**的 store 注册表：每条新 entry 交付都往 `STORE_MERGE_REGISTRY` 里
append 一条（含说明注释）。它在 H10 交付前恰好卡在行数门上限 **800** —— 也就是说
**任何一条**新 entry 都会顶破。拆分是唯一出路（whitelist 只许历史大文件）。

拆分边界取「**声明类** vs **注册表本体**」，而不是按循环切：
  · 声明类（本模块）是稳定面，改动频率极低；
  · 注册表 dict 是**多个并发会话同时 append** 的那一面，留在原文件不动。
⇒ 这条边界让拆分对在途 lane 零冲突（他们的 diff hunk 全在 dict 里）。

🔴 `store_item_registry` 顶部 re-export 本模块全部公开名，既有
   `from ... store_item_registry import StoreItemSpec` 调用点**一处都不用改**。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping

from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.phase5_row_table_sheet import StoreKind

__all__ = [
    "StoreKind",
    "StoreItemSpec",
    "DedicatedStoreItem",
    "StoreMergePlan",
    "StoreMergePlanNotRegisteredError",
    "default_payload_for",
]


class StoreMergePlanNotRegisteredError(SyncDomainError):
    """adapter 未注册 store merge plan —— 显式失败，**不静默跳过**（需求 3.4）。

    静默跳过正是 D4-35 恒空 / D4-13 正文写不进 OO 两个已修 bug 的根因形态。
    """

    error_code = "sync_store_merge_plan_not_registered"


#: per-kind 缺省载荷（**不是** blanket：由 kind 决定，见模块 docstring 的事故背书）。
_DEFAULT_BY_KIND: Final[Mapping[StoreKind, str]] = {
    StoreKind.rows: "[]",
    StoreKind.dict: "{}",
    StoreKind.fixed_text: "",
    StoreKind.dedicated: "[]",   # dedicated 由 provider 门面自定，注册时须显式给 default
}


def default_payload_for(kind: StoreKind) -> str:
    """按 store 形态取缺省载荷。调用方若有 per-item 覆盖，以 `StoreItemSpec.default` 优先。"""
    return _DEFAULT_BY_KIND[kind]


@dataclass(frozen=True)
class StoreItemSpec:
    """一条 store item 的形态声明（四形态 + per-item 缺省值）。

    :param item_id: `checklist_responses.item_id`（如 `D1-cust-rows`）。
    :param kind: store 载荷形状。与 `BindingKind`（Excel 侧几何）**正交**。
    :param default: per-item 缺省值。留空则按 kind 取 `default_payload_for`。
    :param merge_fn: `dedicated` 才有 —— provider 侧专用 merge 门面的函数名（框架按名取）。
    """

    item_id: str
    kind: StoreKind
    default: str | None = None
    merge_fn: str | None = None

    @property
    def effective_default(self) -> str:
        """per-item default 优先；未给则按 kind 取（**绝不** blanket `"[]"`）。"""
        return self.default if self.default is not None else default_payload_for(self.kind)

    def __post_init__(self) -> None:
        if self.kind is StoreKind.dedicated and not self.merge_fn:
            raise ValueError(
                f"store item {self.item_id!r} 声明为 dedicated 但未给 merge_fn —— "
                "dedicated 形态必须指名 provider 侧的专用 merge 门面"
            )


@dataclass(frozen=True)
class DedicatedStoreItem:
    """一个 `dedicated` 形态 store item 的分派声明（Task 13 收敛，取代 `hasattr` 试探）。

    原 `oo_to_html._mirror_store_backed_if_needed` 对 D4 的 6 个 dict/list store item 各写一段
    `hasattr(bridge, merge_fn) and hasattr(bridge, item_id_const)` 判断，本类把它显式化为声明：
    「该 item 是否存在」由**注册表登记**表达，不再靠运行时 `hasattr` 猜。

    :param item_id_const: provider 模块里该 item 的 `STORE_ITEM_ID_*` 常量名（框架按名取值，
        不硬编码具体 item_id 字符串——item_id 由各家 provider 自己定义）。
    :param merge_fn: provider 模块里的 merge 函数名，签名统一为
        `(*, projection, base_state) -> tuple[merged, applied, visited]`。
    :param base_kind: 该 item 的载荷是 `"dict"` 还是 `"list"`（D4-8 是 list，其余 5 个是 dict）——
        决定读库后 `json.loads` 的形态校验分支，**不得**混用（D4-8 混进 dict 分支会让
        `isinstance(parsed, dict)` 恒假，静默丢弹回退成 `None` 基线）。
    :param provider_module: 该 item 归属的 D4 per-sheet 模块名（6 个 item 分布在 4 个不同模块，
        不是全部都在 `phase5_d4_revenue_detail` 里）。
    """

    item_id_const: str
    merge_fn: str
    base_kind: str  # "dict" | "list"
    provider_module: str

    def __post_init__(self) -> None:
        if self.base_kind not in ("dict", "list"):
            raise ValueError(f"DedicatedStoreItem.base_kind 只能是 dict/list，实得 {self.base_kind!r}")


@dataclass(frozen=True)
class StoreMergePlan:
    """一个 adapter 的 store 合并计划（回方向 `oo_to_html` 按它分派，不再 elif 链）。

    :param adapter_id: 契约/adapter 身份（== contract_id == 契约文件名）。
    :param provider_module: provider 模块名（框架按名 import，不硬编码 import 语句）。
    :param items: 该 adapter 的全部 store item 形态声明。
    :param merge_rows_fn: rows 形态的合并函数名（provider 侧，默认
        `merge_projection_into_store_rows`）。
    :param merge_state_fn: state 形态（G7）的合并函数名；仅 state 形态 adapter 给。
    :param dual_store_fn: 多 store item 的整体镜像函数名（D4 的 `_mirror_d4_dual_stores` 同型）。
    :param dedicated_items: `dedicated` 形态 store item 清单（D4 的 6 个 dict/list block）。
    """

    adapter_id: str
    provider_module: str
    items: tuple[StoreItemSpec, ...] = ()
    merge_rows_fn: str = "merge_projection_into_store_rows"
    merge_state_fn: str | None = None
    dual_store_fn: str | None = None
    #: 多 store item 的**整体行 merge 函数**名（bridge 模块顶层导出）。
    #: `_mirror_d4_dual_stores` 用 `getattr(bridge, merge_all_fn)` 取代硬编码。
    #: D4 填 `merge_projection_into_all_d4_stores`，D2 填 `merge_projection_into_all_d2_stores`。
    merge_all_fn: str = "merge_projection_into_all_d4_stores"
    dedicated_items: tuple[DedicatedStoreItem, ...] = ()
    #: 非空 ⇒ 该 adapter 的 provider **未提供** store 镜像门面（实测缺符号）。
    #: `resolve_store_merge_plan` 会抛可归因的 domain 错误，取代原先运行时 AttributeError。
    mirror_unavailable_reason: str = ""
    #: 非空 ⇒ provider 模块导出的一个函数名，`adapters/excel.py` 在 materialize 前后
    #: 对 substrate 副本调用它做「OO 加载期公式崩溃」中性化（G7 的 IF() tocBool 崩溃 workaround）。
    #: 取代原 `adapters/excel.py` 两处 `if self.adapter_id == "g7.soe_subsidiary_disclosure"`
    #: 字面量分支（Task 13 收敛，需求 3.1 / 7.1；requirements.md 现状红基线「adapters/excel 2 处」）。
    oo_crash_neutralization_fn: str | None = None

    @property
    def item_ids(self) -> tuple[str, ...]:
        return tuple(i.item_id for i in self.items)

    def item(self, item_id: str) -> StoreItemSpec | None:
        for i in self.items:
            if i.item_id == item_id:
                return i
        return None
