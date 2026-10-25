# -*- coding: utf-8 -*-
"""M3 库存股双向回写 provider。共享内核 `phase5_m_cycle_common.py`。

spec: m2-m3-m4-m7-m10-bidirectional-pipeline
entry: xlsx/gt-m3-treasury-stock
科目: 4102 库存股（贷方/权益类，借方减）
受管 sheet: 明细表M3-2
审定表 M3-1 全公式（0e+11f），不做 instrumentation。
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

ENTRY_ID: Final[str] = "xlsx/gt-m3-treasury-stock"
ADAPTER_ID: Final[str] = "m3.treasury_stock"
WP_CODES: Final[frozenset[str]] = frozenset({"M3T"})
TEMPLATE_RELATIVE_PATH: Final[str] = "M/M3 库存股.xlsx"
TEMPLATE_SHA256: Final[str] = "ec8448c9df0fc5ae93f83fd2016e2ab26091e38749397595f66da818e9162115"
ACCOUNT_CODE: Final[str] = "4102"
ITEM_PREFIX: Final[str] = "M3-"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
STORE_ITEM_ID: Final[str] = "M3-"

# ═══════════════════════════════════════════════════════════════════════════
# 明细表 M3-2 字段（59r×19c / 72 公式）
# 表头 R12~R14（三级），数据区 R15~R24，R25 合计
# Editable: A/B/C/D/E/G/H/I/J/K/L/Q/R/S（14 列）
# Formula: F/M/N/O/P（5 列）
# ═══════════════════════════════════════════════════════════════════════════

DETAIL_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("category", "A", "editable", "text", "category", "库存股类别"),
    MFieldSpec("prior_opening", "B", "editable", "amount", "priorOpening", "期初数", "未审数"),
    MFieldSpec("current_increase", "C", "editable", "amount", "currentIncrease", "本期增加"),
    MFieldSpec("decrease_transfer", "D", "editable", "amount", "decreaseTransfer", "转让", "本期减少"),
    MFieldSpec("decrease_cancel", "E", "editable", "amount", "decreaseCancel", "注销", "本期减少"),
    MFieldSpec("closing_balance", "F", "formula", "amount", "closingBalance", "期末数", "未审数"),
    MFieldSpec("prior_adj_aje", "G", "editable", "amount", "priorAdjAje", "账项调整", "期初调整"),
    MFieldSpec("prior_adj_rje", "H", "editable", "amount", "priorAdjRje", "重分类调整", "期初调整"),
    MFieldSpec("current_aje_increase", "I", "editable", "amount", "currentAjeIncrease", "本期增加", "账项调整"),
    MFieldSpec("current_aje_decrease", "J", "editable", "amount", "currentAjeDecrease", "本期减少", "账项调整"),
    MFieldSpec("current_rje_increase", "K", "editable", "amount", "currentRjeIncrease", "本期增加", "重分类调整"),
    MFieldSpec("current_rje_decrease", "L", "editable", "amount", "currentRjeDecrease", "本期减少", "重分类调整"),
    MFieldSpec("audited_opening", "M", "formula", "amount", "auditedOpening", "期初数", "审定数"),
    MFieldSpec("audited_increase", "N", "formula", "amount", "auditedIncrease", "本期增加", "审定数"),
    MFieldSpec("audited_decrease", "O", "formula", "amount", "auditedDecrease", "本期减少", "审定数"),
    MFieldSpec("audited_closing", "P", "formula", "amount", "auditedClosing", "期末数", "审定数"),
    MFieldSpec("resolution_ref", "Q", "editable", "text", "resolutionRef", "相关决议索引号"),
    MFieldSpec("accounting_correct", "R", "editable", "text", "accountingCorrect", "相关会计处理是否正确"),
    MFieldSpec("remark", "S", "editable", "text", "remark", "备注"),
)

DETAIL_SHEET: Final[MSheetConfig] = MSheetConfig(
    sheet_name="明细表M3-2",
    sheet_key="m301-managed",
    table_key="m3_detail_rows",
    header_rows=3,
    first_data_row=15,
    last_data_row=24,
    footer_row=25,
    anchor_row=12,
    fields=DETAIL_FIELDS,
    row_identity_kind="template_row_key",
    footer_carries_total=True,
    delete_policy="reject",
)

# ═══════════════════════════════════════════════════════════════════════════
# 组装
# ═══════════════════════════════════════════════════════════════════════════

CONFIG: Final[MEntryConfig] = MEntryConfig(
    code="M3",
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    account_code=ACCOUNT_CODE,
    account_nature="权益类",
    item_prefix=ITEM_PREFIX,
    determination_sheet_name="审定表M3-1",
    sheets=(DETAIL_SHEET,),
    reviewed_basis=(
        "openpyxl 逐 sheet 直读权威模板 M/M3 库存股.xlsx 的 10 张 sheet。"
        "审定表 M3-1（33r×12c / 129 公式）：两级表头 R5-R6，数据区 R7-R16（10 行），"
        "R17 合计 SUM。A~K 列全公式引用明细表。"
        "明细表 M3-2（59r×19c / 72 公式）：三级表头 R12-R14，数据区 R15-R24（10 行），"
        "R25 合计公式。Editable 14 列 + Formula 5 列。"
        "科目码 4102 库存股（贷方/权益类，借方减）。"
    ),
    html_store_note=(
        "M3 的业务内容由 useM3FormData.ts 承载：ITEM_PREFIX='M3-'，命名 M3-{sheet}-{field}。"
        "审定表全公式引用明细表，真正数据入口在明细表。"
    ),
)

# ── 构建 provider ────────────────────────────────────────────────────────

_P = build_m_provider(CONFIG)
_O = _P.orch

# ── 导出 ──────────────────────────────────────────────────────────────────

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
