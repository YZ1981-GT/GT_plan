# -*- coding: utf-8 -*-
"""G6-2「明细表」—— sheet 层薄声明（两区 + 10 公式列 + 33 有效列）。

spec: `g4-g6-shared-workbook-three-entry-lanes` · Task 13

═══ 几何（openpyxl 逐格实测）═══

`明细表G6-2`：`max_row=36` / `max_col=33` / merged 18 / 21 sheets。

* **两级表头 R9/R10**：
  R9 纵向合并 8 列（A B C D E F P Q + AE AF AG）+ 横向组 3 个（G9:O9 R9:U9 V9:AD9）
  R10 叶子行
* **两区**：
  * 区① R11 标题 → 数据 R12-14 → 小计 R15
  * 区② R16（区标题隐含在第一行 R16）→ R16-20 → 小计 R21
* 合计 R22 `=SUM(G21,G15)`（枚举两个小计）。
* **10 公式列**：J O Q U V W X Y AD AF（两区完全同形）。
* 有效列 33（A..AG） ⇒ uuid **AH/AI**。
* payload：`dual_write`。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G602_R1",
    "SPEC_G602_R2",
    "ALL_SPECS_G602",
    "MANAGED_SHEET_G602",
    "STORE_ITEM_ID_G602",
    "FORMULA_COLUMNS_G602",
    "FORMULA_TEMPLATES_G602",
    "FIELD_SPECS_G602",
]

MANAGED_SHEET_G602: Final[str] = "明细表G6-2"
TEMPLATE_ID_G602: Final[str] = "G602"
STORE_ITEM_ID_G602: Final[str] = "G6-2-rows"
ROW_IDENTITY_STORE_KEY_G602: Final[str] = "id"
ROW_SECTION_FIELD_G602: Final[str] = "maturityCategory"

HEADER_GROUP_ROW_G602: Final[int] = 9
HEADER_LEAF_ROW_G602: Final[int] = 10
SECTION_TITLE_ROWS_G602: Final[tuple[int, ...]] = (11,)  # 区② 无显式标题行
SUBTOTAL_ROWS_G602: Final[tuple[int, ...]] = (15, 21)
GRAND_TOTAL_ROW_G602: Final[int] = 22
FOOTER_MARKER_G602: Final[str] = "小计"

FORMULA_COLUMNS_G602: Final[tuple[str, ...]] = (
    "J", "O", "Q", "U", "V", "W", "X", "Y", "AD", "AF",
)

FORMULA_TEMPLATES_G602: Final[dict[str, str]] = {
    "J": "=SUM(G{r}:I{r})",          # 期初小计
    "O": "=K{r}+N{r}",               # 审定数
    "Q": "=O{r}-P{r}",               # 报表数
    "U": "=SUM(R{r}:T{r})",          # 本期变动小计
    "V": "=G{r}+R{r}",              # 期末成本
    "W": "=H{r}+S{r}",              # 期末利息调整
    "X": "=I{r}+T{r}",              # 期末应计利息
    "Y": "=SUM(V{r}:X{r})",          # 期末小计
    "AD": "=Z{r}+AC{r}",            # 期末审定数
    "AF": "=AD{r}-AE{r}",           # 期末报表数
}

#: 33 个受管字段（A..AG）。
FIELD_SPECS_G602: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("invest_type", "A", "editable", "text", "investType", "投资种类", ""),
    ("invest_target", "B", "editable", "text", "investTarget", "投资项目", ""),
    ("face_value", "C", "editable", "amount", "faceValue", "面值", ""),
    ("coupon_rate", "D", "editable", "rate", "couponRate", "票面利率", ""),
    ("effective_rate", "E", "editable", "rate", "effectiveRate", "实际利率", ""),
    ("maturity_date", "F", "editable", "text", "maturityDate", "到期日", ""),
    # 期初余额 (G9:O9)
    ("opening_cost", "G", "editable", "amount", "openingCost", "成本", "G9"),
    ("opening_interest_adj", "H", "editable", "amount", "openingInterestAdj", "利息调整（贷方余额填负数）", "G9"),
    ("opening_accrued_interest", "I", "editable", "amount", "openingAccruedInterest", "应计利息", "G9"),
    ("opening_subtotal", "J", "formula", "amount", "openingSubtotal", "小计", "G9"),
    ("opening_fair_value", "K", "editable", "amount", "openingFairValue", "公允价值", "G9"),
    ("period_fv_change", "L", "editable", "amount", "periodFvChange", "本期公允价值变动", "G9"),
    ("cumulative_fv_change", "M", "editable", "amount", "cumulativeFvChange", "累计公允价值变动", "G9"),
    ("opening_adj_number", "N", "editable", "amount", "openingAdjNumber", "调整数", "G9"),
    ("opening_audited", "O", "formula", "amount", "openingAudited", "审定数", "G9"),
    # 减值 / 报表
    ("opening_within_one_year", "P", "editable", "amount", "openingWithinOneYear", "减：期初超过一年到期的部分", ""),
    ("opening_reported", "Q", "formula", "amount", "openingReported", "期初报表数", ""),
    # 本期变动 (R9:U9)
    ("period_cost_change", "R", "editable", "amount", "periodCostChange", "成本", "R9"),
    ("period_interest_adj", "S", "editable", "amount", "periodInterestAdj", "利息调整", "R9"),
    ("period_accrued_interest", "T", "editable", "amount", "periodAccruedInterest", "应计利息", "R9"),
    ("period_subtotal", "U", "formula", "amount", "periodSubtotal", "小计", "R9"),
    # 期末余额 (V9:AD9)
    ("closing_cost", "V", "formula", "amount", "closingCost", "成本", "V9"),
    ("closing_interest_adj", "W", "formula", "amount", "closingInterestAdj", "利息调整（贷方余额填负数）", "V9"),
    ("closing_accrued_interest", "X", "formula", "amount", "closingAccruedInterest", "应计利息", "V9"),
    ("closing_subtotal", "Y", "formula", "amount", "closingSubtotal", "小计", "V9"),
    ("closing_fair_value", "Z", "editable", "amount", "closingFairValue", "公允价值", "V9"),
    ("closing_fv_change", "AA", "editable", "amount", "closingFvChange", "本期公允价值变动", "V9"),
    ("closing_cumulative_fv", "AB", "editable", "amount", "closingCumulativeFv", "累计公允价值变动", "V9"),
    ("closing_adj_number", "AC", "editable", "amount", "closingAdjNumber", "调整数", "V9"),
    ("closing_audited", "AD", "formula", "amount", "closingAudited", "审定数", "V9"),
    # 一年内到期
    ("closing_within_one_year", "AE", "editable", "amount", "closingWithinOneYear", "减：一年以内到期余额", ""),
    ("closing_reported", "AF", "formula", "amount", "closingReported", "期末报表数", ""),
    # 发函
    ("confirmation_status", "AG", "editable", "text", "confirmationStatus", "发函情况", ""),
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
        managed_sheet=MANAGED_SHEET_G602,
        sheet_key="g602-managed",
        table_key=table_key,
        template_id=f"{TEMPLATE_ID_G602}{template_suffix}",
        table_name=f"GT_{TEMPLATE_ID_G602}_{table_key.upper()}",
        uuid_col=uuid_col,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        footer_row=footer_row,
        header_group_row=HEADER_GROUP_ROW_G602,
        header_leaf_row=HEADER_LEAF_ROW_G602,
        store_item_id=STORE_ITEM_ID_G602,
        empty_payload="[]",
        row_identity_key=ROW_IDENTITY_STORE_KEY_G602,
        store_kind=StoreKind.rows,
        field_specs=FIELD_SPECS_G602,
        formula_columns=FORMULA_COLUMNS_G602,
        formula_templates=FORMULA_TEMPLATES_G602,
        footer_marker=FOOTER_MARKER_G602,
        footer_carries_total_formula=True,
        error_label=error_label,
        row_section_field=ROW_SECTION_FIELD_G602,
        row_section_value=section_value,
        ghost_row_anchor_index=1,
    )


SPEC_G602_R1: Final[RowTableSheetSpec] = _section_spec(
    table_key="g6_2_rows_r1",
    template_suffix="R1",
    uuid_col="AH",
    first_data_row=12,
    last_data_row=14,
    footer_row=15,
    section_value="within_one_year",
    error_label="G6-2 明细表（一年以内到期）",
)

SPEC_G602_R2: Final[RowTableSheetSpec] = _section_spec(
    table_key="g6_2_rows_r2",
    template_suffix="R2",
    uuid_col="AI",
    first_data_row=16,
    last_data_row=20,
    footer_row=21,
    section_value="over_one_year",
    error_label="G6-2 明细表（到期期限超过一年）",
)

ALL_SPECS_G602: Final[tuple[RowTableSheetSpec, ...]] = (SPEC_G602_R1, SPEC_G602_R2)
