# -*- coding: utf-8 -*-
"""G5-2「余额明细表」—— sheet 层薄声明（三段 × 四子区 = 12 个受管区）。

spec: `g5-nested-sections-and-template-defects` · Task 9~10

═══ 几何（openpyxl 逐格实测）═══

`余额明细表G5-2`：`max_row=115` / `max_col=22` / merged 56。

* **两级表头 R10/R11**：R10 主列 + R11 账龄段（N 未逾期 / O 1年以内 / P 1-2年 / Q 2-3年 / R 3年以上）。
* **三段 × 四子区**（每子区 5 行数据 + 1 行小计，段末 1 行合计）：
  * 段①（一）R12-40：子区1 R13-17/R18 · 子区2 R20-24/R25 · 子区3 R27-31/R32 · 子区4 R34-38/R39 · 合计 R40
  * 段②（二）R41-72：同结构 R45-49/R50 · R52-56/R57 · R59-63/R64 · R66-70/R71 · 合计 R72
  * 段③（三）R73-104：同结构 R77-81/R82 · R84-88/R89 · R91-95/R96 · R98-102/R103 · 合计 R104
* 🔴 **三处合计漏加小计**：R40 `=G18+G25+G39` 漏 G32 · R72 `=G50+G57+G71` 漏 G64 · R104 `=G82+G89+G103` 漏 G96
* **公式列 3 个**：G(`=D+E+F`) J(`=D+H-I`) M(`=J+K+L`)
* 有效列 22（A..V） ⇒ uuid 取 **W** 列（每子区共用，但 `row_section_field` 过滤）。
* payload **dual_write**（remark + conclusion 逐字相同）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "ALL_SPECS_G502",
    "MANAGED_SHEET_G502",
    "STORE_ITEM_ID_G502",
    "FORMULA_COLUMNS_G502",
    "FORMULA_TEMPLATES_G502",
    "FIELD_SPECS_G502",
]

MANAGED_SHEET_G502: Final[str] = "余额明细表G5-2"
TEMPLATE_ID_G502: Final[str] = "G502"
STORE_ITEM_ID_G502: Final[str] = "G5-2-rows"
ROW_IDENTITY_STORE_KEY_G502: Final[str] = "id"
ROW_SECTION_FIELD_G502: Final[str] = "sectionKey"

HEADER_GROUP_ROW_G502: Final[int] = 10
HEADER_LEAF_ROW_G502: Final[int] = 11

FORMULA_COLUMNS_G502: Final[tuple[str, ...]] = ("G", "J", "M")
FORMULA_TEMPLATES_G502: Final[dict[str, str]] = {
    "G": "=D{r}+E{r}+F{r}",    # 期初审定数 = 期初余额 + 期初调整 + 期初重分类
    "J": "=D{r}+H{r}-I{r}",    # 期末余额 = 期初余额 + 借方发生 - 贷方发生
    "M": "=J{r}+K{r}+L{r}",    # 审定数 = 期末余额 + 账项调整 + 重分类调整
}

#: 22 个受管字段（A..V）。
FIELD_SPECS_G502: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("seq", "A", "editable", "text", "seq", "序号", ""),
    ("debtor_name", "B", "editable", "text", "debtorName", "债务人名称", ""),
    ("is_related", "C", "editable", "text", "isRelated", "是否关联方", ""),
    ("opening_balance", "D", "editable", "amount", "openingBalance", "期初余额", ""),
    ("opening_adj", "E", "editable", "amount", "openingAdj", "期初调整数", ""),
    ("opening_rje", "F", "editable", "amount", "openingRje", "期初重分类数", ""),
    ("opening_audited", "G", "formula", "amount", "openingAudited", "期初审定数", ""),
    ("debit_incurred", "H", "editable", "amount", "debitIncurred", "借方发生", ""),
    ("credit_incurred", "I", "editable", "amount", "creditIncurred", "贷方发生", ""),
    ("closing_balance", "J", "formula", "amount", "closingBalance", "期末余额", ""),
    ("aje", "K", "editable", "amount", "aje", "账项调整", ""),
    ("rje", "L", "editable", "amount", "rje", "重分类调整", ""),
    ("audited_amount", "M", "formula", "amount", "auditedAmount", "长期应收款原值审定数", ""),
    # 账龄段 (N10:R10)
    ("aging_not_overdue", "N", "editable", "amount", "agingNotOverdue", "未逾期", "N10"),
    ("aging_within_1y", "O", "editable", "amount", "agingWithin1y", "1年以内", "N10"),
    ("aging_1to2y", "P", "editable", "amount", "aging1to2y", "1-2年", "N10"),
    ("aging_2to3y", "Q", "editable", "amount", "aging2to3y", "2-3年", "N10"),
    ("aging_over_3y", "R", "editable", "amount", "agingOver3y", "3年以上", "N10"),
    # 信用风险
    ("ecl_method", "S", "editable", "text", "eclMethod", "信用风险组合方式", ""),
    ("ecl_group_name", "T", "editable", "text", "eclGroupName", "组合名称", ""),
    # 发函 / 索引
    ("confirmation_status", "U", "editable", "text", "confirmationStatus", "发函情况", ""),
    ("subsequent_ref", "V", "editable", "text", "subsequentRef", "期后收款/替代程序索引", ""),
)

# ────────────────────────────────────────────────────────────────
# 三段 × 四子区 = 12 个 spec
# ────────────────────────────────────────────────────────────────

_SECTIONS: Final[list[dict]] = [
    # 段①（一）应收融资租赁款
    {"key": "s1r1", "sfx": "S1R1", "first": 13, "last": 17, "footer": 18, "val": "s1_finance_lease"},
    {"key": "s1r2", "sfx": "S1R2", "first": 20, "last": 24, "footer": 25, "val": "s1_installment_sale"},
    {"key": "s1r3", "sfx": "S1R3", "first": 27, "last": 31, "footer": 32, "val": "s1_installment_service"},
    {"key": "s1r4", "sfx": "S1R4", "first": 34, "last": 37, "footer": 39, "val": "s1_other"},
    # 段②（二）未确认融资收益
    {"key": "s2r1", "sfx": "S2R1", "first": 45, "last": 49, "footer": 50, "val": "s2_finance_lease"},
    {"key": "s2r2", "sfx": "S2R2", "first": 52, "last": 56, "footer": 57, "val": "s2_installment_sale"},
    {"key": "s2r3", "sfx": "S2R3", "first": 59, "last": 63, "footer": 64, "val": "s2_installment_service"},
    {"key": "s2r4", "sfx": "S2R4", "first": 66, "last": 70, "footer": 71, "val": "s2_other"},
    # 段③（三）余额（原值-未确认融资收益）
    {"key": "s3r1", "sfx": "S3R1", "first": 77, "last": 81, "footer": 82, "val": "s3_finance_lease"},
    {"key": "s3r2", "sfx": "S3R2", "first": 84, "last": 88, "footer": 89, "val": "s3_installment_sale"},
    {"key": "s3r3", "sfx": "S3R3", "first": 91, "last": 95, "footer": 96, "val": "s3_installment_service"},
    {"key": "s3r4", "sfx": "S3R4", "first": 98, "last": 102, "footer": 103, "val": "s3_other"},
]

_SEGMENT_LABELS: Final[dict[str, str]] = {
    "S1R1": "段①子区1 应收融资租赁款",
    "S1R2": "段①子区2 应收分期收款销售商品款",
    "S1R3": "段①子区3 应收分期收款提供劳务款",
    "S1R4": "段①子区4 其他",
    "S2R1": "段②子区1 应收融资租赁款",
    "S2R2": "段②子区2 应收分期收款销售商品款",
    "S2R3": "段②子区3 应收分期收款提供劳务款",
    "S2R4": "段②子区4 其他",
    "S3R1": "段③子区1 应收融资租赁款",
    "S3R2": "段③子区2 应收分期收款销售商品款",
    "S3R3": "段③子区3 应收分期收款提供劳务款",
    "S3R4": "段③子区4 其他",
}


def _build_spec(sec: dict) -> RowTableSheetSpec:
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET_G502,
        sheet_key="g502-managed",
        table_key=f"g5_2_{sec['key']}",
        template_id=f"{TEMPLATE_ID_G502}{sec['sfx']}",
        table_name=f"GT_{TEMPLATE_ID_G502}_{sec['key'].upper()}",
        uuid_col="W",
        first_data_row=sec["first"],
        last_data_row=sec["last"],
        footer_row=sec["footer"],
        header_group_row=HEADER_GROUP_ROW_G502,
        header_leaf_row=HEADER_LEAF_ROW_G502,
        store_item_id=STORE_ITEM_ID_G502,
        empty_payload="[]",
        row_identity_key=ROW_IDENTITY_STORE_KEY_G502,
        store_kind=StoreKind.rows,
        field_specs=FIELD_SPECS_G502,
        formula_columns=FORMULA_COLUMNS_G502,
        formula_templates=FORMULA_TEMPLATES_G502,
        footer_marker="小计",
        footer_carries_total_formula=True,
        error_label=f"G5-2 {_SEGMENT_LABELS[sec['sfx']]}",
        row_section_field=ROW_SECTION_FIELD_G502,
        row_section_value=sec["val"],
        ghost_row_anchor_index=1,
    )


ALL_SPECS_G502: Final[tuple[RowTableSheetSpec, ...]] = tuple(
    _build_spec(s) for s in _SECTIONS
)

# 段合计行（不受管，但三处漏加小计须在判据里验证）
SEGMENT_TOTAL_ROWS_G502: Final[tuple[int, ...]] = (40, 72, 104)
# 🔴 三处漏加的小计行号
MISSING_SUBTOTAL_IN_TOTALS_G502: Final[tuple[int, ...]] = (32, 64, 96)
