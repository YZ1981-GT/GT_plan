# -*- coding: utf-8 -*-
"""F2-47 / F2-48 / F2-49 三个 dict 子数组 spec。

spec: f2-sync-coverage-four-entry-lanes · Task 19

store 形态：dict `{products: [...]}` → 行源 `products`（D1-7 同范式）。
dict 子数组的投影/合并门面放 provider 层（F2-H6），不进框架层。

canary = F2-48（dict 最简，公式仅 H=F*G）。
F2-47 卡 FC-10（百分数换算），灰度关待 Task 20。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec, StoreKind,
)

__all__ = ["SPEC_F248", "SPEC_F249", "SPEC_F247"]

ROW_IDENTITY_KEY: Final[str] = "id"

# ═══════════════════════════════════════════════════════════════════════════
# F2-48 长库龄呆滞超保质期存货明细表（canary）
# ═══════════════════════════════════════════════════════════════════════════
# 几何：22r×N，表头 R5/R6（两级），数据 R7-16，footer A17
# store: F2-48-rows → dict {products:[...]}，id 形如 f2imp-…
# formula_in_data: H（=F*G）

_FIELD_SPECS_F248: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_code",   "A", "editable", "text",   "itemCode",     "存货编号", ""),
    ("item_name",   "B", "editable", "text",   "itemName",     "存货名称", ""),
    ("spec",        "C", "editable", "text",   "spec",         "规格型号", ""),
    ("unit",        "D", "editable", "text",   "unit",         "计量单位", ""),
    ("qty",         "E", "editable", "amount", "qty",          "数量",     ""),
    ("unit_cost",   "F", "editable", "amount", "unitCost",     "单位成本", ""),
    ("book_amt",    "G", "editable", "amount", "bookAmt",      "账面金额", ""),
    ("aging_amt",   "H", "formula",  "amount", "agingAmt",     "库龄金额", ""),
    ("aging_desc",  "I", "editable", "text",   "agingDesc",    "库龄说明", ""),
    ("status",      "J", "editable", "text",   "status",       "品质状况", ""),
    ("reason",      "K", "editable", "text",   "reason",       "形成原因", ""),
    ("plan",        "L", "editable", "text",   "plan",         "处理计划", ""),
    ("remark",      "M", "editable", "text",   "remark",       "备注",     ""),
)

SPEC_F248: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet="长库龄 呆滞 超过保质期存货明细表F2-48",
    sheet_key="f248-managed",
    table_key="aging_stale_detail_rows",
    template_id="F248",
    table_name="GT_F248_ROWS",
    uuid_col="O",
    first_data_row=7,
    last_data_row=16,
    footer_row=17,
    header_group_row=5,
    header_leaf_row=6,
    store_item_id="F2-48-rows",
    empty_payload="{}",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.dict,
    field_specs=_FIELD_SPECS_F248,
    formula_columns=("H",),
    formula_templates={"H": "=F{r}*G{r}"},
    footer_marker="合计",
    error_label="F2-48 长库龄呆滞存货明细表",
)


# ═══════════════════════════════════════════════════════════════════════════
# F2-49 跌价转回
# ═══════════════════════════════════════════════════════════════════════════
# 几何：36r×X，表头 R5/R6（两级），数据 R7-15，footer A16
# store: F2-49-rows → dict {products:[...]}，id 形如 f2rev-…
# formula_in_data: T（=O/F*N），X（=U+V+W-T）

_FIELD_SPECS_F249: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_code",     "A", "editable", "text",   "itemCode",     "存货编号",   ""),
    ("item_name",     "B", "editable", "text",   "itemName",     "存货名称",   ""),
    ("spec",          "C", "editable", "text",   "spec",         "规格型号",   ""),
    ("unit",          "D", "editable", "text",   "unit",         "计量单位",   ""),
    ("qty",           "E", "editable", "amount", "qty",          "数量",       ""),
    ("unit_cost",     "F", "editable", "amount", "unitCost",     "单位成本",   ""),
    ("book_amt",      "G", "editable", "amount", "bookAmt",      "账面金额",   ""),
    ("nrv_price",     "H", "editable", "amount", "nrvPrice",     "可变现净值单价", ""),
    ("nrv_amt",       "I", "editable", "amount", "nrvAmt",       "可变现净值",  ""),
    ("impairment_prior", "J", "editable", "amount", "impairmentPrior", "期初跌价准备", ""),
    ("provision_amt", "K", "editable", "amount", "provisionAmt", "本期计提",   ""),
    ("reversal_amt",  "L", "editable", "amount", "reversalAmt",  "本期转回",   ""),
    ("transfer_out",  "M", "editable", "amount", "transferOut",  "转出",       ""),
    ("unit_cost_orig","N", "editable", "amount", "unitCostOrig", "原单位成本", ""),
    ("nrv_price_cur", "O", "editable", "amount", "nrvPriceCur",  "现可变现净值单价", ""),
    ("reversal_calc", "T", "formula",  "amount", "reversalCalc", "应转回金额", ""),
    ("remark",        "S", "editable", "text",   "remark",       "备注",       ""),
    ("diff",          "X", "formula",  "amount", "diff",         "差异",       ""),
)

SPEC_F249: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet="跌价转回F2-49",
    sheet_key="f249-managed",
    table_key="impairment_reversal_rows",
    template_id="F249",
    table_name="GT_F249_ROWS",
    uuid_col="Y",
    first_data_row=7,
    last_data_row=15,
    footer_row=16,
    header_group_row=5,
    header_leaf_row=6,
    store_item_id="F2-49-rows",
    empty_payload="{}",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.dict,
    field_specs=_FIELD_SPECS_F249,
    formula_columns=("T", "X"),
    formula_templates={"T": "=O{r}/F{r}*N{r}", "X": "=U{r}+V{r}+W{r}-T{r}"},
    footer_marker="合计",
    error_label="F2-49 跌价转回",
)


# ═══════════════════════════════════════════════════════════════════════════
# F2-47 跌价准备测试表（FC-10 命中，灰度关待 Task 20）
# ═══════════════════════════════════════════════════════════════════════════
# 几何：56r×AB，表头 R18/R19（两级），数据 R20-29，footer A30
# store: F2-47-rows → dict {auditProcedure, products:[...], sampling}
# 🔴 FC-10：N 列「销售费用率」/ O 列「税率」前端存百分数、模板期望小数

_FIELD_SPECS_F247: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("category",       "A", "editable", "text",   "category",       "存货类别", ""),
    ("item_code",      "B", "editable", "text",   "itemCode",       "编码",     ""),
    ("item_name",      "C", "editable", "text",   "itemName",       "名称",     ""),
    ("unit",           "D", "editable", "text",   "unit",           "单位",     ""),
    ("qty",            "E", "editable", "amount", "qty",            "结存数量", ""),
    ("unit_cost",      "F", "editable", "amount", "unitCost",       "账面单位成本", ""),
    ("book_amt",       "G", "formula",  "amount", "bookAmt",        "账面成本", ""),
    ("aging",          "H", "editable", "text",   "aging",          "库龄",     ""),
    ("status",         "I", "editable", "text",   "status",         "品质状况", ""),
    ("purpose",        "J", "editable", "text",   "holdingPurpose", "持有目的", ""),
    ("price_pre",      "K", "editable", "amount", "pricePreContract", "估计售价（无合同）", ""),
    ("price_contract", "L", "editable", "amount", "priceContract",  "合同价格", ""),
    ("unit_price",     "M", "editable", "amount", "unitPrice",      "确定单位售价", ""),
    ("selling_rate",   "N", "editable", "amount", "sellingExpenseRate", "销售费用率", ""),  # 🔴 FC-10
    ("tax_rate",       "O", "editable", "amount", "taxRate",         "税率",      ""),     # 🔴 FC-10
    ("qty_total",      "P", "editable", "amount", "qtyTotal",       "数量合计", ""),
    ("nrv",            "Q", "formula",  "amount", "nrv",            "可变现净值", ""),
    ("selling_exp",    "T", "formula",  "amount", "sellingExpense", "估计销售费用", ""),
    ("related_tax",    "U", "formula",  "amount", "relatedTax",     "相关税费",   ""),
    ("nrv_unit",       "V", "formula",  "amount", "nrvUnit",        "单位可变现净值", ""),
    ("nrv_total",      "W", "formula",  "amount", "nrvTotal",       "可变现净值合计", ""),
    ("impairment",     "X", "formula",  "amount", "impairment",     "应计提跌价准备", ""),
    ("remark",         "Y", "editable", "text",   "remark",         "备注",       ""),
    ("impairment_end", "Z", "formula",  "amount", "impairmentEnd",  "期末跌价准备", ""),
)

SPEC_F247: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet="跌价准备测试表F2-47",
    sheet_key="f247-managed",
    table_key="impairment_test_rows",
    template_id="F247",
    table_name="GT_F247_ROWS",
    uuid_col="AC",
    first_data_row=20,
    last_data_row=29,
    footer_row=30,
    header_group_row=18,
    header_leaf_row=19,
    store_item_id="F2-47-rows",
    empty_payload="{}",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.dict,
    field_specs=_FIELD_SPECS_F247,
    formula_columns=("G", "Q", "T", "U", "V", "W", "X", "Z"),
    formula_templates={},  # FC-10 换算落地后补公式模板
    footer_marker="合计",
    error_label="F2-47 跌价准备测试表（🔴 FC-10 百分数换算待落地）",
)
