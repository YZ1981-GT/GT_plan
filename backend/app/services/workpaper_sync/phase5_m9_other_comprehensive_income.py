# -*- coding: utf-8 -*-
"""M9 其他综合收益双向回写 provider。共享内核 `phase5_m_cycle_common.py`。

spec: m-cycle-bidirectional-pipeline
entry: xlsx/gt-m9-other-comprehensive-income
科目: 4103 其他综合收益（贷方/权益类）
受管 sheet: 审定表M9-1 + 明细表M9-2
🔴 M9 是唯一 dual_mode_carrier.kind=='none' 的 entry
🔴 明细表 M9-2 是 46r×30c 宽表（30 列中 17 列公式、仅 3 列 editable）
"""
from __future__ import annotations

from typing import Any, Final

from app.services.workpaper_sync.models import DefinitionKind
from app.services.workpaper_sync.phase5_m_cycle_common import (
    MEntryConfig, MFieldSpec, MSheetConfig,
    build_m_provider, publish_m_definitions,
)

ENTRY_ID: Final[str] = "xlsx/gt-m9-other-comprehensive-income"
ADAPTER_ID: Final[str] = "m9.other_comprehensive_income"
WP_CODES: Final[frozenset[str]] = frozenset({"M9O"})
TEMPLATE_RELATIVE_PATH: Final[str] = "M/M9 其他综合收益.xlsx"
TEMPLATE_SHA256: Final[str] = "0cfdc95ce3f9410610037b684f50a07f874df1cab4cebe09aa63c6461b6fbc66"
ACCOUNT_CODE: Final[str] = "4103"
ITEM_PREFIX: Final[str] = "M9-"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"

# ═══════════════════════════════════════════════════════════════════════════
# 审定表 M9-1（47r×12c / 41 公式）
# A 列 editable（项目名称不是公式），L 列 editable，B~K 公式
# ═══════════════════════════════════════════════════════════════════════════

DETERMINATION_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("project_name", "A", "editable", "text", "projectName", "项目名称"),
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
    sheet_name="审定表M9-1",
    sheet_key="m9-determination",
    table_key="m9_determination_summary",
    header_rows=2, first_data_row=7, last_data_row=9, footer_row=10,
    anchor_row=5, fields=DETERMINATION_FIELDS,
    row_identity_kind="",
    footer_carries_total=True, delete_policy="reject",
)

# ═══════════════════════════════════════════════════════════════════════════
# 明细表 M9-2（46r×30c / 145 公式）—— 🔴 宽表
# R10 行（分组小计行）大部分是 SUM 公式
# 只有 A（项目类别）/ R（转损益金额，但 R 在分组行也可能无公式）/ U（备注）是 editable
# 注意：B 列在扫描中缺失（合并单元格导致 R10 的 B 列无值），实际属于 A 列的延伸
# ═══════════════════════════════════════════════════════════════════════════

DETAIL_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("item_category", "A", "editable", "text", "itemCategory", "项目类别"),
    MFieldSpec("prior_opening", "C", "formula", "amount", "priorOpening", "期初数", "未审数"),
    MFieldSpec("current_pretax", "D", "formula", "amount", "currentPretax", "本期所得税前发生额", "未审数"),
    MFieldSpec("transfer_to_pnl", "E", "formula", "amount", "transferToPnl", "减：前期计入其他综合收益当期转入损益/留存收益", "未审数"),
    MFieldSpec("income_tax", "F", "formula", "amount", "incomeTax", "减：所得税费用", "未审数"),
    MFieldSpec("closing_balance", "G", "formula", "amount", "closingBalance", "期末数", "未审数"),
    MFieldSpec("prior_adj_aje", "H", "formula", "amount", "priorAdjAje", "账项调整", "期初调整"),
    MFieldSpec("prior_adj_rje", "I", "formula", "amount", "priorAdjRje", "重分类调整", "期初调整"),
    MFieldSpec("current_aje_pretax", "J", "formula", "amount", "currentAjePretax", "本期所得税前发生额", "账项调整"),
    MFieldSpec("current_aje_transfer", "K", "formula", "amount", "currentAjeTransfer", "减：前期计入其他综合收益当期转入损益/留存收益", "账项调整"),
    MFieldSpec("current_aje_tax", "L", "formula", "amount", "currentAjeTax", "减：所得税费用", "账项调整"),
    MFieldSpec("current_rje_pretax", "M", "formula", "amount", "currentRjePretax", "本期所得税前发生额", "重分类调整"),
    MFieldSpec("current_rje_transfer", "N", "formula", "amount", "currentRjeTransfer", "减：前期计入其他综合收益当期转入损益/留存收益", "重分类调整"),
    MFieldSpec("current_rje_tax", "O", "formula", "amount", "currentRjeTax", "减：所得税费用", "重分类调整"),
    MFieldSpec("audited_opening", "P", "formula", "amount", "auditedOpening", "期初数", "审定数"),
    MFieldSpec("audited_pretax", "Q", "formula", "amount", "auditedPretax", "本期所得税前发生额", "审定数"),
    MFieldSpec("audited_transfer", "R", "formula", "amount", "auditedTransfer", "减：前期计入其他综合收益当期转入损益/留存收益", "审定数"),
    MFieldSpec("audited_tax", "S", "formula", "amount", "auditedTax", "减：所得税费用", "审定数"),
    MFieldSpec("audited_closing", "T", "formula", "amount", "auditedClosing", "期末数", "审定数"),
    MFieldSpec("remark", "U", "editable", "text", "remark", "备注"),
)

DETAIL_SHEET: Final[MSheetConfig] = MSheetConfig(
    sheet_name="明细表M9-2",
    sheet_key="m901-managed",
    table_key="m9_detail_rows",
    header_rows=2, first_data_row=10, last_data_row=26, footer_row=27,
    anchor_row=8, fields=DETAIL_FIELDS,
    row_identity_kind="template_row_key",
    footer_carries_total=True, delete_policy="reject",
)

CONFIG: Final[MEntryConfig] = MEntryConfig(
    code="M9", entry_id=ENTRY_ID, adapter_id=ADAPTER_ID, wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH, template_sha256=TEMPLATE_SHA256,
    account_code=ACCOUNT_CODE, account_nature="权益类",
    item_prefix=ITEM_PREFIX, determination_sheet_name="审定表M9-1",
    sheets=(DETAIL_SHEET,),
    reviewed_basis="openpyxl 逐 sheet 直读权威模板 M/M9 其他综合收益.xlsx。审定表 M9-1（47r×12c / 41 公式）：A/L 列 editable，B~K 公式。明细表 M9-2（46r×30c / 145 公式 / 宽表）：仅 3 列 editable（A 项目类别 / R 转损益 / U 备注），其余 17 列全公式。🔴 M9 是唯一无模式切换开关的 entry。明细表含分组结构（不能重分类 / 能重分类两段）。",
    html_store_note="M9 ITEM_PREFIX='M9-'，唯一 carrier.kind='none' entry。明细表 30 列宽表大部分公式。",
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
