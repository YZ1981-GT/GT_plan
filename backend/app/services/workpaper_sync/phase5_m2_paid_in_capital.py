# -*- coding: utf-8 -*-
"""M2 实收资本（股本）双向回写 provider。共享内核 `phase5_m_cycle_common.py`。

spec: m2-m3-m4-m7-m10-bidirectional-pipeline
entry: xlsx/gt-m2-paid-in-capital
科目: 4001 实收资本（贷方/权益类）
受管 sheet: 明细表（非上市公司）M2-2（主，21e+15f = 24 列）
审定表 M2-1 全公式（0e+11f），不做 instrumentation。

🔴 M2 有两张同码明细表（上市/非上市），m2-m3-m4-m7-m10-sheet-map-drift-and-collapse
   的 BP-8 已处理判别位。本 provider 先覆盖非上市公司版（结构较简，且审定表引用此表），
   上市公司版按需扩展。
🔴 非上市公司明细表 37r×24c，15e + 9f = 24 列。
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

ENTRY_ID: Final[str] = "xlsx/gt-m2-paid-in-capital"
ADAPTER_ID: Final[str] = "m2.paid_in_capital"
WP_CODES: Final[frozenset[str]] = frozenset({"M2P"})
TEMPLATE_RELATIVE_PATH: Final[str] = "M/M2 实收资本（股本）.xlsx"
TEMPLATE_SHA256: Final[str] = "9fb504204d6ab731d85c67ba43fdfc7ccda92787bc0a6d95bc83d14c74ffe15b"
ACCOUNT_CODE: Final[str] = "4001"
ITEM_PREFIX: Final[str] = "M2-"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
STORE_ITEM_ID: Final[str] = "M2-"

# ═══════════════════════════════════════════════════════════════════════════
# 明细表（非上市公司）M2-2 字段（37r×24c / 115 公式）
# 表头 R10~R12（三级），数据区 R13~R22，R23 合计
# Editable: A/B/C/E/F/G/J/K/L/M/N/O/V/W/X（15 列）
# Formula: D/H/I/P/Q/R/S/T/U（9 列）
# ═══════════════════════════════════════════════════════════════════════════

UNLISTED_DETAIL_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("investor_name", "A", "editable", "text", "investorName", "投资方名称"),
    MFieldSpec("invest_method", "B", "editable", "text", "investMethod", "出资方式", "未审数/期初数"),
    MFieldSpec("invest_amount", "C", "editable", "amount", "investAmount", "出资金额", "未审数/期初数"),
    MFieldSpec("invest_ratio", "D", "formula", "rate", "investRatio", "比例%", "未审数/期初数"),
    MFieldSpec("increase_amount", "E", "editable", "amount", "increaseAmount", "出资金额", "本期增加"),
    MFieldSpec("increase_method", "F", "editable", "text", "increaseMethod", "出资方式", "本期增加"),
    MFieldSpec("decrease_amount", "G", "editable", "amount", "decreaseAmount", "本期减少"),
    MFieldSpec("closing_amount", "H", "formula", "amount", "closingAmount", "出资金额", "期末数"),
    MFieldSpec("closing_ratio", "I", "formula", "rate", "closingRatio", "比例%", "期末数"),
    MFieldSpec("prior_adj_aje", "J", "editable", "amount", "priorAdjAje", "账项调整", "期初调整"),
    MFieldSpec("prior_adj_rje", "K", "editable", "amount", "priorAdjRje", "重分类调整", "期初调整"),
    MFieldSpec("current_aje_increase", "L", "editable", "amount", "currentAjeIncrease", "本期增加", "账项调整"),
    MFieldSpec("current_aje_decrease", "M", "editable", "amount", "currentAjeDecrease", "本期减少", "账项调整"),
    MFieldSpec("current_rje_increase", "N", "editable", "amount", "currentRjeIncrease", "本期增加", "重分类调整"),
    MFieldSpec("current_rje_decrease", "O", "editable", "amount", "currentRjeDecrease", "本期减少", "重分类调整"),
    MFieldSpec("audited_opening", "P", "formula", "amount", "auditedOpening", "出资金额", "审定数/期初数"),
    MFieldSpec("audited_opening_ratio", "Q", "formula", "rate", "auditedOpeningRatio", "比例%", "审定数/期初数"),
    MFieldSpec("audited_increase", "R", "formula", "amount", "auditedIncrease", "本期增加", "审定数"),
    MFieldSpec("audited_decrease", "S", "formula", "amount", "auditedDecrease", "本期减少", "审定数"),
    MFieldSpec("audited_closing", "T", "formula", "amount", "auditedClosing", "出资金额", "审定数/期末数"),
    MFieldSpec("audited_closing_ratio", "U", "formula", "rate", "auditedClosingRatio", "比例%", "审定数/期末数"),
    MFieldSpec("verified", "V", "editable", "text", "verified", "是否经过验资"),
    MFieldSpec("verification_ref", "W", "editable", "text", "verificationRef", "验资报告索引号"),
    MFieldSpec("remark", "X", "editable", "text", "remark", "备注"),
)

UNLISTED_DETAIL_SHEET: Final[MSheetConfig] = MSheetConfig(
    sheet_name="明细表（非上市公司）M2-2",
    sheet_key="m201-unlisted-managed",
    table_key="m2_unlisted_detail_rows",
    header_rows=3,
    first_data_row=13,
    last_data_row=22,
    footer_row=23,
    anchor_row=10,
    fields=UNLISTED_DETAIL_FIELDS,
    row_identity_kind="template_row_key",
    footer_carries_total=True,
    delete_policy="reject",
)

# ═══════════════════════════════════════════════════════════════════════════
# 明细表（上市公司）M2-2 字段（38r×36c / 187 公式）
# 表头 R10~R12（三级），数据区 R13~R22，R23 合计
# Editable 21 列 / Formula 15 列 = 36 列 —— M 全域最宽 sheet
# ═══════════════════════════════════════════════════════════════════════════

LISTED_DETAIL_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("investor_name", "A", "editable", "text", "investorName", "投资方名称"),
    MFieldSpec("company_code", "B", "editable", "text", "companyCode", "公司代码"),
    MFieldSpec("invest_method", "C", "editable", "text", "investMethod", "出资方式", "未审数/期初数"),
    MFieldSpec("invest_amount", "D", "editable", "amount", "investAmount", "出资金额", "未审数/期初数"),
    MFieldSpec("invest_ratio", "E", "formula", "rate", "investRatio", "比例%", "未审数/期初数"),
    MFieldSpec("new_shares", "F", "editable", "amount", "newShares", "发行新股", "本期增减"),
    MFieldSpec("bonus_shares", "G", "editable", "amount", "bonusShares", "送股", "本期增减"),
    MFieldSpec("reserve_convert", "H", "editable", "amount", "reserveConvert", "公积金转股", "本期增减"),
    MFieldSpec("other_change", "I", "editable", "amount", "otherChange", "其他", "本期增减"),
    MFieldSpec("change_subtotal", "J", "formula", "amount", "changeSubtotal", "小计", "本期增减"),
    MFieldSpec("closing_amount", "K", "formula", "amount", "closingAmount", "出资金额", "期末数"),
    MFieldSpec("closing_ratio", "L", "formula", "rate", "closingRatio", "比例%", "期末数"),
    MFieldSpec("prior_adj_aje", "M", "editable", "amount", "priorAdjAje", "账项调整", "期初调整"),
    MFieldSpec("prior_adj_rje", "N", "editable", "amount", "priorAdjRje", "重分类调整", "期初调整"),
    MFieldSpec("aje_new_shares", "O", "editable", "amount", "ajeNewShares", "发行新股", "账项调整/本期增减"),
    MFieldSpec("aje_bonus_shares", "P", "editable", "amount", "ajeBonusShares", "送股", "账项调整/本期增减"),
    MFieldSpec("aje_reserve_convert", "Q", "editable", "amount", "ajeReserveConvert", "公积金转股", "账项调整/本期增减"),
    MFieldSpec("aje_other", "R", "editable", "amount", "ajeOther", "其他", "账项调整/本期增减"),
    MFieldSpec("aje_subtotal", "S", "formula", "amount", "ajeSubtotal", "小计", "账项调整/本期增减"),
    MFieldSpec("rje_new_shares", "T", "editable", "amount", "rjeNewShares", "发行新股", "重分类调整/本期增减"),
    MFieldSpec("rje_bonus_shares", "U", "editable", "amount", "rjeBonusShares", "送股", "重分类调整/本期增减"),
    MFieldSpec("rje_reserve_convert", "V", "editable", "amount", "rjeReserveConvert", "公积金转股", "重分类调整/本期增减"),
    MFieldSpec("rje_other", "W", "editable", "amount", "rjeOther", "其他", "重分类调整/本期增减"),
    MFieldSpec("rje_subtotal", "X", "formula", "amount", "rjeSubtotal", "小计", "重分类调整/本期增减"),
    MFieldSpec("audited_opening", "Y", "formula", "amount", "auditedOpening", "出资金额", "审定数/期初数"),
    MFieldSpec("audited_opening_ratio", "Z", "formula", "rate", "auditedOpeningRatio", "比例%", "审定数/期初数"),
    MFieldSpec("audited_new_shares", "AA", "formula", "amount", "auditedNewShares", "发行新股", "审定数/本期增减"),
    MFieldSpec("audited_bonus_shares", "AB", "formula", "amount", "auditedBonusShares", "送股", "审定数/本期增减"),
    MFieldSpec("audited_reserve_convert", "AC", "formula", "amount", "auditedReserveConvert", "公积金转股", "审定数/本期增减"),
    MFieldSpec("audited_other", "AD", "formula", "amount", "auditedOther", "其他", "审定数/本期增减"),
    MFieldSpec("audited_subtotal", "AE", "formula", "amount", "auditedSubtotal", "小计", "审定数/本期增减"),
    MFieldSpec("audited_closing", "AF", "formula", "amount", "auditedClosing", "出资金额", "审定数/期末数"),
    MFieldSpec("audited_closing_ratio", "AG", "formula", "rate", "auditedClosingRatio", "比例%", "审定数/期末数"),
    MFieldSpec("verified", "AH", "editable", "text", "verified", "是否经过验资"),
    MFieldSpec("verification_ref", "AI", "editable", "text", "verificationRef", "验资报告索引号"),
    MFieldSpec("remark", "AJ", "editable", "text", "remark", "备注"),
)

LISTED_DETAIL_SHEET: Final[MSheetConfig] = MSheetConfig(
    sheet_name="明细表（上市公司）M2-2",
    sheet_key="m202-listed-managed",
    table_key="m2_listed_detail_rows",
    header_rows=3,
    first_data_row=13,
    last_data_row=22,
    footer_row=23,
    anchor_row=10,
    fields=LISTED_DETAIL_FIELDS,
    row_identity_kind="template_row_key",
    footer_carries_total=True,
    delete_policy="reject",
)

# ═══════════════════════════════════════════════════════════════════════════
# 组装
# 🔴 M2 有两张同码明细表，contract 各给一份字段映射。
#    sheets 里放两张，build_m_provider 取第一张（非上市）作为主 binding。
# ═══════════════════════════════════════════════════════════════════════════

CONFIG: Final[MEntryConfig] = MEntryConfig(
    code="M2",
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    account_code=ACCOUNT_CODE,
    account_nature="权益类",
    item_prefix=ITEM_PREFIX,
    determination_sheet_name="审定表M2-1",
    sheets=(UNLISTED_DETAIL_SHEET,),
    reviewed_basis=(
        "openpyxl 逐 sheet 直读权威模板 M/M2 实收资本（股本）.xlsx 的 11 张 sheet。"
        "审定表 M2-1（49r×12c / 129 公式）：两级表头 R5-R6，数据区 R7-R16（10 行），"
        "R17 合计 SUM。A~K 全公式引用明细表（非上市公司）。"
        "明细表（非上市公司）M2-2（37r×24c / 115 公式）：三级表头 R10-R12，数据区 R13-R22，"
        "R23 合计。15 editable + 9 formula = 24 列。"
        "明细表（上市公司）M2-2（38r×36c / 187 公式）：三级表头 R10-R12，数据区 R13-R22，"
        "R23 合计。21 editable + 15 formula = 36 列（M 全域最宽 sheet）。"
        "🔴 两张同码明细表结构不同不是简单复制（裸 IF 相同但公式格不同）。"
        "科目码 4001 实收资本（贷方/权益类）。"
    ),
    html_store_note=(
        "M2 的业务内容由 useM2FormData.ts 承载：ITEM_PREFIX='M2-'，命名 M2-{sheet}-{field}。"
        "M2 有两张同码明细表（上市/非上市），审定表全公式引用非上市明细表。"
        "BP-8 判别位：sheet_key 用 m201-unlisted / m202-listed 区分。"
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
