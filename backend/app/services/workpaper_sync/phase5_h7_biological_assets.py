"""H7 生产性生物资产 —— Phase 5 entry 模块（H 循环第八条，**第二条变体轴**）。

spec: `h3-h5-h7-variant-axis-and-dynamic-column-paradigm`

═══ 🔴 先说清楚它交了什么、没交什么 ═══

两张受管 sheet（变体轴，与 H3 同形）：

| sheet | 有效列 | 映射 | 映射率 |
|---|---|---|---|
| 明细表（成本模式）H7-2 | 51 | 5 | 10% |
| 明细表（公允价值模式）H7-2 | 28 | 3 | 11% |

**全 H 最低**。根因是前端行模型最小：成本模式 Tab 内联的 `DetailRow` **11 个**业务字段、
公允模式 `FairDetailRow` **9 个**，而模板分别有 51 / 28 列。

映射的那几格恰是**用户在该 Tab 里手敲的全部格**（类别 / 名称 / 期初原值 / 本期增加 /
本期减少；公允侧是 类别 / 名称 / 本年变动）。其余全判 template-only：OO 侧照旧可编辑、
Excel 照旧自己算，只是不回写 HTML。五条缺口逐条登记带停下报告点。

🔴 **不硬凑**（与 H2-GAP-1 / H3 八条 / H5 三条同族）：宁可留**可见缺口**，
不要**不可见错数**。本 entry 有两处「硬映会静默毁数据」的具体形态：
  · `accDep` / `impairment` 是单值期末余额，模板期末数是公式 ⇒ 映过去被 Excel 按恒空的
    Q..U / AF..AJ 重算成 0，回写把 **0 灌回**（静默清零）；
  · 公允侧 `fvBegin` 是含累计变动的总额，映进原值列会让 `Y=M+V` 把变动**重复计一次**。

═══ 五处不能照抄前七条的地方 ═══

1. 🔴 **载体是 `per_tab_self_persisting`**：store 键与行模型都**内联在 Tab 组件里**
   （`H7TabDetailCost.vue` / `H7TabDetailFair.vue`），不在 composable。
   `useH7DetailCost.ts` / `useH7DetailFair.ts` 各只 32 行、只导出 `getNum`/`getString`
   两个读取器 —— **不是载体**。按文件名推演会把判据指错文件。
2. 🔴 **同一 entry 内两张 sheet 的表头层数不同**：成本模式**四级**（R9-R12）、
   公允模式**三级**（R9-R11）。H3 两张都是三级 ⇒ 不能按 entry 统一写。
3. 🔴 **两张的数据区起始行不同**（成本 R13-R36 / 公允 R12-R36）。
4. 🔴 **两张的 `FORMULA_TEMPLATES` 都是空**（全 H 唯一）：19 / 11 个公式列一个都没进
   `field_specs`。判据若假设「每张受管表至少有一个公式列」会在此假红。
5. 🔴 **小计行在 rows 里**（`DetailRow.isSubtotal?`），与 H5 的 computed `subtotalRow`
   相反 ⇒ `isSubtotal` 判 store-only，且合计行由模板 footer 承担，不得当数据行写入。

═══ HD-7：H7 **有** TB 发布门（H 循环第四例，且**两个计量模式各一个**）═══

`H7TabAdjudicationCost.vue#L401/#L418` 与 `H7TabAdjudicationFair.vue#L273` 各有
`publishToTb` → POST `/api/workpapers/{wpId}/audit-determination/publish-to-tb`。
🔴 与 H3 相反：H3 只有成本模式那侧有发布门，H7 **两侧都有**。
sync 路径对 `trial_balance` 写 **0** 次 —— 发布门是用户显式动作，不是回写副作用。

═══ HC-12 / 幻影码 ═══

册 225,641 B / **26 sheets（全 H 第二多，仅次于 H2 的 21？—— 实测 H7 26 > H2 21，
H7 才是最多）** ⇒ 中性化必挂（per-file，与 G7/G2/H9/H6/H4/H8/H2/H3/H5 共用同一函数）。
幻影码 `H7B` 三条 finder 路径实测全空 ⇒
`phantom_code_resolves_to_own_workbook=False`（程序表码是 `H7A`，不是 `H7B`）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h7_02_cost_detail as _h702c
from app.services.workpaper_sync import phase5_h7_02_fair_detail as _h702f
from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import SyncContract, contract_path_for
from app.services.workpaper_sync.entry_profile import DescriptorFacts, RoomFacts
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_biological_assets_detail"
ENTRY_ID: Final[str] = "xlsx/gt-h7-biological-assets"
ADAPTER_ID: Final[str] = "h7.biological_assets_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"H7B"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "H/H7 生产性生物资产.xlsx"
#: 2026-10-01 安全净化后实测（194,163 B）：3 个 Equation.3 OLE 已转静态预览。
TEMPLATE_SHA256: Final[str] = (
    "109a0e4ba6d08da93fc727adac7473c4047f588253fd62c955db67804bf151ec"
)

STORE_ITEM_ID: Final[str] = _h702c.STORE_ITEM_ID_H702_COST
STORE_ITEM_ID_FAIR: Final[str] = _h702f.STORE_ITEM_ID_H702_FAIR
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = _h702c.ROW_IDENTITY_STORE_KEY_H702_COST

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "dual_write_remark_and_conclusion"

#: 🔴 HD-7：H7 **有** TB 发布门，且**两个计量模式各一个**（H3 只有成本侧）。
TB_PUBLISH_GATE: Final[str] = (
    "H7TabAdjudicationCost#L401/#L418 与 H7TabAdjudicationFair#L273 各有 publishToTb "
    "（POST /api/workpapers/{wpId}/audit-determination/publish-to-tb，中文二次确认）。"
    "🔴 两个计量模式**各有一个**发布门（与 H3 只有成本侧相反）；"
    "挂在 H7-1 审定表上，不是本 entry 的受管 sheet；sync 路径对 trial_balance 写 0 次。"
)

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError

_EXTRA_REVIEW: Final[dict[str, Any]] = {
    "enum_fields": {},
    "derived_fields": [],
    "store_only_fields": sorted(
        set(_h702c.STORE_ONLY_FIELDS_H702_COST) | set(_h702f.STORE_ONLY_FIELDS_H702_FAIR)
    ),
    # 🔴 按 sheet 分开登记：两张的列位含义不同（公允 Q..X 是「公允价值变动」，
    #    成本 Q..AE 是「累计折旧」），合并成平表会让「Q 是什么」无从判断。
    "template_only_columns_by_sheet": {
        _h702c.MANAGED_SHEET_H702_COST: [
            {"column": col, "header_text": text}
            for col, text in _h702c.TEMPLATE_ONLY_COLUMNS_H702_COST
        ],
        _h702f.MANAGED_SHEET_H702_FAIR: [
            {"column": col, "header_text": text}
            for col, text in _h702f.TEMPLATE_ONLY_COLUMNS_H702_FAIR
        ],
    },
    "unmanaged_regions": [
        dict(r) | {"sheet": _h702c.MANAGED_SHEET_H702_COST}
        for r in _h702c.UNMANAGED_REGIONS_H702_COST
    ]
    + [
        dict(r) | {"sheet": _h702f.MANAGED_SHEET_H702_FAIR}
        for r in _h702f.UNMANAGED_REGIONS_H702_FAIR
    ],
    "declared_coverage_gaps": [
        dict(g) | {"sheet": _h702c.MANAGED_SHEET_H702_COST}
        for g in _h702c.DECLARED_COVERAGE_GAPS_H702_COST
    ]
    + [
        dict(g) | {"sheet": _h702f.MANAGED_SHEET_H702_FAIR}
        for g in _h702f.DECLARED_COVERAGE_GAPS_H702_FAIR
    ],
    "resolved_coverage_gaps": [],
    "legacy_folded_fields": {},
    "derived_total_keys": sorted(
        set(_h702c.DERIVED_TOTAL_KEYS_H702_COST) | set(_h702f.DERIVED_TOTAL_KEYS_H702_FAIR)
    ),
    "sibling_tables_not_managed": [
        "H7-2-cost-note",
        "H7-2-cost-conclusion",
        "H7-2-fair-note",
        "H7-2-fair-conclusion",
    ],
    "variant_axis": {
        "kind": "measurement_model",
        "switch_source": (
            "audit-platform/frontend/src/components/workpaper/composables/"
            "useH7MeasurementModel.ts"
        ),
        "variants": [
            {
                "variant": "cost",
                "template_sheet": _h702c.MANAGED_SHEET_H702_COST,
                "sheet_key": _h702c.SHEET_KEY_H702_COST,
                "store_item_id": _h702c.STORE_ITEM_ID_H702_COST,
                "owner_module": (
                    "audit-platform/frontend/src/components/workpaper/h7/core/"
                    "H7TabDetailCost.vue"
                ),
                "effective_columns": _h702c.EFFECTIVE_COLUMNS_H702_COST,
                "mapped": len(_h702c.FIELD_SPECS_H702_COST),
                "header_levels": 4,
                "carrier_note": (
                    "🔴 store 键与行模型**内联在 Tab 组件里**（per_tab_self_persisting）。"
                    "`useH7DetailCost.ts` 只 32 行、只导出 getNum/getString，**不是载体**。"
                ),
            },
            {
                "variant": "fair_value",
                "template_sheet": _h702f.MANAGED_SHEET_H702_FAIR,
                "sheet_key": _h702f.SHEET_KEY_H702_FAIR,
                "store_item_id": _h702f.STORE_ITEM_ID_H702_FAIR,
                "owner_module": (
                    "audit-platform/frontend/src/components/workpaper/h7/core/"
                    "H7TabDetailFair.vue"
                ),
                "effective_columns": _h702f.EFFECTIVE_COLUMNS_H702_FAIR,
                "mapped": len(_h702f.FIELD_SPECS_H702_FAIR),
                "header_levels": 3,
                "carrier_note": "同成本模式：键与行模型内联在 Tab 里。",
            },
        ],
        "intra_entry_divergence": (
            "🔴 同一 entry 内两张 sheet 的**表头层数不同**（成本 4 级 R9-R12 / "
            "公允 3 级 R9-R11）、**数据区起始行不同**（R13 / R12）。H3 两张都是三级 ⇒ "
            "判据不能按 entry 统一写。"
        ),
    },
    "carrier": {
        "write": "per_tab_self_persisting",
        "read": "checklist_get",
        "tb_publish_gate": TB_PUBLISH_GATE,
    },
    "footer_non_sum_cells": {},
    "effective_columns_by_sheet": {
        _h702c.MANAGED_SHEET_H702_COST: _h702c.EFFECTIVE_COLUMNS_H702_COST,
        _h702f.MANAGED_SHEET_H702_FAIR: _h702f.EFFECTIVE_COLUMNS_H702_FAIR,
    },
    "uuid_column_by_sheet": {
        _h702c.MANAGED_SHEET_H702_COST: _h702c.UUID_COL_H702_COST,
        _h702f.MANAGED_SHEET_H702_FAIR: _h702f.UUID_COL_H702_FAIR,
    },
    "column_coverage_closure": {
        _h702c.MANAGED_SHEET_H702_COST: {
            "mapped": len(_h702c.FIELD_SPECS_H702_COST),
            "template_only": len(_h702c.TEMPLATE_ONLY_COLUMNS_H702_COST),
            "effective_columns": _h702c.EFFECTIVE_COLUMNS_H702_COST,
        },
        _h702f.MANAGED_SHEET_H702_FAIR: {
            "mapped": len(_h702f.FIELD_SPECS_H702_FAIR),
            "template_only": len(_h702f.TEMPLATE_ONLY_COLUMNS_H702_FAIR),
            "effective_columns": _h702f.EFFECTIVE_COLUMNS_H702_FAIR,
        },
    },
    # 🔴 全 H 唯一「两张受管表的公式模板都为空」的 entry —— 显式声明，
    #    免得判据假设「每张受管表至少有一个公式列」而在此假红。
    "formula_templates_are_intentionally_empty": {
        _h702c.MANAGED_SHEET_H702_COST: (
            "19 个数据行公式列一个都没进 field_specs：原值期末 I 与净值四列在前端是"
            "展示期 auto-calc 不落库；折旧/减值的期末数是公式且前端只有单值余额"
            "（映过去会被 Excel 按恒空的分项重算成 0，静默清零）。"
        ),
        _h702f.MANAGED_SHEET_H702_FAIR: (
            "11 个公式列同理：期末公允价值是 auto-calc 不落库，且其口径是含原值的总额"
            "而模板 S 只是累计变动那一块。"
        ),
    },
}

IDENTITY: Final[HC.HEntryIdentity] = HC.HEntryIdentity(
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    phase5_wave=PHASE5_WAVE,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    primary_store_item_id=STORE_ITEM_ID,
    expected_profile_id=EXPECTED_PROFILE_ID,
    #: `H7B` 三条 finder 路径实测全空（程序表码是 `H7A`）
    phantom_code_resolves_to_own_workbook=False,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "H7 生产性生物资产是 H 循环**第二条变体轴 entry**（H3 是第一条）：成本模式 / "
    "公允价值模式两张并列明细表，各有独立持久化键（H7-2-cost-rows / H7-2-fair-rows）"
    "⇒ 两张都进受管面，必须同批交付（只放一半，切计量模式就掉桥）。"
    "🔴 **载体是 `per_tab_self_persisting`**：store 键与行模型都**内联在 Tab 组件里**"
    "（H7TabDetailCost.vue#L257/#L275 与 H7TabDetailFair.vue#L230/#L248），不在 composable。"
    "`useH7DetailCost.ts` / `useH7DetailFair.ts` 各只 32 行、只导出 getNum/getString 两个"
    "读取器 —— **不是载体**，按文件名推演会把判据指错文件。"
    "🔴 **映射率全 H 最低**：成本 5/51（10%）· 公允 3/28（11%）。根因是前端行模型最小 ——"
    "成本 Tab 内联的 DetailRow **11 个**业务字段、公允 FairDetailRow **9 个**。"
    "映射的那几格恰是用户在该 Tab 里**手敲的全部格**（类别 / 名称 / 期初原值 / 本期增加 / "
    "本期减少；公允侧是 类别 / 名称 / 本年变动）。"
    "🔴 **两处硬映会静默毁数据**，故判 template-only："
    "①`accDep` / `impairment` 是**单值期末余额**（Tab 列标签是「累计折旧」「减值准备」，"
    "净值 = 期末原值 − 累计折旧 − 减值准备），而模板把每个备抵科目拆成 期初 / 本期增加"
    "（计提·其他）/ 本期减少（处置·其他）/ 期末数，**且期末数是公式**"
    "（V=SUM(Q:S)-SUM(T:U) / AK=SUM(AF:AH)-SUM(AI:AJ)）—— 映到期末数会被 Excel 按恒空的"
    "分项重算成 0，回写把 **0 灌回**（静默清零）；映到期初数是语义错位。"
    "②公允侧 `fvBegin` 是**含累计变动的公允总额**（Tab 标签「期初公允价值」），"
    "模板把「原值 D..P」与「公允价值变动 Q..X」分两块、净值才是两者之和（Y=M+V / Z=P+X）"
    "—— 映进原值列会让 Y 把公允变动**重复计一次**。"
    "🔴 **两张的 FORMULA_TEMPLATES 都是空**（全 H 唯一）：19 / 11 个公式列一个都没进 "
    "field_specs（见 review.formula_templates_are_intentionally_empty）。判据若假设"
    "「每张受管表至少有一个公式列」会在此假红。"
    "🔴 **同一 entry 内两张 sheet 形态不同**：表头层数 4 级（成本 R9-R12）vs 3 级"
    "（公允 R9-R11）、数据区起始行 R13 vs R12。H3 两张都是三级 ⇒ 判据不能按 entry 统一写。"
    "🔴 **小计行在 rows 里**（DetailRow.isSubtotal?），与 H5 的 computed subtotalRow 相反"
    "⇒ isSubtotal 判 store-only，合计行由模板 footer R37 承担，不得当数据行写入 R13-R36。"
    "五条缺口逐条登记在 review.declared_coverage_gaps，各带停下报告点。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 H/H7 生产性生物资产.xlsx（225,641 B / **26 sheets，全 H 最多**）"
    "的两张明细表："
    "①`明细表（成本模式）H7-2`（**四级**表头 R9/R10/R11/R12 共 68 合并域 / 数据 R13-R36 "
    "共 24 行 / footer R37 `合计` 全列 SUM / 有效列 51 即 A..AY / 数据行公式列 19 个"
    "**映射侧 0 个** / 三区块与 H5-2 逐列同构：原值 D9(未审 D-I 含增减方式 / 期初调整 J / "
    "账项调整 K-L / 审定 M-P)· 累计折旧 Q9(未审 Q-V，本期增减各再分两小列 / 期初调整 W / "
    "账项调整 X-AA / 审定 AB-AE)· 减值准备 AF9(同构 AF-AT)· 净值四列 AU/AV/AW/AX · "
    "尾部**只有一个**布尔列 AY 是否提足折旧（H5 有四个）/ footer 之下 R38-R43 `其中：`+"
    "五行 SUMPRODUCT，标签取 =底稿目录!A9..A13（H5 是字面量 ⇒ 判据不共用）); "
    "②`明细表（公允价值模式）H7-2`（**三级**表头 R9/R10/R11 共 28 合并域 / 数据 R12-R36 "
    "共 25 行**起始行比成本模式早一行** / footer R37 全列 SUM / 有效列 28 即 A..AB / "
    "公式列 11 个映射侧 0 个 / 两区块：原值 D9 · 公允价值变动 Q9(未审 Q-S / 期初调整 T / "
    "本期变动调整 U / 审定 V-X)· 尾部 Y 期初净值 Z 期末净值 AA 是否有权属证明 AB 是否抵押受限)"
    " + 前端按值 grep（H7TabDetailCost.vue 内联 DetailRow **11 字段** + 键 "
    "'H7-2-cost-rows' / H7TabDetailFair.vue 内联 FairDetailRow **9 字段** + 键 "
    "'H7-2-fair-rows' / 两个 Tab 的 el-table-column label 逐字读出计价段口径"
    "（期末原值 auto-calc / 累计折旧 / 减值准备 / 净值 auto-calc；"
    "期初公允价值 / 本期增加 / 本期减少 / 公允价值变动损益 / 期末公允价值 auto-calc）/ "
    "useH7DetailCost.ts 与 useH7DetailFair.ts 各 32 行只有 getNum/getString **不是载体**)"
    " + 三条 finder 路径实测幻影码 `H7B` 全空（程序表码是 `H7A`）"
    " + 发布门现算（H7TabAdjudicationCost#L401/#L418 与 H7TabAdjudicationFair#L273，"
    "**两个计量模式各一个**，与 H3 只有成本侧相反）"
    " + 覆盖闭合自检（成本 5+46==51 / 公允 3+25==28，两侧并集各自连续无缺口、无列重复）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本轮放**两张**（变体轴两半必须同批）；册内其余 24 个 sheet 的处置：
#   底稿目录 / 生物资产实质性程序表H7A               → 不接
#   审定表（成本 / 公允）H7-1                        → 归审定表后置族（**两侧各带发布门**）
#   调整分录汇总H7-3                                 → FC-6 默认 `single_html`
#   会计政策估计检查表H7-4 / 分析表H7-5              → 归后续批次
#   增加检查表（成本 / 公允）H7-6                     → 🔴 变体轴，归后续批次
#   减少检查表（成本 / 公允）H7-7                     → 🔴 变体轴，归后续批次
#   监盘计划H7-8 / 盘点检查表H7-9 / 监盘小结H7-10     → 归后续批次
#   折旧测算表（不含减值直线法 / 含减值）H7-11         → 🔴 变体轴，归后续批次
#   折旧分配分析表H7-12                              → 归后续批次
#   公允价值复核表H7-13                              → 归后续批次（fvLevel 的真数据源）
#   互转审核表H7-14                                  → 归后续批次
#   减值测算表H7-15 / 可收回金额测试表H7-16           → 归后续批次（减值块的真数据源）
#   关联交易检查表H7-17                              → 归后续批次
#   附注披露信息（上市公司 / 国有企业）                → 归附注披露族

_INCLUDE_H702_COST: Final[bool] = True
_INCLUDE_H702_FAIR: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_H702_COST:
        specs.append(_h702c.SPEC_H702_COST)
    if _INCLUDE_H702_FAIR:
        specs.append(_h702f.SPEC_H702_FAIR)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """H7-1 审定表（两张，两侧各带 TB 发布门）—— 归后置批次，本 spec 恒 None。"""
    return None


def all_managed_sheet_names() -> tuple[str, ...]:
    return tuple(s.managed_sheet for s in managed_row_table_specs())


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    return HC.instrumentation_specs_for(IDENTITY, managed_row_table_specs())


def template_definition_payload() -> dict[str, Any]:
    return HC.template_definition_payload(IDENTITY, managed_row_table_specs())


def instrumentation_definition_payload() -> dict[str, Any]:
    return HC.instrumentation_definition_payload(IDENTITY, managed_row_table_specs())


def excel_carrier_gate():
    return HC.excel_carrier_gate()


def authoritative_template_path() -> Path:
    return HC.authoritative_template_path(IDENTITY)


def read_authoritative_template() -> bytes:
    return HC.read_authoritative_template(IDENTITY)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件
# ═══════════════════════════════════════════════════════════════════════════

TemplateResolutionFacts = HC.TemplateResolutionFacts


def assert_no_implicit_template_fallback(
    resolution: HC.TemplateResolutionFacts, *, wp_codes: frozenset[str] | None = None
) -> None:
    """口径见 `phase5_h_cycle_common.assert_phantom_code_does_not_leak`。"""
    del wp_codes
    HC.assert_phantom_code_does_not_leak(IDENTITY, resolution)


def assert_entry_selectable(
    *,
    resolution: HC.TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    return HC.assert_entry_selectable(IDENTITY, resolution=resolution, manifest=manifest)


# ═══════════════════════════════════════════════════════════════════════════
# 4. 契约装配
# ═══════════════════════════════════════════════════════════════════════════


def build_contract_payload() -> dict[str, Any]:
    return HC.build_contract_payload(
        IDENTITY,
        managed_row_table_specs(),
        html_store_note=_HTML_STORE_NOTE,
        reviewed_basis=_REVIEWED_BASIS,
        payload_column=PAYLOAD_COLUMN,
        payload_column_mode=PAYLOAD_COLUMN_MODE,
        payload_column_source=(
            "audit-platform/frontend/src/components/workpaper/h7/core/"
            "H7TabDetailCost.vue#L275 与 H7TabDetailFair.vue#L248 —— "
            "`persist('H7-2-cost-rows' | 'H7-2-fair-rows', rows.value)`"
            "（🔴 键与行模型内联在 Tab 里，不在 composable）"
        ),
    )


def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    from app.services.workpaper_sync.contracts import load_contract

    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    return HC.assert_contract_file_matches_source(IDENTITY, build_contract_payload())


# ═══════════════════════════════════════════════════════════════════════════
# 5. store 投影 / 合并（**薄转发**框架层）
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> Any:
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise HC.HEntrySelectionError(
        f"store item {store_item_id!r} 不在 H7 受管清单里；"
        f"已受管：{sorted(all_store_item_ids())}"
    )


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    """HTML store 载荷 → `Projection`。

    🔴 签名形态刚性：`payload` 第一个位置参、`store_item_id` 走关键字。
    🔴 本 entry 有**两个** store item（变体轴）⇒ 调用方**必须**显式传 `store_item_id`；
       两张的列数（51 / 28）与数据区起始行（R13 / R12）都不同，默认落到成本模式会错位。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _engine,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine(spec, payload, contract=contract, limits=limits)


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
    store_item_id: str | None = None,
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_merge(spec, projection=projection, base_rows=base_rows)


def iter_store_rows(payload: Any, *, store_item_id: str | None = None):
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        iter_store_rows as _engine_iter,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_iter(spec, payload)


# ═══════════════════════════════════════════════════════════════════════════
# 6. manifest capability / adapter 注册 / attach
# ═══════════════════════════════════════════════════════════════════════════


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    return HC.manifest_capability_enabled(IDENTITY, manifest=manifest)


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    HC.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)


def build_matcher() -> EntryMatcher:
    """matcher 域：幻影码 `H7B` + `document_type="xlsx"`（FC-3 在 H 成立）。"""
    return HC.build_matcher(IDENTITY)


def build_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return HC.build_registration(
        IDENTITY,
        adapter=adapter,
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        contract=contract,
    )


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return HC.register_adapter(
        registry,
        IDENTITY,
        adapter=adapter,
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        contract=contract,
    )


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    return await HC.resolve_published_frozen_definitions(
        IDENTITY, session=session, representation=representation, contract=contract
    )


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach H7 adapter（实现委托公共骨架）。"""
    return await HC.attach_h_entry_adapter(
        registry,
        IDENTITY,
        session=session,
        contract_payload_builder=build_contract_payload,
    )


# ═══════════════════════════════════════════════════════════════════════════
# provisioning 白名单接口（approved bundle 发布侧）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 这两个名字是**硬前置**，不是装饰：
# `fix_task76_provision_projection_definitions.py` 经
# `projection_provisioning.load_projection_supply()` **只认** `publish_pilot_definitions`
# 与 `PILOT_WP_CODES`，缺任一即抛 `ProviderModuleNotAllowedError: provider 是空壳`，
# 且该脚本连 `--check`（只读）都 fail closed 在第一个缺口上 ⇒ 缺这两行，本 entry 永远
# 拿不到 approved bundle，`register_from_manifest()` 也就永远注册不上。
#
# 实现在 `phase5_h_cycle_common.publish_definitions_for`（九条共用一份，逐行对照
# `phase5_entry_orchestration.publish_definitions`）。`specs` 必须与
# `build_contract_payload` 同源 —— 两者都用 `managed_row_table_specs()`。


async def publish_pilot_definitions(publisher: Any) -> HC.HDefinitions:
    """发布本 entry 的四段 definition + approved bundle。"""
    return await HC.publish_definitions_for(
        IDENTITY,
        managed_row_table_specs(),
        publisher=publisher,
        contract_payload_builder=build_contract_payload,
    )


PILOT_WP_CODES = WP_CODES
