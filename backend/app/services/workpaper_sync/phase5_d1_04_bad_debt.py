# -*- coding: utf-8 -*-
"""D1-4「坏账准备明细表」—— sheet 层薄声明（**三区**，D1 首次同 sheet 多受管区）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 26 · Requirements 5.1 / 5.4 / 5.7 / 5.8
几何证据: docs/operations/evidence/row-table-engine-d1-coverage/d1-04-bad-debt-geometry.json

═══ 三区（逐格实测，2026-09-26）═══

| 区 | 父行（SUM 小计，computed 不落库） | 数据行 | store 键 | UUID 列 |
|---|---|---|---|---|
| 个别计提 | R12 `按单项计提` = SUM(13:16) | **13-16** | `D1-bd-individual-rows` | O |
| 组合计提 | R17 `按组合计提` = SUM(18:21) | **18-21** | `D1-bd-portfolio-rows` | P |
| 票据种类小计 | —（无父行） | **23-24** | `D1-notetype-rows` | Q |

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
_FIELD_SPECS_D104: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item", "A", "editable", "text", "item", "项目", ""),
    ("prior_unadjusted", "B", "editable", "amount", "priorUnadjusted", "期初未审数", f"B{HEADER_GROUP_ROW_D104}"),
    ("prior_aje", "C", "editable", "amount", "priorAje", "账项调整", f"B{HEADER_GROUP_ROW_D104}"),
    ("prior_rje", "D", "editable", "amount", "priorRje", "重分类调整", f"B{HEADER_GROUP_ROW_D104}"),
    ("prior_audited", "E", "formula", "amount", "priorAudited", "期初审定数", f"B{HEADER_GROUP_ROW_D104}"),
    ("provision", "F", "editable", "amount", "provision", "计提", f"F{HEADER_GROUP_ROW_D104}"),
    ("other_increase", "G", "editable", "amount", "otherIncrease", "其他增加", f"F{HEADER_GROUP_ROW_D104}"),
    ("reversal", "H", "editable", "amount", "reversal", "转回", f"H{HEADER_GROUP_ROW_D104}"),
    ("write_off", "I", "editable", "amount", "writeOff", "核销", f"H{HEADER_GROUP_ROW_D104}"),
    ("other_decrease", "J", "editable", "amount", "otherDecrease", "其他减少", f"H{HEADER_GROUP_ROW_D104}"),
    ("current_unadjusted", "K", "formula", "amount", "currentUnadjusted", "期末未审数", f"K{HEADER_GROUP_ROW_D104}"),
    ("current_aje", "L", "editable", "amount", "currentAje", "账项调整", f"K{HEADER_GROUP_ROW_D104}"),
    ("current_rje", "M", "editable", "amount", "currentRje", "重分类调整", f"K{HEADER_GROUP_ROW_D104}"),
    ("current_audited", "N", "formula", "amount", "currentAudited", "期末审定数", f"K{HEADER_GROUP_ROW_D104}"),
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
    store_item_id="D1-notetype-rows",
    empty_payload="[]",
    row_identity_key="",   # 无行维度（static_region）
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_D104,
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
