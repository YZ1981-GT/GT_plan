# -*- coding: utf-8 -*-
"""M6 未分配利润双向回写 provider。共享内核 `phase5_m_cycle_common.py`。

spec: m2-m3-m4-m7-m10-bidirectional-pipeline
entry: xlsx/gt-m6-retained-earnings
科目: 4104 未分配利润（贷方/权益类）
受管 sheet: 明细表M6-2
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

ENTRY_ID: Final[str] = "xlsx/gt-m6-retained-earnings"
ADAPTER_ID: Final[str] = "m6.retained_earnings"
WP_CODES: Final[frozenset[str]] = frozenset({"M6R"})
TEMPLATE_RELATIVE_PATH: Final[str] = "M/M6 未分配利润.xlsx"
TEMPLATE_SHA256: Final[str] = "bedd8b0799b4170b06e0257e9a19e3a5ea5585dae02704231bf93a57cf830bf5"
ACCOUNT_CODE: Final[str] = "4104"
ITEM_PREFIX: Final[str] = "M6-"
STORE_ITEM_ID: Final[str] = "M6-"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"

# ═══════════════════════════════════════════════════════════════════════════
# 明细表 M6-2 字段（32r×19c / 63 公式）
# 表头 R8-R9（两级：B8「本期数」F8「上期数」 / B9~I9 叶子）
# 数据区 R10-R24（15 行固定项：上年年末余额→七、本年年末余额）
# R25 = 年末余额合计行
# Editable: A（项目名）B/C/D（本期未审/AJE/RJE）F/G/H（上期同）J（索引号）K（备注）
# Formula: E（=B+C+D）I（=F+G+H）
# ═══════════════════════════════════════════════════════════════════════════

DETAIL_FIELDS: Final[tuple[MFieldSpec, ...]] = (
    MFieldSpec("item_name", "A", "editable", "text", "itemName", "内容"),
    MFieldSpec("current_unadjusted", "B", "editable", "amount", "currentUnadjusted", "未审数", "本期数"),
    MFieldSpec("current_aje", "C", "editable", "amount", "currentAje", "账项调整", "本期数"),
    MFieldSpec("current_rje", "D", "editable", "amount", "currentRje", "重分类调整", "本期数"),
    MFieldSpec("current_audited", "E", "formula", "amount", "currentAudited", "审定数", "本期数"),
    MFieldSpec("prior_unadjusted", "F", "editable", "amount", "priorUnadjusted", "未审数", "上期数"),
    MFieldSpec("prior_aje", "G", "editable", "amount", "priorAje", "账项调整", "上期数"),
    MFieldSpec("prior_rje", "H", "editable", "amount", "priorRje", "重分类调整", "上期数"),
    MFieldSpec("prior_audited", "I", "formula", "amount", "priorAudited", "审定数", "上期数"),
    MFieldSpec("index_ref", "J", "editable", "text", "indexRef", "索引号"),
    MFieldSpec("remark", "K", "editable", "text", "remark", "备注"),
)

DETAIL_SHEET: Final[MSheetConfig] = MSheetConfig(
    sheet_name="明细表M6-2",
    sheet_key="m601-managed",
    table_key="m6_detail_rows",
    header_rows=2,
    first_data_row=10,
    last_data_row=24,
    footer_row=25,
    anchor_row=8,
    fields=DETAIL_FIELDS,
    row_identity_kind="template_row_key",
    footer_carries_total=True,
    footer_marker="七、本年年末余额",
    delete_policy="reject",
)

# ═══════════════════════════════════════════════════════════════════════════
# 组装
# ═══════════════════════════════════════════════════════════════════════════

CONFIG: Final[MEntryConfig] = MEntryConfig(
    code="M6",
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    account_code=ACCOUNT_CODE,
    account_nature="权益类",
    item_prefix=ITEM_PREFIX,
    determination_sheet_name="审定表M6-1",
    sheets=(DETAIL_SHEET,),
    reviewed_basis=(
        "openpyxl 逐 sheet 直读权威模板 M/M6 未分配利润.xlsx 的 10 张 sheet。"
        "审定表 M6-1（47r×12c）：两级表头 R5-R6，数据区 R7（只有 1 行「未分配利润」），"
        "R10 合计。B~K 列全公式引用明细表，A 列和 L 列 editable。"
        "明细表 M6-2（32r×19c / 63 公式）：两级表头 R8-R9，数据区 R10-R24（15 行固定项），"
        "R25 年末余额合计行。Editable 9 列（A/B/C/D/F/G/H/J/K）+ Formula 2 列（E=B+C+D / I=F+G+H）。"
        "科目码 4104 未分配利润（贷方/权益类）。"
    ),
    html_store_note=(
        "M6 的业务内容由 useM6FormData.ts 承载：ITEM_PREFIX='M6-'，命名 M6-{sheet}-{field}。"
        "明细表固定 15 行（上年年末余额→七、本年年末余额），不可动态插删行。"
        "审定表仅 1 行数据全公式引明细表。"
    ),
)

# ── 构建 provider ────────────────────────────────────────────────────────

_P = build_m_provider(CONFIG)
_O = _P.orch

# ── 导出 ────────────────────────────────────────────────────────────────

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
    """按 DAG 发布 M6 的全套 definition。"""
    return await publish_m_definitions(_P, publisher)


# 别名（与 pilot 接口兼容）
publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
