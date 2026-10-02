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
from typing import Final, Mapping

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

# 声明类已抽到伴生模块（原因见其 docstring：本文件卡在行数门上限 800，而并发 lane 持续往注册表 dict 里 append）。
# 🔴 re-export 全部公开名 —— 既有 `from ... store_item_registry import StoreItemSpec` 调用点一处不改。
from app.services.workpaper_sync.store_item_specs import (  # noqa: F401
    DedicatedStoreItem,
    StoreItemSpec,
    StoreMergePlan,
    StoreMergePlanNotRegisteredError,
    default_payload_for,
)

# ═══════════════════════════════════════════════════════════════════════════
# 注册表本体 —— O(1) dict。新接一张底稿只在这里加一条，不改通用回写层。
#
# 🔴 provider_module / item 清单均按 provider 实测常量登记（不猜）。store item 清单以
#    provider 的 `all_store_item_ids()` 为单一口径时留空 items，由 `resolve_store_merge_plan`
#    的调用方按 provider 单源取（需求 3.3 两方向同源）。
# ═══════════════════════════════════════════════════════════════════════════

STORE_MERGE_REGISTRY: Final[Mapping[str, StoreMergePlan]] = {
    # ── B60 工时预算（2026-09-27：从 NON_STORE_BACKED 转为真 store-backed）────────
    #
    # 🔴 归类变更的依据是**前端长出了载体**，不是重新解读旧事实：
    #    此前 b60 是 `NON_STORE_BACKED_ADAPTERS` 的唯一成员，理由「契约无 html_store 段、
    #    15 字段 store_item_id 全 None ⇒ HTML 宿主不读 checklist store」。那描述的是
    #    「当时前端没有 HTML 面」。`b60/GtB60HourBudgetPanel.vue` 落地后，B60-1 工时表在
    #    HTML 侧读写 `B60-1-hour-budget-rows`（remark 存 JSON 行数组、行身份 `rowUuid`）
    #    ⇒ 不镜像就是「OO 里改的行回不到结构化视图」，面板空态那句
    #    「forcesave 后将镜像至此」成了不成立的承诺。
    #
    # 🔴 `merge_rows_fn` 用默认名，实现在伴生模块 `pilot_b60_store_merge`
    #    （主模块 1007 行，行数门措辞是「打磨应让文件变小不变大」），主模块 re-export。
    #    与 G7/H1 两个伴生门面同一边界。
    #
    # 🔴 meta 表（`hour_budget_meta`：单位名称 / 会计期间 / 编制人…）**不进 items** ——
    #    前端面板只渲染行表、不读 meta，声明它有 store 就是造第二份事实。
    #    merge 门面里对无 `row_key` 的字段显式跳过（不是靠巧合漏掉）。
    "b60.hour_budget": StoreMergePlan(
        adapter_id="b60.hour_budget",
        provider_module="pilot_simple_checklist",
        items=(StoreItemSpec(item_id="B60-1-hour-budget-rows", kind=StoreKind.rows),),
    ),
    "d1.notes_receivable_detail": StoreMergePlan(
        adapter_id="d1.notes_receivable_detail",
        provider_module="phase5_d1_notes_receivable",
        items=(StoreItemSpec(item_id="D1-cust-rows", kind=StoreKind.rows),),
        # 🔴 2026-09-28：D1 扩容面（12 张受管 sheet / 18 个 item）接入两方向装配链。
        #    此前 `dual_store_fn` 为空 ⇒ 回方向走单 item 路径、只镜像 `bridge.STORE_ITEM_ID`
        #    那 1 个，伴生模块 `phase5_d1_expansion.all_store_item_ids()` 没有任何生产代码
        #    调用（实测确认）。形态同 D4-35 恒空，但断口在「entry ↔ 伴生模块」之间。
        #    `dual_store_fn` 只需非空即触发 `_mirror_dual_stores`；真正被按名调用的是
        #    `merge_all_fn`（D1 按 spec 泛化，不是 D4 那种逐 item 手写清单）。
        dual_store_fn="_mirror_dual_stores",
        merge_all_fn="merge_projection_into_all_d1_stores",
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
        # 🔴 spec workpaper-sync-registration-isolation · AC 4.3：开关打开后走多 store 镜像。
        #    merge_all_fn 指向 bridge 上的 D2 版整体 merge 函数。
        dual_store_fn="_mirror_d4_dual_stores",
        merge_all_fn="merge_projection_into_all_d2_stores",
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
        # 🔴 **本条原先缺失**（spec `h2-h6-h10-pilot-cross-reference-lanes` 收口时实测补）：
        #    `H1 固定资产.xlsx` 全册含 IF 公式格 **496 个 —— 全 H 循环最多**
        #    （逐 sheet：折旧测算（多次减值）181 · 折旧测算（含减值）180 · 折旧测算（不含减值）60 ·
        #     减值测算表H1-14 25 · 审定表H1-1 24 · 运输设备权属H1-17 21 · 可收回金额H1-15 3 ·
        #     增加检查表H1-7 1 · **受管表 减少检查表H1-8 1**），对照 H10 只有 46、H6 只有 12。
        #    也就是说：**OO 加载崩溃风险最高的一册，恰恰是唯一连声明都没有的那条**。
        #    中性化是 per-file（整册就地改写 substrate 副本）⇒ 点同册任一 sheet 的在线编辑
        #    都会触发整册加载，受管表自己只有 1 格也必须挂。
        #    函数与 G7/G2/H9…H10 共用，不新造。
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── F1 预付账款 canary（spec: f1-sync-coverage-and-first-canary）──────
    #    同 E1 架构：薄转发框架层引擎，store item 清单取 all_store_item_ids() 单一口径。
    #    canary F1-rp-rows（关联方检查表F1-6），灰度开关控后续 sheet。
    "f1.prepayment_detail": StoreMergePlan(
        adapter_id="f1.prepayment_detail",
        provider_module="phase5_f1_prepayment",
        items=(
            StoreItemSpec(item_id="F1-rp-rows", kind=StoreKind.rows),
        ),
    ),
    # ── F2 四 lane（spec: f2-sync-coverage-four-entry-lanes）──────
    "f2.inventory_main": StoreMergePlan(
        adapter_id="f2.inventory_main",
        provider_module="phase5_f2_inventory_main",
        items=(
            StoreItemSpec(item_id="F2-6-rows", kind=StoreKind.rows),
        ),
    ),
    "f2.stocktake_bundle": StoreMergePlan(
        adapter_id="f2.stocktake_bundle",
        provider_module="phase5_f2_stocktake_bundle",
        items=(
            StoreItemSpec(item_id="F2-25-rows", kind=StoreKind.rows),
            StoreItemSpec(item_id="F2-25-floor-rows", kind=StoreKind.rows),
        ),
    ),
    "f2.inventory_valuation": StoreMergePlan(
        adapter_id="f2.inventory_valuation",
        provider_module="phase5_f2_inventory_valuation",
        items=(
            StoreItemSpec(item_id="F2-48-rows", kind=StoreKind.dict),
        ),
    ),
    "f2.inventory_special": StoreMergePlan(
        adapter_id="f2.inventory_special",
        provider_module="phase5_f2_inventory_special",
        items=(
            StoreItemSpec(item_id="F2-57-rows", kind=StoreKind.dict),
        ),
    ),
    # ── F3 / F4 / F5 canary（spec: f{3,4,5}-sync-coverage-and-first-canary）──────
    # 🔴 `items` 只登记**当前灰度开关打开**的受管区（各 provider 的
    #    `all_store_item_ids()` 是单一口径）。其余 sheet 随灰度开关逐张打开时在此追加，
    #    不预登记未受管的键 —— 预登记会让 `check_sheet_specs_fully_registered` 的分母失真。
    "f3.notes_payable_detail": StoreMergePlan(
        adapter_id="f3.notes_payable_detail",
        provider_module="phase5_f3_notes_payable",
        items=(StoreItemSpec(item_id="F3-5-rows", kind=StoreKind.rows),),
    ),
    "f4.accounts_payable_detail": StoreMergePlan(
        adapter_id="f4.accounts_payable_detail",
        provider_module="phase5_f4_accounts_payable",
        items=(StoreItemSpec(item_id="F4-6-rows", kind=StoreKind.rows),),
    ),
    "f5.cost_of_sales_detail": StoreMergePlan(
        adapter_id="f5.cost_of_sales_detail",
        provider_module="phase5_f5_cost_of_sales",
        items=(StoreItemSpec(item_id="F5-8-rows", kind=StoreKind.rows),),
    ),
    # ── G2 canary（spec: g-cycle-sync-foundation-and-first-canary · Task 11/14）──
    #
    # 🔴 **GC-2：G 循环 13 册全部命中 OO 加载期裸 `IF(`** ⇒ per-file 保守策略，
    #    每条 G plan 一律带 `oo_crash_neutralization_fn`，**无例外**。
    #    G2 册按生产函数 `neutralize_oo_crash_if_formulas` 现算 **21 格**
    #    （审定表G2-1 19 + 应收利息坏账准备测算G2-7 2）——
    #    受管表 `明细表G2-2` 本身**零命中**，但中性化作用于整册 substrate 副本，
    #    「受管表干净」不是豁免理由：用户在同一册里点任一 sheet 的在线编辑都会触发整册加载。
    #    BP-4（真 OO 9.4 场景集）未交付前**不得**以「裸 IF 数少」推断某册不需要 ——
    #    G7 的崩溃不是数量问题而是「参数在 OO 侧解析成 undefined」，只有真 OO 加载能判。
    #
    # 🔴 中性化函数与 G7 **共用一个**（`g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas`，
    #    已被真 OO 栈验收过的口径），**不新造**；也**不得**在 `adapters/excel.py` 加
    #    `if adapter_id == "g2…"` 字面量分支（Task 13 已收敛掉两处，判据
    #    `test_excel_adapter_has_no_adapter_id_literal_branch` 锁住不回退）。
    "g2.interest_receivable_detail": StoreMergePlan(
        adapter_id="g2.interest_receivable_detail",
        provider_module="phase5_g2_interest_receivable",
        items=(StoreItemSpec(item_id="G2-2-detail-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── G9（spec: g-cycle-single-region-detail-lanes · Task 8 / C-5）────────
    #
    # 🔴 **一个 store item、三个受管区**（G 循环首例）：`明细表G9-2` 的三区
    #    （R12-16 / R19-23 / R26-28）行都存在同一个 `G9-detail-rows` 数组里，
    #    区归属由行的 `section` 字段表达。因此 `items` 只有**一条** ——
    #    `item_ids` 长度 1 ⇒ 回方向走 `merge_rows_fn` 单 item 分派（不是 D4 的
    #    `dual_store_fn` 多 item 路径）。三段的遍历在 provider 的
    #    `merge_projection_into_store_rows` 里完成（顺序穿线），框架无需知道分段。
    #
    # 🔴 GC-2：G9 册裸 IF **42 格**（全在 `审定表G9-1`，受管表 `明细表G9-2` 零命中）。
    #    per-file 保守策略 ⇒ 受管表干净也必须挂：点同册任一 sheet 的在线编辑都会
    #    触发整册加载。中性化函数与 G7/G2/H9 **共用一个**（已被真 OO 栈验收过的
    #    口径），不新造；也不得在 `adapters/excel.py` 加 `if adapter_id == "g9…"`。
    "g9.other_noncurrent_detail": StoreMergePlan(
        adapter_id="g9.other_noncurrent_detail",
        provider_module="phase5_g9_other_noncurrent",
        items=(StoreItemSpec(item_id="G9-detail-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── G10（spec: g-cycle-single-region-detail-lanes · Task 9 / C-7）───────
    #
    # 与首条 G9 的差别只在受管区数量：G10 是**单区**（`明细表G10-2` 的 R11-R20）⇒
    # provider 的三个 store 门面各自 ≤3 行薄转发框架层引擎（照 G2），不需要 G9 那样的
    # 「遍历三段」伴生模块。`items` 一条 ⇒ 回方向走 `merge_rows_fn` 单 item 分派。
    #
    # 🔴 GC-2：G10 册裸 IF **28 格**（全在 `审定表G10-1`，受管表 `明细表G10-2` 零命中）。
    #    per-file 保守策略 ⇒ 受管表干净也必须挂；中性化函数与 G7/G2/G9/H9 **共用一个**。
    "g10.trading_liabilities_detail": StoreMergePlan(
        adapter_id="g10.trading_liabilities_detail",
        provider_module="phase5_g10_trading_liabilities",
        items=(StoreItemSpec(item_id="G10-detail-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── G8（spec: g-cycle-single-region-detail-lanes · Task 9b / C-8）────────
    #
    # 几何同 G10（两级表头 + 单区 R11-R20 + footer R21）⇒ 薄转发，无伴生模块。
    #
    # 🔴 G8 是 **FVOCI**（其他权益工具投资）—— OCI 三列 F/L/R 是 CAS22 要求的，
    #    与 G9/G10 的「删 OCI 四列」**反向**。照抄那两条的移除清单会删掉准则要求的列。
    #
    # 🔴 模板有**四处行级公式缺陷**（M 在 R12-20 漏 L · P 在 R11+R13-20 漏 K ·
    #    R 在 R13-20 整格无公式 · T 在 R12 整格无公式）⇒ `R`/`T` 只能判 `editable`
    #    （判 formula 会撞 `excel_materialize` 的 `ProtectedRegionWriteError`），
    #    由前端按恒等式重算覆盖。逐格台账见 `phase5_g8_02_detail` 模块头。
    #
    # 🔴 GC-2：G8 册裸 IF **12 格**（全 G 循环最少，全在 `审定表G8-1`，受管表零命中）。
    #    per-file 保守策略 ⇒ 受管表干净也必须挂；中性化函数与 G7/G2/G9/G10/H9 共用一个。
    "g8.other_equity_detail": StoreMergePlan(
        adapter_id="g8.other_equity_detail",
        provider_module="phase5_g8_other_equity",
        items=(StoreItemSpec(item_id="G8-detail-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── G14（spec: g-cycle-single-region-detail-lanes · Task 10 / C-9）───────
    #
    # 几何同 G8/G10（两级表头 + 单区 + footer）⇒ 薄转发，无伴生模块。
    #
    # 🔴 **固定 9 行** R11-R19（模板 A 列写死行名），行身份是 **`rowKey`**
    #    （`stable_template_row_key`）—— 全 G 循环唯一一家不用生成式 id 的，GC-6 裁决它是
    #    最稳的一族。照抄 F 循环的 `row_identity_key in ('rowId','id')` 白名单会判它违规。
    #
    # 🔴 `L` 列是**布尔**校验列 `=D=K`（裁决 G1R-H4）：`value_type=boolean` +
    #    `mode=formula` ⇒ 不入 store（`PROTECTED_MODES`），TRUE/FALSE 不会落库。
    #
    # 🔴 模板缺陷：`K=G+H` 把「本期转回」当成增加损益，而同表 `J` 的 `-H` 要求 H 填正数
    #    ⇒ 会计正确应为 `=G-H`。`formula_templates` 逐字记模板原式（判据比对模板），
    #    前端按正确口径算 ⇒ 有转回时两侧相差 2×转回，如实登记为欠账。
    #
    # 🔴 GC-2：G14 册裸 IF **11 格**（全在 `审定表G14-1`，受管表零命中）。
    #    per-file 保守策略 ⇒ 受管表干净也必须挂；中性化函数与 G7/G2/G9/G10/G8/H9 共用。
    "g14.credit_impairment_detail": StoreMergePlan(
        adapter_id="g14.credit_impairment_detail",
        provider_module="phase5_g14_credit_impairment",
        items=(StoreItemSpec(item_id="G14-detail-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── G11（spec: g-cycle-single-region-detail-lanes · Task 11 / C-10）──────
    #
    # 🔴 **九条里唯一「受管表自身命中裸 IF」的一家**（44 格：G/K 两列占比公式 21×2 +
    #    footer 的 shared 成员格 2）。前四条 G9/G10/G8/G14 的受管表都是零命中，中性化
    #    只动审定表 —— 这条的中性化会**摘掉受管列自己的公式**。
    #
    #    `adapters/excel.py` 在 materialize **之前**跑中性化（substrate 副本），逐格实测：
    #      数据区 R10-R30：F 21/21→21/21 · G 21/21→**0/21** · J 21/21→21/21
    #                      · K 21/21→**0/21** · L 21/21→21/21
    #    而 `excel_materialize` 的两条检查方向**相反**：`formula` 要求 `view.has_formula`、
    #    `auto_source` 要求该格**不是**公式 ⇒ 只有一种声明能过：
    #      F/J/L → `mode=formula`（进 formula_columns）
    #      G/K   → `mode=auto_source`（同属 PROTECTED_MODES，不入 store、OO 改动不合并）
    #    判 formula 会在 materialize 阶段抛 `ProtectedRegionWriteError`。
    #    先例：`phase5_f1_05_long_term` 的 J 列（模板无公式 + 前端派生 + OO 不合并）。
    #
    # 🔴 整册裸 IF **95 格**（受管表 44 + 收益率分析表G11-4 32 + 审定表G11-1 19）——
    #    全 G 循环最多，per-file 挂中性化在这条上不是保守而是必需。
    "g11.investment_income_detail": StoreMergePlan(
        adapter_id="g11.investment_income_detail",
        provider_module="phase5_g11_investment_income",
        items=(StoreItemSpec(item_id="G11-detail-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── G13（spec: g-cycle-single-region-detail-lanes · Task 12 / C-11）───────
    #
    # 🔴 **item_id 是 `G13-detail-skeleton` 不是 `G13-detail-rows`** —— 本 lane 最易接错的
    #    一处。模板 `明细表G13-2` R11-R20 是**固定 10 个损益表项目**，而 `G13-detail-rows`
    #    存的是动态增删的**金融工具级明细**（`instrumentName` 用户自填）⇒ 两侧行模型不同构，
    #    按序映射会把第 N 条工具写进第 N 个损益项目行（**产出错数**）。
    #    前端原有 `buildG13CategorySkeleton()` 已按 10 个固定项目汇总出骨架但只是 `computed`
    #    不落库 ⇒ 本轮持久化成独立 store item（`g13SkeletonStore.ts`），受管它；
    #    工具明细保持 HTML-only 平台增强、**不进 items**（登记在
    #    `phase5_g13_02_detail.LEGACY_INSTRUMENT_STORE_ITEM_ID_G1302`）。
    #    🔴 手工覆盖优先：骨架落库行带 `manualOverride`，有标记的行不被汇总重算冲掉
    #    （否则 OO 回流会被立刻覆盖 = 回流无效）。
    #
    # 🔴 **受管 sheet 零裸 IF**（整册 11 格全在别的 sheet）—— 与 G11 的 44 格相反。
    #    中性化照挂：GC-2 要求 per-file 一律挂，本表零命中只意味着这一趟白跑，
    #    而同册别的 sheet（审定表/附注）仍需要它。
    "g13.fair_value_changes_detail": StoreMergePlan(
        adapter_id="g13.fair_value_changes_detail",
        provider_module="phase5_g13_fair_value_changes",
        items=(StoreItemSpec(item_id="G13-detail-skeleton", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── G12（spec: g-cycle-single-region-detail-lanes · Task 13 / C-12）───────
    #
    # 🔴 本条的受管面是「零公式列」形态：数据区 R9-R13 没有任何一列每行都有公式
    #    （`G` 只 R9 一格、`I` 只 R9/R10 两格）⇒ `formula_columns=()`、10 列全 `editable`。
    #    `G`/`I` 原本是前端派生量（`rowCalcs`），本轮改为落库（`fvCheck`/`netHedgePnl`）——
    #    不落库的话 R11-R13 那两列在 Excel 里永远是空格（模板缺 fill-down、后端又不写）。
    #
    # 🔴 **受管 sheet 零裸 IF**（整册 7 格全在别的 sheet）。中性化照挂：GC-2 要求 per-file
    #    一律挂，本表零命中只意味着这一趟白跑，同册别的 sheet（审定表/附注/G12-4）仍需要它。
    "g12.net_hedge_detail": StoreMergePlan(
        adapter_id="g12.net_hedge_detail",
        provider_module="phase5_g12_net_hedge_gains",
        items=(StoreItemSpec(item_id="G12-hedge-detail-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── G1（spec: g-cycle-single-region-detail-lanes · Task 14 / C-13，九条最后一条）──
    #
    # 🔴 **三区共用这一个 store 键**（`row_section_field="acctClass"`，值
    #    trading / classified_fvpl / designated_fvpl）⇒ `items` 只有一条，但受管 spec 是 3 个。
    #    区① 的 `formula_columns` 多一个跨表 `T`（引 `公允价值测试表G1-6!H10..H14`），
    #    区②③ 的 `T` 整格无公式 ⇒ 三区**不共用**那份声明（判据 P6 的不等点）。
    #    payload 列是 **conclusion**（`conclusion_only` 族，与另七条的 remark 相反）。
    #
    # 🔴 **整册裸 IF 0 格**（G1 册 18 sheet 全零，G 循环唯一）⇒ 中性化对本册是空操作。
    #    仍照挂：GC-2 要求 per-file 一律挂，零命中只意味着这一趟白跑；将来模板改版引入裸 IF
    #    时不需要再回来补这一行。
    "g1.trading_financial_assets_detail": StoreMergePlan(
        adapter_id="g1.trading_financial_assets_detail",
        provider_module="phase5_g1_trading_financial_assets",
        items=(StoreItemSpec(item_id="G1-2-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    "g3.dividend_receivable_detail": StoreMergePlan(
        adapter_id="g3.dividend_receivable_detail",
        provider_module="phase5_g3_dividend_receivable",
        items=(StoreItemSpec(item_id="G3-2-detail-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── G4-sppi（spec: g4-g6-shared-workbook-three-entry-lanes · Task 8）──
    #
    # 🔴 G4 一册三 entry 中的首条。零公式列、无合计、表头起于 B 列。
    # 册裸 IF **186 格**（G 循环第二多），per-file 中性化照挂。
    "g4.bond_main": StoreMergePlan(
        adapter_id="g4.bond_main",
        provider_module="phase5_g4_bond_investment",
        items=(StoreItemSpec(item_id="G4-7-items", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── G6-sppi（spec: g4-g6-shared-workbook-three-entry-lanes · Task 14）──
    "g6.other_bond_main": StoreMergePlan(
        adapter_id="g6.other_bond_main",
        provider_module="phase5_g6_other_bond",
        items=(StoreItemSpec(item_id="G6-5-fair-value-data", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── G5（spec: g5-nested-sections-and-template-defects · Task 8）──
    "g5.long_term_receivable_detail": StoreMergePlan(
        adapter_id="g5.long_term_receivable_detail",
        provider_module="phase5_g5_long_term_receivable",
        items=(StoreItemSpec(item_id="G5-2-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── H9 canary（spec: h-cycle-sync-foundation-and-first-canary · Task 20）──
    #
    # 🔴 **HC-12：H 循环 9 册全部命中 OO 加载期裸 `IF(`** ⇒ 同 G 的 per-file 保守策略，
    #    每条 H plan 一律带 `oo_crash_neutralization_fn`，**无例外**。
    #    逐册按生产函数正则现算的**格数**（不是 findall 出现次数）跨度极大：
    #    最重的 H8 与最轻的 H6 差 **20 倍以上**（H8 的主来源是
    #    `使用权资产 租赁负债初始及后续计量（按月）H8-6`，361 行 × 16 列）。
    #    ⇒ 这正是「per-file 挂」而不是「整册统一挂」的依据：统一挂会在 H6 上白跑、
    #    在 H8 上一次处理量过大。判据
    #    `test_h_foundation_hc_guards.py::TestHfP12BareIfNeutralization` 现算逐册计数。
    #    H9 册现算 **24 格**（全 H 次少，仅多于 H6）。
    #
    # 🔴 中性化函数与 G7 / G2 **共用一个**（已被真 OO 栈验收过的口径），**不新造**；
    #    也**不得**在 `adapters/excel.py` 加 `if adapter_id == "h9…"` 字面量分支。
    "h9.lease_liability_detail": StoreMergePlan(
        adapter_id="h9.lease_liability_detail",
        provider_module="phase5_h9_lease_liabilities",
        items=(StoreItemSpec(item_id="H9-2-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── H6 发布链首例（spec: h2-h6-h10-pilot-cross-reference-lanes）──
    #
    # 🔴 H6 册裸 `IF(` 现算 **12 格，全 H 最低** —— 仍必挂中性化：中性化是 **per-file**
    #    （整册就地改写 substrate 副本），点同册任一 sheet 的在线编辑都会触发整册加载。
    #    BP-4（真 OO 9.4 场景集）未交付前**不得**以「裸 IF 最少」推断本册不需要。
    #    同上，中性化函数与 G7/G2/H9 **共用一个**，不新造、不加 adapter_id 字面量分支。
    #
    # 🔴 与 H9 的差异（照抄会静默出错）：`H6A` 不是幻影码（同时是真实程序表码，解析到
    #    自己的册）；审定期末公式是**资产口径** `L=I+J-K`（H9 是负债口径 `L=I-J+K`）；
    #    H6 **有** TB 发布门（H 循环首例，但发布是用户显式动作，sync 对 TB 写 0 次）。
    "h6.asset_disposal_clearing_detail": StoreMergePlan(
        adapter_id="h6.asset_disposal_clearing_detail",
        provider_module="phase5_h6_asset_disposal_clearing",
        items=(StoreItemSpec(item_id="H6-2-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── H4 首个四级表头 + 三区块宽表（spec: h4-h8-sub-entry-lanes-…）──
    #
    # 🔴 与 H9/H6 的规模差异：**四级表头**（R8-R11）+ **49 有效列** + 三区块
    #    （原值 E..AH / 减值准备 AI..AS / 期末净值 AT..AU）。H9 是 22 列单区块、
    #    H6 是 16 列单区块。这是 `contracts.MAX_HEADER_ROWS` 从 3 扩到 4 之后的
    #    首个真实消费者 —— schema 回退到 3 则本 entry 直接无法表达。
    #
    # 🔴 **18 个 template-only 列**（调整/审定块的数量列与单价列）：前端在那些位置
    #    只有金额标量。映射闭合自检 = 31 映射 + 18 template-only == 49 有效列。
    #    把金额标量映到数量列会把金额写进数量格，且单价公式 `=金额/数量` 立刻算出
    #    荒谬单价 —— 该判定由 `useH4Detail.ts#L63` 注释 + `#L140` 算式定死，非命名推测。
    #
    # 🔴 **footer R28 之下还有不受管区域 R29-R34**（按类别 SUMPRODUCT 小计）——
    #    H9/H6 的 footer 之下无内容；不显式登记，merge 可能把它们当数据行覆盖。
    #
    # 🔴 **2 条 `H4T` 子入口**（H4TabImpairment / H4TabRecoverable）按 AC 1.6 复用
    #    本 adapter —— 不新建 adapter、不给子入口单独登记契约。
    #
    # 中性化函数与 G7/G2/H9/H6 共用一个，不新造、不加 adapter_id 字面量分支。
    "h4.engineering_materials_detail": StoreMergePlan(
        adapter_id="h4.engineering_materials_detail",
        provider_module="phase5_h4_engineering_materials",
        items=(StoreItemSpec(item_id="H4-2-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── H8 58 列全 1:1、零 template-only（spec: h4-h8-sub-entry-lanes-…）──
    #
    # 🔴 **全 H 唯一 `template_only_columns` 为空的主表**：前端 `H8DetailRow` 的
    #    `cost*` / `dep*` / `impair*` 三族与模板三大区块逐列同构，连六个增减去向都对上。
    #    闭合自检 = 58 映射 + 0 template-only == 58 有效列。
    #
    # 🔴 册 465,476 B 全 H 最大，裸 `IF(` 也最重（主来源
    #    `使用权资产 租赁负债初始及后续计量（按月）H8-6`，361 行 × 16 列）⇒ 中性化必挂。
    #    函数与 G7/G2/H9/H6/H4 共用一个，不新造。
    #
    # 🔴 三处"看着像、其实不同"（照抄会静默出错，已在 sheet 声明逐条钉住）：
    #    ①原值块 3 增 3 减 vs 折旧/减值块 2 增 3 减 —— 照抄会多映一列整块右移；
    #    ②未审期末 `K=SUM(D:G)-SUM(H:J)` 含期初 D，而 `AC=SUM(W:Y)-SUM(Z:AB)` 首格即期初；
    #    ③`BE`/`BF` 是**审定**净值（`=S-AJ-BA` / `=V-AM-BD`），映 netBeginAud/netEndAud；
    #      前端 netBeginUnadj/netEndUnadj 模板无列，按名字直觉映过去会把审定值写进未审字段。
    #
    # 🔴 `H8-2-rows` 的 12 个消费方**全在 entry 内**（不是跨 entry）⇒ 冻结力度比
    #    H9/H6 更强，改名要同步改 12 个文件。
    #
    # 🔴 3 条 `H8T` 子入口（H8TabRecoverable / H8TabMeasurementAnnual /
    #    H8TabMeasurementMonthly，按 manifest entry_id 现算）按 AC 1.6 复用本 adapter。
    "h8.right_of_use_assets_detail": StoreMergePlan(
        adapter_id="h8.right_of_use_assets_detail",
        provider_module="phase5_h8_right_of_use_assets",
        items=(StoreItemSpec(item_id="H8-2-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── H2 首条带**声明缺口**的 entry（spec: h2-h6-h10-pilot-cross-reference-lanes）──
    #
    # 🔴 前四条（H9/H6/H4/H8）每个模板列要么有 store 字段、要么明确无对端。
    #    H2 有两处两侧**语义打架**，硬凑映射会造成静默错数，故留**可见缺口**：
    #      · H2-GAP-1 `L 增加`：模板无公式是可输入格，而 HTML 的 increaseTotal 由 5 个
    #        分项在 _recalcFormulas 派生且不落库 ⇒ 权威方向相反。L 判 template-only、
    #        5 分项判 store-only，本格不参与双向。硬映会把 OO 的输入吞掉。
    #      · H2-GAP-2 `O 其他减少`：useH2Detail#L254 `_otherDecrease = decrease +
    #        transferOut` 是 1 格对 2 字段 ⇒ O 映 decrease（主字段），transferOut 判
    #        store-only + legacy_folded。硬映会漏掉 transferOut 那部分金额。
    #    两处各带停下报告点（契约 review.declared_coverage_gaps），需审计域裁决的
    #    部分不由接线方拍板。覆盖闭合仍成立：34 映射 + 16 template-only == 50 有效列。
    #
    # 🔴 三处不能照抄前四条：①footer 之下**无** SUMPRODUCT 小计区（R22 是审计说明；
    #    H4/H8 都有）②footer R21 **不是一律 SUM**（AA/AC/AG/AH 四格行内派生）
    #    ③**两对**净值（期初 + 期末），H8 只有一对。
    #
    # 册 162,616 B / 21 sheets 全 H 最多 ⇒ 中性化必挂，函数与 G7/G2/H9/H6/H4/H8 共用。
    "h2.construction_in_progress_detail": StoreMergePlan(
        adapter_id="h2.construction_in_progress_detail",
        provider_module="phase5_h2_construction_in_progress",
        items=(StoreItemSpec(item_id="H2-2-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── H3 首条**变体轴** entry（spec: h3-h5-h7-variant-axis-and-dynamic-column-paradigm）──
    #
    # 🔴 **两个** item：成本模式与公允价值模式各一张受管明细表，各有独立持久化键。
    #    两张必须同批登记 —— 只放一半，用户在 `useH3MeasurementModel` 里切模式就掉桥。
    #    这与 E1-3 的 currency_variant 不同源（那是两张同尾码 sheet **共用**一个键）。
    #
    # 🔴 `H3-2-fair-rows` 在 **HC-8 冻结键**清册上：被 **G 循环**消费
    #    （g13SourceDetailPull.ts 的 `{ wpCode: 'H3', itemId: 'H3-2-fair-rows' }` 与
    #    gCycleSourceFv.ts 的 `H3: 'H3-2-fair-rows'`）⇒ 只补契约不动键名。
    #
    # 册 146,096 B / 22 sheets ⇒ 中性化必挂，函数与 G7/G2/H9/H6/H4/H8/H2 共用。
    "h3.investment_property_detail": StoreMergePlan(
        adapter_id="h3.investment_property_detail",
        provider_module="phase5_h3_investment_property",
        items=(
            StoreItemSpec(item_id="H3-2-cost-rows", kind=StoreKind.rows),
            StoreItemSpec(item_id="H3-2-fair-rows", kind=StoreKind.rows),
        ),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── H5 映射率最低档（spec: h3-h5-h7-variant-axis-and-dynamic-column-paradigm）──
    #
    # 🔴 键是**拼接**出来的：`useH5Detail.ts` 用 `${ITEM_PREFIX}-rows`（ITEM_PREFIX='H5-2'）
    #    ⇒ 按值 grep 字面量 'H5-2-rows' **零命中**（HC-4）。这里登记的是解析后的真键。
    #
    # 册 195,306 B / 24 sheets ⇒ 中性化必挂，函数与 G7/G2/H9/H6/H4/H8/H2/H3 共用。
    "h5.oil_gas_assets_detail": StoreMergePlan(
        adapter_id="h5.oil_gas_assets_detail",
        provider_module="phase5_h5_oil_gas_assets",
        items=(StoreItemSpec(item_id="H5-2-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── H7 第二条变体轴（同 spec）────────────────────────────────────────────
    #
    # 🔴 **两个** item，且两张 sheet 的形态**在 entry 内就不一致**：
    #    表头层数 4 级（成本）vs 3 级（公允）、数据区起始行 R13 vs R12。
    #    两张必须同批登记（切计量模式就掉桥）。
    # 🔴 载体是 `per_tab_self_persisting`：键与行模型内联在 Tab 组件里，
    #    `useH7DetailCost.ts` / `useH7DetailFair.ts` 只是 getNum/getString 读取器，不是载体。
    #
    # 册 225,641 B / 26 sheets（全 H 最多）⇒ 中性化必挂，函数共用不新造。
    "h7.biological_assets_detail": StoreMergePlan(
        adapter_id="h7.biological_assets_detail",
        provider_module="phase5_h7_biological_assets",
        items=(
            StoreItemSpec(item_id="H7-2-cost-rows", kind=StoreKind.rows),
            StoreItemSpec(item_id="H7-2-fair-rows", kind=StoreKind.rows),
        ),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── H10 资产处置损益（spec: h2-h6-h10-pilot-cross-reference-lanes）─────────
    #
    # 🔴 受管 sheet 是 **调整分录汇总H10-3**，不是 slice 声明的 `明细表H10-2` ——
    #    后者是 9 类固定行 × 12 月的月度矩阵，而前端按值 grep `1月|月度|monthly|各月`
    #    在全部 H10 组件/composable 下**零命中** ⇒ 结构性不匹配（见契约 H10-GAP-1）。
    #    故本条登记的键是 `H10-adjustment-rows`（`useH10Adjustment.ITEM_ID_ROWS`），
    #    **不是** `H10-detail-rows`。
    #
    # 🔴 `H10-adj-overlay` / `H10-adj-rows` 是 `syncWriteback` 的**派生聚合**，
    #    不进 items（进契约 `review.derived_total_keys`，roundtrip 排除）。
    #
    # 册 42,334 B / 9 sheets（全 H 最小）；含 IF 公式格 46 ⇒ 中性化必挂，函数共用不新造。
    "h10.asset_disposal_income_adjustment": StoreMergePlan(
        adapter_id="h10.asset_disposal_income_adjustment",
        provider_module="phase5_h10_asset_disposal_income",
        items=(StoreItemSpec(item_id="H10-adjustment-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── L1（spec: l-cycle-true-adapter-registration · Task 6）──────────────────
    #
    # L 循环首条真双向 entry。受管 sheet = `明细表L1-2`（数据源头），**不是**前序 spec
    # 选的 `审定表L1-1` —— 后者 R7~R11 无一个可输入格（B/C/D/F/G/H 全是 SUMIF 引用本表、
    # E/I/J/L 是加总、K 是裸 IF、R11 是 SUM），写它会毁掉整册取数联动，已在契约里
    # 登记为 `review.derived_readonly_sheet` 只读投影。
    #
    # 🔴 `items` 只登记本轮**真受管**的一条。L1 另有四张位置化表（`L1-int-*` /
    #    `L1-cred-*` / `L1-ovd-*` / `L1-plg-*`）本 spec 不动 —— `int` 被
    #    `h2L1LoanPull.ts` 跨循环消费，改它会连带 H2；预登记它们会让
    #    `check_sheet_specs_fully_registered` 的分母失真。
    #
    # 🔴 旧 store 形态 `L1-det-{rowIndex+1}-{field}` 是位置化行身份（`removeRow` 后
    #    `_triggerSaveAll` 重建整个序列 ⇒ 删中间行让后续行 item_id 全错位），
    #    `FORBIDDEN_ROW_IDENTITY_KINDS` 明含 `index`/`ordinal`/`position`/`array_index`
    #    ⇒ 换成 d6 式单条 item + 稳定 `rowId`。真库 `L1-det-*` 现算 0 行，零迁移负担。
    #
    # 🔴 GC-2：L1 册裸 IF **112 格**（审定表L1-1 34 / 附注上市 28 / 附注国企 20 /
    #    利息测算表L1-5 22 / 逾期贷款检查表L1-7 8），**受管表 `明细表L1-2` 零命中**。
    #    per-file 保守策略 ⇒ 受管表干净也必须挂：点同册任一 sheet 的在线编辑都会触发
    #    整册加载。中性化函数与 G7/G2/G9/G10/G8/G14/H9/H6/H4/H8/H10 **共用一个**
    #    （已被真 OO 栈验收过的口径），不新造；也不得在 `adapters/excel.py` 加
    #    `if adapter_id == "l1…"` 字面量分支（会打红 P9 框架层零 wp_code 分支判据）。
    "l1.short_term_loans": StoreMergePlan(
        adapter_id="l1.short_term_loans",
        provider_module="phase5_l1_short_term_loans",
        items=(StoreItemSpec(item_id="L1-2-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── J1（spec: j-cycle-sync-foundation-and-first-canary · 参照 D/H/L 真双向注册）──
    #
    # 受管 sheet = `计提情况检查表J1-6` 短期薪酬区（R17:R35，19 行），canary 键
    # `J1-6-short-term`（真库 3473 B，全 J 最大）。行身份字段是 **`id`**（不是 `rowId`）。
    #
    # 🔴 `items` 只登记本轮真受管的一条：同 Tab 兄弟键 `J1-6-post-employment`
    #    （structured_row_array）/ `J1-6-questions`（free_text_array）/
    #    `J1-6-conclusion`（free_text_scalar）**不预登记**；primary table
    #    `J1-2-detail-*` 三键真库全空，归后续批次。
    #
    # 🔴 GC-2：J1 册裸 IF **224 格**，**受管表零命中** ⇒ per-file 保守策略照挂，
    #    中性化函数与 G7/H9/L1 **共用一个**，不新造、不加 adapter_id 字面量分支。
    "j1.accrual_check_short_term": StoreMergePlan(
        adapter_id="j1.accrual_check_short_term",
        provider_module="phase5_j1_employee_compensation",
        items=(StoreItemSpec(item_id="J1-6-short-term", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── K1-9 单 dict item / 同 sheet 双区（专用 merge，保留未受管标量）──
    "k1.baddebt_reversal_writeoff_check": StoreMergePlan(
        adapter_id="k1.baddebt_reversal_writeoff_check",
        provider_module="phase5_k1_baddebt_reversal_writeoff",
        items=(),
        dedicated_items=(
            DedicatedStoreItem(
                item_id_const="STORE_ITEM_ID",
                merge_fn="merge_k1_from_projection",
                base_kind="dict",
                provider_module="phase5_k1_baddebt_reversal_writeoff",
            ),
        ),
    ),
    # ── K 循环调整分录汇总六条（per-file 中性化同 G7/H9/L1，共用一个函数）──
    "k8.selling_expenses_adjustment": StoreMergePlan(
        adapter_id="k8.selling_expenses_adjustment",
        provider_module="phase5_k8_selling_expenses",
        items=(StoreItemSpec(item_id="K8-3-adj-entries", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    "k9.admin_expenses_adjustment": StoreMergePlan(
        adapter_id="k9.admin_expenses_adjustment",
        provider_module="phase5_k9_admin_expenses",
        items=(StoreItemSpec(item_id="K9-3-adj-entries", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    "k10.other_income_adjustment": StoreMergePlan(
        adapter_id="k10.other_income_adjustment",
        provider_module="phase5_k10_other_income",
        items=(StoreItemSpec(item_id="K10-3-entries", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    "k11.asset_impairment_loss_adjustment": StoreMergePlan(
        adapter_id="k11.asset_impairment_loss_adjustment",
        provider_module="phase5_k11_asset_impairment_loss",
        items=(StoreItemSpec(item_id="K11-3-adj-entries", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    "k12.non_operating_income_adjustment": StoreMergePlan(
        adapter_id="k12.non_operating_income_adjustment",
        provider_module="phase5_k12_non_operating_income",
        items=(StoreItemSpec(item_id="K12-3-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    "k13.non_operating_expense_adjustment": StoreMergePlan(
        adapter_id="k13.non_operating_expense_adjustment",
        provider_module="phase5_k13_non_operating_expense",
        items=(StoreItemSpec(item_id="K13-3-adj-entries", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── L4（spec: l-cycle-true-adapter-registration · Task 12）──
    #
    # 受管 sheet = `划分为金融负债的其他金融工具明细表L4-3`，store = `L4-3-rows`
    # （行身份 `rowId`）。只登记这一条：L4-2/L4-5/L4-6 等 JSON 键属后续批次，不预登记。
    # 🔴 GC-2：受管表零裸 IF，但同册其他 sheet 有（现算见 test_l4_adapter_registration）
    #    ⇒ per-file 策略照挂，与 G7/H9/L1 共用同一个中性化函数。
    "l4.bonds_payable": StoreMergePlan(
        adapter_id="l4.bonds_payable",
        provider_module="phase5_l4_bonds_payable",
        items=(StoreItemSpec(item_id="L4-3-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── L3（task 12）：受管 L3-9；criteria/note/conclusion 不预登记 ──
    "l3.long_term_loans": StoreMergePlan(
        adapter_id="l3.long_term_loans",
        provider_module="phase5_l3_long_term_loans",
        items=(StoreItemSpec(item_id="L3-L3-9-voucher-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── L2（task 12 最后一条）：受管 L2-4 应付利息检查表（L3-9 孪生）；
    #    criteria/note/conclusion 不预登记 ──
    "l2.interest_payable": StoreMergePlan(
        adapter_id="l2.interest_payable",
        provider_module="phase5_l2_interest_payable",
        items=(StoreItemSpec(item_id="L2-L2-4-voucher-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── L7（spec l7-true-bidirectional）：受管 明细表L7-2（整册唯一数据录入源）；
    #    sibling L7-L7-2-rows / -row-N-end_balance 不预登记。受管表零裸 IF，整册裸 IF 仅
    #    审定表L7-1 6 格 ⇒ per-file 中性化照挂 ──
    "l7.other_noncurrent_liabilities": StoreMergePlan(
        adapter_id="l7.other_noncurrent_liabilities",
        provider_module="phase5_l7_other_noncurrent_liabilities",
        items=(StoreItemSpec(item_id="L7-L7-2-full-data", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
    # ── L6（spec l6-true-bidirectional）：受管 明细表L6-2（科目 2711，整册唯一数据录入源）；
    #    store 单键 `L6-L6-2-rows`（非 L7 的 -full-data）；sibling L6-L6-2-row-N-end_balance
    #    不预登记。受管表零裸 IF，整册裸 IF 仅 审定表L6-1 11 格 ⇒ per-file 中性化照挂 ──
    "l6.special_payables": StoreMergePlan(
        adapter_id="l6.special_payables",
        provider_module="phase5_l6_special_payables",
        items=(StoreItemSpec(item_id="L6-L6-2-rows", kind=StoreKind.rows),),
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas",
    ),
}


#: **显式登记**为「不做 store 镜像」的 adapter（回方向直接跳过，不抛错）。
#:
#: 🔴 为什么必须显式登记而不是「查不到就跳过」：原 `oo_to_html` 的 `else: return` 让
#:    「provider 声明了 store 却漏接回写层」与「该 adapter 本来就不镜像」在观测面上长得
#:    一模一样 —— 那正是 D4-35 恒空 / D4-13 写不进 OO 两个 bug 能活下来的原因。登记在此
#:    集合里的是后者；前者会在 `resolve_store_merge_plan` 显式打红。
#:
#: 🔴 **当前为空集** —— 曾经的唯一成员 `b60.hour_budget` 已于 2026-09-27 转为真
#:    store-backed（见 `STORE_MERGE_REGISTRY` 里那条的注释）。
#:
#:    历史脉络值得留着，因为它示范了一条容易走错的路：b60 最初被归进本集合，理由是
#:    「契约 `review` 段无 `html_store`、15 字段 `store_item_id` 全 None ⇒ 纯 Excel entry，
#:    HTML 宿主不读 checklist store」。那个观察**当时是准确的**，但它描述的其实是
#:    「前端还没有 HTML 面」这个时点事实，而不是 entry 的固有形态。
#:    `b60/GtB60HourBudgetPanel.vue` 一落地，同一句话就不再成立。
#:
#:    ⇒ 往本集合里加成员时，判据得是「该 entry 的 HTML 侧**结构上**不可能有 store 载体」，
#:      而不是「现在还没有载体」。后者会随前端交付而过期，并让「回写不通」伪装成设计。
#:
#:    空集是**合法状态**：`store_merge_plan_or_skip` 只是不会命中提前 return 分支，
#:    仍由 `looks_like_adapter_id` 兜住「传进来的其实是 entry_id」那一类。
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
