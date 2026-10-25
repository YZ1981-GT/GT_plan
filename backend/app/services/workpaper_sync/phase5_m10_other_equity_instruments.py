# -*- coding: utf-8 -*-
"""M10 其他权益工具双向回写 provider。共享内核 `phase5_m_cycle_common.py`。

spec: m2-m3-m4-m7-m10-bidirectional-pipeline
entry: xlsx/gt-m10-other-equity-instruments
科目: 4001 其他权益工具（贷方/权益类）
受管 sheet: 明细表M10-2
审定表 M10-1 除 A 列外全公式（1e+10f），不做 instrumentation。

🔴 M10 明细表是三段结构：一、优先股 R12~R14 / 二、永续债 R16~R19 / 三、转股特征 R21~R24
   各段有小计行 R15/R20/R25，合计行 R26。
🔴 明细表 30 列宽表，24e + 6f。
"""
from __future__ import annotations

from typing import Any, Final

from app.services.workpaper_sync.phase5_m_cycle_common import (
    MEntryConfig,
    MFieldSpec,
    MSheetConfig,
    build_m_provider,
    publish_m_definitions,
)

# ═══════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════

ENTRY_ID: Final[str] = "xlsx/gt-m10-other-equity-instruments"
ADAPTER_ID: Final[str] = "m10.other_equity_instruments"
WP_CODES: Final[frozenset[str]] = frozenset({"M10O"})
TEMPLATE_RELATIVE_PATH: Final[str] = "M/M10 其他权益工具.xlsx"
TEMPLATE_SHA256: Final[str] = "073d75ae83274d4d54147934b5a4ef2b00d4be5c8a020b7cd074a99613ac8077"
ACCOUNT_CODE: Final[str] = "4001"
ITEM_PREFIX: Final[str] = "M10-"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
STORE_ITEM_ID: Final[str] = "M10-"

# ═══════════════════════════════════════════════════════════════════════════
# 明细表 M10-2 字段（45r×30c / 125 公式）
# 表头 R9~R11（三级），数据区 R12~R25（含 3 个小计行），R26 合计
# Editable 24 列：A/B/C/D/E/F/G/H/I/J/K/L/M/O/P/Q/U/V/W/X/AA/AB/AC/AD
# Formula 6 列：N/R/S/T/Y/Z
# ═══════════════════════════════════════════════════════════════════════════

DETAIL_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("instrument_type", "A", "editable", "text", "instrumentType", "融资工具种类"),
    MFieldSpec("issue_date", "B", "editable", "text", "issueDate", "发行时间"),
    MFieldSpec("interest_rate", "C", "editable", "text", "interestRate", "股利率或利息率"),
    MFieldSpec("issue_price", "D", "editable", "amount", "issuePrice", "发行价格"),
    MFieldSpec("quantity", "E", "editable", "amount", "quantity", "数量"),
    MFieldSpec("maturity_renewal", "F", "editable", "text", "maturityRenewal", "到期日或续期情况"),
    MFieldSpec("accounting_class", "G", "editable", "text", "accountingClass", "会计分类"),
    MFieldSpec("issue_total_face", "H", "editable", "amount", "issueTotalFace", "发行总额（面值）"),
    MFieldSpec("opening_qty", "I", "editable", "amount", "openingQty", "数量", "期初账面价值"),
    MFieldSpec("opening_amount", "J", "editable", "amount", "openingAmount", "金额", "期初账面价值"),
    MFieldSpec("issue_qty", "K", "editable", "amount", "issueQty", "数量", "本期发行"),
    MFieldSpec("issue_amount", "L", "editable", "amount", "issueAmount", "金额", "本期发行"),
    MFieldSpec("transaction_cost", "M", "editable", "amount", "transactionCost", "交易费用"),
    MFieldSpec("book_value", "N", "formula", "amount", "bookValue", "账面价值"),
    MFieldSpec("decrease_qty", "O", "editable", "amount", "decreaseQty", "数量", "本期减少"),
    MFieldSpec("decrease_amount", "P", "editable", "amount", "decreaseAmount", "金额", "本期减少"),
    MFieldSpec("other_change", "Q", "editable", "amount", "otherChange", "其他变动"),
    MFieldSpec("decrease_subtotal", "R", "formula", "amount", "decreaseSubtotal", "小计"),
    MFieldSpec("closing_qty", "S", "formula", "amount", "closingQty", "数量", "期末账面价值"),
    MFieldSpec("closing_amount", "T", "formula", "amount", "closingAmount", "金额", "期末账面价值"),
    MFieldSpec("adj_increase_qty", "U", "editable", "amount", "adjIncreaseQty", "数量", "审计调整（增加）"),
    MFieldSpec("adj_increase_amount", "V", "editable", "amount", "adjIncreaseAmount", "金额", "审计调整（增加）"),
    MFieldSpec("adj_decrease_qty", "W", "editable", "amount", "adjDecreaseQty", "数量", "审计调整（减少）"),
    MFieldSpec("adj_decrease_amount", "X", "editable", "amount", "adjDecreaseAmount", "金额", "审计调整（减少）"),
    MFieldSpec("audited_closing_qty", "Y", "formula", "amount", "auditedClosingQty", "数量", "审计调整后期末账面价值"),
    MFieldSpec("audited_closing_amount", "Z", "formula", "amount", "auditedClosingAmount", "金额", "审计调整后期末账面价值"),
    MFieldSpec("conversion_condition", "AA", "editable", "text", "conversionCondition", "转股条件"),
    MFieldSpec("conversion_status", "AB", "editable", "text", "conversionStatus", "转换情况"),
    MFieldSpec("remark", "AC", "editable", "text", "remark", "备注"),
    MFieldSpec("doc_index_ref", "AD", "editable", "text", "docIndexRef", "文件索引号"),
)

DETAIL_SHEET: Final[MSheetConfig] = MSheetConfig(
    sheet_name="明细表M10-2",
    sheet_key="m1001-managed",
    table_key="m10_detail_rows",
    header_rows=3,
    first_data_row=12,
    last_data_row=25,
    footer_row=26,
    anchor_row=9,
    fields=DETAIL_FIELDS,
    row_identity_kind="template_row_key",
    footer_carries_total=True,
    delete_policy="reject",
)

# ═══════════════════════════════════════════════════════════════════════════
# 组装
# ═══════════════════════════════════════════════════════════════════════════

CONFIG: Final[MEntryConfig] = MEntryConfig(
    code="M10",
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    account_code=ACCOUNT_CODE,
    account_nature="权益类",
    item_prefix=ITEM_PREFIX,
    determination_sheet_name="审定表M10-1",
    sheets=(DETAIL_SHEET,),
    reviewed_basis=(
        "openpyxl 逐 sheet 直读权威模板 M/M10 其他权益工具.xlsx 的 11 张 sheet。"
        "审定表 M10-1（38r×14c / 86 公式）：三级表头 R5-R7，数据区 R8-R21（含 3 段小计行），"
        "R22 合计 SUM。除 A 列外全公式。"
        "明细表 M10-2（45r×30c / 125 公式）：三级表头 R9-R11，"
        "三段数据区（一、优先股 R12~R14 / 二、永续债 R16~R19 / 三、转股特征 R21~R24），"
        "各段小计 R15/R20/R25，合计 R26。Editable 24 列 + Formula 6 列 = 30 列宽表。"
        "科目码 4001 其他权益工具（贷方/权益类）。"
    ),
    html_store_note=(
        "M10 的业务内容由 useM10FormData.ts 承载：ITEM_PREFIX='M10-'，命名 M10-{sheet}-{field}。"
        "明细表 30 列宽表，三段式结构（优先股/永续债/转股特征）。"
    ),
)

_P = build_m_provider(CONFIG)
_O = _P.orch

EntrySelectionError = _P.EntrySelectionError
StorePayloadError = _P.StorePayloadError
Phase5Definitions = _P.Phase5Definitions
TemplateResolutionFacts = _P.TemplateResolutionFacts

excel_carrier_gate = _P.excel_carrier_gate
authoritative_template_path = _P.authoritative_template_path
read_authoritative_template = _P.read_authoritative_template
assert_no_implicit_template_fallback = _P.assert_no_implicit_template_fallback
assert_entry_selectable = _P.assert_entry_selectable

template_definition_payload = _P.template_definition_payload
instrumentation_definition_payload = _P.instrumentation_definition_payload
authority_model_payload = _P.authority_model_payload

build_contract_payload = _P.build_contract_payload
contract_file_path = _P.contract_file_path
load_contract_from_disk = _P.load_contract_from_disk
assert_contract_file_matches_source = _P.assert_contract_file_matches_source

build_store_projection = _P.build_store_projection
merge_projection_into_store_rows = _P.merge_projection_into_store_rows
all_store_item_ids = _P.all_store_item_ids
instrumentation_spec = _P.instrumentation_spec
instrumentation_specs = _P.instrumentation_specs

build_matcher = _P.build_matcher
build_registration = _P.build_registration
register_adapter = _P.register_adapter
attach_adapters = _P.attach_adapters
manifest_capability_enabled = _P.manifest_capability_enabled
assert_manifest_capability_enabled = _P.assert_manifest_capability_enabled


async def publish_definitions(publisher: Any) -> Any:
    return await publish_m_definitions(_P, publisher)


publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
