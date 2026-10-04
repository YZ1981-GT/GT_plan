# -*- coding: utf-8 -*-
"""G4-2「明细表」—— sheet 层薄声明（两区 + 11 公式列 + 34 有效列）。

spec: `g4-g6-shared-workbook-three-entry-lanes` · Task 9

═══ 几何（openpyxl 逐格实测）═══

`明细表G4-2`：`max_row=48` / `max_col=44` / merged 23 / 19 sheets。

* **两级表头 R9/R10**：
  R9 纵向合并 14 列（A B C D E F K L M N O + AC AG AH）+ 横向组 4 个（G9:J9 P9:S9 T9:X9 Y9:AB9）
  R10 叶子行 14 个值（G H I J P Q R S T U V W X + AD AE AF）
* **两区**：
  * 区① R11「一、购入…一年以内到期的债权投资（列报为"其他流动资产"）」→ 数据 R12-17 → 小计 R18
  * 区② R19「二、购入…到期期限超过一年的债权投资」→ R20-25 → 小计 R26
* 合计 R27 `=SUM(G18,G26)`（枚举两个小计）。
* 🔴 有效列 **34**（A..AH）< max_col=44 ⇒ uuid **AI/AJ**。
* **11 公式列**：J L O S T U V X AC AF AG（两区完全同形）。
* R11/R19 的 B 列有 `【预留插行区：在「小计」行之上填写或插入】` = G 循环**唯一模板自带插行声明**。
* R28-R30 是注释说明行，R32 审计结论，R36 编制说明 —— 都不在受管区。
* payload 列：`conclusion`（`conclusion_canonical_remark_mirror` 族）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G402_R1",
    "SPEC_G402_R2",
    "ALL_SPECS_G402",
    "MANAGED_SHEET_G402",
    "STORE_ITEM_ID_G402",
    "FORMULA_COLUMNS_G402",
    "FORMULA_TEMPLATES_G402",
    "FIELD_SPECS_G402",
]

MANAGED_SHEET_G402: Final[str] = "明细表G4-2"
TEMPLATE_ID_G402: Final[str] = "G402"
STORE_ITEM_ID_G402: Final[str] = "G4-2-rows"
ROW_IDENTITY_STORE_KEY_G402: Final[str] = "id"
ROW_SECTION_FIELD_G402: Final[str] = "maturityCategory"

HEADER_GROUP_ROW_G402: Final[int] = 9
HEADER_LEAF_ROW_G402: Final[int] = 10
SECTION_TITLE_ROWS_G402: Final[tuple[int, ...]] = (11, 19)
SUBTOTAL_ROWS_G402: Final[tuple[int, ...]] = (18, 26)
GRAND_TOTAL_ROW_G402: Final[int] = 27
FOOTER_MARKER_G402: Final[str] = "小计"

#: 11 公式列（两区完全相同）
FORMULA_COLUMNS_G402: Final[tuple[str, ...]] = (
    "J", "L", "O", "S", "T", "U", "V", "X", "AC", "AF", "AG",
)

FORMULA_TEMPLATES_G402: Final[dict[str, str]] = {
    "J": "=SUM(G{r}:I{r})",          # 小计 = 成本 + 利息调整 + 应计利息
    "L": "=J{r}-K{r}",               # 摊余成本 = 小计 − 减值准备
    "O": "=L{r}-M{r}+N{r}",          # 审定数 = 摊余成本 − 一年内到期 + 调整数
    "S": "=SUM(P{r}:R{r})",          # 本期变动小计
    "T": "=G{r}+P{r}",              # 期末成本 = 期初成本 + 本期成本变动
    "U": "=H{r}+Q{r}",              # 期末利息调整
    "V": "=I{r}+R{r}",              # 期末应计利息
    "X": "=SUM(T{r}:W{r})",          # 期末审定数 = 成本 + 利息调整 + 应计利息 + 调整数
    "AC": "=X{r}-Y{r}",             # 期末摊余成本 = 审定数 − 减值准备
    "AF": "=AD{r}-AE{r}",           # 一年内净值 = 余额 − 减值
    "AG": "=AC{r}-AF{r}",           # 期末账面价值 = 摊余成本 − 一年内净值
}

#: 34 个受管字段（A..AH），顺序即 Excel 列序。
FIELD_SPECS_G402: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("invest_type", "A", "editable", "text", "investType", "投资种类", ""),
    ("invest_target", "B", "editable", "text", "investTarget", "投资项目", ""),
    ("face_value", "C", "editable", "amount", "faceValue", "面值", ""),
    ("coupon_rate", "D", "editable", "rate", "couponRate", "票面利率", ""),
    ("effective_rate", "E", "editable", "rate", "effectiveRate", "实际利率", ""),
    ("maturity_date", "F", "editable", "text", "maturityDate", "到期日", ""),
    # 期初余额 (G9:J9)
    ("opening_cost", "G", "editable", "amount", "openingCost", "成本", "G9"),
    ("opening_interest_adj", "H", "editable", "amount", "openingInterestAdj", "利息调整（贷方余额填负数）", "G9"),
    ("opening_accrued_interest", "I", "editable", "amount", "openingAccruedInterest", "应计利息", "G9"),
    ("opening_subtotal", "J", "formula", "amount", "openingSubtotal", "小计", "G9"),
    # 减值准备 / 摊余成本
    ("opening_impairment", "K", "editable", "amount", "openingImpairment", "债权投资期初减值准备", ""),
    ("opening_amortized_cost", "L", "formula", "amount", "openingAmortizedCost", "债权投资期初摊余成本", ""),
    ("opening_within_one_year", "M", "editable", "amount", "openingWithinOneYear", "减：期初一年以内到期部分", ""),
    ("opening_adj_number", "N", "editable", "amount", "openingAdjNumber", "期初调整数", ""),
    ("opening_audited", "O", "formula", "amount", "openingAudited", "期初审定数", ""),
    # 本期变动 (P9:S9)
    ("period_cost_change", "P", "editable", "amount", "periodCostChange", "成本", "P9"),
    ("period_interest_adj", "Q", "editable", "amount", "periodInterestAdj", "利息调整", "P9"),
    ("period_accrued_interest", "R", "editable", "amount", "periodAccruedInterest", "应计利息", "P9"),
    ("period_subtotal", "S", "formula", "amount", "periodSubtotal", "小计", "P9"),
    # 期末余额 (T9:X9)
    ("closing_cost", "T", "formula", "amount", "closingCost", "成本", "T9"),
    ("closing_interest_adj", "U", "formula", "amount", "closingInterestAdj", "利息调整（贷方余额填负数）", "T9"),
    ("closing_accrued_interest", "V", "formula", "amount", "closingAccruedInterest", "应计利息", "T9"),
    ("closing_adj_number", "W", "editable", "amount", "closingAdjNumber", "调整数", "T9"),
    ("closing_audited", "X", "formula", "amount", "closingAudited", "审定数", "T9"),
    # 减值准备（审定）(Y9:AB9)
    ("closing_impairment_closing", "Y", "editable", "amount", "closingImpairmentClosing", "期末数", "Y9"),
    ("ecl_stage", "Z", "editable", "text", "eclStage", "阶段划分", "Y9"),
    ("ecl_method", "AA", "editable", "text", "eclMethod", "信用组合方式", "Y9"),
    ("ecl_group_name", "AB", "editable", "text", "eclGroupName", "信用组合名称", "Y9"),
    # 摊余成本
    ("closing_amortized_cost", "AC", "formula", "amount", "closingAmortizedCost", "债权投资期末摊余成本", ""),
    # 一年内到期 (AD9:AF9)
    ("within_one_year_balance", "AD", "editable", "amount", "withinOneYearBalance", "账面余额", "AD9"),
    ("within_one_year_impairment", "AE", "editable", "amount", "withinOneYearImpairment", "减值", "AD9"),
    ("within_one_year_net", "AF", "formula", "amount", "withinOneYearNet", "小计", "AD9"),
    # 账面价值
    ("closing_book_value", "AG", "formula", "amount", "closingBookValue", "债权投资期末账面价值", ""),
    # 发函
    ("confirmation_status", "AH", "editable", "text", "confirmationStatus", "发函情况", ""),
)


def _section_spec(
    *,
    table_key: str,
    template_suffix: str,
    uuid_col: str,
    first_data_row: int,
    last_data_row: int,
    footer_row: int,
    section_value: str,
    error_label: str,
) -> RowTableSheetSpec:
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET_G402,
        sheet_key="g402-managed",
        table_key=table_key,
        template_id=f"{TEMPLATE_ID_G402}{template_suffix}",
        table_name=f"GT_{TEMPLATE_ID_G402}_{table_key.upper()}",
        uuid_col=uuid_col,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        footer_row=footer_row,
        header_group_row=HEADER_GROUP_ROW_G402,
        header_leaf_row=HEADER_LEAF_ROW_G402,
        store_item_id=STORE_ITEM_ID_G402,
        empty_payload="[]",
        row_identity_key=ROW_IDENTITY_STORE_KEY_G402,
        store_kind=StoreKind.rows,
        field_specs=FIELD_SPECS_G402,
        formula_columns=FORMULA_COLUMNS_G402,
        formula_templates=FORMULA_TEMPLATES_G402,
        footer_marker=FOOTER_MARKER_G402,
        footer_carries_total_formula=True,
        error_label=error_label,
        row_section_field=ROW_SECTION_FIELD_G402,
        row_section_value=section_value,
        ghost_row_anchor_index=1,
    )


SPEC_G402_R1: Final[RowTableSheetSpec] = _section_spec(
    table_key="g4_2_rows_r1",
    template_suffix="R1",
    uuid_col="AI",
    first_data_row=12,
    last_data_row=17,
    footer_row=18,
    section_value="within_one_year",
    error_label="G4-2 明细表（一年以内到期）",
)

SPEC_G402_R2: Final[RowTableSheetSpec] = _section_spec(
    table_key="g4_2_rows_r2",
    template_suffix="R2",
    uuid_col="AJ",
    first_data_row=20,
    last_data_row=25,
    footer_row=26,
    section_value="over_one_year",
    error_label="G4-2 明细表（到期期限超过一年）",
)

ALL_SPECS_G402: Final[tuple[RowTableSheetSpec, ...]] = (SPEC_G402_R1, SPEC_G402_R2)
