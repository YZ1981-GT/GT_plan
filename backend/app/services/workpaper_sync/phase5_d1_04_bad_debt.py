# -*- coding: utf-8 -*-
"""D1-4「坏账准备明细表」—— sheet 层薄声明（**三区**，D1 首次同 sheet 多受管区）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 26 · Requirements 5.1 / 5.4 / 5.7 / 5.8
几何证据: docs/operations/evidence/row-table-engine-d1-coverage/d1-04-bad-debt-geometry.json

═══ 三区（逐格实测，2026-09-26）═══

| 区 | 父行（SUM 小计，computed 不落库） | 数据行 | store 键 | UUID 列 |
|---|---|---|---|---|
| 个别计提 | R12 `按单项计提` = SUM(13:16) | **13-16** | `D1-bd-individual-rows` | O |
| 组合计提 | R17 `按组合计提` = SUM(18:21) | **18-21** | `D1-bd-portfolio-rows` | P |
| 票据种类小计 | —（无父行） | **23-24** | `D1-bd-notetype-rows` | **无**（static_region） |

footer R22 `合计  ` = B12+B17。

🔴 **三区必须各用不同 UUID 列**（D4-1 主营 W / 其他 X 的实测教训：同列会让行身份串区，
   回写落到错的区块）。模板 max_column=14(N) ⇒ 注入列取 O/P/Q。

🔴 **第三区（R23-24）在 footer 之下**。这命中 `HTML_ONLY_ITEM_IDS_D45` 那条实证冲突
   （「footer 下 `static_row` 与插行 fail-closed 冲突」）⇒ 它**不按动态行表接入**，
   而是按 `static_region`（绝对坐标直写、绕开整条位移链）声明：两行是写死的票据种类小计
   （银行承兑 / 商业承兑），无行维度、不增删。见 `SPEC_D104_NOTETYPE` 的 binding_kind。

🔴 **第三区与前两区是不同维度**：前两区按「计提方法」（单项 / 组合），第三区按「票据种类」
   （银行承兑 / 商业承兑）。**不得合并**（spec Task 26）。第三区专门喂 D1-1 坏账区块。

═══ 🔴 `D1-bd-portfolio-rows` 有第三个写入方（需求 5.7 / P17）═══

除 HTML 保存与 OO 回写之外，`useD1WriteoffCheck.syncReversalToD14` 会**回写**本键的
「按组合计提」父行（其注释写明「D1-4 的期末未审随之重算，并沿 D1-4 → D1-1 → 披露 → 附注
逐级联动」）。三方写同一 store 键必须定序：OO 模式期间禁用该跨 sheet 回写入口并给中文原因，
或把它改走 sync 的 pending-mutations 通道 —— **不得**两条路同时直写 store（会与 materialize
产物分叉，下次 extract 反读到非预期值 ⇒ roundtrip 门红或静默覆盖 OO 改动）。

本模块以 `THIRD_WRITER_STORE_KEYS` 显式登记该事实，供宿主 gating 与判据引用。

═══ 下游 computed 消费方（需求 5.8 / P18）═══

`useD1EclCalc.d1_4DataAvailable`(:475) · `useD1EclCalc.parseD1_4Rows`(:497/:499) ·
`useD1Adjudication` 坏账区（`d1AdjudicationModel.readD1BadDebtByNoteType`）·
`D1TabIndex.vue:49` 的 `progressKeys`。零回归**不得**只验本 sheet 自身读回等值。
"""
from __future__ import annotations

from typing import Final, Mapping

from app.services.workpaper_sync.excel_extract import BindingKind
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_D104_INDIVIDUAL",
    "SPEC_D104_PORTFOLIO",
    "SPEC_D104_NOTETYPE",
    "SPECS_D104",
    "MANAGED_SHEET_D104",
    "THIRD_WRITER_STORE_KEYS",
    "DOWNSTREAM_CONSUMERS_D104",
]

MANAGED_SHEET_D104: Final[str] = "坏账准备明细表D1-4"
TEMPLATE_ID_D104: Final[str] = "D14"
SHEET_KEY_D104: Final[str] = f"{TEMPLATE_ID_D104.lower()}-managed"

#: 两级表头：R10 组标题（项目/期初余额/本期增加/本期减少/期末余额）、R11 叶子。
HEADER_GROUP_ROW_D104: Final[int] = 10
HEADER_LEAF_ROW_D104: Final[int] = 11

FOOTER_ROW_D104: Final[int] = 22
#: 🔴 footer marker 实测为「合计」+ **一个半角空格**（codepoints 5408 8ba1 0020）。
#:    与 D1-2 的「合计」纯两字、D3 的「合计」无空格、D7 的「合   计」三半角空格都不同 ——
#:    照抄任一家都会 footer 定位失败。
#:
#:    🔴 本常量自身踩过一次「推演」的坑：首版据终端输出目测写成「两个全角空格」，
#:    被 test_d104_footer_marker_has_two_ideographic_spaces 判据按 codepoint 打红后改为实测值。
#:    这正是「禁推演」铁律的实证价值 —— 目测终端输出不算实测，必须按 codepoint 断言。
FOOTER_MARKER_D104: Final[str] = "合计 "
MANAGED_LAST_COL_D104: Final[str] = "N"

#: 三区共用的 14 列字段骨架（7 元组）。E/K/N 三列逐行有真公式 ⇒ formula。
#: 🔴 表头文本取 R11 叶子（B..G）与 R10 组标题（A/K 等无叶子的列），逐格实测。
#
# 🔴🔴 2026-09-28 修正 `json_key`（裁决 B1：spec 对齐前端）——前端是**写入方**，
#     真库已有数据，故改 spec 不动数据。
#
#     `json_key`（元组第 5 位）进契约成为 `json_pointer = /rows/{row_uuid}/{json_key}`，
#     是寻址 HTML store 行对象的**唯一**依据。原声明逐列照模板列头语义命名，
#     与前端 `useD1BadDebt.serializeRows()` 实际落库的键**六处不一致**：
#
#         item → label            provision  → currentProvision
#         otherIncrease → currentRecovery    reversal → currentReversal
#         writeOff → currentWriteOff         otherDecrease → currentOther
#
#     后果（两向都断）：materialize 按 pointer 取不到值 ⇒ `_render_number(None)` 落
#     **`0`**、文本落 `""`，**擦掉**审计师直接在 Excel 里填的内容；extract/merge 把
#     Excel 值写进前端从不读的键 ⇒ 静默丢弃。
#
#     对应关系的定位依据（不靠名字猜）：Excel F/H/I 列头「计提/转回/核销」与前端 UI
#     列头「本期计提/本期转回/本期核销」**逐字相同**，作三个定位锚；五列顺序一致
#     ⇒ G「其他增加」↔`currentRecovery`（UI 作「本期收回」）、J「其他减少」↔`currentOther`
#     （UI 作「本期其他」）在位置上无歧义。
#     📌 顺带登记：G/J 两列**前端 UI 措辞与源模板列头不一致**（收回 vs 其他增加 /
#        其他 vs 其他减少），属前端文案问题，不影响列身份，归 UI 一致性批次。
#
_FIELD_SPECS_D104: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item", "A", "editable", "text", "label", "项目", ""),
    ("prior_unadjusted", "B", "editable", "amount", "priorUnadjusted", "期初未审数", f"B{HEADER_GROUP_ROW_D104}"),
    ("prior_aje", "C", "editable", "amount", "priorAje", "账项调整", f"B{HEADER_GROUP_ROW_D104}"),
    ("prior_rje", "D", "editable", "amount", "priorRje", "重分类调整", f"B{HEADER_GROUP_ROW_D104}"),
    ("prior_audited", "E", "formula", "amount", "priorAudited", "期初审定数", f"B{HEADER_GROUP_ROW_D104}"),
    ("provision", "F", "editable", "amount", "currentProvision", "计提", f"F{HEADER_GROUP_ROW_D104}"),
    ("other_increase", "G", "editable", "amount", "currentRecovery", "其他增加", f"F{HEADER_GROUP_ROW_D104}"),
    ("reversal", "H", "editable", "amount", "currentReversal", "转回", f"H{HEADER_GROUP_ROW_D104}"),
    ("write_off", "I", "editable", "amount", "currentWriteOff", "核销", f"H{HEADER_GROUP_ROW_D104}"),
    ("other_decrease", "J", "editable", "amount", "currentOther", "其他减少", f"H{HEADER_GROUP_ROW_D104}"),
    ("current_unadjusted", "K", "formula", "amount", "currentUnadjusted", "期末未审数", f"K{HEADER_GROUP_ROW_D104}"),
    ("current_aje", "L", "editable", "amount", "currentAje", "账项调整", f"K{HEADER_GROUP_ROW_D104}"),
    ("current_rje", "M", "editable", "amount", "currentRje", "重分类调整", f"K{HEADER_GROUP_ROW_D104}"),
    ("current_audited", "N", "formula", "amount", "currentAudited", "期末审定数", f"K{HEADER_GROUP_ROW_D104}"),
)

#: 🔴 第三区**不由 HTML 拥有**的列（模板 F~J「计提/其他增加/转回/核销/其他减少」）。
#:
#: 前端 `useD1BadDebt.serializeNoteTypeRows()` 对本区只落 6 个金额
#: （priorUnadjusted / priorAje / priorRje / currentUnadjusted / currentAje / currentRje）
#: 外加 noteType / rowId / isFixed —— **F~J 五列一个都不持久化**（真库载荷现查证实）。
#:
#: 为什么必须显式排除而不是「声明了但反正没值」：
#:   `split_store_row` 对每个声明列都 yield，缺键时值为 `None`，而
#:   `excel_materialize._render_number(None)` 返回 **`"0"`**、`inline_text` 返回 `""`
#:   ⇒ 声明它们会让每次 materialize 把 F23:J24 **写成 0**，擦掉审计师在 OO 侧填的内容。
#:
#: 排除后的语义是**分权拥有**：F~J 由审计师直接在 Excel 填，模板 K23 的
#: `=B23+SUM(F23:G23)-SUM(H23:J23)` 因此能正确求值；HTML 侧不碰这五列。
#: 已验证安全：静态写入路径 `_plan_static_writes` 对投影里没有的键 `continue`（不写），
#: `verify_unmanaged_regions` 比对 before/after 而未写的格前后相同 ⇒ 不判漂移。
_HTML_UNOWNED_COLUMNS_D104_NOTETYPE: Final[frozenset[str]] = frozenset({"F", "G", "H", "I", "J"})

#: 第三区（票据种类小计 R23-24）的字段面。与两个动态区差两处：
#:   ① A 列 json_key 是 `noteType`（前端用票据种类名）而非 `label`；
#:   ② 排除 F~J 五列（见上方 `_HTML_UNOWNED_COLUMNS_D104_NOTETYPE`）。
#: ⇒ 9 列：A / B / C / D / E(formula) / K(formula) / L / M / N(formula)。
#:
#: 🔴 **由 `_FIELD_SPECS_D104` 派生而非复制一份**（复制的两份必漂移；本仓库已有
#:    「四处拼锚点三处拼错」的事故背书）。
_FIELD_SPECS_D104_NOTETYPE: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = tuple(
    (fs[0], fs[1], fs[2], fs[3], "noteType", fs[5], fs[6]) if fs[1] == "A" else fs
    for fs in _FIELD_SPECS_D104
    if fs[1] not in _HTML_UNOWNED_COLUMNS_D104_NOTETYPE
)

#: 公式模板（逐格实测；K 列用 SUM 区间形态而非简单加减）。
_FORMULA_TEMPLATES_D104: Final[dict[str, str]] = {
    "E": "=B{r}+C{r}+D{r}",
    "K": "=B{r}+SUM(F{r}:G{r})-SUM(H{r}:J{r})",
    "N": "=K{r}+L{r}+M{r}",
}

_FORMULA_COLUMNS_D104: Final[tuple[str, ...]] = ("E", "K", "N")


def _base_spec(
    *,
    section: str,
    table_key: str,
    store_item_id: str,
    first_data_row: int,
    last_data_row: int,
    uuid_col: str,
    binding_kind: BindingKind = BindingKind.excel_table,
    row_identity_key: str = "rowId",
    defined_name: str = "",
    error_label: str = "",
) -> RowTableSheetSpec:
    """三区共用骨架，只差几何/键/身份列（**不复制三份字段声明**）。"""
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET_D104,
        sheet_key=SHEET_KEY_D104,
        table_key=table_key,
        template_id=f"{TEMPLATE_ID_D104}{section.upper()}",
        table_name=f"GT_{TEMPLATE_ID_D104}_{section.upper()}_ROWS",
        uuid_col=uuid_col,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        footer_row=FOOTER_ROW_D104,
        header_group_row=HEADER_GROUP_ROW_D104,
        header_leaf_row=HEADER_LEAF_ROW_D104,
        binding_kind=binding_kind,
        defined_name=defined_name,
        store_item_id=store_item_id,
        empty_payload="[]",
        row_identity_key=row_identity_key,
        store_kind=StoreKind.rows,
        field_specs=_FIELD_SPECS_D104,
        formula_columns=_FORMULA_COLUMNS_D104,
        formula_templates=_FORMULA_TEMPLATES_D104,
        footer_marker=FOOTER_MARKER_D104,
        error_label=error_label,
    )


#: 区一：按单项计提（父行 R12 = SUM(13:16)，动态行 13-16）。
SPEC_D104_INDIVIDUAL: Final[RowTableSheetSpec] = _base_spec(
    section="individual",
    table_key="bad_debt_individual_rows",
    store_item_id="D1-bd-individual-rows",
    first_data_row=13,
    last_data_row=16,
    uuid_col="O",
    error_label="D1-4 坏账准备明细表（按单项计提）",
)

#: 区二：按组合计提（父行 R17 = SUM(18:21)，动态行 18-21）。
#: 🔴 本键有第三个写入方 `useD1WriteoffCheck.syncReversalToD14`（见模块 docstring）。
SPEC_D104_PORTFOLIO: Final[RowTableSheetSpec] = _base_spec(
    section="portfolio",
    table_key="bad_debt_portfolio_rows",
    store_item_id="D1-bd-portfolio-rows",
    first_data_row=18,
    last_data_row=21,
    uuid_col="P",
    error_label="D1-4 坏账准备明细表（按组合计提）",
)

#: 区三：按票据种类小计（R23-24，**在 footer R22 之下**）。
#:
#: 🔴 走 `static_region` 而非动态行表：两行是写死的票据种类小计（银行承兑 / 商业承兑），
#:    无行维度、不增删；且它在 footer 之下 ⇒ 若按动态行表接入会命中
#:    `HTML_ONLY_ITEM_IDS_D45` 那条实证冲突（footer 下 static_row 与插行 fail-closed）。
#:    static_region 按绝对坐标直写、**绕开整条位移链**（无 row_shift / 无 footer 两门 /
#:    无 minted UUID / 无 workbook 传播），正是这种形态的正解。
#:
#: 🔴 `static_region` 的 `table_name` / `uuid_col` 必空、`defined_name` 必填
#:    （`excel_extract.BindingKind` 的分派铁律）。
SPEC_D104_NOTETYPE: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D104,
    sheet_key=SHEET_KEY_D104,
    table_key="bad_debt_notetype_rows",
    template_id=f"{TEMPLATE_ID_D104}NOTETYPE",
    table_name="",   # static_region 必空
    uuid_col="",     # static_region 必空
    first_data_row=23,
    last_data_row=24,
    footer_row=FOOTER_ROW_D104,
    header_group_row=HEADER_GROUP_ROW_D104,
    header_leaf_row=HEADER_LEAF_ROW_D104,
    binding_kind=BindingKind.static_region,
    defined_name=f"GT_MANAGED_REGION_{TEMPLATE_ID_D104}NOTETYPE",
    # 🔴 2026-09-28 修正键名错误：原写 `D1-notetype-rows`（吃掉了 `D1-bd` 前缀）。
    #    真源按值实测四处一致 —— 前端 `d1AdjudicationModel.ts` 的
    #    `D1_BD_NOTETYPE_KEY = 'D1-bd-notetype-rows'` · 后端 `prefill_anchor_map.py` 的
    #    `AnchorSpec(item_id="D1-bd-notetype-rows", column="currentUnadjusted")` ·
    #    `d_cycle_extraction/presets.py` 的 `"anchor": "D1-bd-notetype-rows"` ·
    #    真库 `checklist_responses` 中 `D1-bd-notetype-rows` 有真实载荷而错键 0 行。
    #    错键的后果：本区（专门喂 D1-1 坏账区块的票据种类小计）在 OO 侧读空、回写落进
    #    无任何消费方的键 ⇒ 静默丢数据；且它走 static_region 绕开位移链，位移判据抓不到。
    store_item_id="D1-bd-notetype-rows",
    empty_payload="[]",
    row_identity_key="",   # 无行维度（static_region）
    store_kind=StoreKind.rows,
    # 🔴 2026-09-28：本区 A 列的 json_key 是 `noteType`（前端 `serializeNoteTypeRows`），
    #    与两个动态区的 `label` 不同 ⇒ 用派生出来的 notetype 变体。
    field_specs=_FIELD_SPECS_D104_NOTETYPE,
    formula_columns=_FORMULA_COLUMNS_D104,
    formula_templates=_FORMULA_TEMPLATES_D104,
    footer_marker=FOOTER_MARKER_D104,
    error_label="D1-4 坏账准备明细表（按票据种类小计）",
)

#: 三区清单（顺序即 Excel 行序）。
SPECS_D104: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_D104_INDIVIDUAL,
    SPEC_D104_PORTFOLIO,
    SPEC_D104_NOTETYPE,
)

#: 🔴 有第三个写入方的 store 键（需求 5.7 / P17）—— 宿主须据此定序，判据须据此断言。
#:    实测全仓唯一命中：`useD1WriteoffCheck.syncReversalToD14` 回写「按组合计提」父行。
#:    触类旁通已 grep：D2 侧同型但**无此冲突**（`useD2WriteoffCheck.reversalConsistencyWarning`
#:    只**读** D2-3 三键不回写，仅告警）。
THIRD_WRITER_STORE_KEYS: Final[Mapping[str, str]] = {
    "D1-bd-portfolio-rows": (
        "useD1WriteoffCheck.syncReversalToD14 回写「按组合计提」父行"
        "（注释：D1-4 的期末未审随之重算，并沿 D1-4 → D1-1 → 披露 → 附注 逐级联动）"
    ),
}

#: 三键的下游 computed 消费方（需求 5.8 / P18）—— 零回归须覆盖它们，不得只验自身读回等值。
DOWNSTREAM_CONSUMERS_D104: Final[tuple[str, ...]] = (
    "useD1EclCalc.d1_4DataAvailable(:475)",
    "useD1EclCalc.parseD1_4Rows(:497/:499)",
    "useD1Adjudication 坏账区（d1AdjudicationModel.readD1BadDebtByNoteType）",
    "D1TabIndex.vue:49 progressKeys",
)


# ═══════════════════════════════════════════════════════════════════════════
# 第三区（票据种类小计 R23-24）的静态受管区通路
# ═══════════════════════════════════════════════════════════════════════════
#
# spec: d1-sync-row-table-engine-and-d1-coverage · 契约层 `static_tables`（Task 25~29 前置）
#
# ═══ 为什么不能复用行表引擎 ═══
#
# `phase5_row_table_sheet.store_row_identity()` 对 `row_identity_key == ""` **直接抛**
# `RowTableStorePayloadError("… 声明为无行身份（static_region）—— 不应走行表投影路径")`
# ⇒ `build_store_projection` / `merge_projection_into_store_rows` 这条通路对本区走不通，
#    必须像 D4-13 / D4-33 那样自带一对投影/回写函数。
#
# ═══ 形态先例取 D4-33 而非 D4-5 ═══
#
# * D4-5 的 fixed 表是「每字段一个格」（`("biz_scene","B",11)` / `("biz_order","B",12)`），
#   它只证明「同 sheet 可以动静两 table 并列」，没证明**多行**静态区怎么表达；
# * D4-33（`phase5_d4_other_margin_sheet.sheet_payload_d433`）是「固定 12 月行 × 3 业务槽」，
#   做法 = 把行身份**编进 `column_key`** + `cell = {"column": col, "row_from": <绝对行号>}`。
#   本区（2 固定行 × 9 列）同构，照它。
#
# ═══ 不需要独立 binding ═══
#
# `managed_tables_of(contract, binding=…)` 按 `binding.table_key` 找到 sheet 后，把该 sheet 上
# **所有**不带 `row_identity` 的 table 作为 `static_tables` 一并返回；而 `plan_managed_writes`
# （动态路径）本身就遍历 `static_tables`（:1942）⇒ 走已有 `bad_debt_individual_rows`／
# `bad_debt_portfolio_rows` 的 binding 就能到达本区。
# 🔴 这也是为什么 `_static_sheet_declarations()` 里**不需要**补 `tables[0].table_key`
#    （`_static_region_bindings` 只为**整张 sheet 都是静态**的 entry 生成独立 binding，
#     如 D4-13 / D4-33）。

#: 两条固定行：(前端 `rowId`, Excel 绝对行号, 源模板 A 列行名逐字)。
#:
#: 🔴 `rowId` 取自前端 `useD1BadDebt.DEFAULT_NOTETYPE_ROWS`，**不是**我们自己编的 slug ——
#:    它同时是 HTML 载荷里的行身份与本区 stable key 的中段，两侧必须逐字相同。
#: 🔴 行名取自源模板 A23/A24（openpyxl 现读），前端也标 `isFixed` 不允许改名。
NOTETYPE_FIXED_ROWS: Final[tuple[tuple[str, int, str], ...]] = (
    ("fixed-bank", 23, "银行承兑汇票小计"),
    ("fixed-commercial", 24, "商业承兑汇票小计"),
)


def notetype_stable_key(row_id: str, column_key: str) -> str:
    """`{table_key}/{rowId}/{column_key}` —— 与行表的 `stable_key_for` 同构。

    中段用**前端 `rowId`**（`fixed-bank`/`fixed-commercial`）而非序号，
    这样 stable key 与 HTML 载荷的行身份一眼对得上，插删行也不会错位。
    """
    return f"{SPEC_D104_NOTETYPE.table_key}/{row_id}/{column_key}"


#: HTML 真正拥有（会落库）的**可编辑**列 —— 投影只供这些。
#:
#: 前端 `serializeNoteTypeRows()` 落 7 个值：noteType + 6 个金额，其中 `currentUnadjusted`
#: 对应模板 K 列而 K 是**公式列**（`=B23+SUM(F23:G23)-SUM(H23:J23)`）⇒ 不由 HTML 写，
#: 故投影不供它。E/N 同为公式列（派生，前端本就不落库）。
#: `_emit` 对投影里缺键的字段 `return`（跳过）⇒ E/K/N 的模板公式原样保留。
_NOTETYPE_PROJECTED_COLUMNS: Final[tuple[str, ...]] = (
    "A",  # noteType
    "B",  # priorUnadjusted
    "C",  # priorAje
    "D",  # priorRje
    "L",  # currentAje
    "M",  # currentRje
)


def notetype_static_table_payload() -> dict[str, Any]:
    """第三区的契约 **static table** payload（无 `row_identity` ⇒ `has_dynamic_rows == False`）。

    `TableSpec.has_dynamic_rows` 就定义为 `row_identity is not None`（`contracts.py:745`）
    ⇒ 不给 `row_identity` 即被 `managed_tables_of` 归入 `static_tables`。

    2 固定行 × 9 列 = **18** 个 field，每个 `cell` 用绝对行号（`row_from: 23|24`）
    而非动态表的 `row_from: "row_identity"`。
    """
    src = f"源xlsx!{MANAGED_SHEET_D104}"
    fields: list[dict[str, Any]] = []
    for row_id, row_no, _label in NOTETYPE_FIXED_ROWS:
        for col_key, col, mode, vtype, json_key, hdr, _group in SPEC_D104_NOTETYPE.field_specs:
            fields.append(
                {
                    "stable_field_key": notetype_stable_key(row_id, col_key),
                    # 🔴 指向**数组里该 rowId 的那一行**：回写侧按 rowId 定位，
                    #    不用数组下标（下标会随前端增删行错位）。
                    "json_pointer": f"/rows/{row_id}/{json_key}",
                    "column_key": f"{row_id}_{col_key}",
                    "cell": {"column": col, "row_from": row_no},
                    "mode": mode,
                    "value_type": vtype,
                    "source_ref": f"{src}!{col}{row_no}",
                    "header_source_ref": f"{src}!{col}{HEADER_LEAF_ROW_D104}",
                    "store_item_id": SPEC_D104_NOTETYPE.store_item_id,
                    "header_text": hdr,
                }
            )
    return {
        "table_key": SPEC_D104_NOTETYPE.table_key,
        "anchor": f"A{SPEC_D104_NOTETYPE.first_data_row}",
        "header_rows": 1,
        # E/K/N 三列逐行有真公式（模板实测）⇒ 进 mask 受保护，OO 侧改它们会产生受保护冲突。
        "formula_mask": [
            f"{c}{SPEC_D104_NOTETYPE.first_data_row}:{c}{SPEC_D104_NOTETYPE.last_data_row}"
            for c in _FORMULA_COLUMNS_D104
        ],
        "fields": fields,
        # 🔴 **刻意不给** `row_identity` / `uuid_col` / `delete_policy` / `footer_anchor`：
        #    静态区无行维度、不注 UUID 列、不参与位移链，footer 两门只对动态表成立。
    }


def build_notetype_store_projection(payload: Any, *, contract: Any) -> Any:
    """HTML 载荷（行数组）→ 本区 `Projection`（按 rowId 映射到固定行）。

    载荷形态与动态区相同（`serializeNoteTypeRows()` 产出的行对象数组），但**只认**
    `NOTETYPE_FIXED_ROWS` 里那两个 `rowId`：
    * 缺其中某一行 ⇒ 该行不投影（`_emit` 跳过 ⇒ Excel 那行保持原值，不被清零）；
    * 出现第三个 `rowId`（历史遗留自定义行）⇒ **显式忽略并不报错** ——
      模板 R23/R24 之下紧接「三、审计说明」、零余量，Excel 侧无处安放；
      新增入口已按裁决 A1 移除，故这里只需容忍存量、不需要支持它。
    """
    import json as _json

    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        rows = _json.loads(text) if text.strip() else []
    else:
        rows = payload or []
    if not isinstance(rows, list):
        raise ValueError(
            f"{SPEC_D104_NOTETYPE.store_item_id} 的载荷必须是行对象数组，"
            f"实得 {type(rows).__name__} —— 整块被存成别的形态时必须 fail closed"
        )

    by_row_id = {
        str(r.get("rowId") or ""): r for r in rows if isinstance(r, Mapping)
    }
    projected = {
        fs[0]: fs for fs in SPEC_D104_NOTETYPE.field_specs if fs[1] in _NOTETYPE_PROJECTED_COLUMNS
    }

    values: dict[str, Any] = {}
    for row_id, _row_no, _label in NOTETYPE_FIXED_ROWS:
        row = by_row_id.get(row_id)
        if row is None:
            continue
        for col_key, (_ck, _col, mode, _vt, json_key, _hdr, _g) in projected.items():
            sk = notetype_stable_key(row_id, col_key)
            spec = contract.field_by_stable_key(sk)
            values[sk] = FieldValue(
                stable_key=sk,
                value=row.get(json_key),
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=None,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={},
    )


def merge_projection_into_notetype_rows(
    *, projection: Any, base_rows: list[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """OO 侧 `Projection` → 回写进 HTML 行数组（返回形态与行表引擎一致）。

    返回 `(rows, touched, skipped, protected_keys)` —— 与
    `phase5_row_table_sheet.merge_projection_into_store_rows` **同签名**，
    这样 `merge_projection_into_all_d1_stores` 对动静两类可以同一套编排。

    🔴 三条纪律：
    * **按 `rowId` 定位**（不用数组下标）；base 里缺该固定行时补一条（带 `isFixed=True`
      与源模板行名），否则 OO 侧首次录入会无处落；
    * **受保护字段不回写**（`is_protected`）—— E/K/N 是模板公式，OO 侧的计算结果不是权威值；
    * **历史遗留的第三方自定义行原样保留**（不在 `NOTETYPE_FIXED_ROWS` 里的 rowId 不动），
      删除它们归前端 `removeNoteTypeRow`，同步层不代为清理。
    """
    rows: list[dict[str, Any]] = [dict(r) for r in base_rows]
    index = {str(r.get("rowId") or ""): i for i, r in enumerate(rows)}
    by_col = {fs[0]: fs for fs in SPEC_D104_NOTETYPE.field_specs}

    touched = 0
    skipped = 0
    protected: set[str] = set()

    for row_id, _row_no, label in NOTETYPE_FIXED_ROWS:
        idx = index.get(row_id)
        if idx is None:
            rows.append({"rowId": row_id, "noteType": label, "isFixed": True})
            idx = len(rows) - 1
            index[row_id] = idx
        target = rows[idx]
        for col_key, (_ck, _col, _mode, _vt, json_key, _hdr, _g) in by_col.items():
            sk = notetype_stable_key(row_id, col_key)
            fv = projection.get(sk) if hasattr(projection, "get") else None
            if fv is None:
                values = getattr(projection, "values", None)
                if isinstance(values, Mapping):
                    fv = values.get(sk)
            if fv is None:
                skipped += 1
                continue
            if getattr(fv, "is_protected", False):
                protected.add(sk)
                skipped += 1
                continue
            new_val = getattr(fv, "value", None)
            if target.get(json_key) != new_val:
                target[json_key] = new_val
                touched += 1
        # 固定行的名字与 `isFixed` 标记不许被 OO 侧改掉（前端也不允许改名）
        target["noteType"] = label
        target["isFixed"] = True

    return rows, touched, skipped, protected
