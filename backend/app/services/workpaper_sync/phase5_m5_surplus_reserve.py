# -*- coding: utf-8 -*-
"""M5 盈余公积双向回写 provider。共享内核 `phase5_m_cycle_common.py`。

spec: m-cycle-bidirectional-pipeline
entry: xlsx/gt-m5-surplus-reserve
科目: 4101 盈余公积（贷方/权益类）
受管 sheet: 审定表M5-1 + 明细表M5-2
"""
from __future__ import annotations

from typing import Any, Final

from app.services.workpaper_sync.models import DefinitionKind
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

ENTRY_ID: Final[str] = "xlsx/gt-m5-surplus-reserve"
ADAPTER_ID: Final[str] = "m5.surplus_reserve"
WP_CODES: Final[frozenset[str]] = frozenset({"M5S"})
TEMPLATE_RELATIVE_PATH: Final[str] = "M/M5 盈余公积.xlsx"
TEMPLATE_SHA256: Final[str] = "0e32a0567e4e3a36e137fa2f2d8ae66a0b1d5eaf266dfd57f9ffd1ce24ae2316"
ACCOUNT_CODE: Final[str] = "4101"
ITEM_PREFIX: Final[str] = "M5-"
STORE_ITEM_ID: Final[str] = "M5-"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"

# ═══════════════════════════════════════════════════════════════════════════
# 审定表 M5-1 字段（48r×12c / 59 公式）
# 表头 R5-R6（两级），数据区 R7-R10，R11 合计
# B~K 列全是公式（引用明细表），只有 A 列和 L 列是 editable
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
    sheet_name="审定表M5-1",
    sheet_key="m5-determination",
    table_key="m5_determination_summary",
    header_rows=2,
    first_data_row=7,
    last_data_row=10,
    footer_row=11,
    anchor_row=5,
    fields=DETERMINATION_FIELDS,
    row_identity_kind="",
    footer_carries_total=True,
    delete_policy="reject",
)

# ═══════════════════════════════════════════════════════════════════════════
# 明细表 M5-2 字段（38r×17c / 41 公式）
# 表头 R9-R11（三级），数据区 R12-R15，R16 合计
# Editable: A/B/C/D/E/F/H/I/J/K/L/M（12 列）
# Formula: G/N/O/P/Q（5 列）
# ═══════════════════════════════════════════════════════════════════════════

DETAIL_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("item_name", "A", "editable", "text", "itemName", "明细项目"),
    MFieldSpec("prior_opening", "B", "editable", "amount", "priorOpening", "期初数", "未审数"),
    MFieldSpec("increase_amount", "C", "editable", "amount", "increaseAmount", "金额", "本期增加"),
    MFieldSpec("increase_method", "D", "editable", "text", "increaseMethod", "增加方式", "本期增加"),
    MFieldSpec("decrease_amount", "E", "editable", "amount", "decreaseAmount", "金额", "本期减少"),
    MFieldSpec("decrease_method", "F", "editable", "text", "decreaseMethod", "减少方式", "本期减少"),
    MFieldSpec("closing_balance", "G", "formula", "amount", "closingBalance", "期末数", "未审数"),
    MFieldSpec("prior_adj_aje", "H", "editable", "amount", "priorAdjAje", "账项调整", "期初调整"),
    MFieldSpec("prior_adj_rje", "I", "editable", "amount", "priorAdjRje", "重分类调整", "期初调整"),
    MFieldSpec("current_aje_increase", "J", "editable", "amount", "currentAjeIncrease", "本期增加", "账项调整"),
    MFieldSpec("current_aje_decrease", "K", "editable", "amount", "currentAjeDecrease", "本期减少", "账项调整"),
    MFieldSpec("current_rje_increase", "L", "editable", "amount", "currentRjeIncrease", "本期增加", "重分类调整"),
    MFieldSpec("current_rje_decrease", "M", "editable", "amount", "currentRjeDecrease", "本期减少", "重分类调整"),
    MFieldSpec("audited_opening", "N", "formula", "amount", "auditedOpening", "期初数", "审定数"),
    MFieldSpec("audited_increase", "O", "formula", "amount", "auditedIncrease", "本期增加", "审定数"),
    MFieldSpec("audited_decrease", "P", "formula", "amount", "auditedDecrease", "本期减少", "审定数"),
    MFieldSpec("audited_closing", "Q", "formula", "amount", "auditedClosing", "期末数", "审定数"),
)

DETAIL_SHEET: Final[MSheetConfig] = MSheetConfig(
    sheet_name="明细表M5-2",
    sheet_key="m501-managed",
    table_key="m5_detail_rows",
    header_rows=3,
    first_data_row=12,
    last_data_row=15,
    footer_row=16,
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
    code="M5",
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    account_code=ACCOUNT_CODE,
    account_nature="权益类",
    item_prefix=ITEM_PREFIX,
    determination_sheet_name="审定表M5-1",
    sheets=(DETAIL_SHEET,),
    reviewed_basis=(
        "openpyxl 逐 sheet 直读权威模板 M/M5 盈余公积.xlsx 的 10 张 sheet。"
        "审定表 M5-1（48r×12c / 59 公式）：两级表头 R5-R6，数据区 R7-R10（4 行固定科目），"
        "R11 合计 SUM。B~K 列全公式引用明细表，A 列项目名称 + L 列原因分析为 editable。"
        "明细表 M5-2（38r×17c / 41 公式）：三级表头 R9-R11，数据区 R12-R15（4 行固定），"
        "R16 合计公式。Editable 12 列 + Formula 5 列。科目码 4101 盈余公积（贷方/权益类）。"
    ),
    html_store_note=(
        "M5 的业务内容由 useM5FormData.ts 承载：ITEM_PREFIX='M5-'，命名 M5-{sheet}-{field}。"
        "审定表几乎全是公式，真正数据入口在明细表。"
    ),
)

# ── 构建 provider ────────────────────────────────────────────────────────

_P = build_m_provider(CONFIG)
_O = _P.orch

# ── 导出（与 K3 同款，逐个显式导出）────────────────────────────────────────

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


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: Any
) -> Any:
    from pathlib import Path
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import (
        observe_published_frozen_definitions,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    backend_root = Path(__file__).resolve().parents[3]
    obs = await observe_published_frozen_definitions(
        session=session,
        resolution=CanonicalResolutionService(session, CanonicalArtifactRepository(backend_root)),
        representation=representation,
        correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if obs.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise EntrySelectionError(
            f"entry {ENTRY_ID}: digest mismatch "
            f"{obs.definitions.contract.canonical_sha256} vs {contract.canonical_sha256}"
        )
    return obs


async def publish_definitions(publisher: Any) -> Any:
    """按 DAG 发布 M5 的全套 definition。"""
    return await publish_m_definitions(_P, publisher)


# 别名（与 pilot 接口兼容）
publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
