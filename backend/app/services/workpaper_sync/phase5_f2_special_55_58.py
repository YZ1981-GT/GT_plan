# -*- coding: utf-8 -*-
"""F2-55 / F2-56 / F2-57 / F2-58 四个 dict 子数组 spec。

spec: f2-sync-coverage-four-entry-lanes · Task 23

store 形态：dict + 子数组（F2-55/57/58 `products`；F2-56 `samples`）。
canary = F2-57（dict 最简，单级表头，无 FC-10）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec, StoreKind,
)

__all__ = ["SPEC_F257", "SPEC_F258", "SPEC_F255", "SPEC_F256"]

ROW_IDENTITY_KEY: Final[str] = "id"


# ═══════════════════════════════════════════════════════════════════════════
# F2-57 合同履约成本减值准备测算表（canary）
# ═══════════════════════════════════════════════════════════════════════════
# 几何：27r×N，表头 R5（单级），数据 R6-17，footer A18
# store: F2-57-rows → dict {products:[...]}

_FIELD_SPECS_F257: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("project_code", "A", "editable", "text",   "projectCode",  "项目编码", ""),
    ("project_name", "B", "editable", "text",   "projectName",  "项目名称", ""),
    ("revenue",      "C", "editable", "amount", "revenue",      "合同收入", ""),
    ("cost",         "D", "editable", "amount", "cost",         "合同成本", ""),
    ("diff",         "E", "formula",  "amount", "diff",         "差额",     ""),
    ("book_open",    "F", "editable", "amount", "bookOpen",     "期初账面", ""),
    ("book_inc",     "G", "editable", "amount", "bookInc",      "本期增加", ""),
    ("book_close",   "H", "formula",  "amount", "bookClose",    "期末账面", ""),
    ("audit_open",   "I", "formula",  "amount", "auditOpen",    "审定期初", ""),
    ("audit_inc",    "J", "formula",  "amount", "auditInc",     "审定增加", ""),
    ("audit_close",  "K", "editable", "amount", "auditClose",   "审定期末", ""),
    ("adj_amt",      "L", "formula",  "amount", "adjAmt",       "调整金额", ""),
    ("remark",       "M", "editable", "text",   "remark",       "备注",     ""),
)

SPEC_F257: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet="合同履约成本减值准备测算表F2-57",
    sheet_key="f257-managed",
    table_key="contract_impairment_rows",
    template_id="F257",
    table_name="GT_F257_ROWS",
    uuid_col="O",
    first_data_row=6,
    last_data_row=17,
    footer_row=18,
    header_row=5,
    store_item_id="F2-57-rows",
    empty_payload="{}",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.dict,
    field_specs=_FIELD_SPECS_F257,
    formula_columns=("E", "H", "I", "J", "L"),
    formula_templates={},
    footer_marker="合计",
    error_label="F2-57 合同履约成本减值准备测算表",
)


# ═══════════════════════════════════════════════════════════════════════════
# F2-58 亏损合同预计损失测算表
# ═══════════════════════════════════════════════════════════════════════════
# 几何：25r×O，表头 R5（R6 公式说明行），数据 R7-20，footer A21
# store: F2-58-rows → dict {products:[...]}
# FC-10 不命中（completionRate 存 0~1 与模板一致）

_FIELD_SPECS_F258: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("project_code",       "A", "editable", "text",   "projectCode",        "项目编码",     ""),
    ("project_name",       "B", "editable", "text",   "projectName",        "项目名称",     ""),
    ("completion_rate",    "C", "editable", "amount", "completionRate",     "完工进度",     ""),
    ("recognized_revenue", "D", "editable", "amount", "recognizedRevenue",  "已确认收入",   ""),
    ("est_total_revenue",  "E", "editable", "amount", "estimatedTotalRevenue", "预计总收入", ""),
    ("est_total_cost",     "F", "formula",  "amount", "estimatedTotalCost", "预计总成本",   ""),
    ("contract_loss",      "G", "formula",  "amount", "contractEstimatedLoss", "合同预计损失", ""),
    ("recognized_loss",    "H", "formula",  "amount", "recognizedLossInPl", "已在损益反映",  ""),
    ("prior_loss",         "I", "editable", "amount", "priorRecognizedLoss","已在损益反映（手填）", ""),
    ("current_loss",       "J", "formula",  "amount", "currentPeriodLoss",  "本期应确认",   ""),
    ("book_loss",          "K", "editable", "amount", "bookRecognizedLoss", "账面已确认",   ""),
    ("remark",             "L", "editable", "text",   "remark",             "备注",         ""),
)

SPEC_F258: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet="亏损合同预计损失测算表F2-58",
    sheet_key="f258-managed",
    table_key="loss_contract_rows",
    template_id="F258",
    table_name="GT_F258_ROWS",
    uuid_col="P",
    first_data_row=7,
    last_data_row=20,
    footer_row=21,
    header_row=5,
    store_item_id="F2-58-rows",
    empty_payload="{}",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.dict,
    field_specs=_FIELD_SPECS_F258,
    formula_columns=("F", "G", "H", "J"),
    formula_templates={},
    footer_marker="合计",
    error_label="F2-58 亏损合同预计损失测算表",
)


# ═══════════════════════════════════════════════════════════════════════════
# F2-55 合同履约成本构成明细表
# ═══════════════════════════════════════════════════════════════════════════
# 几何：40r×AK，表头 R5/R6（两级），数据 R7-24，footer A25
# store: F2-55-rows → dict {products:[...]}
# 🔴 footer SUM(D6:D24) 起点是 R6（表头叶子行），需实测位移行为

_FIELD_SPECS_F255: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("project_code",  "A", "editable", "text",   "projectCode",   "项目编码",     ""),
    ("project_name",  "B", "editable", "text",   "projectName",   "项目名称",     ""),
    ("contract_name", "C", "editable", "text",   "contractName",  "收入合同名称", ""),
    ("contract_amt",  "D", "editable", "amount", "contractAmt",   "收入合同金额", ""),
    # 后续列（E~AJ）大部分是公式列，Task 23 扩容时逐列声明
    ("remark",        "AK","editable", "text",   "remark",        "备注",         ""),
)

SPEC_F255: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet="合同履约成本构成明细表F2-55",
    sheet_key="f255-managed",
    table_key="contract_cost_detail_rows",
    template_id="F255",
    table_name="GT_F255_ROWS",
    uuid_col="AL",
    first_data_row=7,
    last_data_row=24,
    footer_row=25,
    header_group_row=5,
    header_leaf_row=6,
    store_item_id="F2-55-rows",
    empty_payload="{}",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.dict,
    field_specs=_FIELD_SPECS_F255,
    formula_columns=(),  # Task 23 扩容时补
    formula_templates={},
    footer_marker="合计",
    error_label="F2-55 合同履约成本构成明细表",
)


# ═══════════════════════════════════════════════════════════════════════════
# F2-56 合同履约成本检查表
# ═══════════════════════════════════════════════════════════════════════════
# 几何：37r×W，表头 R15/R16（两级），数据 R17-31，footer A32
# store: F2-56-rows → dict {samples:[...], sampling, statNote}
# 🔴 行源是 samples（非 products）

_FIELD_SPECS_F256: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("project_name",   "A", "editable", "text",   "projectName",     "项目名称",     ""),
    ("account_detail", "B", "editable", "text",   "accountDetail",   "明细科目",     ""),
    ("voucher_no",     "C", "editable", "text",   "voucherNo",       "凭证号",       ""),
    ("business_content","D","editable", "text",   "businessContent", "业务内容",     ""),
    ("voucher_amount", "E", "editable", "amount", "voucherAmount",   "凭证金额",     ""),
    ("index_ref",      "F", "editable", "text",   "indexRef",        "索引号",       ""),
    ("is_abnormal",    "G", "editable", "text",   "isAbnormal",      "是否异常",     ""),
    ("issue_desc",     "H", "editable", "text",   "issueDesc",       "问题描述",     ""),
)

SPEC_F256: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet="合同履约成本检查表F2-56",
    sheet_key="f256-managed",
    table_key="contract_cost_check_rows",
    template_id="F256",
    table_name="GT_F256_ROWS",
    uuid_col="X",
    first_data_row=17,
    last_data_row=31,
    footer_row=32,
    header_group_row=15,
    header_leaf_row=16,
    store_item_id="F2-56-rows",
    empty_payload="{}",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.dict,
    field_specs=_FIELD_SPECS_F256,
    formula_columns=(),
    formula_templates={},
    footer_marker="合计",
    error_label="F2-56 合同履约成本检查表",
)
