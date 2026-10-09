# -*- coding: utf-8 -*-
"""F5-2「主营业务成本月度明细表」—— sheet 层薄声明。

spec: f5-sync-coverage-and-first-canary · Task 16 · Requirements 4.3, 4.5
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 几何 ═══

两级表头 **R9（组）/ R10（叶子）**：
    A(A9:A10) 项目月份  |  B~M(B9:M9) 主营业务成本分月小计(1~12月)  |
    N(N9:N10) 本期未审数  |  O~P(O9:P9) 本期审计调整(AJE/RJE)  |
    Q(Q9:Q10) 本期审定数  |  R(R9:R10) 上期未审数  |
    S~T(S9:T9) 上期审计调整(AJE/RJE)  |  U(U9:U10) 上期审定数  |
    V(V9:V10) 未审变动比例  |  W(W9:W10) 审定变动比例  |  X(X9:X10) 备注

数据区 **R11~R22**（12 行）· footer **R23** 合计。

═══ 公式列（5 列，逐行同构）═══

    N{r} = SUM(B{r}:M{r})                                     本期未审（12 月合计）
    Q{r} = N{r}+O{r}+P{r}                                    本期审定
    U{r} = R{r}+S{r}+T{r}                                    上期审定
    V{r} = IF(AND(R{r}=0,N{r}-R{r}=0),0,IF(AND(R{r}=0,N{r}-R{r}>0),1,(N{r}-R{r})/R{r}))
    W{r} = IF(AND(U{r}=0,Q{r}-U{r}=0),0,IF(AND(U{r}=0,Q{r}-U{r}>0),1,(Q{r}-U{r})/U{r}))

🔴 V/W 有百分比格式但是**公式列** ⇒ FC-10 不命中。

═══ nested 月度路径（裁决 F5-H5）═══

B~M 12 个月度列用 **nested 路径** `months/0`…`months/11`，不展平成 `month1`…`month12`。
`json_path.py` 的数组感知实现（`FIXED_ARRAY_LENGTHS={"months":12}`，D4 先例）支持该路径。

P13 判据：改一格只变对应下标元素，其余 11 个不变。

═══ footer ═══

R23「合计」，B~W 全部 22 列有 SUM 或公式。footer_carries_total_formula=True。

═══ UUID 列 ═══

max_col=X(24)，Y 列 non_null=0 ⇒ 取 **Y**。🔴 Y 超出 max_column ⇒ instrumentation 需扩列。

═══ 字段 ═══

行身份 **`id`**。前端 `STORAGE_KEY = 'F5-2-monthly-rows'`。

🔴 **容量裁决**（Task 15，F5-H4）：品种数 ≤ 10 受管、> 10 整表降级 legacy。
常量 `F5_2_MAX_MANAGED_ROWS = 10` 在 provider 层。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F502",
    "MANAGED_SHEET_F502",
    "STORE_ITEM_ID_F502",
]

MANAGED_SHEET_F502: Final[str] = "主营业务成本月度明细表F5-2"
TEMPLATE_ID_F502: Final[str] = "F52"
SHEET_KEY_F502: Final[str] = "f52-managed"
ROWS_TABLE_KEY_F502: Final[str] = "monthly_detail_rows"
STORE_ITEM_ID_F502: Final[str] = "F5-2-monthly-rows"

ROW_IDENTITY_STORE_KEY_F502: Final[str] = "id"

HEADER_GROUP_ROW_F502: Final[int] = 9
HEADER_LEAF_ROW_F502: Final[int] = 10
FIRST_DATA_ROW_F502: Final[int] = 11
LAST_DATA_ROW_F502: Final[int] = 22
FOOTER_ROW_F502: Final[int] = 23
FOOTER_MARKER_F502: Final[str] = "合计"
MANAGED_LAST_COL_F502: Final[str] = "X"
UUID_COL_F502: Final[str] = "Y"

#: 18 个受管 editable 字段：A(项目) + B~M(12月 nested) + O/P(AJE/RJE) + R/S/T(上期) + X(备注)。
#: 公式列 N/Q/U/V/W 不进 field_specs。
FIELD_SPECS_F502: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("product", "A", "editable", "text", "product", "项目月份", ""),
    # ── B~M 12 个月度列（nested 路径 months/0 … months/11）──
    ("month_01", "B", "editable", "amount", "months/0", "1月", "B9"),
    ("month_02", "C", "editable", "amount", "months/1", "2月", "B9"),
    ("month_03", "D", "editable", "amount", "months/2", "3月", "B9"),
    ("month_04", "E", "editable", "amount", "months/3", "4月", "B9"),
    ("month_05", "F", "editable", "amount", "months/4", "5月", "B9"),
    ("month_06", "G", "editable", "amount", "months/5", "6月", "B9"),
    ("month_07", "H", "editable", "amount", "months/6", "7月", "B9"),
    ("month_08", "I", "editable", "amount", "months/7", "8月", "B9"),
    ("month_09", "J", "editable", "amount", "months/8", "9月", "B9"),
    ("month_10", "K", "editable", "amount", "months/9", "10月", "B9"),
    ("month_11", "L", "editable", "amount", "months/10", "11月", "B9"),
    ("month_12", "M", "editable", "amount", "months/11", "12月", "B9"),
    # ── N 公式（本期未审 SUM）——
    # ── 本期审计调整 ──
    ("current_aje", "O", "editable", "amount", "currentAje", "账项调整", "O9"),
    ("current_rje", "P", "editable", "amount", "currentRje", "重分类调整", "O9"),
    # ── Q 公式（本期审定）──
    # ── 上期 ──
    ("prior_unaudited", "R", "editable", "amount", "priorUnaudited", "上期未审数", ""),
    ("prior_aje", "S", "editable", "amount", "priorAje", "账项调整", "S9"),
    ("prior_rje", "T", "editable", "amount", "priorRje", "重分类调整", "S9"),
    # ── U/V/W 公式（上期审定 / 变动比例）──
    ("remark", "X", "editable", "text", "remark", "备注", ""),
)

SPEC_F502: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F502,
    sheet_key=SHEET_KEY_F502,
    table_key=ROWS_TABLE_KEY_F502,
    template_id=TEMPLATE_ID_F502,
    table_name=f"GT_{TEMPLATE_ID_F502}_ROWS",
    uuid_col=UUID_COL_F502,
    first_data_row=FIRST_DATA_ROW_F502,
    last_data_row=LAST_DATA_ROW_F502,
    footer_row=FOOTER_ROW_F502,
    header_group_row=HEADER_GROUP_ROW_F502,
    header_leaf_row=HEADER_LEAF_ROW_F502,
    store_item_id=STORE_ITEM_ID_F502,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F502,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F502,
    formula_columns=("N", "Q", "U", "V", "W"),
    formula_templates={
        "N": "=SUM(B{r}:M{r})",
        "Q": "=N{r}+O{r}+P{r}",
        "U": "=R{r}+S{r}+T{r}",
        "V": "=IF(AND(R{r}=0,N{r}-R{r}=0),0,IF(AND(R{r}=0,N{r}-R{r}>0),1,(N{r}-R{r})/R{r}))",
        "W": "=IF(AND(U{r}=0,Q{r}-U{r}=0),0,IF(AND(U{r}=0,Q{r}-U{r}>0),1,(Q{r}-U{r})/U{r}))",
    },
    footer_marker=FOOTER_MARKER_F502,
    footer_carries_total_formula=True,
    error_label="F5-2 主营业务成本月度明细表",
)
