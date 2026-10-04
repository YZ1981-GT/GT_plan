# -*- coding: utf-8 -*-
"""G3-2「应收股利明细表」—— sheet 层薄声明（两区 + 三级表头 + 12 公式列）。

spec: `g-cycle-single-region-detail-lanes` · Task 14 / C-13

═══ 几何（openpyxl 逐格实测，禁推演）═══

`明细表G3-2`：`max_row=38` / **`max_column=33`** / **491 definedName** / merged 24 / 9 sheets。

* **三级表头 R9/R10/R11**（G 循环唯一）：
  R9 五个一级组（`A 项目` / `C 账面余额(C9:P9)` / `Q 减值准备(Q9:AD9)` / `AE 账面价值(AE9:AF9)` / `AG 备注`）
  R10 十一个二级组（`C 未审数(C10:F10)` / `G 期初调整(G10:H10)` / `I 账项调整(I10:J10)` / `K 重分类(K10:L10)` /
  `M 审定数(M10:P10)` / `Q 未审数(Q10:T10)` / `U 期初调整(U10:V10)` / `W 账项调整(W10:X10)` / `Y 重分类(Y10:Z10)` /
  `AA 审定数(AA10:AD10)` / `AE 审定数(AE10:AF10)`）
  R11 叶子行（逐列 30 个值）+ 纵向合并列 `A9:B11` + `AG9:AG11`
* **B 列空**（`A9:B11` 合并覆盖，但 B 列无独立内容，不占受管列位）
* 🔴 **两区**（区标题行不受管）：
  * 区① `R12`「1、账龄一年以内的应收股利」→ 数据 **R13-R20**（8 行）→ 小计 `R21`
  * 区② `R22`「2、账龄一年以上的应收股利」→ **R23-R28**（6 行）→ `R29`
* 合计 `R30` = `=C29+C21`（枚举两个小计，逐列同形）。
* 有效列 **32**（A + C..AG）**≤** `max_column=33` ⇒ 两区 uuid 列取 **AH/AI**
  （max_col + 1 / +2，避开空的 B 列 + 有效列之后）。
* 🔴 两区公式列**完全相同**（12 个），公式模板逐行同形（不像 G1 有跨表差异）。
* 🔴 **B 列空但 A9:B11 合并** ⇒ `A` 是受管列（「项目」= 被投资方名称），`B` 不声明。
* payload 列是 **`conclusion`**（FD-1 的 `conclusion_only` 族）。
* 🔴 整册裸 IF **0 格**（9 sheet 全零）⇒ 中性化为空操作；per-file 照挂（GC-2）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G302_R1",
    "SPEC_G302_R2",
    "ALL_SPECS_G302",
    "MANAGED_SHEET_G302",
    "STORE_ITEM_ID_G302",
    "ROW_SECTION_FIELD_G302",
    "SECTION_TITLE_ROWS_G302",
    "SUBTOTAL_ROWS_G302",
    "GRAND_TOTAL_ROW_G302",
    "FORMULA_COLUMNS_G302",
    "FORMULA_TEMPLATES_G302",
    "FIELD_SPECS_G302",
]

MANAGED_SHEET_G302: Final[str] = "明细表G3-2"
TEMPLATE_ID_G302: Final[str] = "G302"
STORE_ITEM_ID_G302: Final[str] = "G3-2-detail-rows"
ROW_IDENTITY_STORE_KEY_G302: Final[str] = "id"
#: 两区归属字段 —— 前端的 `agingCategory`
ROW_SECTION_FIELD_G302: Final[str] = "agingCategory"

HEADER_L1_ROW_G302: Final[int] = 9
HEADER_L2_ROW_G302: Final[int] = 10
HEADER_LEAF_ROW_G302: Final[int] = 11
SECTION_TITLE_ROWS_G302: Final[tuple[int, ...]] = (12, 22)
SUBTOTAL_ROWS_G302: Final[tuple[int, ...]] = (21, 29)
GRAND_TOTAL_ROW_G302: Final[int] = 30
FOOTER_MARKER_G302: Final[str] = "小计"

#: 12 公式列（两区完全相同）
FORMULA_COLUMNS_G302: Final[tuple[str, ...]] = (
    "F", "M", "N", "O", "P", "T", "AA", "AB", "AC", "AD", "AE", "AF",
)

#: 逐行同形公式模板（`{r}` 为行号）
FORMULA_TEMPLATES_G302: Final[dict[str, str]] = {
    "F": "=SUM(C{r}:D{r})-E{r}",        # 期末数 = 期初 + 增加 − 减少
    "M": "=C{r}+G{r}+H{r}",              # 审定期初 = 未审期初 + 期初调整(AJE+RJE)
    "N": "=D{r}+I{r}+K{r}",              # 审定增加
    "O": "=E{r}+J{r}+L{r}",              # 审定减少
    "P": "=M{r}+N{r}-O{r}",              # 审定期末
    "T": "=SUM(Q{r}:R{r})-S{r}",         # 减值准备期末
    "AA": "=Q{r}+U{r}+V{r}",             # 审定减值期初
    "AB": "=R{r}+W{r}+Y{r}",             # 审定减值增加
    "AC": "=S{r}+X{r}+Z{r}",             # 审定减值减少
    "AD": "=AA{r}+AB{r}-AC{r}",           # 审定减值期末
    "AE": "=M{r}-AA{r}",                  # 账面价值期初 = 审定余额期初 − 审定减值期初
    "AF": "=P{r}-AD{r}",                  # 账面价值期末
}

#: 32 个受管字段（7 元组：snake_key, col, mode, vtype, json_key, header_text, group_cell）。
#: 顺序即 Excel 列序 A → AG（跳过空的 B 列）。
#: 三级表头取最深一级有值的行（叶子行 R11 有值取 R11，否则上溯 R10/R9）。
#: `group_cell` 记叶子列所属的**最窄**分组合并区起始格（有两级分组的取二级 R10 格，
#: 只有一级的取 R9 格，纵向合并列留空）。
FIELD_SPECS_G302: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    # A —— 项目（纵向合并 A9:B11，B 列空不声明）
    ("investee_name", "A", "editable", "text", "investeeName", "项目", ""),
    # ── 账面余额 (C9:P9) ──
    # 未审数 (C10:F10)
    ("bv_unaudited_opening", "C", "editable", "amount", "bvUnauditedOpening", "期初数", "C10"),
    ("bv_unaudited_increase", "D", "editable", "amount", "bvUnauditedIncrease", "本期增加", "C10"),
    ("bv_unaudited_decrease", "E", "editable", "amount", "bvUnauditedDecrease", "本期减少", "C10"),
    ("bv_unaudited_closing", "F", "formula", "amount", "bvUnauditedClosing", "期末数", "C10"),
    # 期初调整 (G10:H10)
    ("bv_prior_adj_aje", "G", "editable", "amount", "bvPriorAdjAje", "账项调整", "G10"),
    ("bv_prior_adj_rje", "H", "editable", "amount", "bvPriorAdjRje", "重分类调整", "G10"),
    # 账项调整 (I10:J10)
    ("bv_aje_increase", "I", "editable", "amount", "bvAjeIncrease", "本期增加", "I10"),
    ("bv_aje_decrease", "J", "editable", "amount", "bvAjeDecrease", "本期减少", "I10"),
    # 重分类调整 (K10:L10)
    ("bv_rje_increase", "K", "editable", "amount", "bvRjeIncrease", "本期增加", "K10"),
    ("bv_rje_decrease", "L", "editable", "amount", "bvRjeDecrease", "本期减少", "K10"),
    # 审定数 (M10:P10)
    ("bv_audited_opening", "M", "formula", "amount", "bvAuditedOpening", "期初数", "M10"),
    ("bv_audited_increase", "N", "formula", "amount", "bvAuditedIncrease", "本期增加", "M10"),
    ("bv_audited_decrease", "O", "formula", "amount", "bvAuditedDecrease", "本期减少", "M10"),
    ("bv_audited_closing", "P", "formula", "amount", "bvAuditedClosing", "期末数", "M10"),
    # ── 减值准备 (Q9:AD9) ──
    # 未审数 (Q10:T10)
    ("imp_unaudited_opening", "Q", "editable", "amount", "impUnauditedOpening", "期初数", "Q10"),
    ("imp_unaudited_increase", "R", "editable", "amount", "impUnauditedIncrease", "本期增加", "Q10"),
    ("imp_unaudited_decrease", "S", "editable", "amount", "impUnauditedDecrease", "本期减少", "Q10"),
    ("imp_unaudited_closing", "T", "formula", "amount", "impUnauditedClosing", "期末数", "Q10"),
    # 期初调整 (U10:V10)
    ("imp_prior_adj_aje", "U", "editable", "amount", "impPriorAdjAje", "账项调整", "U10"),
    ("imp_prior_adj_rje", "V", "editable", "amount", "impPriorAdjRje", "重分类调整", "U10"),
    # 账项调整 (W10:X10)
    ("imp_aje_increase", "W", "editable", "amount", "impAjeIncrease", "本期增加", "W10"),
    ("imp_aje_decrease", "X", "editable", "amount", "impAjeDecrease", "本期减少", "W10"),
    # 重分类调整 (Y10:Z10)
    ("imp_rje_increase", "Y", "editable", "amount", "impRjeIncrease", "本期增加", "Y10"),
    ("imp_rje_decrease", "Z", "editable", "amount", "impRjeDecrease", "本期减少", "Y10"),
    # 审定数 (AA10:AD10)
    ("imp_audited_opening", "AA", "formula", "amount", "impAuditedOpening", "期初数", "AA10"),
    ("imp_audited_increase", "AB", "formula", "amount", "impAuditedIncrease", "本期增加", "AA10"),
    ("imp_audited_decrease", "AC", "formula", "amount", "impAuditedDecrease", "本期减少", "AA10"),
    ("imp_audited_closing", "AD", "formula", "amount", "impAuditedClosing", "期末数", "AA10"),
    # ── 账面价值 (AE9:AF9 / AE10:AF10) ──
    ("net_book_opening", "AE", "formula", "amount", "netBookOpening", "期初数", "AE10"),
    ("net_book_closing", "AF", "formula", "amount", "netBookClosing", "期末数", "AE10"),
    # ── 备注 (AG9:AG11 纵向合并) ──
    ("remark", "AG", "editable", "text", "remark", "备注", ""),
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
        managed_sheet=MANAGED_SHEET_G302,
        sheet_key="g302-managed",
        table_key=table_key,
        template_id=f"{TEMPLATE_ID_G302}{template_suffix}",
        table_name=f"GT_{TEMPLATE_ID_G302}_{table_key.upper()}",
        uuid_col=uuid_col,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        footer_row=footer_row,
        header_group_row=HEADER_L1_ROW_G302,
        header_leaf_row=HEADER_LEAF_ROW_G302,
        store_item_id=STORE_ITEM_ID_G302,
        empty_payload="[]",
        row_identity_key=ROW_IDENTITY_STORE_KEY_G302,
        store_kind=StoreKind.rows,
        field_specs=FIELD_SPECS_G302,
        formula_columns=FORMULA_COLUMNS_G302,
        formula_templates=FORMULA_TEMPLATES_G302,
        footer_marker=FOOTER_MARKER_G302,
        footer_carries_total_formula=True,
        error_label=error_label,
        row_section_field=ROW_SECTION_FIELD_G302,
        row_section_value=section_value,
        ghost_row_anchor_index=0,
    )


#: 区① 账龄一年以内（R12 区标题）
SPEC_G302_R1: Final[RowTableSheetSpec] = _section_spec(
    table_key="g3_2_rows_r1",
    template_suffix="R1",
    uuid_col="AH",
    first_data_row=13,
    last_data_row=20,
    footer_row=21,
    section_value="within_one_year",
    error_label="G3-2 应收股利明细表（账龄一年以内）",
)

#: 区② 账龄一年以上（R22 区标题）
SPEC_G302_R2: Final[RowTableSheetSpec] = _section_spec(
    table_key="g3_2_rows_r2",
    template_suffix="R2",
    uuid_col="AI",
    first_data_row=23,
    last_data_row=28,
    footer_row=29,
    section_value="over_one_year",
    error_label="G3-2 应收股利明细表（账龄一年以上）",
)

ALL_SPECS_G302: Final[tuple[RowTableSheetSpec, ...]] = (SPEC_G302_R1, SPEC_G302_R2)
