# -*- coding: utf-8 -*-
"""F1-2「明细表」—— 两级表头 + 三套 nested 账龄。

spec: f1-sync-coverage-and-first-canary · Task 19

═══ 几何（openpyxl 逐格实测）═══

两级表头 R12（组标题）/ R13（叶子标题）· 数据区 R14-34 · footer R35「合计」
四列公式：H=E+F+G / O=E+M-N / Q=O+P / X=O+V+W
三套 nested 账龄：agingPrior(I-L) / agingCurrent(R-U) / agingAudited(Y-AB)
UUID 列 AF

═══ 仅 THREE_YEAR 启用（需求 3.3）═══

模板只有 4 列账龄格（within1/y1to2/y2to3/over3）；
非 THREE_YEAR 时受管关闭 + 中文原因。

═══ 口径已修复（Task 17 裁决 F1-H3）═══

O = E + M - N（模板权威，以期初未审起算）
X = O + V + W（模板权威，以期末余额起算）
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    AgingGroupSpec,
    AgingLayout,
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F102",
    "MANAGED_SHEET_F102",
    "STORE_ITEM_ID_F102",
]

MANAGED_SHEET_F102: Final[str] = "明细表F1-2"
TEMPLATE_ID_F102: Final[str] = "F12"
SHEET_KEY_F102: Final[str] = "f12-managed"
ROWS_TABLE_KEY_F102: Final[str] = "prepayment_detail_rows"
STORE_ITEM_ID_F102: Final[str] = "F1-det-rows"
ROW_IDENTITY_F102: Final[str] = "rowId"

HEADER_GROUP_ROW_F102: Final[int] = 12
HEADER_LEAF_ROW_F102: Final[int] = 13
FIRST_DATA_ROW_F102: Final[int] = 14
LAST_DATA_ROW_F102: Final[int] = 34
FOOTER_ROW_F102: Final[int] = 35
FOOTER_MARKER_F102: Final[str] = "合计"
UUID_COL_F102: Final[str] = "AF"


#: THREE_YEAR 的 4 段（与前端 useAgingConfig DEFAULT_SUBJECT_PRESETS['F1'] 一致）。
AGING_SEGMENTS_F102: Final[tuple[tuple[str, str], ...]] = (
    ("within1", "1年以下"),
    ("y1to2", "1～2年"),
    ("y2to3", "2～3年"),
    ("over3", "3年以上"),
)

#: 三个账龄组：期初审定(I-L) / 期末未审(R-U) / 审定(Y-AB)。
AGING_GROUPS_F102: Final[tuple[AgingGroupSpec, ...]] = (
    AgingGroupSpec(
        json_prefix="agingPrior",
        group_header_cell=f"I{HEADER_GROUP_ROW_F102}",
        segments=tuple(
            (seg_key, col)
            for (seg_key, _), col in zip(AGING_SEGMENTS_F102, ("I", "J", "K", "L"))
        ),
        leaf_labels=tuple(label for _, label in AGING_SEGMENTS_F102),
    ),
    AgingGroupSpec(
        json_prefix="agingCurrent",
        group_header_cell=f"R{HEADER_GROUP_ROW_F102}",
        segments=tuple(
            (seg_key, col)
            for (seg_key, _), col in zip(AGING_SEGMENTS_F102, ("R", "S", "T", "U"))
        ),
        leaf_labels=tuple(label for _, label in AGING_SEGMENTS_F102),
    ),
    AgingGroupSpec(
        json_prefix="agingAudited",
        group_header_cell=f"Y{HEADER_GROUP_ROW_F102}",
        segments=tuple(
            (seg_key, col)
            for (seg_key, _), col in zip(AGING_SEGMENTS_F102, ("Y", "Z", "AA", "AB"))
        ),
        leaf_labels=tuple(label for _, label in AGING_SEGMENTS_F102),
    ),
)


#: 19 个标量列（非账龄）。键名取自 useF1Detail.DetailRow + 真库载荷 23 键。
#: H/O/Q/X 四列模板逐行有真公式 ⇒ formula；其余无公式 ⇒ editable。
SCALAR_FIELD_SPECS_F102: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("customer_name", "A", "editable", "text", "customerName", "债权人名称", ""),
    ("company_code", "B", "editable", "text", "companyCode", "公司代码", ""),
    ("relation_type", "C", "editable", "text", "relationType", "关联方类型", ""),
    ("nature", "D", "editable", "text", "nature", "款项性质", ""),
    ("prior_unadjusted", "E", "editable", "amount", "priorUnadjusted", "期初未审数", ""),
    ("prior_adjustment", "F", "editable", "amount", "priorAdjustment", "期初调整", ""),
    ("prior_reclass", "G", "editable", "amount", "priorReclass", "期初重分类", ""),
    ("prior_audited", "H", "formula", "amount", "priorAudited", "期初审定数", ""),
    ("debit", "M", "editable", "amount", "debit", "借方发生", ""),
    ("credit", "N", "editable", "amount", "credit", "贷方发生", ""),
    ("end_balance", "O", "formula", "amount", "endBalance", "期末余额", ""),
    ("entity_reclass", "P", "editable", "amount", "entityReclass", "被审计单位重分类", ""),
    ("end_unadjusted", "Q", "formula", "amount", "endUnadjusted", "期末未审数", ""),
    ("end_aje", "V", "editable", "amount", "endAje", "审计调整", ""),
    ("end_rje", "W", "editable", "amount", "endRje", "重分类调整", ""),
    ("end_audited", "X", "formula", "amount", "endAudited", "审定数", ""),
    ("is_confirmed", "AC", "editable", "text", "isConfirmed", "是否函证", ""),
    ("post_period_settlement", "AD", "editable", "amount", "postPeriodSettlement", "期后结算", ""),
    ("remark", "AE", "editable", "text", "remark", "备注", ""),
)

SPEC_F102: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F102,
    sheet_key=SHEET_KEY_F102,
    table_key=ROWS_TABLE_KEY_F102,
    template_id=TEMPLATE_ID_F102,
    table_name=f"GT_{TEMPLATE_ID_F102}_ROWS",
    uuid_col=UUID_COL_F102,
    first_data_row=FIRST_DATA_ROW_F102,
    last_data_row=LAST_DATA_ROW_F102,
    footer_row=FOOTER_ROW_F102,
    header_group_row=HEADER_GROUP_ROW_F102,
    header_leaf_row=HEADER_LEAF_ROW_F102,
    store_item_id=STORE_ITEM_ID_F102,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_F102,
    store_kind=StoreKind.rows,
    field_specs=SCALAR_FIELD_SPECS_F102,
    formula_columns=("H", "O", "Q", "X"),
    aging_layout=AgingLayout.nested,
    aging_groups=AGING_GROUPS_F102,
    footer_marker=FOOTER_MARKER_F102,
    error_label="F1-2 明细表",
)
