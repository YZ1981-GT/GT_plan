# -*- coding: utf-8 -*-
"""D7-4「合同负债分析表」—— 双区声明（区①借方发生额分析 / 区②贷方发生额分析）。

spec: d567-sync-coverage-via-row-table-engine · Task 16 · Requirements 3.1；
区② 改接：spec oo-writeback-template-parity-closure R3 任务 9（批 A2）。

几何（openpyxl 直读 2026-09-26）：43r × 8c(H) / 32f。
区①借方分析：表头 R10（项目 / 金额 / 数据来源 / 备注），R11「本期借方发生额合计」，R12「对方科目：」，
  数据 R13-R14，R15「……」排版占位，footer R16「差异」（=B11-B13-B14-B15）。
区②贷方分析：表头 R19（金额 / 数据来源 / 与对方科目核对 / 说明），R20「本期贷方发生额合计」，
  数据 R21-R22（模板预填「其中：银行存款收款」「应收票据」），R23「……」排版占位，footer R24「差异合理性分析」
  （纯文字说明，无公式）。与 D3-4 贷方段同构。
🔴 store keys = D7-4-debit-rows / D7-4-credit-rows（不是 D7-4-rows 聚合键！）。

🔴 原区② 接的是「（四）期末合同负债主要债权人余额分析」R26-R37（债权人名称 / 期末 / 期初 …），
   但前端 `D7-4-credit-rows` 存的是「（三）贷方发生额分析」（item / amount / dataSource / remark），
   且期末 / 期初两列对调 ⇒ OO 改的贷方分析行写不回、债权人区被贷方行覆盖。改接到 R21-R22。
   区④ 的前十大债权人由前端按 D7-2 明细现算、不落库 ⇒ 不受管（同 D3-4 段③的主要债务人分析）。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = ["SPEC_D704_DEBIT", "SPEC_D704_CREDIT", "MANAGED_SHEET_D704"]

MANAGED_SHEET_D704: Final[str] = "合同负债分析表D7-4"

# ─── 区① 借方发生额分析 ──────────────────────────────────────────────────

TEMPLATE_ID_D704_DEBIT: Final[str] = "D74DEBIT"
SHEET_KEY_D704: Final[str] = "d74-managed"
STORE_ITEM_ID_D704_DEBIT: Final[str] = "D7-4-debit-rows"

FIELD_SPECS_D704_DEBIT: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item", "A", "editable", "text", "item", "项目", ""),
    ("amount", "B", "editable", "amount", "amount", "金额", ""),
    ("data_source", "C", "editable", "text", "dataSource", "数据来源", ""),
    ("remark", "D", "editable", "text", "remark", "备注", ""),
)

SPEC_D704_DEBIT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D704,
    sheet_key=SHEET_KEY_D704,
    table_key="analysis_debit_rows",
    template_id=TEMPLATE_ID_D704_DEBIT,
    table_name=f"GT_{TEMPLATE_ID_D704_DEBIT}_ROWS",
    uuid_col="H",
    first_data_row=13,  # R12 是「对方科目：」标签行，不是数据行
    last_data_row=14,  # R15 是排版续行省略号「……」不是业务行（BP-21）
    footer_row=16,  # R16「差异」行作为 footer（数据区之后第一行）
    header_row=10,
    store_item_id=STORE_ITEM_ID_D704_DEBIT,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D704_DEBIT,
    formula_columns=(),
    aging_layout=None,
    footer_marker="差异",
    error_label="D7-4 分析表 区①借方",
)

# ─── 区② 贷方发生额分析 ─────────────────────────────────────────────────

TEMPLATE_ID_D704_CREDIT: Final[str] = "D74CREDIT"
STORE_ITEM_ID_D704_CREDIT: Final[str] = "D7-4-credit-rows"

#: 表头取 R19（A19 空，项目列沿用区①的「项目」）；json 键逐字取前端 `useD7Analysis.AnalysisRow`。
#: D 列「与对方科目核对」前端原来没有，按模板补 `counterCheck`（spec R3.1 模板有、前端没有的列前端补上）。
FIELD_SPECS_D704_CREDIT: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item", "A", "editable", "text", "item", "项目", ""),
    ("amount", "B", "editable", "amount", "amount", "金额", ""),
    ("data_source", "C", "editable", "text", "dataSource", "数据来源", ""),
    ("counter_check", "D", "editable", "text", "counterCheck", "与对方科目核对", ""),
    ("remark", "E", "editable", "text", "remark", "说明", ""),
)

SPEC_D704_CREDIT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D704,
    sheet_key=SHEET_KEY_D704,
    table_key="analysis_credit_rows",
    template_id=TEMPLATE_ID_D704_CREDIT,
    table_name=f"GT_{TEMPLATE_ID_D704_CREDIT}_ROWS",
    uuid_col="I",  # 🔴 不同区不同 UUID 列
    first_data_row=21,  # R20 是「本期贷方发生额合计」总额行（前端取 TB），不是明细行
    last_data_row=22,  # R23 是排版续行省略号「……」不是业务行（BP-21）
    footer_row=24,  # R24「差异合理性分析」
    header_row=19,
    store_item_id=STORE_ITEM_ID_D704_CREDIT,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D704_CREDIT,
    formula_columns=(),
    aging_layout=None,
    footer_marker="差异合理性分析",
    # R24 是纯文字说明行、无公式（同 D3-4 段②），不得沿用默认 True
    footer_carries_total_formula=False,
    error_label="D7-4 分析表 区②贷方",
)
