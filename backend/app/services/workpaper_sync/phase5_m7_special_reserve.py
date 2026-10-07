# -*- coding: utf-8 -*-
"""M7 专项储备双向回写 provider。共享内核 `phase5_m_cycle_common.py`。

spec: m2-m3-m4-m7-m10-bidirectional-pipeline
entry: xlsx/gt-m7-special-reserve
科目: 4301 专项储备（贷方/权益类）
受管 sheet: 明细表M7-2
审定表 M7-1 除 A 列外全公式（1e+10f），不做 instrumentation。
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

ENTRY_ID: Final[str] = "xlsx/gt-m7-special-reserve"
ADAPTER_ID: Final[str] = "m7.special_reserve"
WP_CODES: Final[frozenset[str]] = frozenset({"M7S"})
TEMPLATE_RELATIVE_PATH: Final[str] = "M/M7 专项储备.xlsx"
TEMPLATE_SHA256: Final[str] = "9604cf8805dbf0446853c3f718bab1f7e0f126002c4df4bf468d04923086dbfc"
ACCOUNT_CODE: Final[str] = "4301"
ITEM_PREFIX: Final[str] = "M7-"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
STORE_ITEM_ID: Final[str] = "M7-"

# ═══════════════════════════════════════════════════════════════════════════
# 明细表 M7-2 字段（24r×27c / 56 公式）
# 表头 R8~R9（两级），数据区 R10~R16，R17 合计
# Editable: A/B/C/D/F/G/H/I/J/K/P/Q/R（13 列）
# Formula: E/L/M/N/O（5 列）
# ═══════════════════════════════════════════════════════════════════════════

DETAIL_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("project_name", "A", "editable", "text", "projectName", "项目"),
    MFieldSpec("prior_opening", "B", "editable", "amount", "priorOpening", "期初数", "未审数"),
    MFieldSpec("current_increase", "C", "editable", "amount", "currentIncrease", "本期增加"),
    MFieldSpec("current_decrease", "D", "editable", "amount", "currentDecrease", "本期减少"),
    MFieldSpec("closing_balance", "E", "formula", "amount", "closingBalance", "期末数", "未审数"),
    MFieldSpec("prior_adj_aje", "F", "editable", "amount", "priorAdjAje", "账项调整", "期初调整"),
    MFieldSpec("prior_adj_rje", "G", "editable", "amount", "priorAdjRje", "重分类调整", "期初调整"),
    MFieldSpec("current_aje_increase", "H", "editable", "amount", "currentAjeIncrease", "本期增加", "账项调整"),
    MFieldSpec("current_aje_decrease", "I", "editable", "amount", "currentAjeDecrease", "本期减少", "账项调整"),
    MFieldSpec("current_rje_increase", "J", "editable", "amount", "currentRjeIncrease", "本期增加", "重分类调整"),
    MFieldSpec("current_rje_decrease", "K", "editable", "amount", "currentRjeDecrease", "本期减少", "重分类调整"),
    MFieldSpec("audited_opening", "L", "formula", "amount", "auditedOpening", "期初数", "审定数"),
    MFieldSpec("audited_increase", "M", "formula", "amount", "auditedIncrease", "本期增加", "审定数"),
    MFieldSpec("audited_decrease", "N", "formula", "amount", "auditedDecrease", "本期减少", "审定数"),
    MFieldSpec("audited_closing", "O", "formula", "amount", "auditedClosing", "期末数", "审定数"),
    MFieldSpec("doc_ref", "P", "editable", "text", "docRef", "文件依据"),
    MFieldSpec("index_ref", "Q", "editable", "text", "indexRef", "索引号"),
    MFieldSpec("remark", "R", "editable", "text", "remark", "备注"),
)

DETAIL_SHEET: Final[MSheetConfig] = MSheetConfig(
    sheet_name="明细表M7-2",
    sheet_key="m701-managed",
    table_key="m7_detail_rows",
    header_rows=2,
    first_data_row=10,
    last_data_row=16,
    footer_row=17,
    anchor_row=8,
    fields=DETAIL_FIELDS,
    row_identity_kind="template_row_key",
    footer_carries_total=True,
    delete_policy="reject",
)

# ═══════════════════════════════════════════════════════════════════════════
# 组装
# ═══════════════════════════════════════════════════════════════════════════

CONFIG: Final[MEntryConfig] = MEntryConfig(
    code="M7",
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    account_code=ACCOUNT_CODE,
    account_nature="权益类",
    item_prefix=ITEM_PREFIX,
    determination_sheet_name="审定表M7-1",
    sheets=(DETAIL_SHEET,),
    reviewed_basis=(
        "openpyxl 逐 sheet 直读权威模板 M/M7 专项储备.xlsx 的 10 张 sheet。"
        "审定表 M7-1（32r×12c / 78 公式）：两级表头 R5-R6，数据区 R7-R12（6 行），"
        "R13 合计 SUM。除 A 列外全公式引用明细表。"
        "明细表 M7-2（24r×27c / 56 公式）：两级表头 R8-R9，数据区 R10-R16（7 行），"
        "R17 合计公式。Editable 13 列 + Formula 5 列。"
        "科目码 4301 专项储备（贷方/权益类）。"
    ),
    html_store_note=(
        "M7 的业务内容由 useM7FormData.ts 承载：ITEM_PREFIX='M7-'，命名 M7-{sheet}-{field}。"
        "审定表除 A 列外全公式引用明细表，真正数据入口在明细表。"
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
