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
    "DedicatedStoreItem",
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


# ═══════════════════════════════════════════════════════════════════════════
# 注册表本体 —— O(1) dict。新接一张底稿只在这里加一条，不改通用回写层。
#
# 🔴 provider_module / item 清单均按 provider 实测常量登记（不猜）。store item 清单以
#    provider 的 `all_store_item_ids()` 为单一口径时留空 items，由 `resolve_store_merge_plan`
#    的调用方按 provider 单源取（需求 3.3 两方向同源）。
# ═══════════════════════════════════════════════════════════════════════════

STORE_MERGE_REGISTRY: Final[Mapping[str, StoreMergePlan]] = {
    # 🔴 b60 保留一条 plan 仅为「已登记」可查（`check_sheet_specs_fully_registered` 的分母是
    #    8 家已交付 contract）。它的**实际路径**走 `NON_STORE_BACKED_ADAPTERS` 直接跳过 ——
    #    契约无 html_store 段、15 字段 store_item_id 全 None ⇒ 纯 Excel entry，不做 store 镜像。
    "b60.hour_budget": StoreMergePlan(
        adapter_id="b60.hour_budget",
        provider_module="pilot_simple_checklist",
        mirror_unavailable_reason=(
            "B60 是纯 Excel entry：契约 review 段无 html_store、15 个字段 store_item_id 全为 "
            "None（2026-09-26 契约逐项实测）⇒ 它的 HTML 宿主不读 checklist store，"
            "本来就不需要镜像。实际路径由 NON_STORE_BACKED_ADAPTERS 提前跳过，"
            "本 reason 只在有人绕过该集合直接 resolve 时兜底报错"
        ),
    ),
    "d1.notes_receivable_detail": StoreMergePlan(
        adapter_id="d1.notes_receivable_detail",
        provider_module="phase5_d1_notes_receivable",
        items=(StoreItemSpec(item_id="D1-cust-rows", kind=StoreKind.rows),),
        dedicated_items=(
            DedicatedStoreItem(
                item_id_const="STORE_ITEM_ID_D107",
                merge_fn="merge_d17_from_projection",
                base_kind="dict",
                provider_module="phase5_d1_07_memo",
            ),
        ),
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
        # 🔴 6 个 dedicated dict/list store item（Task 13 收敛，取代 6×2=12 处 hasattr 试探）：
        # 原 `oo_to_html._mirror_store_backed_if_needed` 对每个都写 `hasattr(bridge, "merge_d*")
        # and hasattr(bridge, "STORE_ITEM_ID_D*_DICT")` 判断是否走它。改为显式声明 + 统一分派
        # 循环（_mirror_dedicated_dict_stores），逐段行为不变（同一 SQL / 同一 merge 函数 /
        # 同一 applied<=0 跳过写库判断），只收敛判断入口。
        dedicated_items=(
            DedicatedStoreItem(
                item_id_const="STORE_ITEM_ID_D435_DICT", merge_fn="merge_d435_from_projection",
                base_kind="dict", provider_module="phase5_d4_revenue_detail",
            ),
            DedicatedStoreItem(
                item_id_const="STORE_ITEM_ID_D49_DICT", merge_fn="merge_d49_from_projection",
                base_kind="dict", provider_module="phase5_d4_revenue_detail",
            ),
            DedicatedStoreItem(
                item_id_const="STORE_ITEM_ID_D48_DICT", merge_fn="merge_d48_from_projection",
                base_kind="list", provider_module="phase5_d4_product_margin_sheet",
            ),
            DedicatedStoreItem(
                item_id_const="STORE_ITEM_ID_D433_DICT", merge_fn="merge_d433_from_projection",
                base_kind="dict", provider_module="phase5_d4_other_margin_sheet",
            ),
            DedicatedStoreItem(
                item_id_const="STORE_ITEM_ID_D434_DICT", merge_fn="merge_d434_from_projection",
                base_kind="dict", provider_module="phase5_d4_other_contract_sheet",
            ),
            DedicatedStoreItem(
                item_id_const="STORE_ITEM_ID_D436_DICT", merge_fn="merge_d436_from_projection",
                base_kind="dict", provider_module="phase5_d4_other_cutoff_sheet",
            ),
        ),
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
    # 🔴 E1（spec e1-sync-coverage-and-first-canary）：provider 已建、声明层已就绪，但
    #    adapter 尚未注册（平台级供给缺口 umbrella BP-61-1）⇒ 此处先登记 plan，使
    #    「adapter 一注册即可用」；store item 清单取 provider 的 all_store_item_ids() 单一口径
    #    （随灰度开关增长，需求 3.3）。
    # 🔴 E1（spec e1-sync-coverage-and-first-canary）：2026-09-26 起 **provider 侧就绪** ——
    #    契约已生成并双向锁死（`e1.monetary_fund_detail.json`，digest 7fa51f14）、
    #    `STORE_ITEM_ID` 单数常量指向 canary、投影/合并门面**薄转发框架层引擎**（每个 ≤3 行，
    #    这是三层架构的收益兑现点：新 entry 无需复制 200 行投影合并代码）。
    #    store item 清单取 provider 的 `all_store_item_ids()` 单一口径（随灰度开关增长，需求 3.3）。
    #    ⚠️ adapter 注册本身仍卡 umbrella BP-61-1 平台级缺口（三表近空），与 D1/D3/D5/D6/D7 同。
    "e1.monetary_fund_detail": StoreMergePlan(
        adapter_id="e1.monetary_fund_detail",
        provider_module="phase5_e1_monetary_fund",
        items=(
            StoreItemSpec(item_id="E1-cash-detail-rows", kind=StoreKind.rows),
            StoreItemSpec(item_id="E1-digital-rows", kind=StoreKind.rows),
        ),
    ),
    "g7.soe_subsidiary_disclosure": StoreMergePlan(
        adapter_id="g7.soe_subsidiary_disclosure",
        provider_module="pilot_g7_two_level_dynamic",
        merge_state_fn="merge_projection_into_store_state",
        # 🔴 该门面**已于 2026-09-26 补齐**（此前 HEAD 实测缺失 ⇒ AttributeError → opaque 500）：
        #    state 形态走矩阵格级合并，保留 version / entitySlots / 其他 table，且**不新建**
        #    metric 行与实体列（契约外的 metric、实体清单外的列一律 fail-closed 跳过 ——
        #    凭空造结构会重演 legacy 列键搁浅：改造前的 `c{n}Current` 至今读不到）。
        items=(
            StoreItemSpec(item_id="G7-main-disclosure-soe-v2", kind=StoreKind.dict),
        ),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    "h1.disposal_check": StoreMergePlan(
        adapter_id="h1.disposal_check",
        provider_module="pilot_h1_grouped_dynamic",
        # 🔴 该门面**已于 2026-09-26 补齐**（此前 HEAD 实测缺失）：rows 形态，复用框架层
        #    `set_json_path` / `resolve_json_path`；幽灵行判据用业务名称列 `asset_name`
        #    而非首列 `seq` —— 后者是 `auto_source` 序号，用它会把「只填了序号的空行」当真行留下。
        items=(StoreItemSpec(item_id="H1-8-rows", kind=StoreKind.rows),),
    ),
}


#: **显式登记**为「不做 store 镜像」的 adapter（回方向直接跳过，不抛错）。
#:
#: 🔴 为什么必须显式登记而不是「查不到就跳过」：原 `oo_to_html` 的 `else: return` 让
#:    「provider 声明了 store 却漏接回写层」与「该 adapter 本来就不镜像」在观测面上长得
#:    一模一样 —— 那正是 D4-35 恒空 / D4-13 写不进 OO 两个 bug 能活下来的原因。登记在此
#:    集合里的是后者；前者会在 `resolve_store_merge_plan` 显式打红。
#:
#: 🔴 **b60 实测属此类**（2026-09-26 契约逐项核实）：`b60.hour_budget.json` 的 `review` 段
#:    **无 `html_store`**（只有 authority_root / entry_id / pilot_class / reviewed_basis），
#:    且 15 个字段的 `store_item_id` **全为 None** ⇒ B60 是**纯 Excel entry**，
#:    它的 HTML 宿主不读 checklist store，本来就不需要镜像。
#:
#:    ⚠️ 本条修正了一次**我方误判**：首版把 b60 与 g7/h1 一起标成
#:    「provider 缺 merge 门面」。实际三家情况不同 —— g7/h1 有完整 store 声明与投影链、
#:    确实只缺 merge（已于本轮补齐），而 b60 **压根没有 store** ⇒ 它不是缺陷，
#:    是形态不同。判据 `test_b60_has_no_html_store_by_design` 钉住这条事实。
NON_STORE_BACKED_ADAPTERS: Final[frozenset[str]] = frozenset({
    "b60.hour_budget",
})


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
