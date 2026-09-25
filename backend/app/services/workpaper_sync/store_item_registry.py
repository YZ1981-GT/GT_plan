# -*- coding: utf-8 -*-
"""store item 形态注册表 —— 取代 `oo_to_html` 的 9 分支 elif 链与 9 处 hasattr 试探。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 11/12 · Requirements 3.1~3.5 / 8.2

═══ 这个注册表解决什么 ═══

`oo_to_html._mirror_store_backed_if_needed` 现有一条 9 分支 `elif adapter_id == "…"` 链：接一张
新底稿就得改通用回写层，且「未命中 ⇒ 静默 `return`」正是 D4-35 恒空 / D4-13 正文写不进 OO
两个已修 bug 的**根因形态**。本模块把「adapter → store 合并计划」做成 O(1) dict 查表，未命中
抛显式错误（含已注册清单），**不静默跳过**（需求 3.4）。

🔴 **本模块是需求 7.1 AST 卡点的显式白名单**：注册表的职责就是持有 adapter_id → plan 的映射，
   字面量作 dict key 是合法的，不是「特化分支」。白名单只有两类且须显式登记：注册表模块本身、
   错误消息文案。

🔴 **per-item default 不得 blanket `"[]"`**（需求 3.2，有事故背书）：dict-store（D4-9 `{}`）与
   singleton（D4-31 `{}`）拿到列表默认 `"[]"` 会在 provider 内抛非 domain `ValueError`，一路
   冒泡成 opaque 500 并连累整个 entry 的 store-projection（`store_projection_response.py:207`
   记录了这次修复）。本模块沿用 per-item 单源规则，由 `StoreItemSpec.default` 表达。

🔴 **O(1) 不得退化成线性试探**（需求 3.5）：`for spec in REGISTRY: if spec.matches()` 是
   `field_by_stable_key` O(n²) 的同款错误。判据 `check_sync_registry_lookup_is_o1.py` 以规模
   递增的合成注册表钉住这条。
"""
from __future__ import annotations

import re as _re
from dataclasses import dataclass
from typing import Final, Mapping

from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.phase5_row_table_sheet import StoreKind

__all__ = [
    "StoreKind",
    "StoreItemSpec",
    "StoreMergePlan",
    "StoreMergePlanNotRegisteredError",
    "STORE_MERGE_REGISTRY",
    "NON_STORE_BACKED_ADAPTERS",
    "resolve_store_merge_plan",
    "store_merge_plan_or_skip",
    "looks_like_adapter_id",
    "all_registered_adapter_ids",
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
class StoreMergePlan:
    """一个 adapter 的 store 合并计划（回方向 `oo_to_html` 按它分派，不再 elif 链）。

    :param adapter_id: 契约/adapter 身份（== contract_id == 契约文件名）。
    :param provider_module: provider 模块名（框架按名 import，不硬编码 import 语句）。
    :param items: 该 adapter 的全部 store item 形态声明。
    :param merge_rows_fn: rows 形态的合并函数名（provider 侧，默认
        `merge_projection_into_store_rows`）。
    :param merge_state_fn: state 形态（G7）的合并函数名；仅 state 形态 adapter 给。
    :param dual_store_fn: 多 store item 的整体镜像函数名（D4 的 `_mirror_d4_dual_stores` 同型）。
    """

    adapter_id: str
    provider_module: str
    items: tuple[StoreItemSpec, ...] = ()
    merge_rows_fn: str = "merge_projection_into_store_rows"
    merge_state_fn: str | None = None
    dual_store_fn: str | None = None
    #: 非空 ⇒ 该 adapter 的 provider **未提供** store 镜像门面（实测缺符号）。
    #: `resolve_store_merge_plan` 会抛可归因的 domain 错误，取代原先运行时 AttributeError。
    mirror_unavailable_reason: str = ""

    @property
    def item_ids(self) -> tuple[str, ...]:
        return tuple(i.item_id for i in self.items)

    def item(self, item_id: str) -> StoreItemSpec | None:
        for i in self.items:
            if i.item_id == item_id:
                return i
        return None


# ═══════════════════════════════════════════════════════════════════════════
# 注册表本体 —— O(1) dict。新接一张底稿只在这里加一条，不改通用回写层。
#
# 🔴 provider_module / item 清单均按 provider 实测常量登记（不猜）。store item 清单以
#    provider 的 `all_store_item_ids()` 为单一口径时留空 items，由 `resolve_store_merge_plan`
#    的调用方按 provider 单源取（需求 3.3 两方向同源）。
# ═══════════════════════════════════════════════════════════════════════════

STORE_MERGE_REGISTRY: Final[Mapping[str, StoreMergePlan]] = {
    # 🔴 b60 / g7 / h1 三家：**provider 未提供 merge 门面**（2026-09-26 实测）。
    #    原 `oo_to_html` 的 elif 链对它们写了 `bridge.STORE_ITEM_ID` /
    #    `bridge.merge_projection_into_store_rows` / `…_store_state`，而这三个 provider 里
    #    **这些符号都不存在**（`git show HEAD:` 逐个实测确认，非本次改动引入）⇒ 那三个分支
    #    一旦被执行就是 AttributeError → opaque 500。注册表把这个隐藏缺陷显式化：
    #    `mirror_unavailable_reason` 非空 ⇒ `resolve_store_merge_plan` 抛可归因的 domain 错误，
    #    而不是等运行时炸在属性访问上。修它们归各自 provider 的 spec（本 spec 只暴露不掩盖）。
    "b60.hour_budget": StoreMergePlan(
        adapter_id="b60.hour_budget",
        provider_module="pilot_simple_checklist",
        mirror_unavailable_reason=(
            "pilot_simple_checklist 未提供 STORE_ITEM_ID 与 merge_projection_into_store_rows"
            "（HEAD 实测缺失）—— B60 是 simple_checklist 形态，store 镜像门面从未实现"
        ),
    ),
    "d1.notes_receivable_detail": StoreMergePlan(
        adapter_id="d1.notes_receivable_detail",
        provider_module="phase5_d1_notes_receivable",
        items=(StoreItemSpec(item_id="D1-cust-rows", kind=StoreKind.rows),),
    ),
    "d2.receivable_detail": StoreMergePlan(
        adapter_id="d2.receivable_detail",
        provider_module="d2_bidirectional_bridge",
        items=(StoreItemSpec(item_id="D2-detail-rows", kind=StoreKind.rows),),
    ),
    "d3.prepaid_receipts_detail": StoreMergePlan(
        adapter_id="d3.prepaid_receipts_detail",
        provider_module="phase5_d3_prepaid_receipts",
        items=(StoreItemSpec(item_id="D3-det-rows", kind=StoreKind.rows),),
    ),
    "d4.revenue_detail": StoreMergePlan(
        adapter_id="d4.revenue_detail",
        provider_module="phase5_d4_revenue_detail",
        # D4 有 46 个 store item，清单单源在 provider.all_store_item_ids()（需求 3.3）；
        # 它的多 item 镜像走专用门面。
        dual_store_fn="_mirror_d4_dual_stores",
    ),
    "d5.receivables_financing_detail": StoreMergePlan(
        adapter_id="d5.receivables_financing_detail",
        provider_module="phase5_d5_receivables_financing",
        items=(StoreItemSpec(item_id="D5-2-rows", kind=StoreKind.rows),),
    ),
    "d6.contract_assets_detail": StoreMergePlan(
        adapter_id="d6.contract_assets_detail",
        provider_module="phase5_d6_contract_assets",
        items=(StoreItemSpec(item_id="D6-2-rows", kind=StoreKind.rows),),
    ),
    "d7.contract_liabilities_detail": StoreMergePlan(
        adapter_id="d7.contract_liabilities_detail",
        provider_module="phase5_d7_contract_liabilities",
        items=(StoreItemSpec(item_id="D7-2-rows", kind=StoreKind.rows),),
    ),
    "g7.soe_subsidiary_disclosure": StoreMergePlan(
        adapter_id="g7.soe_subsidiary_disclosure",
        provider_module="pilot_g7_two_level_dynamic",
        merge_state_fn="merge_projection_into_store_state",
        mirror_unavailable_reason=(
            "pilot_g7_two_level_dynamic 有 STORE_ITEM_ID 但无 merge_projection_into_store_state"
            "（HEAD 实测缺失）—— state 形态的合并门面从未实现"
        ),
    ),
    "h1.disposal_check": StoreMergePlan(
        adapter_id="h1.disposal_check",
        provider_module="pilot_h1_grouped_dynamic",
        mirror_unavailable_reason=(
            "pilot_h1_grouped_dynamic 有 STORE_ITEM_ID 但无 merge_projection_into_store_rows"
            "（HEAD 实测缺失）—— rows 形态的合并门面从未实现"
        ),
    ),
}


#: **显式登记**为「不做 store 镜像」的 adapter（回方向直接跳过，不抛错）。
#:
#: 🔴 为什么必须显式登记而不是「查不到就跳过」：原 `oo_to_html` 的 `else: return` 让
#:    「provider 声明了 store 却漏接回写层」与「该 adapter 本来就不镜像」在观测面上长得
#:    一模一样 —— 那正是 D4-35 恒空 / D4-13 写不进 OO 两个 bug 能活下来的原因。登记在此
#:    集合里的是后者；前者会在 `resolve_store_merge_plan` 显式打红。
#:
#: 当前为空：现有 10 个 store-backed adapter 全部有 plan。新增非 store-backed adapter 时
#: 在此登记并写明理由。
NON_STORE_BACKED_ADAPTERS: Final[frozenset[str]] = frozenset()


#: 真实 adapter_id 的形态（== contract_id == 契约文件名，如 `d4.revenue_detail` /
#: `b60.hour_budget`）。用来区分两种「注册表查不到」：
#:   * **形如 adapter_id 却未注册** ⇒ 真漏接，必须显式打红（D4-35 / D4-13 缺陷形态）
#:   * **压根不是 adapter_id**（如 entry_id `xlsx/gt-d2-accounts-receivable`，测试 harness
#:     与部分调用点会把 entry_id 传进来）⇒ 它本来就没有 store 计划，跳过是正确行为
#:
#: 🔴 这条区分有实测背书：`test_task26_oo_to_html_pg` 的 harness 用
#:    `adapter_id = "xlsx/gt-d2-accounts-receivable"`（entry_id 形态）。原 `else: return` 把它
#:    与「真漏接」混为一谈；一律抛错则 5 个 scenario 全部构建失败（实测 49 个判据红）。
_ADAPTER_ID_SHAPE = _re.compile(r"^[a-z][a-z0-9]*\d*\.[a-z0-9_]+$")


def looks_like_adapter_id(value: str) -> bool:
    """形态判定：是否像真实 adapter_id（`<prefix>.<name>` 全小写）。"""
    return bool(_ADAPTER_ID_SHAPE.match(value or ""))


def resolve_store_merge_plan(adapter_id: str) -> StoreMergePlan:
    """O(1) dict 查表。**形如 adapter_id 却未注册** ⇒ 抛显式错误（需求 3.4，不静默跳过）。

    IF 命中但 plan 标了 `mirror_unavailable_reason` THEN 同样抛显式错误 —— 那三家
    （b60/g7/h1）的 provider 实测缺 merge 门面，原代码会在属性访问处炸出无来源的
    AttributeError；这里换成可归因的 domain 错误。

    :raises StoreMergePlanNotRegisteredError: 未注册（且形如 adapter_id）或镜像门面不可用。
    """
    plan = STORE_MERGE_REGISTRY.get(adapter_id)
    if plan is None:
        raise StoreMergePlanNotRegisteredError(
            f"adapter {adapter_id!r} 未注册 store merge plan；已注册："
            f"{sorted(STORE_MERGE_REGISTRY)}"
        )
    if plan.mirror_unavailable_reason:
        raise StoreMergePlanNotRegisteredError(
            f"adapter {adapter_id!r} 的 store 镜像门面不可用：{plan.mirror_unavailable_reason}"
        )
    return plan


def store_merge_plan_or_skip(adapter_id: str) -> StoreMergePlan | None:
    """回方向入口：返回 plan，或对「不是 adapter_id 的输入」返回 None（跳过镜像）。

    三态而非二态，这是本函数存在的全部理由：
      1. **已注册且门面可用** → 返回 plan
      2. **不像 adapter_id**（entry_id 等）→ 返回 None，调用方跳过（原 `else: return` 的合法部分）
      3. **像 adapter_id 但未注册 / 门面不可用** → 抛 `StoreMergePlanNotRegisteredError`
         （原 `else: return` 的**缺陷部分**：D4-35 恒空 / D4-13 写不进 OO 的根因形态）
    """
    if not looks_like_adapter_id(adapter_id):
        return None
    if adapter_id in NON_STORE_BACKED_ADAPTERS:
        return None
    return resolve_store_merge_plan(adapter_id)


def all_registered_adapter_ids() -> tuple[str, ...]:
    """已注册 adapter 的稳定排序清单（供 CI 卡点与报告用）。"""
    return tuple(sorted(STORE_MERGE_REGISTRY))
