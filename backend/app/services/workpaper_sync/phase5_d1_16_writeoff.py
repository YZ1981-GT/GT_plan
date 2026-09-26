# -*- coding: utf-8 -*-
"""D1-16「坏账准备转回、核销检查表」—— sheet 层薄声明（**双区**）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 27 · Requirements 5.1 / 5.4

═══ 几何（openpyxl 直读实测，2026-09-26）═══

| 区 | 标题 | 表头 | 数据行 | footer | 公式列 | store 键 | UUID 列 |
|---|---|---|---|---|---|---|---|
| 转回 | R10（一） | R11（单级） | R12-R14 (3行) | R15 `合计` | E/F SUM | `D1-writeoff-reversal-rows` | I |
| 核销 | R16（二） | R17（单级） | R18-R20 (3行) | R21 `合计` | C SUM | `D1-writeoff-writeoff-rows` | J |

两区共 managed_sheet 与 sheet_key，各自独立 UUID 列（I/J，max_col=H=8 故注入列从 I 起）。
两区 footer marker 逐字相同 `合计`（codepoints 5408 8ba1）。

🔴 **`row_identity_key = "id"`**（不是 D1-3/D1-4/D1-8 的 `"rowId"`）——前端
`useD1WriteoffCheck.ts` 的 `ReversalRow`/`WriteoffRow` 接口用 `id: string` 作行标识，
与 `useD1EndorsementDetail.ts` 的 `rowId: string` 命名不同。这是**前端既有命名**，
不是 bug；声明必须照前端的 json_key 逐字匹配（materialize/extract 按此键定位行）。

🔴 数据区内零公式（全 editable），公式只在 footer 的 SUM。
🔴 区一有两个 amount 字段（E 转回金额/F 累计已计提），区二只有一个（C 核销金额）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_D116_REVERSAL",
    "SPEC_D116_WRITEOFF",
    "SPECS_D116",
    "MANAGED_SHEET_D116",
]

MANAGED_SHEET_D116: Final[str] = "坏账准备转回、核销检查表D1-16"
TEMPLATE_ID_D116: Final[str] = "D116"
SHEET_KEY_D116: Final[str] = f"{TEMPLATE_ID_D116.lower()}-managed"

FOOTER_ROW_REVERSAL: Final[int] = 15
FOOTER_ROW_WRITEOFF: Final[int] = 21
FOOTER_MARKER_D116: Final[str] = "合计"  # [5408 8ba1]

MANAGED_LAST_COL_D116: Final[str] = "H"

#: ──── 区一（转回）field_specs（8 列 A-H，单级表头 R11）────
_FIELD_SPECS_REVERSAL: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("unit_name", "A", "editable", "text", "unitName", "单位名称", ""),
    ("reason", "B", "editable", "text", "reason", "转回原因", ""),
    ("recovery_method", "C", "editable", "text", "recoveryMethod", "收回方式", ""),
    ("original_basis", "D", "editable", "text", "originalBasis", "原确定坏账准备的依据", ""),
    ("reversal_amount", "E", "editable", "amount", "reversalAmount", "收回或转回金额", ""),
    ("prior_provision_amount", "F", "editable", "amount", "priorProvisionAmount", "收回或转回前累计已计提坏账准备金额", ""),
    ("reasonability_analysis", "G", "editable", "text", "reasonabilityAnalysis", "合理性分析", ""),
    ("index_ref", "H", "editable", "text", "indexRef", "索引号", ""),
)

#: ──── 区二（核销）field_specs（8 列 A-H，单级表头 R17）────
_FIELD_SPECS_WRITEOFF: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("unit_name", "A", "editable", "text", "unitName", "单位名称", ""),
    ("note_nature", "B", "editable", "text", "noteNature", "应收票据的性质", ""),
    ("writeoff_amount", "C", "editable", "amount", "writeoffAmount", "核销金额", ""),
    ("writeoff_reason", "D", "editable", "text", "writeoffReason", "核销原因", ""),
    ("writeoff_procedure", "E", "editable", "text", "writeoffProcedure", "履行的核销程序", ""),
    ("is_related_party", "F", "editable", "text", "isRelatedPartyGenerated", "是否由关联交易产生", ""),
    ("reasonability_analysis", "G", "editable", "text", "reasonabilityAnalysis", "合理性分析", ""),
    ("index_ref", "H", "editable", "text", "indexRef", "索引号", ""),
)

_FORMULA_COLUMNS_REVERSAL: Final[tuple[str, ...]] = ("E", "F")
_FORMULA_TEMPLATES_REVERSAL: Final[dict[str, str]] = {
    "E": "=SUM(E12:E{r})", "F": "=SUM(F12:F{r})",
}

_FORMULA_COLUMNS_WRITEOFF: Final[tuple[str, ...]] = ("C",)
_FORMULA_TEMPLATES_WRITEOFF: Final[dict[str, str]] = {"C": "=SUM(C18:C{r})"}


SPEC_D116_REVERSAL: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D116,
    sheet_key=SHEET_KEY_D116,
    table_key="writeoff_reversal_rows",
    template_id=f"{TEMPLATE_ID_D116}REVERSAL",
    table_name=f"GT_{TEMPLATE_ID_D116}_REVERSAL_ROWS",
    uuid_col="I",
    first_data_row=12,
    last_data_row=14,
    footer_row=FOOTER_ROW_REVERSAL,
    header_row=11,
    store_item_id="D1-writeoff-reversal-rows",
    empty_payload="[]",
    row_identity_key="id",  # 🔴 前端用 `id` 不是 `rowId`
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_REVERSAL,
    formula_columns=_FORMULA_COLUMNS_REVERSAL,
    formula_templates=_FORMULA_TEMPLATES_REVERSAL,
    footer_marker=FOOTER_MARKER_D116,
    error_label="D1-16 坏账准备转回",
)

SPEC_D116_WRITEOFF: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D116,
    sheet_key=SHEET_KEY_D116,
    table_key="writeoff_writeoff_rows",
    template_id=f"{TEMPLATE_ID_D116}WRITEOFF",
    table_name=f"GT_{TEMPLATE_ID_D116}_WRITEOFF_ROWS",
    uuid_col="J",
    first_data_row=18,
    last_data_row=20,
    footer_row=FOOTER_ROW_WRITEOFF,
    header_row=17,
    store_item_id="D1-writeoff-writeoff-rows",
    empty_payload="[]",
    row_identity_key="id",  # 🔴 前端用 `id` 不是 `rowId`
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_WRITEOFF,
    formula_columns=_FORMULA_COLUMNS_WRITEOFF,
    formula_templates=_FORMULA_TEMPLATES_WRITEOFF,
    footer_marker=FOOTER_MARKER_D116,
    error_label="D1-16 坏账准备核销",
)

SPECS_D116: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_D116_REVERSAL,
    SPEC_D116_WRITEOFF,
)
