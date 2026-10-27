# -*- coding: utf-8 -*-
"""D6-3「合同资产减值准备明细表」—— sheet 层薄声明（**双区**：按单项评估计提 / 信用风险组合计提）。

spec: d567-sync-coverage-via-row-table-engine · Task 9 · Requirements 2.1；
双区与列对齐：spec oo-writeback-template-parity-closure R3 任务 9（批 A2）。

几何（openpyxl 直读权威模板 D/D6 合同资产.xlsx）：29r × 14c(N)。
两级表头 R10（组：项目 / 期初数 / 本期增加 / 本期减少 / 期末数）+ R11（叶子）。

| 区 | 父行（SUM 小计，不落库） | 数据行 | 分区值 category | UUID 列 |
|---|---|---|---|---|
| 按单项评估计提 | R12 = SUM(13:16) | 13-16 | single | O |
| 信用风险组合计提 | R17 = SUM(18:21) | 18-21 | group | P |

footer R22「合计」= R12 + R17（两区共用，同 D1-4 / D2-3）。数据行公式逐行
E = B+C+D、K = B+SUM(F:G)-SUM(H:J)、N = K+L+M。

🔴 两区共用一个 store 键 `D6-3-rows`：前端 `useD6ImpairmentDetail` 把两区的行存在同一个数组里、
   用行内 `category`（'single' | 'group'）分组 ⇒ 引擎 `row_section_field="category"` + 各区
   `row_section_value` 过滤（同 G9 / G1 / L5 的分段范式），不拆键（真库 D6-3-rows 0 行，但前端、
   导入导出、预填锚点都读这一个键）。

🔴 原声明的错位（R3 修正，模板与前端逐列核对）：只受管单项区，且 B 列接成 `category`（模板 B 是
   期初未审余额）、C → priorUnadjusted、D → priorAje，priorRje 没接 ⇒ 模板 E = B+C+D 代入的是分类
   文本、K 的期初起点也接成了分类；组合区的行全被投影进单项区。改为 B/C/D = 期初未审 / 账项调整 /
   重分类调整，json 键与前端 `ImpairmentDetailRow` 逐字段同名；`category` 不是模板列，改作分区字段。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = [
    "SPEC_D603_SINGLE",
    "SPEC_D603_GROUP",
    "SPECS_D603",
    "MANAGED_SHEET_D603",
    "STORE_ITEM_ID_D603",
]

MANAGED_SHEET_D603: Final[str] = "合同资产减值准备明细表D6-3"
TEMPLATE_ID_D603: Final[str] = "D63"
SHEET_KEY_D603: Final[str] = "d63-managed"
STORE_ITEM_ID_D603: Final[str] = "D6-3-rows"
ROW_IDENTITY_STORE_KEY_D603: Final[str] = "rowId"
#: 分区字段（前端 `ImpairmentDetailRow.category`）。
ROW_SECTION_FIELD_D603: Final[str] = "category"

HEADER_GROUP_ROW_D603: Final[int] = 10
HEADER_LEAF_ROW_D603: Final[int] = 11
FOOTER_ROW_D603: Final[int] = 22
FOOTER_MARKER_D603: Final[str] = "合计"

#: 14 列受管字段（7 元组，末位 = R10 组标题格）。表头文本取 R11 叶子（A 列取 R10「项目」）。
#: E / K / N 三列逐行有真公式 ⇒ formula。
FIELD_SPECS_D603: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("prior_unadjusted", "B", "editable", "amount", "priorUnadjusted", "未审余额", f"B{HEADER_GROUP_ROW_D603}"),
    ("prior_aje", "C", "editable", "amount", "priorAje", "账项调整", f"B{HEADER_GROUP_ROW_D603}"),
    ("prior_rje", "D", "editable", "amount", "priorRje", "重分类调整", f"B{HEADER_GROUP_ROW_D603}"),
    ("prior_audited", "E", "formula", "amount", "priorAudited", "审定余额", f"B{HEADER_GROUP_ROW_D603}"),
    ("provision", "F", "editable", "amount", "provision", "计提", f"F{HEADER_GROUP_ROW_D603}"),
    ("other_increase", "G", "editable", "amount", "otherIncrease", "其他增加", f"F{HEADER_GROUP_ROW_D603}"),
    ("reversal", "H", "editable", "amount", "reversal", "转回", f"H{HEADER_GROUP_ROW_D603}"),
    ("write_off", "I", "editable", "amount", "writeOff", "核销", f"H{HEADER_GROUP_ROW_D603}"),
    ("other_decrease", "J", "editable", "amount", "otherDecrease", "其他减少", f"H{HEADER_GROUP_ROW_D603}"),
    ("end_unadjusted", "K", "formula", "amount", "endUnadjusted", "未审余额", f"K{HEADER_GROUP_ROW_D603}"),
    ("end_aje", "L", "editable", "amount", "endAje", "账项调整", f"K{HEADER_GROUP_ROW_D603}"),
    ("end_rje", "M", "editable", "amount", "endRje", "重分类调整", f"K{HEADER_GROUP_ROW_D603}"),
    ("end_audited", "N", "formula", "amount", "endAudited", "审定余额", f"K{HEADER_GROUP_ROW_D603}"),
)


def _region_spec(
    *, section: str, table_key: str, first_data_row: int, last_data_row: int, uuid_col: str, label: str,
) -> RowTableSheetSpec:
    """两区只差行区间 / 分区值 / UUID 列 / 表键，字段与表头共用一份（不复制两份声明）。"""
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET_D603,
        sheet_key=SHEET_KEY_D603,
        table_key=table_key,
        template_id=f"{TEMPLATE_ID_D603}{section[0].upper()}",
        table_name=f"GT_{TEMPLATE_ID_D603}{section[0].upper()}_ROWS",
        uuid_col=uuid_col,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        footer_row=FOOTER_ROW_D603,
        # 扩容面契约构建器（phase5_d567_expansion_contract）按 header_row 取表头格；
        # 组标题格由 field_specs 第 7 位给出（group_source_ref）。
        header_row=HEADER_LEAF_ROW_D603,
        store_item_id=STORE_ITEM_ID_D603,
        empty_payload="[]",
        row_identity_key=ROW_IDENTITY_STORE_KEY_D603,
        store_kind=StoreKind.rows,
        field_specs=FIELD_SPECS_D603,
        formula_columns=("E", "K", "N"),
        aging_layout=None,  # D6-3 无账龄组（明细表级别，不同于 D6-2）
        footer_marker=FOOTER_MARKER_D603,
        error_label=f"D6-3 减值准备明细表（{label}）",
        row_section_field=ROW_SECTION_FIELD_D603,
        row_section_value=section,
    )


#: 区一：按单项评估计提（父行 R12，数据 13-16，UUID 列 O）。
SPEC_D603_SINGLE: Final[RowTableSheetSpec] = _region_spec(
    section="single", table_key="impairment_single_rows",
    first_data_row=13, last_data_row=16, uuid_col="O", label="按单项评估计提",
)

#: 区二：信用风险组合计提（父行 R17，数据 18-21，UUID 列 P —— 两区不同 UUID 列，防行身份串区）。
SPEC_D603_GROUP: Final[RowTableSheetSpec] = _region_spec(
    section="group", table_key="impairment_group_rows",
    first_data_row=18, last_data_row=21, uuid_col="P", label="信用风险组合计提",
)

#: 双区清单（顺序即 Excel 行序）。
SPECS_D603: Final[tuple[RowTableSheetSpec, ...]] = (SPEC_D603_SINGLE, SPEC_D603_GROUP)
