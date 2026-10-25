# -*- coding: utf-8 -*-
"""F5-3「其他业务成本明细表」—— sheet 层薄声明。

spec: f5-sync-coverage-and-first-canary · Task 14 · Requirements 4.2
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 几何 ═══

两级表头 **R9（组）/ R10（叶子）**：
    A(A9:A10) 项目  |  B~F(B9:F9) 本期数  |  G~K(G9:K9) 上期数  |
    L~M(L9 实际标题跨 L:M) 本期数比上期增加（减少） |  N(N9:N10) 备注

叶子行 R10：B 本期未审数 / C 账项调整 / D 重分类调整 / E 审定数 / F 结构比 /
             G 上期未审数 / H 账项调整 / I 重分类调整 / J 审定额 / K 结构比 /
             L 变动额 / M 变动率

数据区 **R11~R21**（11 行）· footer **R22** 合计。

🔴 R11~R17 七行预填标签（`F5_OTHER_COST_FIXED_ITEMS`）：
    R11 出租固定资产 / R12 出租无形资产 / R13 出租包装物和商品 /
    R14 销售材料 / R15 用材料进行非货币性交换 / R16 用材料进行债务重组 /
    R17 与投资性房地产相关的支出...
    R18 "……" / R19~R21 空行

这些标签是模板预填（不是用户输入），照 E1-2 `PREFILLED_CURRENCY_ROWS` 范式登记为**预填行**。

═══ 公式列（6 列，逐行同构）═══

    E{r} = B{r}+C{r}+D{r}                         审定数 = 未审+AJE+RJE
    F{r} = IF(E{r}=0,0,E{r}/E$22)                 结构比（审定数/合计审定数）
    J{r} = G{r}+H{r}+I{r}                         上期审定额
    K{r} = IF(J{r}=0,0,J{r}/$J$22)               上期结构比
    L{r} = E{r}-J{r}                              变动额
    M{r} = IF(AND(J{r}=0,L{r}=0),0,IF(AND(J{r}=0,L{r}>0),1,L{r}/J{r}))  变动率

🔴 除零容错（前端 `calcF5OtherCostChangeRate`）：prior=0 且 change=0→0%，change>0→100%，
change<0→-100%。与 F5-5 的 N/A 逻辑不同。

═══ footer ═══

R22「合计」，B~M 全部 12 列有 SUM 或公式。footer_carries_total_formula=True。

═══ UUID 列 ═══

max_col=N(14)，O 列 non_null=0 ⇒ 取 **O**。

═══ 字段 ═══

行身份 **`id`**（F5 系列统一）。
前端 `STORAGE_KEY = 'F5-3-other-cost-rows'`。
store-only: `isFixed`（前端固定行标记，7 个预填科目用）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F503",
    "MANAGED_SHEET_F503",
    "STORE_ITEM_ID_F503",
    "STORE_ONLY_KEYS_F503",
    "PREFILLED_ROWS_F503",
]

MANAGED_SHEET_F503: Final[str] = "其他业务成本明细表F5-3"
TEMPLATE_ID_F503: Final[str] = "F53"
SHEET_KEY_F503: Final[str] = "f53-managed"
ROWS_TABLE_KEY_F503: Final[str] = "other_cost_rows"
STORE_ITEM_ID_F503: Final[str] = "F5-3-other-cost-rows"

ROW_IDENTITY_STORE_KEY_F503: Final[str] = "id"

HEADER_GROUP_ROW_F503: Final[int] = 9
HEADER_LEAF_ROW_F503: Final[int] = 10
FIRST_DATA_ROW_F503: Final[int] = 11
LAST_DATA_ROW_F503: Final[int] = 21
FOOTER_ROW_F503: Final[int] = 22
FOOTER_MARKER_F503: Final[str] = "合计"
MANAGED_LAST_COL_F503: Final[str] = "N"
UUID_COL_F503: Final[str] = "O"

#: store-only 键（模板无对应列）。
STORE_ONLY_KEYS_F503: Final[tuple[tuple[str, str], ...]] = (
    ("isFixed", "前端固定行标记（7 个预填科目的 isFixed=true，不可删改）；模板无该列"),
)

#: R11~R17 七行模板预填标签（照 E1-2 范式登记）。
PREFILLED_ROWS_F503: Final[tuple[str, ...]] = (
    "出租固定资产",
    "出租无形资产",
    "出租包装物和商品",
    "销售材料",
    "用材料进行非货币性交换",
    "用材料进行债务重组",
    "与投资性房地产相关的支出（成本模式计量的投资性房地产计提的折旧，其他后续支出）",
)

#: 8 个受管 editable 字段。公式列（E,F,J,K,L,M）不进 field_specs。
FIELD_SPECS_F503: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("item", "A", "editable", "text", "item", "项目", ""),
    ("current_unaudited", "B", "editable", "amount", "currentUnaudited", "本期未审数", "B9"),
    ("current_aje", "C", "editable", "amount", "currentAje", "账项调整", "B9"),
    ("current_rje", "D", "editable", "amount", "currentRje", "重分类调整", "B9"),
    ("prior_unaudited", "G", "editable", "amount", "priorUnaudited", "上期未审数", "G9"),
    ("prior_aje", "H", "editable", "amount", "priorAje", "账项调整", "G9"),
    ("prior_rje", "I", "editable", "amount", "priorRje", "重分类调整", "G9"),
    ("remark", "N", "editable", "text", "remark", "备注", ""),
)

SPEC_F503: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F503,
    sheet_key=SHEET_KEY_F503,
    table_key=ROWS_TABLE_KEY_F503,
    template_id=TEMPLATE_ID_F503,
    table_name=f"GT_{TEMPLATE_ID_F503}_ROWS",
    uuid_col=UUID_COL_F503,
    first_data_row=FIRST_DATA_ROW_F503,
    last_data_row=LAST_DATA_ROW_F503,
    footer_row=FOOTER_ROW_F503,
    header_group_row=HEADER_GROUP_ROW_F503,
    header_leaf_row=HEADER_LEAF_ROW_F503,
    store_item_id=STORE_ITEM_ID_F503,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F503,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F503,
    formula_columns=("E", "F", "J", "K", "L", "M"),
    formula_templates={
        "E": "=B{r}+C{r}+D{r}",
        "F": "=IF(E{r}=0,0,E{r}/E$22)",
        "J": "=G{r}+H{r}+I{r}",
        "K": "=IF(J{r}=0,0,J{r}/$J$22)",
        "L": "=E{r}-J{r}",
        "M": "=IF(AND(J{r}=0,L{r}=0),0,IF(AND(J{r}=0,L{r}>0),1,L{r}/J{r}))",
    },
    footer_marker=FOOTER_MARKER_F503,
    footer_carries_total_formula=True,
    error_label="F5-3 其他业务成本明细表",
)
