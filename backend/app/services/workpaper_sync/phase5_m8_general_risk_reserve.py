# -*- coding: utf-8 -*-
"""M8 一般风险准备双向回写 provider。共享内核 `phase5_m_cycle_common.py`。

spec: m-cycle-bidirectional-pipeline
entry: xlsx/gt-m8-general-risk-reserve
科目: 4104 一般风险准备（贷方/权益类/金融企业专属）
受管 sheet: 审定表M8-1 + 明细表M8-2
🔴 「针对性测试M8-5-删除」和 Q8A 修订前 不在受管范围
"""
from __future__ import annotations

from typing import Any, Final

from app.services.workpaper_sync.models import DefinitionKind
from app.services.workpaper_sync.phase5_m_cycle_common import (
    MEntryConfig, MFieldSpec, MSheetConfig,
    build_m_provider, publish_m_definitions,
)

ENTRY_ID: Final[str] = "xlsx/gt-m8-general-risk-reserve"
ADAPTER_ID: Final[str] = "m8.general_risk_reserve"
WP_CODES: Final[frozenset[str]] = frozenset({"M8G"})
TEMPLATE_RELATIVE_PATH: Final[str] = "M/M8 一般风险准备.xlsx"
TEMPLATE_SHA256: Final[str] = "248a8bb72f1b3c2f8ec28950f718138462ec26a33b6e46c58884a47a74cbbcc1"
ACCOUNT_CODE: Final[str] = "4104"
ITEM_PREFIX: Final[str] = "M8-"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"

# 审定表 M8-1（25r×12c / 84 公式）—— A~K 全公式，只有 L 列 editable
DETERMINATION_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("project_name", "A", "formula", "text", "projectName", "项目名称"),
    MFieldSpec("prior_unadjusted", "B", "formula", "amount", "priorUnadjusted", "未审数", "期初数"),
    MFieldSpec("prior_aje", "C", "formula", "amount", "priorAje", "账项调整", "期初数"),
    MFieldSpec("prior_rje", "D", "formula", "amount", "priorRje", "重分类调整", "期初数"),
    MFieldSpec("prior_audited", "E", "formula", "amount", "priorAudited", "审定数", "期初数"),
    MFieldSpec("current_unadjusted", "F", "formula", "amount", "currentUnadjusted", "未审数", "期末数"),
    MFieldSpec("current_aje", "G", "formula", "amount", "currentAje", "账项调整", "期末数"),
    MFieldSpec("current_rje", "H", "formula", "amount", "currentRje", "重分类调整", "期末数"),
    MFieldSpec("current_audited", "I", "formula", "amount", "currentAudited", "审定数", "期末数"),
    MFieldSpec("change_amount", "J", "formula", "amount", "changeAmount", "变动额"),
    MFieldSpec("change_rate", "K", "formula", "rate", "changeRate", "变动率"),
    MFieldSpec("reason_analysis", "L", "editable", "text", "reasonAnalysis", "原因分析"),
)

DETERMINATION_SHEET: Final[MSheetConfig] = MSheetConfig(
    sheet_name="审定表M8-1",
    sheet_key="m8-determination",
    table_key="m8_determination_summary",
    header_rows=2, first_data_row=7, last_data_row=12, footer_row=13,
    anchor_row=5, fields=DETERMINATION_FIELDS,
    row_identity_kind="",
    footer_carries_total=True, delete_policy="reject",
)

# 明细表 M8-2（24r×18c / 56 公式）
# Editable: A/B/C/D/F/G/H/I/J/K/P/Q/R（13 列） Formula: E/L/M/N/O（5 列）
DETAIL_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("item_name", "A", "editable", "text", "itemName", "项目"),
    MFieldSpec("prior_opening", "B", "editable", "amount", "priorOpening", "期初数", "未审数"),
    MFieldSpec("increase_amount", "C", "editable", "amount", "increaseAmount", "本期增加", "未审数"),
    MFieldSpec("decrease_amount", "D", "editable", "amount", "decreaseAmount", "本期减少", "未审数"),
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
    MFieldSpec("doc_reference", "P", "editable", "text", "docReference", "文件依据"),
    MFieldSpec("ref_index", "Q", "editable", "text", "refIndex", "索引号"),
    MFieldSpec("remark", "R", "editable", "text", "remark", "备注"),
)

DETAIL_SHEET: Final[MSheetConfig] = MSheetConfig(
    sheet_name="明细表M8-2",
    sheet_key="m801-managed",
    table_key="m8_detail_rows",
    header_rows=2, first_data_row=10, last_data_row=16, footer_row=17,
    anchor_row=8, fields=DETAIL_FIELDS,
    row_identity_kind="template_row_key",
    footer_carries_total=True, delete_policy="reject",
)

CONFIG: Final[MEntryConfig] = MEntryConfig(
    code="M8", entry_id=ENTRY_ID, adapter_id=ADAPTER_ID, wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH, template_sha256=TEMPLATE_SHA256,
    account_code=ACCOUNT_CODE, account_nature="权益类",
    item_prefix=ITEM_PREFIX, determination_sheet_name="审定表M8-1",
    sheets=(DETAIL_SHEET,),
    reviewed_basis="openpyxl 逐 sheet 直读权威模板 M/M8 一般风险准备.xlsx。审定表 M8-1（25r×12c / 84 公式）：A~K 全公式，只有 L 列 editable。明细表 M8-2（24r×18c / 56 公式）：13 editable + 5 formula。🔴 「针对性测试M8-5-删除」和 Q8A 修订前历史 sheet 不在受管范围。",
    html_store_note="M8 ITEM_PREFIX='M8-'，金融企业专属科目。",
)

_P = build_m_provider(CONFIG)
_O = _P.orch

EntrySelectionError = _P.EntrySelectionError; StorePayloadError = _P.StorePayloadError
Phase5Definitions = _P.Phase5Definitions; TemplateResolutionFacts = _P.TemplateResolutionFacts
excel_carrier_gate = _P.excel_carrier_gate; authoritative_template_path = _P.authoritative_template_path
read_authoritative_template = _P.read_authoritative_template
assert_no_implicit_template_fallback = _P.assert_no_implicit_template_fallback
assert_entry_selectable = _P.assert_entry_selectable
template_definition_payload = _P.template_definition_payload
instrumentation_definition_payload = _P.instrumentation_definition_payload
authority_model_payload = _P.authority_model_payload
build_contract_payload = _P.build_contract_payload; contract_file_path = _P.contract_file_path
load_contract_from_disk = _P.load_contract_from_disk
assert_contract_file_matches_source = _P.assert_contract_file_matches_source
build_store_projection = _P.build_store_projection
merge_projection_into_store_rows = _P.merge_projection_into_store_rows
all_store_item_ids = _P.all_store_item_ids
instrumentation_spec = _P.instrumentation_spec
instrumentation_specs = _P.instrumentation_specs
build_matcher = _P.build_matcher; build_registration = _P.build_registration
register_adapter = _P.register_adapter; attach_adapters = _P.attach_adapters
manifest_capability_enabled = _P.manifest_capability_enabled
assert_manifest_capability_enabled = _P.assert_manifest_capability_enabled

async def resolve_published_frozen_definitions(*, session: Any, representation: Any, contract: Any) -> Any:
    from pathlib import Path
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import observe_published_frozen_definitions
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    backend_root = Path(__file__).resolve().parents[3]
    obs = await observe_published_frozen_definitions(session=session, resolution=CanonicalResolutionService(session, CanonicalArtifactRepository(backend_root)), representation=representation, correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}")
    if obs.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise EntrySelectionError(f"entry {ENTRY_ID}: digest mismatch {obs.definitions.contract.canonical_sha256} vs {contract.canonical_sha256}")
    return obs

async def publish_definitions(publisher: Any) -> Any:
    return await publish_m_definitions(_P, publisher)

publish_pilot_definitions = publish_definitions; attach_pilot_adapters = attach_adapters; PILOT_WP_CODES = WP_CODES
