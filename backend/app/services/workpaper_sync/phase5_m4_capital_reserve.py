# -*- coding: utf-8 -*-
"""M4 资本公积双向回写 provider。共享内核 `phase5_m_cycle_common.py`。

spec: m2-m3-m4-m7-m10-bidirectional-pipeline
entry: xlsx/gt-m4-capital-reserve
科目: 4002 资本公积（贷方/权益类）
受管 sheet: 明细表M4-2
审定表 M4-1 除 A 列外全公式（1e+10f），不做 instrumentation。

🔴 M4 明细表结构特殊：R10 / R15 是一级分组合计行（全 SUM），
   R11~R14 / R16~R19 是子项行。数据区 R10~R19，子项的 B~D/F~K 是 editable。
   一级分组行全公式 ⇒ contract 的 row_identity 按「分组+子项」两级处理。
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

ENTRY_ID: Final[str] = "xlsx/gt-m4-capital-reserve"
ADAPTER_ID: Final[str] = "m4.capital_reserve"
WP_CODES: Final[frozenset[str]] = frozenset({"M4C"})
TEMPLATE_RELATIVE_PATH: Final[str] = "M/M4 资本公积.xlsx"
TEMPLATE_SHA256: Final[str] = "40a8fa32902252105c2fe06409f6366a83881c305d97c7a08419f0fc84596a0a"
ACCOUNT_CODE: Final[str] = "4002"
ITEM_PREFIX: Final[str] = "M4-"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
STORE_ITEM_ID: Final[str] = "M4-"

# ═══════════════════════════════════════════════════════════════════════════
# 明细表 M4-2 字段（50r×24c / 89 公式）
# 表头 R8~R9（两级），数据区 R10~R19，R20 合计
# 结构：R10 一级分组（一、资本溢价，全 SUM）→ R11~R14 子项
#       R15 一级分组（二、其他资本公积，全 SUM）→ R16~R19 子项
# 子项行：A editable / B~D editable / E formula / F~K editable / L~O formula
# 一级分组行：A editable / B~O 全 formula（SUM子项）
# contract 取子项行口径：B~D/F~K editable，E/L~O formula
# Editable: A/B/C/D/F/G/H/I/J/K/P/Q（12 列）
# Formula: E/L/M/N/O（5 列）
# 🔴 P/Q 列在数据区之后（备注类），合计行无公式
# ═══════════════════════════════════════════════════════════════════════════

DETAIL_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("category", "A", "editable", "text", "category", "项目类别"),
    MFieldSpec("prior_opening", "B", "formula", "amount", "priorOpening", "期初数", "未审数"),
    MFieldSpec("current_increase", "C", "formula", "amount", "currentIncrease", "本期增加"),
    MFieldSpec("current_decrease", "D", "formula", "amount", "currentDecrease", "本期减少"),
    MFieldSpec("closing_balance", "E", "formula", "amount", "closingBalance", "期末数", "未审数"),
    MFieldSpec("prior_adj_aje", "F", "formula", "amount", "priorAdjAje", "账项调整", "期初调整"),
    MFieldSpec("prior_adj_rje", "G", "formula", "amount", "priorAdjRje", "重分类调整", "期初调整"),
    MFieldSpec("current_aje_increase", "H", "formula", "amount", "currentAjeIncrease", "本期增加", "账项调整"),
    MFieldSpec("current_aje_decrease", "I", "formula", "amount", "currentAjeDecrease", "本期减少", "账项调整"),
    MFieldSpec("current_rje_increase", "J", "formula", "amount", "currentRjeIncrease", "本期增加", "重分类调整"),
    MFieldSpec("current_rje_decrease", "K", "formula", "amount", "currentRjeDecrease", "本期减少", "重分类调整"),
    MFieldSpec("audited_opening", "L", "formula", "amount", "auditedOpening", "期初数", "审定数"),
    MFieldSpec("audited_increase", "M", "formula", "amount", "auditedIncrease", "本期增加", "审定数"),
    MFieldSpec("audited_decrease", "N", "formula", "amount", "auditedDecrease", "本期减少", "审定数"),
    MFieldSpec("audited_closing", "O", "formula", "amount", "auditedClosing", "期末数", "审定数"),
    MFieldSpec("accounting_correct", "P", "editable", "text", "accountingCorrect", "相关会计处理是否正确"),
    MFieldSpec("remark", "Q", "editable", "text", "remark", "备注"),
)

DETAIL_SHEET: Final[MSheetConfig] = MSheetConfig(
    sheet_name="明细表M4-2",
    sheet_key="m401-managed",
    table_key="m4_detail_rows",
    header_rows=2,
    first_data_row=10,
    last_data_row=19,
    footer_row=20,
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
    code="M4",
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    account_code=ACCOUNT_CODE,
    account_nature="权益类",
    item_prefix=ITEM_PREFIX,
    determination_sheet_name="审定表M4-1",
    sheets=(DETAIL_SHEET,),
    reviewed_basis=(
        "openpyxl 逐 sheet 直读权威模板 M/M4 资本公积.xlsx 的 9 张 sheet。"
        "审定表 M4-1（44r×12c / 41 公式）：两级表头 R5-R6，数据区 R7-R9（3 行），"
        "R10 合计 SUM。除 A 列外全公式引用明细表。"
        "明细表 M4-2（50r×24c / 89 公式）：两级表头 R8-R9，数据区 R10-R19（10 行/含 2 分组合计行），"
        "R20 合计公式。两级分组结构：一级分组行全 SUM，子项行 B~D/F~K editable。"
        "Editable 12 列 + Formula 5 列。科目码 4002 资本公积（贷方/权益类）。"
    ),
    html_store_note=(
        "M4 的业务内容由 useM4FormData.ts 承载：ITEM_PREFIX='M4-'，命名 M4-{sheet}-{field}。"
        "明细表有两级分组，一级分组行是 SUM 公式。"
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
