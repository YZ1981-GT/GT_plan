# -*- coding: utf-8 -*-
"""G6-5「公允价值测试表」—— sheet 层薄声明（无表头行 + 3 公式列）。

spec: `g4-g6-shared-workbook-three-entry-lanes` · Task 14

═══ 几何（openpyxl 逐格实测）═══

`公允价值测试表G6-5`：`max_row=40` / `max_col=18` / merged 10 / 21 sheets。

* **两级表头 R7/R8**：R7 五个大组（A 投资项目 / B 期末未审数 / F 期末审定数 / J 差异 / K..R 公允价值详情）
  R8 逐列叶子（B 数量 / C 单位公允价值 / D 公允价值 / E 层次 / F..I 审定端同结构 / K 估值方法 / …）
* 数据区 **R9-R18**（10 行）。
* 合计 R19 `=SUM(D9:D18)` / `=SUM(H9:H18)` / `=SUM(J9:J18)`。
* **3 公式列**：D(`=B*C`) H(`=F*G`) J(`=H-D`)。
* 有效列 18（A..R） ⇒ uuid **S**。
* 🔴 D 列在 R9/R10 **两行**有公式 `=B*C`，R11-18 **无公式** ⇒ 行级 mask
  （列级只能 editable 或 auto_source，判 formula 会在 R11-18 抛）。
  但 H 列 R9-18 **全行有公式** `=F*G`，J 列同理 `=H-D` ⇒ H/J 是真公式列。
  D 原判 editable（前端按 `=B*C` 重算覆盖）；2026-10-28 改 **auto_source**（见下）；H/J 判 **formula**。
* payload 列：**conclusion_only**（真库 remark 0 B / conclusion 2 B 空数组）。

═══ 字段名对齐前端（spec oo-writeback-template-parity-closure R3 批 B）═══

json 键逐字取前端 `useG6SppiFairValue.FairValueItem`（字段名守卫 `test_contract_field_names_in_frontend.py`
报出 15 个对不上）：原写 investTarget / unauditedQuantity / unauditedUnitFv / unauditedFv / unauditedFvTier /
auditedQuantity / auditedUnitFv / auditedFv / auditedFvTier / fvDifference / valuationConsistent / fvSourceMechanism /
fvInputFactors / unobservableValue / valuationRef，前端存 investProject / unadjQty / unadjPrice / unadjFairValue /
unadjFairValueLevel / auditedQty / auditedPrice / auditedFairValue / auditedFairValueLevel / difference /
consistencyWithPrior / sourceInstitution / inputSource / inputValue / valuationFileRef。列键不变。
D 未审公允价值前端恒按 数量 × 单价 现算（不可手填）⇒ auto_source（HTML 侧带出，OO 改了报受保护冲突）。

═══ 接通（R3 批 B3，2026-10-28）═══

前端 store 是 `{rows, conclusion}` 对象、存在 conclusion 列。原先 provider 的 store 门面借自 G9（取 G9 的 spec）、
单数 STORE_ITEM_ID 照抄成 G6-2-rows、载荷一律读写 remark ⇒ 两方向都没接上（`KNOWN_UNWIRED` 冻结）。现门面按
本 provider 绑定（`SectionStoreFacade(rows_key="rows")`：投影取 rows、回写只换 rows 其余键原样），载荷列按
`PAYLOAD_COLUMN = "conclusion"` 读写（`store_payload_columns`），基线已删该条。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G605",
    "MANAGED_SHEET_G605",
    "STORE_ITEM_ID_G605",
    "FIELD_SPECS_G605",
]

MANAGED_SHEET_G605: Final[str] = "公允价值测试表G6-5"
TEMPLATE_ID_G605: Final[str] = "G605"
STORE_ITEM_ID_G605: Final[str] = "G6-5-fair-value-data"
ROW_IDENTITY_STORE_KEY_G605: Final[str] = "id"

HEADER_GROUP_ROW_G605: Final[int] = 7
HEADER_LEAF_ROW_G605: Final[int] = 8

FORMULA_COLUMNS_G605: Final[tuple[str, ...]] = ("H", "J")

FORMULA_TEMPLATES_G605: Final[dict[str, str]] = {
    "H": "=F{r}*G{r}",   # 审定公允价值 = 审定数量 × 审定单位公允价值
    "J": "=H{r}-D{r}",    # 差异 = 审定公允价值 − 未审公允价值
}

#: 18 个受管字段（A..R）。
FIELD_SPECS_G605: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("invest_target", "A", "editable", "text", "investProject", "投资项目", ""),
    # 期末未审数 (B7:E7)
    ("unaudited_quantity", "B", "editable", "amount", "unadjQty", "数量（张/股）", "B7"),
    ("unaudited_unit_fv", "C", "editable", "amount", "unadjPrice", "单位公允价值", "B7"),
    ("unaudited_fv", "D", "auto_source", "amount", "unadjFairValue", "公允价值", "B7"),
    ("unaudited_fv_tier", "E", "editable", "text", "unadjFairValueLevel", "公允价值层次", "B7"),
    # 期末审定数 (F7:I7)
    ("audited_quantity", "F", "editable", "amount", "auditedQty", "数量（张/股）", "F7"),
    ("audited_unit_fv", "G", "editable", "amount", "auditedPrice", "单位公允价值", "F7"),
    ("audited_fv", "H", "formula", "amount", "auditedFairValue", "公允价值", "F7"),
    ("audited_fv_tier", "I", "editable", "text", "auditedFairValueLevel", "公允价值层次", "F7"),
    # 差异
    ("fv_difference", "J", "formula", "amount", "difference", "差异", ""),
    # 估值方法
    ("valuation_method", "K", "editable", "text", "valuationMethod", "估值方法", ""),
    ("valuation_consistent", "L", "editable", "text", "consistencyWithPrior", "估值方法与上期是否一致", ""),
    # 公允价值来源
    ("fv_source_mechanism", "M", "editable", "text", "sourceInstitution", "公允价值来源机构", "M7"),
    ("fv_input_factors", "N", "editable", "text", "inputSource", "输入值来源及调整考虑因素", "M7"),
    ("valuation_technique", "O", "editable", "text", "valuationTechnique", "估值技术", "M7"),
    ("unobservable_inputs", "P", "editable", "text", "unobservableInputs", "不可观察输入值", "M7"),
    ("unobservable_value", "Q", "editable", "text", "inputValue", "数值", "M7"),
    # 估值文件索引号
    ("valuation_ref", "R", "editable", "text", "valuationFileRef", "估值文件索引号", ""),
)

SPEC_G605: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_G605,
    sheet_key="g605-managed",
    table_key="g6_5_fair_value",
    template_id=TEMPLATE_ID_G605,
    table_name="GT_G605_FAIR_VALUE",
    uuid_col="S",
    first_data_row=9,
    last_data_row=18,
    footer_row=19,
    header_group_row=HEADER_GROUP_ROW_G605,
    header_leaf_row=HEADER_LEAF_ROW_G605,
    store_item_id=STORE_ITEM_ID_G605,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_G605,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_G605,
    formula_columns=FORMULA_COLUMNS_G605,
    formula_templates=FORMULA_TEMPLATES_G605,
    footer_marker="合计",
    footer_carries_total_formula=True,
    error_label="G6-5 公允价值测试表",
    ghost_row_anchor_index=0,
)
