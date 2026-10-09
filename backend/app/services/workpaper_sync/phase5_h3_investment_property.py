"""H3 投资性房地产 —— Phase 5 entry 模块（H 循环第六条，**首条变体轴 entry**）。

spec: `h3-h5-h7-variant-axis-and-dynamic-column-paradigm`

═══ 与前五条最大的不同：一个 entry 两张受管主表 ═══

H9/H6/H4/H8/H2 各只有一张受管 sheet。H3 是 slice 登记的**变体轴**（另一条是 H7）：
同一 wp_code 下两套并列 sheet（成本模式 / 公允价值模式），源模板 sheet 名不同
（`明细表（成本模式）H3-2` vs `明细表（公允价值模式）H3-2`）但 sheet_code 尾码相同，
且两套**各有独立持久化键**（`H3-2-cost-rows` / `H3-2-fair-rows`）。

🔴 这与 E 循环的 `currency_variant` 形态相似但不同源：E1-3 是两张同尾码 sheet
**共用**一个键，H3 是两套 sheet **各有**键 ⇒ 不触发 `currency_variant_model` 的
`decoupling_rule`（无适用对象），而是各自一个 `RowTableSheetSpec` 并列进受管清单。

计量模式本身持久化在 `useH3MeasurementModel.ts`（不在本 entry 的受管面内）。

═══ 🔴 覆盖率远低于前五条，如实登记 ═══

| sheet | 有效列 | 映射 | template-only | 映射率 |
|---|---|---|---|---|
| 明细表（成本模式）H3-2 | 45 | 17 | 28 | 38% |
| 明细表（公允价值模式）H3-2 | 27 | 6 | 21 | 22% |

对照：H2 是 34/50（68%）、H8 是 58/58（100%）。**低不是漏做，是两侧口径正交**：
模板把调整按**作用位置**分段（期初调整 / 账项调整），前端按**调整来源**分档
（AJE / RJE）。两者不是命名差异而是维度差异，硬凑映射会产出**不可见错数**。
八条缺口逐条登记在两个 sheet 模块的 `DECLARED_COVERAGE_GAPS_*`，各带停下报告点。

公允价值模式更低的额外原因：前端 `fairValueBegin/End` 是**含累计公允变动的总额**
（`calcFairEndBalance` 把 change 加了进去），模板把「原值」与「公允价值变动」分成两块
（净值才是两者之和）⇒ 原值整块 C..O 无对端。

═══ 🔴 模板真实缺陷一处（走覆盖层，不改字节）═══

公允价值模式的 `R` 列（公允价值变动·未审·期末余额）**只有首行 R12 有 `=P12+Q12`，
R13-R26 共 14 行缺公式**；对照 H7 公允同位列 S 满格 25/25。详见
`phase5_h3_02_fair_detail.TEMPLATE_DEFECTS_H302_FAIR`。这是本循环第三例
（前两例 F2-26!J9 / F5-7!G31），处置沿用既有规则。

═══ 三处不能照抄前五条的地方 ═══

1. 🔴 **三级表头**（R9/R10/R11），H4/H8/H2 是四级 ⇒ `header_group_row` 不同。
2. 🔴 **两张 sheet 的数据区起始行不同**：成本 R13-R27 / 公允 R12-R26。
   照抄任一张会让另一张的 merge 越界（写进表头或吃掉 footer）。
3. 🔴 **footer 全是列 SUM**（无行内派生格）。H2 的 footer 有 4 格行内派生 ⇒
   那条「footer 非 SUM」判据在 H3 不适用，本 entry `footer_non_sum_cells` 为空。

═══ HD-7：H3 **有** TB 发布门（H 循环第二例，H6 是首例）═══

`H3TabAdjudicationCost.vue#L706 publishToTb` → POST
`/api/workpapers/{wpId}/audit-determination/publish-to-tb`，中文二次确认。
🔴 两处细节与 H6 不同：
  · 科目码**按项目动态解析**（`grossCode` / `accumDepCode`），不是写死常量，
    且带防污染守卫（无科目则跳过该行并提示，历史上误写过 1503/1504）；
  · 发布门只在**成本模式**审定 Tab 上；`H3TabAdjudicationFair.vue` 现算 0 处。
sync 路径对 `trial_balance` 写 **0** 次 —— 发布门是用户显式动作，不是回写副作用。

═══ HC-12 / 幻影码 ═══

册 146,096 B / 22 sheets ⇒ 中性化必挂（per-file，与 G7/G2/H9/H6/H4/H8/H2 共用同一
函数，不新造）。幻影码 `H3I` 三条 finder 路径实测全空 ⇒
`phantom_code_resolves_to_own_workbook=False`（程序表码是 `H3A`，不是 `H3I`）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h3_02_cost_detail as _h302c
from app.services.workpaper_sync import phase5_h3_02_fair_detail as _h302f
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

PHASE5_WAVE: Final[str] = "phase5_investment_property_detail"
ENTRY_ID: Final[str] = "xlsx/gt-h3-investment-property"
ADAPTER_ID: Final[str] = "h3.investment_property_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"H3I"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "H/H3 投资性房地产.xlsx"
#: 2026-10-01 安全净化后实测（122,537 B）：Equation.3 OLE 已转静态预览。
TEMPLATE_SHA256: Final[str] = (
    "ca856caebfc5b09b3ad9fbe3980ccf8e5c46260da9ba1a0ecd8acdb44498bc89"
)

#: 🔴 **两个** store item（变体轴）。`primary_store_item_id` 取成本模式那张 ——
#:    它是 22 sheets 里列数最多、映射面最大的一张，且计量模式默认成本模式。
STORE_ITEM_ID: Final[str] = _h302c.STORE_ITEM_ID_H302_COST
STORE_ITEM_ID_FAIR: Final[str] = _h302f.STORE_ITEM_ID_H302_FAIR
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = _h302c.ROW_IDENTITY_STORE_KEY_H302_COST

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "dual_write_remark_and_conclusion"

#: 🔴 HD-7：H3 **有** TB 发布门（H 循环第二例）。科目码按项目动态解析，非写死常量。
TB_PUBLISH_GATE: Final[str] = (
    "H3TabAdjudicationCost → publishToTb "
    "（POST /api/workpapers/{wpId}/audit-determination/publish-to-tb，"
    "科目码按项目动态解析 grossCode/accumDepCode 并带防污染守卫（无科目则跳过该行），"
    "中文二次确认；只在成本模式审定 Tab 上，公允模式现算 0 处；"
    "sync 路径对 trial_balance 写 0 次）"
)

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError

_EXTRA_REVIEW: Final[dict[str, Any]] = {
    "enum_fields": {},
    "derived_fields": [],
    "store_only_fields": sorted(
        set(_h302c.STORE_ONLY_FIELDS_H302_COST) | set(_h302f.STORE_ONLY_FIELDS_H302_FAIR)
    ),
    # 🔴 两张 sheet 的 template-only 列**按 sheet 分开登记**：两张的列位含义不同
    #    （公允模式 P..W 是「公允价值变动」，成本模式 P..AB 是「累计折旧/摊销」），
    #    合并成一个平表会让「AA 是什么」无从判断。
    "template_only_columns_by_sheet": {
        _h302c.MANAGED_SHEET_H302_COST: [
            {"column": col, "header_text": text}
            for col, text in _h302c.TEMPLATE_ONLY_COLUMNS_H302_COST
        ],
        _h302f.MANAGED_SHEET_H302_FAIR: [
            {"column": col, "header_text": text}
            for col, text in _h302f.TEMPLATE_ONLY_COLUMNS_H302_FAIR
        ],
    },
    "unmanaged_regions": [
        dict(r) | {"sheet": _h302c.MANAGED_SHEET_H302_COST}
        for r in _h302c.UNMANAGED_REGIONS_H302_COST
    ]
    + [
        dict(r) | {"sheet": _h302f.MANAGED_SHEET_H302_FAIR}
        for r in _h302f.UNMANAGED_REGIONS_H302_FAIR
    ],
    # 🔴 本 entry 的核心：**八条**声明缺口（前五条 entry 加起来只有一条）
    "declared_coverage_gaps": [
        dict(g) | {"sheet": _h302c.MANAGED_SHEET_H302_COST}
        for g in _h302c.DECLARED_COVERAGE_GAPS_H302_COST
    ]
    + [
        dict(g) | {"sheet": _h302f.MANAGED_SHEET_H302_FAIR}
        for g in _h302f.DECLARED_COVERAGE_GAPS_H302_FAIR
    ],
    "resolved_coverage_gaps": [],
    "legacy_folded_fields": {},
    # 🔴 模板真实缺陷（走覆盖层，不改 wp_templates 字节）
    "template_defects": [
        dict(d) | {"sheet": _h302f.MANAGED_SHEET_H302_FAIR}
        for d in _h302f.TEMPLATE_DEFECTS_H302_FAIR
    ],
    "derived_total_keys": sorted(
        set(_h302c.DERIVED_TOTAL_KEYS_H302_COST) | set(_h302f.DERIVED_TOTAL_KEYS_H302_FAIR)
    ),
    "sibling_tables_not_managed": [],
    # 🔴 变体轴：本 entry 的形态标识（H7 是另一条）
    "variant_axis": {
        "kind": "measurement_model",
        "switch_source": (
            "audit-platform/frontend/src/components/workpaper/composables/"
            "useH3MeasurementModel.ts"
        ),
        "variants": [
            {
                "variant": "cost",
                "template_sheet": _h302c.MANAGED_SHEET_H302_COST,
                "sheet_key": _h302c.SHEET_KEY_H302_COST,
                "store_item_id": _h302c.STORE_ITEM_ID_H302_COST,
                "owner_module": (
                    "audit-platform/frontend/src/components/workpaper/composables/"
                    "useH3DetailCost.ts"
                ),
                "effective_columns": _h302c.EFFECTIVE_COLUMNS_H302_COST,
                "mapped": len(_h302c.FIELD_SPECS_H302_COST),
            },
            {
                "variant": "fair_value",
                "template_sheet": _h302f.MANAGED_SHEET_H302_FAIR,
                "sheet_key": _h302f.SHEET_KEY_H302_FAIR,
                "store_item_id": _h302f.STORE_ITEM_ID_H302_FAIR,
                "owner_module": (
                    "audit-platform/frontend/src/components/workpaper/composables/"
                    "useH3DetailFair.ts"
                ),
                "effective_columns": _h302f.EFFECTIVE_COLUMNS_H302_FAIR,
                "mapped": len(_h302f.FIELD_SPECS_H302_FAIR),
                "frozen_key_note": (
                    "🔴 H3-2-fair-rows 在 HC-8 冻结键清册上（被 G 循环的 "
                    "g13SourceDetailPull.ts / gCycleSourceFv.ts 消费）⇒ 只补契约不动键名。"
                ),
            },
        ],
    },
    "carrier": {
        "write": "formdata_composable",
        "read": "formdata_composable",
        "tb_publish_gate": TB_PUBLISH_GATE,
    },
    # H3 两张 footer 全是列 SUM（H2 有 4 格行内派生 ⇒ 那条判据在此不适用）
    "footer_non_sum_cells": {},
    "effective_columns_by_sheet": {
        _h302c.MANAGED_SHEET_H302_COST: _h302c.EFFECTIVE_COLUMNS_H302_COST,
        _h302f.MANAGED_SHEET_H302_FAIR: _h302f.EFFECTIVE_COLUMNS_H302_FAIR,
    },
    "uuid_column_by_sheet": {
        _h302c.MANAGED_SHEET_H302_COST: _h302c.UUID_COL_H302_COST,
        _h302f.MANAGED_SHEET_H302_FAIR: _h302f.UUID_COL_H302_FAIR,
    },
    "column_coverage_closure": {
        _h302c.MANAGED_SHEET_H302_COST: {
            "mapped": len(_h302c.FIELD_SPECS_H302_COST),
            "template_only": len(_h302c.TEMPLATE_ONLY_COLUMNS_H302_COST),
            "effective_columns": _h302c.EFFECTIVE_COLUMNS_H302_COST,
        },
        _h302f.MANAGED_SHEET_H302_FAIR: {
            "mapped": len(_h302f.FIELD_SPECS_H302_FAIR),
            "template_only": len(_h302f.TEMPLATE_ONLY_COLUMNS_H302_FAIR),
            "effective_columns": _h302f.EFFECTIVE_COLUMNS_H302_FAIR,
        },
    },
    "row_identity_known_weaknesses": [
        {
            "weakness": "载入回填不稳定",
            "detail": (
                "`rowId` 缺失时 `_normalize` 每次载入生成新串"
                "（`dc-`/`df-` + Math.random），同一行两次载入身份不同。"
            ),
            "owner": "spec h3-h5-h7-variant-axis-and-dynamic-column-paradigm 后续任务",
        },
        {
            "weakness": "addRow 无随机后缀",
            "detail": "`dc-${Date.now()}` / `df-${Date.now()}` —— 同毫秒连加两行会撞 id。",
            "owner": "同上",
        },
    ],
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
    #: `H3I` 三条 finder 路径实测全空（程序表码是 `H3A`）
    phantom_code_resolves_to_own_workbook=False,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "H3 投资性房地产是 H 循环**首条变体轴 entry**：同一 wp_code 下两套并列明细表"
    "（成本模式 / 公允价值模式），源模板 sheet 名不同但 sheet_code 尾码相同，"
    "且两套**各有独立持久化键**（H3-2-cost-rows / H3-2-fair-rows）⇒ 两张都进受管面，"
    "各自一个 RowTableSheetSpec。计量模式本身持久化在 useH3MeasurementModel.ts。"
    "两张 sheet 的行数据都存成 checklist_responses 的 **remark** JSON 数组，"
    "按 stable field + 行身份 `rowId` 拆开。"
    "🔴 **覆盖率远低于前五条 entry，低不是漏做而是两侧口径正交**："
    "成本模式 17/45（38%）· 公允模式 6/27（22%），对照 H2 34/50、H8 58/58。"
    "模板把调整按**作用位置**分段（期初调整 / 账项调整本期增减 / 审定期初·增·减），"
    "前端按**调整来源**分档（costAje 审计调整 / costRje 重分类调整）且两档都作用在"
    "期末口径上（costAudited = costUnadj + costAje + costRje，costUnadj 默认取期末）。"
    "两套分类是正交维度，不存在 1:1 映射 —— 硬凑会产出**不可见错数**"
    "（映到期初调整会让审定本期发生额算错），宁可留**可见缺口**。"
    "两侧只在**期末**这一点上对齐：O↔costAudited / AB↔depAudited / AO↔impairAudited / "
    "AQ↔netAudited。"
    "🔴 公允模式更低的额外原因：前端 fairValueBegin/End 是**含累计公允变动的总额**"
    "（calcFairEndBalance 把 change 加了进去），而模板把「原值 C..O」与"
    "「公允价值变动 P..W」分成两块、净值才是两者之和（X=L+U / Y=O+W）⇒ 原值整块无对端；"
    "把总额映进原值列会让 X 把公允变动**重复计一次**。能对上的只有 Q↔fairValueChange、"
    "V↔fvChangeAudited（🔴 是 V 不是 W —— 前端 fvChangeUnadj 默认取本年变动，"
    "映到审定期末累计会差一个期初）、Y↔fairAudited、AA↔mortgaged。"
    "🔴 **八条缺口逐条登记**（见 review.declared_coverage_gaps），各带停下报告点："
    "四段↔四分正交 ×2、增减金额 1 格对 2 字段（transferIn/Out 是活字段不能像 H2-GAP-2 "
    "那样折叠）、增减方式两列对一个混装双向的 changeType ×2、"
    "「是否有权属证明」≠「是否权属受限」×2（权属核对另有 产权核对表H3-12）、"
    "公允总额口径不同源。"
    "🔴 **模板真实缺陷一处**（见 review.template_defects）：公允模式 `R` 列"
    "（公允价值变动·未审·期末余额）只有首行 R12 有 `=P12+Q12`，R13-R26 共 14 行缺公式；"
    "对照 H7 公允同位列 S 满格 25/25 ⇒ H3 独有漏填。后果是同一张表里审定段算得出期末、"
    "未审段算不出。走覆盖层不改模板字节（同 F2-26!J9 / F5-7!G31）。"
    "🔴 三处不能照抄前五条：**三级**表头 R9/R10/R11（H4/H8/H2 是四级）· "
    "两张 sheet 数据区起始行不同（成本 R13-R27 / 公允 R12-R26，照抄任一张会让另一张 "
    "merge 越界）· footer 全是列 SUM（H2 有 4 格行内派生 ⇒ 那条判据在此不适用）。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 H/H3 投资性房地产.xlsx（146,096 B / 22 sheets）的两张明细表："
    "① `明细表（成本模式）H3-2`（三级表头 R9/R10/R11 共 68 个合并域 / 数据 R13-R27 共 15 行 / "
    "footer R28 `合计` 全列 SUM 无行内派生 / 有效内容列 45 即 A..AS / 数据行公式列 17 个"
    "（映射侧 7 个进 FORMULA_TEMPLATES）/ 三区块四段：原值 C9(未审 C-H / 期初调整 I / "
    "账项调整 J-K / 审定 L-O)· 累计折旧摊销 P9(P-U / V / W-X / Y-AB)· 减值准备 AC9"
    "(AC-AH / AI / AJ-AK / AL-AO)· 尾部 AP 期初净值 AQ 期末净值 AR 是否有权属证明 "
    "AS 是否抵押受限 / footer 之下 R29-R33 `其中：`+四行 SUMPRODUCT 按类别小计"
    "（标签取 =底稿目录!A9..A12，**四行**不是 H4 的五行）); "
    "② `明细表（公允价值模式）H3-2`（三级表头 25 个合并域 / 数据 R12-R26 共 15 行"
    "**起始行比成本模式早一行** / footer R27 全列 SUM / 有效内容列 27 即 A..AA / "
    "数据行公式列 11 个（映射侧 2 个）/ 两区块：原值 C9 与成本模式逐列同构 · "
    "公允价值变动 P9(未审 P-R / 期初调整 S / 本期变动调整 T / 审定 U-W)· "
    "尾部 X 期初净值 Y 期末净值 Z 是否有权属证明 AA 是否抵押受限 / "
    "🔴 `R` 列仅首行有公式，R13-R26 共 14 行缺 —— 与 H7 公允同位列 S 满格 25/25 对照)"
    " + 前端按值 grep（useH3DetailCost.ts ITEM_ID='H3-2-cost-rows' / DetailCostRow 47 字段 / "
    "_normalize 的 costEnd=costBegin+costInc-costDec+transIn-transOut 定死 GAP-2 / "
    "useH3DetailFair.ts ITEM_ID='H3-2-fair-rows' / DetailFairRow 31 字段 / "
    "useH3FormulaEngine.calcFairEndBalance=begin+inc-dec+transfer+change 定死 H3F-GAP-1 / "
    "calcAuditedAmount=unadj+aje+rje 定死四分口径 / CHANGE_TYPE_OPTIONS 与 "
    "FAIR_CHANGE_TYPE_OPTIONS 混装双向定死 GAP-3)"
    " + 三条 finder 路径实测幻影码 `H3I` 全空（程序表码是 `H3A`）"
    " + 发布门现算（H3TabAdjudicationCost.vue#L706 publishToTb，科目码按项目动态解析"
    "并带防污染守卫；H3TabAdjudicationFair.vue 现算 0 处）"
    " + 覆盖闭合自检（成本 17+28==45 / 公允 6+21==27，两侧并集各自连续无缺口、无列重复）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本轮放**两张**（变体轴两半必须同批，否则切计量模式就掉桥）；册内其余 20 个 sheet：
#   底稿目录 / 投资性房地产实质性程序表H3A              → 不接
#   审定表（成本模式 / 公允价值模式）H3-1                → 归审定表后置族（各带 TB 发布门）
#   调整分录汇总H3-3                                    → FC-6 默认 `single_html`
#   会计政策会计估计检查表H3-4                          → 归后续批次
#   增减检查表（成本 / 公允）H3-5                        → 🔴 变体轴，归后续批次
#   互转审核表H3-6                                      → 归后续批次（transferIn/Out 的主表）
#   折旧测算表（成本模式不含减值 / 含减值）H3-7          → 🔴 变体轴，归后续批次
#   公允价值复核表H3-8                                  → 归后续批次（fairValueSource 的主表）
#   盘点检查表H3-9 / 减值测算表H3-10 /
#   可收回金额测试表H3-11                                → 归后续批次
#   产权核对表H3-12                                     → 🔴 GAP-4 的真数据源，归后续批次
#   关联交易检查表H3-13 / 租金收入测算表H3-14            → 归后续批次
#   附注披露信息（上市公司 / 国有企业）                  → 归附注披露族

_INCLUDE_H302_COST: Final[bool] = True
_INCLUDE_H302_FAIR: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_H302_COST:
        specs.append(_h302c.SPEC_H302_COST)
    if _INCLUDE_H302_FAIR:
        specs.append(_h302f.SPEC_H302_FAIR)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """H3-1 审定表（两张，各带 TB 发布门）—— 归后置批次，本 spec 恒 None。"""
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
            "audit-platform/frontend/src/components/workpaper/composables/"
            "useH3FormData.ts —— `_persist()` 走 api.put "
            "{ item_id: 'H3-2-cost-rows' | 'H3-2-fair-rows', remark: JSON.stringify(rows) }"
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
        f"store item {store_item_id!r} 不在 H3 受管清单里；"
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
    🔴 本 entry 有**两个** store item ⇒ 调用方**必须**显式传 `store_item_id`，
       否则默认落到成本模式那张；公允模式载荷若不传就会被按成本模式的 45 列投影。
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
    """matcher 域：幻影码 `H3I` + `document_type="xlsx"`（FC-3 在 H 成立）。"""
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
    """发布链编排：attach H3 adapter（实现委托公共骨架）。"""
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
