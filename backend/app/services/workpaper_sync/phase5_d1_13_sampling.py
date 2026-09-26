# -*- coding: utf-8 -*-
"""D1-13「应收票据检查表」—— sheet 层薄声明（**双区**）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 29 · Requirements 5.1

═══ 几何（openpyxl 直读实测，2026-09-26）═══

| 区 | 标题 | 表头 | 数据行 | footer | 公式列 | store 键 | UUID 列 |
|---|---|---|---|---|---|---|---|
| 增减变动检查 | R13（1） | R14-15（两级） | R16-R31 (16行) | R32 `合计` | G/H SUM | `D1-sampling-vouching-rows` | R |
| 期后检查 | R34（2） | R35-36（两级） | R37-R44 (8行) | R45 `合计` | G SUM | `D1-sampling-specific-samples` | S |

两区共 managed_sheet 与 sheet_key，各自独立 UUID 列（R/S，max_col=Q=17 故从 R 起）。

🔴 **区一 17 列 A-Q 宽表**：R14 分组表头（记账凭证 B-H / 核对内容 J-N）+ R15 叶子。
核对内容 J-N 在模板里是 5 个编号列（1~5），前端映射为 3 个语义字段
（existenceCheck/accuracyCheck/appropriatenessCheck）—— 模板5列 vs 前端3字段是既有设计，
**本声明按模板实际列数（17）声明**，json_key 在前端不匹配的位置按 check1~check5 命名
（前端侧若未来要走 OO 双向，需在 composable 加映射）。

🔴 **区二仅 4 个前端字段**（id/description/amount/reason），但模板有 17 列同区一——
实际上区二的「核对内容」列在模板里也画了 5 个编号但前端不用。声明仍按模板实际表头。

🔴 数据区无行级公式，公式仅在 footer SUM。
🔴 `row_identity_key = "id"`。
🔴 R47-R50 是检查比例核对区（全公式+跨 sheet 引用），不受管。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_D113_VOUCHING",
    "SPEC_D113_SPECIFIC",
    "SPECS_D113",
    "MANAGED_SHEET_D113",
]

MANAGED_SHEET_D113: Final[str] = "应收票据检查表D1-13"
TEMPLATE_ID_D113: Final[str] = "D113"
SHEET_KEY_D113: Final[str] = f"{TEMPLATE_ID_D113.lower()}-managed"

HEADER_GROUP_ROW_VOUCHING: Final[int] = 14
HEADER_LEAF_ROW_VOUCHING: Final[int] = 15
HEADER_GROUP_ROW_SPECIFIC: Final[int] = 35
HEADER_LEAF_ROW_SPECIFIC: Final[int] = 36

FOOTER_ROW_VOUCHING: Final[int] = 32
FOOTER_ROW_SPECIFIC: Final[int] = 45
FOOTER_MARKER_D113: Final[str] = "合计"  # [5408 8ba1]

#: ──── 区一（增减变动检查）field_specs（17 列 A-Q）────
_FIELD_SPECS_VOUCHING: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("detail_item", "A", "editable", "text", "noteType", "明细项目", ""),
    ("voucher_date", "B", "editable", "text", "voucherDate", "日期", f"B{HEADER_GROUP_ROW_VOUCHING}"),
    ("voucher_no", "C", "editable", "text", "noteNo", "凭证编号", f"B{HEADER_GROUP_ROW_VOUCHING}"),
    ("content", "D", "editable", "text", "drawer", "业务内容", f"B{HEADER_GROUP_ROW_VOUCHING}"),
    ("counter_account", "E", "editable", "text", "acceptor", "对方科目", f"B{HEADER_GROUP_ROW_VOUCHING}"),
    ("counter_detail", "F", "editable", "text", "counterDetail", "对方明细科目", f"B{HEADER_GROUP_ROW_VOUCHING}"),
    ("debit_amount", "G", "editable", "amount", "amount", "借方金额", f"B{HEADER_GROUP_ROW_VOUCHING}"),
    ("credit_amount", "H", "editable", "amount", "creditAmount", "贷方金额", f"B{HEADER_GROUP_ROW_VOUCHING}"),
    ("support_doc", "I", "editable", "text", "supportDoc", "支持性文件", ""),
    ("check1", "J", "editable", "text", "existenceCheck", "核对内容1", f"J{HEADER_GROUP_ROW_VOUCHING}"),
    ("check2", "K", "editable", "text", "accuracyCheck", "核对内容2", f"J{HEADER_GROUP_ROW_VOUCHING}"),
    ("check3", "L", "editable", "text", "appropriatenessCheck", "核对内容3", f"J{HEADER_GROUP_ROW_VOUCHING}"),
    ("check4", "M", "editable", "text", "check4", "核对内容4", f"J{HEADER_GROUP_ROW_VOUCHING}"),
    ("check5", "N", "editable", "text", "check5", "核对内容5", f"J{HEADER_GROUP_ROW_VOUCHING}"),
    ("index_ref", "O", "editable", "text", "indexRef", "索引号", ""),
    ("is_abnormal", "P", "editable", "text", "isAbnormal", "是否异常", ""),
    ("remark", "Q", "editable", "text", "remark", "备注说明", ""),
)

#: ──── 区二（期后检查）field_specs ────
#: 区二模板表头 R35-36 与区一 R14-15 **不同**：缺借方金额（H列变空），只有贷方金额（G列）。
#: 但前端 SpecificSampleRow 仅 4 字段（id/description/amount/reason），其余列在前端不可见。
_FIELD_SPECS_SPECIFIC: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("detail_item", "A", "editable", "text", "description", "明细项目", ""),
    ("voucher_date", "B", "editable", "text", "voucherDate", "日期", f"B{HEADER_GROUP_ROW_SPECIFIC}"),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证编号", f"B{HEADER_GROUP_ROW_SPECIFIC}"),
    ("content", "D", "editable", "text", "content", "业务内容", f"B{HEADER_GROUP_ROW_SPECIFIC}"),
    ("counter_account", "E", "editable", "text", "counterAccount", "对方科目", f"B{HEADER_GROUP_ROW_SPECIFIC}"),
    ("counter_detail", "F", "editable", "text", "counterDetail", "对方明细科目", f"B{HEADER_GROUP_ROW_SPECIFIC}"),
    ("amount", "G", "editable", "amount", "amount", "贷方金额", f"B{HEADER_GROUP_ROW_SPECIFIC}"),
    ("support_doc", "H", "editable", "text", "supportDoc", "支持性文件", ""),
    ("check1", "J", "editable", "text", "check1", "核对内容1", f"J{HEADER_GROUP_ROW_SPECIFIC}"),
    ("check2", "K", "editable", "text", "check2", "核对内容2", f"J{HEADER_GROUP_ROW_SPECIFIC}"),
    ("check3", "L", "editable", "text", "check3", "核对内容3", f"J{HEADER_GROUP_ROW_SPECIFIC}"),
    ("check4", "M", "editable", "text", "check4", "核对内容4", f"J{HEADER_GROUP_ROW_SPECIFIC}"),
    ("check5", "N", "editable", "text", "check5", "核对内容5", f"J{HEADER_GROUP_ROW_SPECIFIC}"),
    ("index_ref", "O", "editable", "text", "indexRef", "索引号", ""),
    ("is_abnormal", "P", "editable", "text", "isAbnormal", "是否异常", ""),
    ("remark", "Q", "editable", "text", "reason", "备注说明", ""),
)

_FORMULA_COLUMNS_VOUCHING: Final[tuple[str, ...]] = ("G", "H")
_FORMULA_TEMPLATES_VOUCHING: Final[dict[str, str]] = {
    "G": "=SUM(G16:G{r})", "H": "=SUM(H16:H{r})",
}

_FORMULA_COLUMNS_SPECIFIC: Final[tuple[str, ...]] = ("G",)
_FORMULA_TEMPLATES_SPECIFIC: Final[dict[str, str]] = {"G": "=SUM(G37:G{r})"}


SPEC_D113_VOUCHING: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D113,
    sheet_key=SHEET_KEY_D113,
    table_key="sampling_vouching_rows",
    template_id=f"{TEMPLATE_ID_D113}VOUCH",
    table_name=f"GT_{TEMPLATE_ID_D113}_VOUCHING_ROWS",
    uuid_col="R",
    first_data_row=16,
    last_data_row=31,
    footer_row=FOOTER_ROW_VOUCHING,
    header_group_row=HEADER_GROUP_ROW_VOUCHING,
    header_leaf_row=HEADER_LEAF_ROW_VOUCHING,
    store_item_id="D1-sampling-vouching-rows",
    empty_payload="[]",
    row_identity_key="id",
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_VOUCHING,
    formula_columns=_FORMULA_COLUMNS_VOUCHING,
    formula_templates=_FORMULA_TEMPLATES_VOUCHING,
    footer_marker=FOOTER_MARKER_D113,
    error_label="D1-13 增减变动检查",
)

SPEC_D113_SPECIFIC: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D113,
    sheet_key=SHEET_KEY_D113,
    table_key="sampling_specific_samples",
    template_id=f"{TEMPLATE_ID_D113}SPEC",
    table_name=f"GT_{TEMPLATE_ID_D113}_SPECIFIC_ROWS",
    uuid_col="S",
    first_data_row=37,
    last_data_row=44,
    footer_row=FOOTER_ROW_SPECIFIC,
    header_group_row=HEADER_GROUP_ROW_SPECIFIC,
    header_leaf_row=HEADER_LEAF_ROW_SPECIFIC,
    store_item_id="D1-sampling-specific-samples",
    empty_payload="[]",
    row_identity_key="id",
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_SPECIFIC,
    formula_columns=_FORMULA_COLUMNS_SPECIFIC,
    formula_templates=_FORMULA_TEMPLATES_SPECIFIC,
    footer_marker=FOOTER_MARKER_D113,
    error_label="D1-13 期后检查",
)

SPECS_D113: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_D113_VOUCHING,
    SPEC_D113_SPECIFIC,
)
