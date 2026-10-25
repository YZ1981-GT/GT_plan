# -*- coding: utf-8 -*-
"""I3 商誉 —— Phase 5 entry 模块（I 循环第五条接入，lane 1 的两条之一）。

spec: `i1-i3-disclosure-positional-identity-and-classification-source` · Task 13 / 15 / 17

═══ 🔴 I3 的三个「全 I 唯一/最」 ═══

| 维度 | I3 | 其余 5 条 |
|---|---|---|
| mount 数 | 🔴 **4** | 全部 2 |
| `legacyOO` | 🔴 **6**（全 I 最多） | 各 4~5 |
| 表头层级 | 🔴 **四级 R10-R13**（平台 header_rows 上界） | 三级/两级/单级 |
| 位置化 site | 🔴 **7 处**（全 I 8 处里占 7） | I1 1 处 · 其余 4 条 0 |

**mount=4 的含义**：`force_component_type` 判据 SHALL 覆盖**全部 4 个挂载点**；
变异「只验 1 个」SHALL 打红 —— 这是「分母为空的重言式」的**反面**：分母是 4 却只验 1，
同样是假绿。

**四级表头**：平台的 `header_rows` 上界在 H9 那轮从 3 扩到 **4**（结清 Task 42 登记的
`pilot_h1_grouped_dynamic.UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE` 欠账），
本表正好用到上界。

═══ 🔴 两处模板真实缺陷，两种不同处置（详见 sheet spec docstring）═══

**缺陷①（IC-14 / ID-3）`AA23:AD23` 四格引错区间 ⇒ `overlay_fixed`**

实际 `=SUM(AA27:AA30)` / 应为 `=SUM(AA14:AA22)`。根因：R27-29 是**编制说明文本行**、
R30 **超出 max_row(29)** ⇒ 区间完全落在数据区外 ⇒ 🔴 **减值准备区审定数四列合计恒 0**。
同行左侧 `S23..Z23` 全部正确 ⇒ 四格错法一致 = **复制粘贴错误**。

走**模板覆盖层**（FC-5 的第 **5** 个例外）。`backend/wp_templates/` 字节不动。
🔴 判据载荷必须是「**只有减值准备区有数**」——「全区都有数」会假绿、「全区都是 0」会恒真。

**缺陷②（本轮新发现）`I14` 缺公式 ⇒ `registered_not_fixed`**

`I15`..`I18` 逐行都有 `=SUM(Dx:Ex)-Gx`，唯**数据区首行 `I14` 是 `None`**。
处置与缺陷① **不同**（不开第二个覆盖层例外）：前端 `costEnding` 本就按同一套公式重算并落库
⇒ merge 时该格由 `formula_columns` 重新写入，**不影响回写正确性**；但须登记，
否则后来者会以为「I 列公式逐行齐全」。

═══ 🔴 BP-6：位置化行身份 7 处全在 I3，但都在披露/减值层不在本 sheet ═══

全 I 8 处位置化 site 里 **I3 占 7**，全在 `useI3Disclosure.ts`（族 A′ 1 + 族 B 3 + 族 D 2）
与 `i3/impairment/I3TabRecoverableTest.vue`（族 B 1）—— **披露层 / 减值测试层**。

本 sheet（`明细表I3-2`）的行身份是 `useI3Detail.ts` 的 `rowId`（`row-${Date.now()}-${random}`
族 A 安全生成）⇒ 本契约 `positional_identity_sites` 为空，
🔴 但**不得**据此推断「I3 无位置化问题」——那 7 处的修复归 lane 1 的 Task 3~9。

🔴 **本 lane 是唯一「下标族删行 × 位置化行身份」双重叠**：
`useI3Detail.ts#L580 removeRow(rowIndex: number)` 属**下标族**，而披露层的行身份又曾是位置化的
⇒ lane 1 有一条组合判据「删中间一行后剩余行 rowId 集合不变」，两个单独判据都抓不到。

═══ 排除 sheet：三张（含全角连字符陷阱）═══

* `参考－商誉减值测试示例`（🔴 **全角连字符 `－`** U+FF0D，**非 hidden**，104 行 / 114 公式）
  —— 是**示例数据不是项目数据**，同步会把示例数字当审定数
* `市场平均收益率2017`（hidden，167 行）—— **固定年份的基准表**，不随项目变
* `GT_Custom`（hidden）—— 平台自用隐藏页

🔴 变异「用半角连字符 `参考-商誉减值测试示例` 匹配」SHALL 找不到而打红。

═══ CD-7：分类 clean ═══

I3 **无 impl 分类常量** ⇒ `SOURCE_ITSELF_DERIVES_FROM_DETAIL` / clean。

═══ IC-9：I3 册裸 IF **63 格** ⇒ per-file 挂 ═══

I1 321 / I4 186 / I2 113 / **I3 63** / I5 49 / I6 45，总 777。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync import phase5_i3_02_detail as _i302
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_goodwill_detail"
ENTRY_ID: Final[str] = "xlsx/gt-i3-goodwill"
ADAPTER_ID: Final[str] = "i3.goodwill_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"I3G"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "I/I3 商誉.xlsx"
#: 🔴 2026-10-01 净化（`sanitize_i_cycle_template_external_links.py`，过 OOXML 门）后现算；
#: 净化前 `96cd6d6cb70698ce90087269aa3f5c3f70a7d80955bd2985904099c3d9257366`（slice 冻结值，append-only 保留；`.preclean.bak` 即其字节）。
TEMPLATE_SHA256: Final[str] = (
    "99512b340ccb79bf884d9f3362010f302bd8aaf45be0f3b082c99899f5253085"
)

STORE_ITEM_ID: Final[str] = _i302.STORE_ITEM_ID_I302
EMPTY_STORE_PAYLOAD: Final[str] = _i302.EMPTY_PAYLOAD_I302
ROW_IDENTITY_STORE_KEY: Final[str] = _i302.ROW_IDENTITY_STORE_KEY_I302

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "remark_only"

TB_PUBLISH_GATE: Final[str] = (
    "composables/useI3Adjudication.ts#L402 + i3/core/I3TabAdjudication.vue#L708"
)

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError


_EXTRA_REVIEW: Final[dict[str, Any]] = {
    # 🔴 两处模板真实缺陷（两种处置，不得混写）
    "known_template_quirks": [
        dict(_i302.TEMPLATE_DEFECT_AA23_I302),
        dict(_i302.TEMPLATE_DEFECT_I14_I302),
    ],
    "known_template_quirks_note": (
        "🔴 **两处缺陷两种处置**：①`AA23:AD23` 四格引错区间 ⇒ `overlay_fixed`"
        "（FC-5 第 **5** 个例外；减值准备区审定数四列合计恒 0，是真金额错误）"
        "②`I14` 缺公式 ⇒ `registered_not_fixed`（首行漏公式；前端 costEnding 本就重算并落库，"
        "merge 时由 formula_columns 重新写入 ⇒ 不影响回写正确性，但须登记）。"
        "**不得混写** —— 把②也标 overlay_fixed 会开一个不必要的覆盖层例外。"
    ),
    # 🔴 footer 三形态混行
    "footer_shape_facts": dict(_i302.FOOTER_SHAPE_FACTS_I302),
    "footer_kind": "row_formula_applied",
    "footer_convention_split": True,
    "footer_kind_note": (
        "🔴 照 I1/I2 的 `pure_sum` 口径去验本表 R23 会因「不是 SUM 开头」而**假红** —— "
        "同一 footer 行混了三种形态（14 格纯 SUM + 5 格套用行公式 + 4 格引错区间）。"
    ),
    # 🔴 mount=4 全 I 唯一
    "carrier": {
        "write": "host_inline",
        "write_client": "http",
        "read": "host_inline_render_config_refetch",
        "force_component_type": "i3-goodwill",
        "tb_publish_gate": TB_PUBLISH_GATE,
        "gate_layer": "composable",
        "mounts": 4,
        "host_checklist_get_hits": 0,
    },
    "mounts_note": (
        "🔴 **4 个挂载点（全 I 唯一 ≠2）**⇒ `force_component_type` 判据 SHALL 覆盖**全部 4 个**；"
        "变异「只验 1 个」SHALL 打红 —— 这是「分母为空的重言式」的**反面**：分母是 4 却只验 1，"
        "同样是假绿。"
    ),
    "oo_flags": {
        "legacyOO": 6,
        "http_import": 1,
        "isOoAvailable": 2,
        "structured_only_switch": 1,
    },
    "oo_flags_note": (
        "`legacyOO`=**6** 是全 I 最多（对应 mount=4）。断言注册 adapter 后 legacyOO 分支"
        "**不再被走到**，但**不删代码**（删它会牵动 OO 不可用时的降级路径）。"
    ),
    # 🔴 BP-6：7 处位置化全在披露/减值层，不在本 sheet
    "positional_identity_sites": [],
    "positional_identity_note": (
        "🔴 全 I 8 处位置化 site 里 **I3 占 7**，但全在 `useI3Disclosure.ts`"
        "（族 A′ #L488 `cgu-${i}` 1 + 族 B #L441/#L463/#L503 3 + 族 D #L665/#L725 2）与 "
        "`i3/impairment/I3TabRecoverableTest.vue#L686`（族 B 1）—— **披露层 / 减值测试层**。"
        "本 sheet（明细表I3-2）的行身份是 `useI3Detail.ts` 的 rowId"
        "（`row-${Date.now()}-${random}` 族 A 安全生成）⇒ 本契约 sites 为空，"
        "🔴 但**不得**据此推断「I3 无位置化问题」—— 那 7 处的修复归 lane 1 的 Task 3~9。"
    ),
    # ✅ 2026-10-01 lane 1 Task 4~7 已修：7 处改为「上游 rowId 优先 → 按业务值复用旧 id → 新生成」，
    #    守卫 `test_i_cycle_registered_defects_fixed.py` + vitest `i3DisclosureRowIdentity.spec.ts`。
    "positional_identity_fix_status": "fixed_out_of_sheet",
    "legacy_positional_ids_grandfathered": True,
    "legacy_positional_id_pattern": r"^(cgu|bv|imp|perf|ap|tc-i18)-\d+$",
    "positional_identity_persist_chain": (
        "useI3Disclosure pullFromDetailRows → _persistSection('cgu_allocation') → "
        "options.onSave(`${prefix}-cgu_allocation-rows`) → GtI3Goodwill.vue http.put；"
        "键 I3-disc-{listed|soe}-cgu_allocation-rows（修复未改键名）"
    ),
    # 🔴 删行属下标族 + 双重叠
    "row_delete_api": {
        "kind": "index",
        "signature": "removeRow(rowIndex: number)",
        "site": "composables/useI3Detail.ts#L580",
        "note": (
            "🔴 **lane 1 两条 entry 100% 下标族**（I1 `removeRow(rowIndex)` / I3 同），"
            "而 lane 2 是 1:2 跨两族（I2 index / I4+I5 identity）⇒ 两 lane **不得复用同一签名断言**。"
            "🔴 **本 lane 是唯一「下标族删行 × 位置化行身份」双重叠** ⇒ lane 1 有一条组合判据"
            "「删中间一行后剩余行 rowId 集合不变」，两个单独判据都抓不到。"
        ),
    },
    # CD-7
    "classification": dict(_i302.CLASSIFICATION_FACTS_I302),
    # 🔴 排除 sheet 三张（含全角连字符陷阱）
    "excluded_sheets": [
        "参考－商誉减值测试示例",
        "市场平均收益率2017",
        "GT_Custom",
    ],
    "excluded_sheets_reasons": {
        "参考－商誉减值测试示例": (
            "🔴 **全角连字符 `－`**（U+FF0D）· **非 hidden** · 104 行 / 114 公式 —— "
            "是**示例数据不是项目数据**，同步会把示例数字当审定数。"
            "🔴 变异「用半角连字符 `参考-商誉减值测试示例` 匹配」SHALL 找不到而打红。"
        ),
        "市场平均收益率2017": "hidden，167 行 —— **固定年份的基准表**，不随项目变",
        "GT_Custom": "hidden —— 平台自用隐藏页",
    },
    # 数据区全空的两列
    "empty_data_columns": [
        {"column": col, "reason": reason}
        for col, reason in _i302.EMPTY_DATA_COLUMNS_I302
    ],
    "store_only_fields": [],
    "store_only_note": (
        "`I3DetailRow` 的 Section 2（入账测算 mergerCost / netAssetFairValue / "
        "entryGoodwillCalc / minorityInterest / …）与 Section 3（基础信息 acquisitionDate / "
        "shareholding / cguName / recoverableAmount / …）**模板本表无对应列** —— 它们属 "
        "`入账价值测算表I3-4` / `商誉减值测试I3-6` / `可收回金额测试I3-7` 三张后置 sheet，"
        "**不进本 sheet 契约**（Requirement 6.1 禁止无来源自造字段）。"
    ),
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _i302.TEMPLATE_ONLY_FORMULA_COLUMNS_I302
    ],
    "template_cell_lock_facts": dict(_i302.TEMPLATE_CELL_LOCK_FACTS_I302),
    "variant_axis": None,
    "effective_columns": _i302.EFFECTIVE_COLUMNS_I302,
    "max_column": _i302.MAX_COLUMN_I302,
    "uuid_column": _i302.UUID_COL_I302,
    "uuid_column_note": (
        "有效 30 + 1 = AE。🔴 本表 `max_column` **也是 30** ⇒ 两者相等、无空列间隙"
        "（与 I2 的 20/61 差 41 列、I6 的 26/65 差 39 列形成对照）。"
    ),
    # IC-18：现算 0（已裁非漏扫）
    "derived_total_keys": [],
    "derived_total_keys_note": (
        "现算 **0** 个。IC-18 已裁 I3/I4/I5 皆 0 **不是漏扫**（I1 8 / I2 2 / I6 3）"
        "⇒ 按 IC-20 空分母纪律断言「现算 0」但不宣称该维度通过。"
    ),
    "defined_name_baseline": 0,
    "defined_name_baseline_note": (
        "本册 **0**。🔴 但判据仍须用「基线不增长」口径而非「断言全 0」—— "
        "同一套判据到 lane 2 的 I4(476)/I5(334) 会直接假红。"
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
    "I3 商誉的结构化 Tab 行数据存成 checklist_responses 的 **remark** JSON 数组。"
    "本契约按 stable field + 行身份 `rowId` 拆开。"
    "🔴 **左右两表同一行**：左表 A..P 是商誉原值滚动、右表 Q..AD 是减值准备滚动，"
    "`Q` 列是**镜像** `=A{r}`（右表的被投资单位名称镜像左表）⇒ 进 formula_columns 且"
    "**不映射 store 字段**（同 I5 区② A 列口径）。"
    "🔴 12 个受管字段；11 个公式列（I/M/N/O/P/Q/W/AA/AB/AC/AD）是前端按同一套公式重算的"
    "派生值或镜像 ⇒ 只进 formula_columns 不进 field_specs。"
    "🔴 `AB`/`AC` 的口径是**三项相加**（本期增加 = S+Y+T / 本期减少 = U+Z+V），"
    "抄成两项（S+Y / U+Z）会漏掉「其他增加 T」与「其他减少 V」。"
    "🔴 **B/C 两列在数据区全空**（B 是间隔列；C11='发生日期' 只是表头）⇒ 两列都不进 field_specs。"
    "`I3DetailRow` 的 Section 2/3（入账测算 + 基础信息共 30+ 字段）属 I3-4/I3-6/I3-7 三张"
    "后置 sheet，**不进本契约**。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 I/I3 商誉.xlsx 的 `明细表I3-2`"
    "（🔴 **四级**表头 R10/R11/R12/R13 ⇒ header_rows=**4**（平台上界，H9 那轮从 3 扩来，"
    "结清 Task 42 的 UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE 欠账）/ "
    "数据 R14-22 九行 / footer R23 🔴 **三形态混行**（14 格纯 SUM E·G·J·K·L·R..Z + "
    "**5 格套用行公式** I23=SUM(D23:E23)-G23 · M23=D23+J23 · N23=E23+K23 · O23=G23+L23 · "
    "P23=M23+N23-O23 + **4 格引错区间** AA23:AD23）/ "
    "公式列 11 个 I·M·N·O·P·Q·W·AA·AB·AC·AD（Q 是镜像 =A{r}；AB/AC 是**三项相加**口径）/ "
    "🔴 **B/C 两列数据区全空** / 有效内容列 30 == max_column 30（无空列间隙）⇒ UUID 放 AE / "
    "133 公式 / merged 47 / definedName 0 / 裸 IF 63 / 无 Excel Table / "
    "ws.protection.sheet=False ⇒ locked 全惰性）"
    " + 🔴 **两处模板真实缺陷逐格实证**：①`AA23:AD23` 四格 =SUM(<列>27:<列>30) 应为 "
    "=SUM(<列>14:<列>22)（R27-29 是编制说明文本行 B27='编制说明：'、R30 超 max_row(29)）⇒ "
    "减值准备区审定数四列合计恒 0，同行左侧 S23..Z23 全部正确 ⇒ 复制粘贴错误 ⇒ **overlay_fixed** "
    "②**本轮新发现** `I14` 是 None 而 I15..I18 逐行都有 =SUM(Dx:Ex)-Gx ⇒ 数据区首行漏公式 ⇒ "
    "**registered_not_fixed**（前端 costEnding 本就重算落库，merge 时由 formula_columns 重写）"
    " + 前端 `useI3Detail.ts` 按值 grep（ITEM_ID_ROWS='I3-2-rows' / 身份 rowId 族 A 安全生成 / "
    "🔴 removeRow(rowIndex: number) 属**下标族** / I3DetailRow 的核心 12 字段 + Section 2/3 "
    "的 30+ 字段属后置 sheet）"
    " + 宿主 `GtI3Goodwill.vue` 按值 grep（🔴 **mount=4 全 I 唯一**、legacyOO=6 全 I 最多、"
    "checklist GET=0）"
    " + 真库现算（checklist_responses.item_id='I3-2-rows' **无行** ⇒ roundtrip 只能合成载荷）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本批只放 I3-2 一张；册内其余 14 个 sheet 的处置：
#   底稿目录 / 商誉实质性程序 I3A              → 不接
#   审定表I3-1                                → 归后置（审定表族）
#   调整分录汇总I3-3                          → FC-6 默认 `single_html`
#   入账价值测算表I3-4 / 针对性检查表I3-5      → 归后续批次（Section 2 字段的归属）
#   商誉减值测试I3-6 / 可收回金额测试I3-7      → 归后续批次（Section 3 字段的归属）
#   复核公司减值测试过程及结论I3-8             → 归后续批次
#   附注披露（上市公司 / 国有企业）             → 归附注披露族（🔴 BP-6 的 7 处位置化在这里）
#   🔴 参考－商誉减值测试示例（**全角连字符**，非 hidden）→ **excluded**（示例数据非项目数据）
#   🔴 市场平均收益率2017（hidden, 167 行）    → **excluded**（固定年份基准表）
#   GT_Custom（hidden）                       → 🔴 **不纳管**

#: 本批：明细表I3-2
_INCLUDE_I302: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_I302:
        specs.append(_i302.SPEC_I302)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """I3-1 审定表 —— 归后置批次，本 spec 恒 None。"""
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
            "audit-platform/frontend/src/components/workpaper/composables/useI3Detail.ts"
            " —— `_persist()` 经宿主 onSave 写 "
            "{ item_id: 'I3-2-rows', remark: JSON.stringify(rows) }"
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


# ═══════════════════════════════════════════════════════════════════════════
# 5. manifest capability
# ═══════════════════════════════════════════════════════════════════════════


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    return HC.manifest_capability_enabled(IDENTITY, manifest=manifest)


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    HC.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)


# ═══════════════════════════════════════════════════════════════════════════
# 6. adapter 注册
# ═══════════════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════════════
# ── 五环发布面（委托 HC，2026-10-01）
#
# 🔴 硬前置：`projection_provisioning.load_projection_supply()` 只认
#    `publish_pilot_definitions` + `PILOT_WP_CODES`；`projection_first_publication`
#    另要 `instrumentation_spec()`（单数 = 主表）与 `build_store_projection`。
#    实现全在 `phase5_h_cycle_common`，这里只写薄委托（与 J1 / L1 同形，不复制逻辑）。
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec() -> ExcelInstrumentationSpec:
    return HC.primary_instrumentation_spec(IDENTITY, managed_row_table_specs())


def build_store_projection(
    payload: Any,
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    """🔴 `payload` 必须是首位位置参数（golden digest 门按此调用）。"""
    return HC.build_store_projection_for(
        IDENTITY,
        managed_row_table_specs(),
        payload,
        contract=contract,
        limits=limits,
        store_item_id=store_item_id,
    )


def merge_projection_into_store_rows(
    *, projection: Any, base_rows: list, store_item_id: str | None = None
) -> Any:
    return HC.merge_projection_into_store_rows_for(
        IDENTITY,
        managed_row_table_specs(),
        projection=projection,
        base_rows=base_rows,
        store_item_id=store_item_id,
    )


def iter_store_rows(payload: Any, *, store_item_id: str | None = None) -> Any:
    return HC.iter_store_rows_for(
        IDENTITY, managed_row_table_specs(), payload, store_item_id=store_item_id
    )


async def publish_definitions(publisher: Any) -> HC.HEntryDefinitions:
    return await HC.publish_h_entry_definitions(
        IDENTITY,
        managed_row_table_specs(),
        publisher=publisher,
        contract_payload_builder=build_contract_payload,
    )


publish_pilot_definitions = publish_definitions

#: 首版发布 binding 装配读的两个 provider 常量（与 J1 / L1 同名）。🔴 必须有：
#: `ExcelInstrumentationSpec` 的字段名是 `uuid_col`，而 `projection_first_publication`
#: 按 `spec.uuid_column or provider.UUID_COL` 取 ⇒ 缺这个常量时 UUID 列解析为 None，
#: 首版发布炸在 `excel_entry_identity_inventory_invalid`（I6 实测）。
#: 多受管表（I5）时 `ROWS_TABLE_KEY` 指向主表，其余由 sibling binding 覆盖。
UUID_COL: Final[str] = instrumentation_spec().uuid_col
ROWS_TABLE_KEY: Final[str] = managed_row_table_specs()[0].table_key
PILOT_WP_CODES = WP_CODES
