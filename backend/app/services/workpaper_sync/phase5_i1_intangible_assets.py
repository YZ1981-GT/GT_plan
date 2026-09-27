# -*- coding: utf-8 -*-
"""I1 无形资产 —— Phase 5 entry 模块（I 循环第六条，lane 1 两条之一）。

spec: `i1-i3-disclosure-positional-identity-and-classification-source` · Task 14 / 17

═══ 🔴 I1 的四个「全 I 最」 ═══

| 维度 | I1 | 对照 |
|---|---|---|
| 有效列 | 🔴 **47**（A..AU） | I3 30 · I4 22 · I2 20 · I5 17 · I6 26 |
| merged | 🔴 **72** | I3 47 · I4 27 · I2 21 · I5 8 · I6 2 |
| 裸 IF | 🔴 **321** | I4 186 · I2 113 · I3 63 · I5 49 · I6 45 |
| `derived_total_keys` | 🔴 **8**（全 I 最多） | I2 2 · I6 3 · I3/I4/I5 各 0 |
| 数据区行数 | 🔴 **6 行（最少）** | I4 12 · I2 10 · I6 10 · I3 9 · I5 11×3 |

═══ 🔴 三大滚动区口径各不相同（抄错会算错两区）═══

三区**结构同构**（各 13 列），但公式口径**逐区不同**：

| 区 | 未审期末 | 审定本期增加 | 审定本期减少 |
|---|---|---|---|
| 原值 C-O | `H=SUM(C:D)-F` | `M=D+J`（**两项**） | `N=F+K`（**两项**） |
| 累计摊销 P-AB | `U=SUM(P:Q)-S` | `Z=Q+W+R`（**三项**） | `AA=S+X+T`（**三项**） |
| 减值准备 AC-AO | 🔴 `AH=SUM(AC:AE)-SUM(AF:AG)` | `AM=AD+AJ+AE` | `AN=AF+AK+AG` |

🔴 **减值区的未审期末是两个 SUM 相减**，与前两区的 `SUM(x:y)-z` 形态**不同** ——
抄前两区会漏掉「其他减少 AG」。
🔴 **摊销/减值区的审定本期增减是三项相加**（含「其他增加 R/AE」与「其他减少 T/AG」），
原值区是两项 —— 三区用同一套模板会算错两区。

另有净值区 **AP-AS 四列全公式**（`AP=C-P-AC` / `AQ=L-Y-AL` / `AR=H-U-AH` / `AS=O-AB-AO`）。

═══ 双区：R12-17 业务区（6 行）+ R19-30 派生区（11 行）═══

第 2 区 `R19「其中：」+ R20-30`：A 列逐格 `=底稿目录!A9`..`A19`，
C/D/F/H/I/J/K 等列是 **ArrayFormula / SUMPRODUCT**
（`=SUMPRODUCT(($B$12:$B$17=$A20)*(F$12:F$17))`）按 **B 列类别**回汇总第 1 区。

🔴 **R29 例外是字面 `数据资源`**（其余 10 行都是 `=底稿目录!Ax`）⇒
改 `底稿目录!A18` **不传播**到 R29。这是**源模板内部的真源断链**（另 2 处：
`附注披露信息（上市公司）!K10` 与 `明细表I2-2!A17` 同型）⇒ 登记不修，不改模板字节。

═══ 🔴 footer R18 是全 I 唯一单一形态 ═══

`C18..AS18` **41 格全部纯 SUM**（`=SUM(x12:x17)`）⇒ 本表可以安全用 `pure_sum` 口径。
🔴 但**该口径不得复用到 I2/I3**（I2 有 1 格 `R23=P23-Q23` 例外、I3 有 5 格套用行公式 +
4 格引错区间）。

═══ CD-1：分类 MATCH 但 impl 边曾是**双定义**（ID-2 本轮新发现，已收敛）═══

`I1_DEFAULT_CATEGORIES` 曾在两处独立定义（`i1CategoryScope.ts#L19` 的
`I1CategorySlot[]` 与 `useI1Adjudication.ts#L105` 的纯串数组），两边 11 条 label
**有序完全一致**但是**两个独立真源**。平台在 `i1ListedDisclosureModel.ts#L41` 收敛过一次
却**漏掉了 useI1Adjudication.ts**。

✅ **已收敛**：`useI1Adjudication.ts#L105` 改为 `I1_DEFAULT_CATEGORIES.map(c => c.label)` 派生；
零回归 **16 tests passed**。

🔴 CD-1 判据仍 SHALL **同时比对两处导出**（收敛后第二处不再有独立字面量，
判据须断言这一点），变异「只改 `i1CategoryScope.ts` 的第 8 条 `软件`」SHALL 打红。

═══ BP-7：`I1_SOE_CATEGORIES` 与两个真源都不符（登记不修）═══

impl **12 条** vs 源 `附注披露信息（国有企业）!A9:A19` **11 格**，**五项差异**：
条数 12↔11 · `软件` 位次 1↔8 · `房屋使用权`↔`住房使用权` ·
`特许权`/`采矿权`↔`特许经营权`/`矿产权` · 多出 `探矿权`。

🔴 第二真源 `note_template_soe.json` 里 `采矿权`/`探矿权`/`房屋使用权` 命中 **0**
⇒ **两个真源都不支持 impl 的写法**。修法归**业务确认**（国企附注该用哪套分类名是
会计披露口径问题），且改常量会同时改附注列头（涉已归档的附注同步 spec）⇒ 登记不修。

═══ BP-6：位置化行身份 1 处在 I1（本 sheet 外）═══

全 I 8 处位置化 site 里 **I1 占 1 处**：`i1DisclosureEnhance.ts#L241`
`tc-i18-${r.rowId || i}`（族 B 下标兜底，在**披露增强层**）。
本 sheet（`明细表I1-2`）的行身份是 `useI1Detail.ts` 的 `rowId`（族 A 安全生成）⇒
本契约 `positional_identity_sites` 为空，🔴 但那 1 处的修复归 lane 1 的 Task 5。

🔴 **删行属下标族**（`useI1Detail.ts#L623 removeRow(rowIndex: number)`）⇒
lane 1 两条 entry **100% 下标族**，与 lane 2 的 1:2 跨两族不同 ⇒ 判据不得复用。

═══ sheet 命名四陷阱本册命中三条（IC-11）═══

* 🔴 **`审定表I1` 不带 `-1`**（其余 5 册是 `审定表I{n}-1`）⇒ 按 `审定表I{n}-1` 模式定位失配
* 🔴 **括号后缀**：`摊销测算表（不含减值）I1-10（剩余年限法）`（**两个括号**）⇒ 禁 strip
* 🔴 **附注披露名多「信息」二字**：`附注披露信息（上市公司）`/`（国有企业）`
  （其余 5 册是 `附注披露（…）`）⇒ 统一模式匹配在 I1 上失配

🔴 `prefill_formula_mapping.json` 的 16 条 I mapping **已正确用 sheet 全名**（含 `审定表I1`
与两张括号后缀 sheet）⇒ 契约照此口径，不另造。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync import phase5_i1_02_detail as _i102
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

PHASE5_WAVE: Final[str] = "phase5_intangible_assets_detail"
ENTRY_ID: Final[str] = "xlsx/gt-i1-intangible-assets"
ADAPTER_ID: Final[str] = "i1.intangible_assets_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"I1I"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "I/I1 无形资产、累计摊销及减值准备.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "97eced1f58ab392551d2dca25db7267ca0ea0a120381b0126f8391e2b2977b63"
)

STORE_ITEM_ID: Final[str] = _i102.STORE_ITEM_ID_I102
EMPTY_STORE_PAYLOAD: Final[str] = _i102.EMPTY_PAYLOAD_I102
ROW_IDENTITY_STORE_KEY: Final[str] = _i102.ROW_IDENTITY_STORE_KEY_I102

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "remark_only"

TB_PUBLISH_GATE: Final[str] = (
    "composables/useI1Adjudication.ts#L659 + i1/core/I1TabAdjudication.vue#L1119"
)

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError


_EXTRA_REVIEW: Final[dict[str, Any]] = {
    # 🔴 双区：第 2 区派生不受管
    "regions": [
        {"idx": 0, "rows": [12, 17], "kind": "editable", "row_count": 6},
        {
            "idx": 1,
            "rows": list(_i102.DERIVED_REGION_I102["rows"]),
            "kind": "derived",
            "marker_row": _i102.DERIVED_REGION_I102["marker_row"],
            "label_source": _i102.DERIVED_REGION_I102["label_source"],
            "editable_labels": False,
            "row_count": 11,
        },
    ],
    "derived_region_facts": dict(_i102.DERIVED_REGION_I102),
    # 🔴 footer 全 I 唯一单一形态
    "footer_shape_facts": dict(_i102.FOOTER_SHAPE_FACTS_I102),
    # CD-1 + BP-7
    "classification": dict(_i102.CLASSIFICATION_FACTS_I102),
    "soe_classification": dict(_i102.SOE_CLASSIFICATION_FACTS_I102),
    # 载体
    "carrier": {
        "write": "host_inline",
        "write_client": "http",
        "read": "host_inline_render_config_refetch",
        "force_component_type": "i1-intangible-assets",
        "tb_publish_gate": TB_PUBLISH_GATE,
        "gate_layer": "composable",
        "mounts": 2,
        "host_checklist_get_hits": 0,
    },
    "oo_flags": {
        "legacyOO": 4,
        "http_import": 1,
        "isOoAvailable": 2,
        "structured_only_switch": 1,
        "el_segmented_total": 3,
    },
    "oo_flags_note": (
        "🔴 `el_segmented` 共 **3** 个 —— 其中 `#L171` 是 **Tab 内部分段控件**不是模式切换器 ⇒ "
        "IC-16 门控判据 SHALL **按 toolbar class `i1-header-toolbar` 定位区块**再判，"
        "全文件 grep `el-segmented` 会误判成有第二个模式切换器。"
    ),
    # 🔴 删行属下标族
    "row_delete_api": {
        "kind": "index",
        "signature": "removeRow(rowIndex: number)",
        "site": "composables/useI1Detail.ts#L623",
        "note": (
            "🔴 **lane 1 两条 entry 100% 下标族**（I1 + I3），而 lane 2 是 1:2 跨两族"
            "（I2 index / I4+I5 identity）⇒ 两 lane **不得复用同一签名断言**。"
            "🔴 **lane 1 是唯一「下标族删行 × 位置化行身份」双重叠** ⇒ 有一条组合判据"
            "「删中间一行后剩余行 rowId 集合不变」。"
        ),
    },
    # BP-6：本 sheet 外 1 处
    "positional_identity_sites": [],
    "positional_identity_note": (
        "🔴 全 I 8 处位置化 site 里 **I1 占 1 处**：`i1DisclosureEnhance.ts#L241` "
        "`tc-i18-${r.rowId || i}`（族 B 下标兜底，在**披露增强层**）。"
        "本 sheet 的行身份是 `useI1Detail.ts` 的 rowId（族 A 安全生成）⇒ 本契约 sites 为空，"
        "但那 1 处的修复归 lane 1 的 Task 5。"
    ),
    # IC-11：本册命中三条命名陷阱
    "sheet_name_traps": [
        "🔴 `审定表I1` **不带 -1**（其余 5 册是 `审定表I{n}-1`）⇒ 按 `审定表I{n}-1` 模式定位失配",
        "🔴 `摊销测算表（不含减值）I1-10（剩余年限法）` **两个括号后缀** ⇒ 禁 strip",
        "🔴 `附注披露信息（上市公司）` / `附注披露信息（国有企业）` **多「信息」二字**"
        "（其余 5 册是 `附注披露（…）`）⇒ 统一模式匹配在 I1 上失配",
    ],
    "sheet_name_precedent": (
        "🔴 `prefill_formula_mapping.json` 的 16 条 I mapping **已正确用 sheet 全名**"
        "（含 `审定表I1` 与两张括号后缀 sheet）⇒ 契约照此口径，不另造。"
    ),
    # 源模板真源断链（本册 2 处中的 1 处在本 sheet）
    "template_source_break": [
        "🔴 `明细表I1-2!A29` 是**字面** `数据资源`（其余 10 行都是 =底稿目录!Ax）⇒ "
        "改 `底稿目录!A18` 不传播（**本 sheet 内**，登记不修）",
        "`附注披露信息（上市公司）!K10` 同型（本册另一 sheet，归附注披露族）",
    ],
    "store_only_fields": [
        "acquisitionDate",
        "usefulLifeMonths",
        "salvageRate",
        "amortizationMethod",
        "indefiniteLife",
        "notReadyForUse",
        "amortTransferOut",
        "impairmentReversal",
        "netBegin",
        "netValue",
        "auditedNetBegin",
        "auditedNetEnd",
    ],
    "store_only_note": (
        "12 个 store-only 字段分两类：①**摊销政策族**（acquisitionDate / usefulLifeMonths / "
        "salvageRate / amortizationMethod / indefiniteLife / notReadyForUse）在本 sheet 无对应列 —— "
        "它们属 `使用寿命检查表I1-7` / `摊销测算表（不含减值）I1-10（剩余年限法）` / "
        "`摊销测算表（含减值）I1-11` 三张后置 sheet ②**兼容/派生字段**（amortTransferOut = "
        "amortDisposal + amortOtherDecrease · impairmentReversal 处置结转 · netBegin/netValue/"
        "auditedNetBegin/auditedNetEnd 对应 AP-AS 四个**全公式列**）⇒ 前端按公式重算，不映射格。"
    ),
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _i102.TEMPLATE_ONLY_FORMULA_COLUMNS_I102
    ],
    "template_cell_lock_facts": dict(_i102.TEMPLATE_CELL_LOCK_FACTS_I102),
    "variant_axis": None,
    "effective_columns": _i102.EFFECTIVE_COLUMNS_I102,
    "max_column": _i102.MAX_COLUMN_I102,
    "uuid_column": _i102.UUID_COL_I102,
    "uuid_column_note": (
        "有效 47 + 1 = AV。🔴 **不得放 57** —— `max_column` 是 56，有效与 max 之间 9 列全空，"
        "放 57 会让 OO 打开后列宽错位。"
    ),
    # 🔴 IC-18：全 I 最多
    "derived_total_keys": [
        "I1-10-period-amort-total",
        "I1-11-period-amort-total",
        "I1-12-supplement-total",
        "I1-5-period-total",
        "I1-9-alloc-totals",
        "I1-adj-amort-increase-total",
        "I1-adj-cost-increase-total",
        "I1-adjudication-cost-addition-total",
    ],
    "derived_total_keys_note": (
        "🔴 现算 **8 个（全 I 最多**；I2 2 / I6 3 / I3/I4/I5 各 0）。"
        "🔴 注意 `I1-9-alloc-totals` 是**复数** —— 正则只写 `-total$` 会漏它。"
        "禁写死阈值。"
    ),
    "defined_name_baseline": 0,
    "defined_name_baseline_note": (
        "本册 **0**。但判据仍须用「基线不增长」口径 —— 同一套判据到 lane 2 的 "
        "I4(476)/I5(334) 会直接假红。"
    ),
    "formula_paradigm_warning": (
        "🔴 **三大滚动区口径各不相同，用同一套模板会算错两区**："
        "原值区审定增减是**两项**（M=D+J / N=F+K）；摊销/减值区是**三项**"
        "（Z=Q+W+R / AA=S+X+T / AM=AD+AJ+AE / AN=AF+AK+AG，含「其他增加/减少」）；"
        "🔴 减值区未审期末是**两个 SUM 相减**（AH=SUM(AC:AE)-SUM(AF:AG)）而非 SUM(x:y)-z。"
    ),
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
    phantom_code_resolves_to_own_workbook=False,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "I1 无形资产的结构化 Tab 行数据存成 checklist_responses 的 **remark** JSON 数组。"
    "本契约按 stable field + 行身份 `rowId` 拆开。"
    "🔴 **全 I 最宽（47 有效列）**：三大滚动区各 13 列（原值 C-O / 累计摊销 P-AB / "
    "减值准备 AC-AO）+ 净值区 AP-AS（**四列全公式**）+ 合规区 AT/AU（文本）。"
    "🔴 **28 个受管字段 / 19 个公式列**；公式列在 `I1DetailRow` 里虽有同名字段"
    "（costEnd / auditedCostBegin / … / auditedNetEnd）但都是前端按同一套公式重算的派生值 ⇒ "
    "只进 formula_columns 不进 field_specs。"
    "🔴 **三区公式口径各不相同**：原值区审定增减**两项**、摊销/减值区**三项**（含其他增减）、"
    "减值区未审期末是**两个 SUM 相减** —— 三区用同一套模板会算错两区。"
    "12 个 store-only 字段分摊销政策族（属 I1-7/I1-10/I1-11 三张后置 sheet）与"
    "兼容/派生字段（对应 AP-AS 全公式列）两类。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 I/I1 无形资产、累计摊销及减值准备.xlsx 的 `明细表I1-2`"
    "（🔴 **四级**表头 R8/R9/R10/R11 ⇒ header_rows=**4**（与 I3 同为平台上界）/ "
    "数据 R12-17 **仅 6 行（全 I 最少）**，A 列模板预填的是**占位符** A/B/C/D/… 不是业务名 / "
    "footer R18 🔴 **C18..AS18 四十一格全部纯 SUM**（全 I **唯一单一形态** footer；"
    "I2 有 1 格例外、I3 有 5 格套用行公式 + 4 格引错区间）/ "
    "🔴 **第 2 区 R19「其中：」+ R20-30 十一行是派生区**（A 列逐格 =底稿目录!A9..A19，"
    "🔴 **R29 例外是字面 `数据资源`** ⇒ 改 A18 不传播；C/D/F/H/I/J/K 等列是 "
    "**ArrayFormula / SUMPRODUCT** `=SUMPRODUCT(($B$12:$B$17=$A20)*(F$12:F$17))` 按 B 列类别"
    "回汇总第 1 区）⇒ 标 derived + editable_labels=false / "
    "**19 个公式列** H·L·M·N·O（原值）· U·Y·Z·AA·AB（摊销）· AH·AL·AM·AN·AO（减值）· "
    "AP·AQ·AR·AS（净值）—— 🔴 **三区口径各不相同**：原值区审定增减**两项**（M=D+J / N=F+K）、"
    "摊销/减值区**三项**（Z=Q+W+R / AA=S+X+T / AM=AD+AJ+AE / AN=AF+AK+AG）、"
    "🔴 减值区未审期末是**两个 SUM 相减**（AH=SUM(AC:AE)-SUM(AF:AG)）而非 SUM(x:y)-z / "
    "有效内容列 **47 即 A..AU（全 I 最宽）** / max_column 56（差 9 列）⇒ UUID 放 AV 不放 57 / "
    "179 公式 / **merged 72（全 I 最多）** / definedName 0 / **裸 IF 321（全 I 最多）** / "
    "无 Excel Table / ws.protection.sheet=False ⇒ locked 全惰性）"
    " + 前端 `useI1Detail.ts` 按值 grep（ITEM_ID_ROWS='I1-2-rows' / 身份 rowId 族 A / "
    "🔴 removeRow(rowIndex: number) 属**下标族** / I1DetailRow 的 28 受管字段 + 12 store-only）"
    " + 🔴 **CD-1 impl 边曾是双定义**（`i1CategoryScope.ts#L19` 的 I1CategorySlot[] 与 "
    "`useI1Adjudication.ts#L105` 的纯串数组，两边 11 条 label 有序完全一致但是两个独立真源；"
    "平台在 `i1ListedDisclosureModel.ts#L41` 收敛过一次却漏掉后者）⇒ ✅ **已收敛**为 "
    "`I1_DEFAULT_CATEGORIES.map(c => c.label)` 派生，零回归 16 tests passed"
    " + 🔴 **BP-7 五项差异**（impl I1_SOE_CATEGORIES **12 条** vs 源 "
    "`附注披露信息（国有企业）!A9:A19` **11 格**：条数 12↔11 · `软件` 位次 1↔8 · "
    "`房屋使用权`↔`住房使用权` · `特许权`/`采矿权`↔`特许经营权`/`矿产权` · 多出 `探矿权`；"
    "第二真源 note_template_soe.json 里 `采矿权`/`探矿权`/`房屋使用权` 命中 **0** ⇒ "
    "两个真源都不支持 impl 的写法）⇒ 修法归业务确认，登记不修"
    " + 真库现算（checklist_responses.item_id='I1-2-rows' **无行** ⇒ roundtrip 只能合成载荷）"
)

#: 本批：明细表I1-2（册内其余 17 个 sheet 归后置/附注/排除）
_INCLUDE_I102: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_I102:
        specs.append(_i102.SPEC_I102)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """🔴 `审定表I1`（**不带 -1**）—— 归后置批次，本 spec 恒 None。"""
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


TemplateResolutionFacts = HC.TemplateResolutionFacts


def assert_no_implicit_template_fallback(
    resolution: HC.TemplateResolutionFacts, *, wp_codes: frozenset[str] | None = None
) -> None:
    del wp_codes
    HC.assert_phantom_code_does_not_leak(IDENTITY, resolution)


def assert_entry_selectable(
    *,
    resolution: HC.TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    return HC.assert_entry_selectable(IDENTITY, resolution=resolution, manifest=manifest)


def build_contract_payload() -> dict[str, Any]:
    return HC.build_contract_payload(
        IDENTITY,
        managed_row_table_specs(),
        html_store_note=_HTML_STORE_NOTE,
        reviewed_basis=_REVIEWED_BASIS,
        payload_column=PAYLOAD_COLUMN,
        payload_column_mode=PAYLOAD_COLUMN_MODE,
        payload_column_source=(
            "audit-platform/frontend/src/components/workpaper/composables/useI1Detail.ts"
            " —— `_persist()` 经宿主 onSave 写 "
            "{ item_id: 'I1-2-rows', remark: JSON.stringify(rows) }"
        ),
    )


def contract_file_path() -> Path:
    from app.services.workpaper_sync.contracts import contract_path_for

    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    from app.services.workpaper_sync.contracts import load_contract

    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    return HC.assert_contract_file_matches_source(IDENTITY, build_contract_payload())


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    return HC.manifest_capability_enabled(IDENTITY, manifest=manifest)


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    HC.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)


def build_matcher() -> EntryMatcher:
    return HC.build_matcher(IDENTITY)


def build_registration(
    *, manifest: Mapping[str, Any] | None = None
) -> AdapterRegistration:
    return HC.build_registration(IDENTITY, manifest=manifest)


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    *,
    manifest: Mapping[str, Any] | None = None,
) -> AdapterRegistration:
    return HC.register_adapter(IDENTITY, registry, manifest=manifest)


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach 本 entry 的 adapter（照 H 循环 9 条同构，实现委托公共骨架）。

    🔴 符号名必须是 `attach_pilot_adapters` —— `adapters/registry.py` 的 `_attach_of()`
    按这个**固定名字**从白名单模块里取（不是按 `register_adapter`），
    `test_registrar_delegates_to_each_entry_own_attach` 逐 provider 核它存在。

    🔴 第③环（published representation）缺供给时公共骨架**返回空元组**而不是伪造通过 ——
    BP-1~BP-3 是平台级欠账，如实登记为 `upstream_gap`。
    """
    return await HC.attach_h_entry_adapter(
        registry,
        IDENTITY,
        session=session,
        contract_payload_builder=build_contract_payload,
    )


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    """读已发布的冻结身份（照 H 循环 9 条同构，实现委托公共骨架）。

    🔴 **薄委托**：函数体只有一条 `return await HC.<同名>(...)`。
    `test_task75_published_identity_observer` 的 `implementing_node()` 据此把四条判据
    转移到骨架那层执行（真 await 共享观测器 / 真做 contract digest 比对 / raise 在条件
    分支里 / 不返回 None）。这里**多写一条语句**就会被判为「provider 自有实现」，
    转而按严格判据核本函数 —— 那是故意的：借薄委托外壳偷塞逻辑必须打红。

    🔴 **不得**在本函数里抄 loader 九步（`ExcelEntryDefinitionLoader` /
    `assert_no_structure_drift` / `parse_identity_inventory` / `structure_fingerprint`）
    —— 抄一遍就是第二真源，任一侧被短路都不改变行为。
    """
    return await HC.resolve_published_frozen_definitions(
        IDENTITY, session=session, representation=representation, contract=contract
    )
