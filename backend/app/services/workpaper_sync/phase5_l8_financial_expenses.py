# -*- coding: utf-8 -*-
"""L8 财务费用「明细表 L8-2」—— L 循环真双向 entry（科目 6603 损益类）。

spec: l8-true-bidirectional-2026-10-01 · 第3步；几何/选型/三件补课裁决见 `phase5_l8_sheets`。
本模块只声明 IDENTITY+SPECS 与 L8 幻影码选型，流程委派 `phase5_l_cycle_common`。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_l_cycle_common as _L
from app.services.workpaper_sync.adapters.registry import AdapterRegistration, EntryMatcher, WorkpaperSyncAdapterRegistry
from app.services.workpaper_sync.contracts import SyncContract, contract_path_for, load_contract
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import DescriptorFacts, RoomFacts, load_entry_manifest, manifest_entries_by_id
from app.services.workpaper_sync.excel_instrumentation import ExcelIdentityCarrierGate, ExcelInstrumentationSpec
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec
from app.services.workpaper_sync.phase5_l8_sheets import (  # noqa: F401
    ACCOUNT_CODE, ADAPTER_ID, AMOUNT_KIND, AUTHORITY_MODEL, AUTO_SOURCE_COLUMNS, DERIVED_ROWS, EMPTY_STORE_PAYLOAD,
    ENTRY_ID, EXPECTED_PROFILE_ID, FIRST_DATA_ROW, FOOTER_MARKER, FOOTER_ROW, FOOTER_SEARCH_COLUMN,
    FORMULA_COLUMNS, FORMULA_MASK, FORMULA_TEMPLATES, GROUP_HEADER_CELLS, HEADER_ROW,
    HTML_ONLY_ROW_KEYS, LAST_DATA_ROW, MANAGED_FIELD_SPECS, MANAGED_FIELD_SPECS_7,
    MANAGED_LAST_COL, MANAGED_SHEET, MANAGED_SHEET_BARE_IF, NEUTRALIZED_COLUMNS, PHASE5_WAVE,
    PRE_SANITIZE_TEMPLATE_SHA256, ROW_IDENTITY_STORE_KEY, ROWS_TABLE_KEY, SHEET_KEY, SPEC_L82,
    STORE_ITEM_ID, TABLE_NAME, TEMPLATE_ID, TEMPLATE_RELATIVE_PATH, TEMPLATE_SHA256, UUID_COL,
    WP_CODES, _HTML_STORE_NOTE, _REVIEWED_BASIS,
)

IDENTITY: Final[_L.LEntryIdentity] = _L.LEntryIdentity(
    entry_id=ENTRY_ID, adapter_id=ADAPTER_ID, phase5_wave=PHASE5_WAVE,
    wp_codes=frozenset(WP_CODES), template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256, primary_store_item_id=STORE_ITEM_ID,
    row_identity_store_key=ROW_IDENTITY_STORE_KEY, html_store_note=_HTML_STORE_NOTE,
    reviewed_basis=_REVIEWED_BASIS, authority_model=AUTHORITY_MODEL,
    expected_profile_id=EXPECTED_PROFILE_ID, html_only_keys=HTML_ONLY_ROW_KEYS,
    derived_readonly_sheet={
        "excel_name": "审定表L8-1",
        "reason": "R7~R16 全部是跨 sheet SUMIF 聚合 明细表L8-2 的下游视图，非录入表；受管表选 L8-2",
    },
    extra_review={
        "template_defects_registered": {
            "bare_if": {
                "sheet": "明细表L8-2 + 审定表L8-1",
                "managed_sheet_bare_if": MANAGED_SHEET_BARE_IF,
                "neutralized_columns": list(NEUTRALIZED_COLUMNS),
                "note": (
                    "受管 sheet 本身 28 个裸 IF（R 列占比 + R23 各月比例），per-file "
                    "neutralize_oo_crash_if_formulas 摘 <f>；N/Q/W 非 IF 公式往返幸存"
                ),
            },
            "derived_rows": {
                "rows": list(DERIVED_ROWS),
                "note": (
                    "跨行派生行 R11=R9-R10 / R13=R11-R12 / R20=R17-R18-R19 的 B~M 作模板预置公式"
                    "幸存，不受管（B~M 列 editable，HTML 12 项缺 R20 汇兑净损失，往返按稳定 key 对齐）"
                ),
            },
            "amount_kind": {
                "value": AMOUNT_KIND,
                "account_code": ACCOUNT_CODE,
                "note": (
                    "科目 6603 财务费用（损益类），取数=本期发生额、兜底 tb_balance.debit_amount 本身；"
                    "受管改线不碰回写逻辑，L8-2 本身不直接回写 TB（回写在下游 L8-1 发布门取 L8-2 合计 Q22）"
                ),
            },
        }
    },
)
SPECS: Final[tuple[RowTableSheetSpec, ...]] = (SPEC_L82,)
EntrySelectionError = _L.LEntrySelectionError
StorePayloadError = _L.LStorePayloadError


def excel_carrier_gate() -> ExcelIdentityCarrierGate: return _L.excel_carrier_gate()
def authoritative_template_path() -> Path: return _L.authoritative_template_path(IDENTITY)
def read_authoritative_template() -> bytes: return _L.read_authoritative_template(IDENTITY)


@dataclass(frozen=True)
class TemplateResolutionFacts:
    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


def assert_no_implicit_template_fallback(resolution: TemplateResolutionFacts, *, wp_codes: frozenset[str]) -> None:
    missing = sorted(wp_codes - set(resolution.by_wp_code))
    if missing: raise EntrySelectionError(f"缺少 wp_code {missing} 的 finder 实测结果")
    leaked = {c: [str(h) for h in v if h] for c, v in resolution.by_wp_code.items() if any(v)}
    if leaked: raise EntrySelectionError(f"幻影码 {sorted(leaked)} 在 finder 上命中了 {leaked}")
    resolved = resolution.parent_resolved_path
    if resolved is None or Path(str(resolved)).resolve() != authoritative_template_path().resolve():
        raise EntrySelectionError(f"父码 {resolution.parent_code!r} 未解析到 {TEMPLATE_RELATIVE_PATH}")


def assert_entry_selectable(*, resolution: TemplateResolutionFacts | None = None,
                            manifest: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    entry = manifest_entries_by_id(manifest if manifest is not None else load_entry_manifest()).get(ENTRY_ID)
    if entry is None or entry.get("document_type") != "xlsx" or not entry.get("independent_entry"):
        raise EntrySelectionError(f"{ENTRY_ID} 非独立 xlsx entry")
    profile = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
    codes = {str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()}
    if profile != EXPECTED_PROFILE_ID or codes != set(WP_CODES):
        raise EntrySelectionError(f"{ENTRY_ID} manifest 身份漂移 profile={profile} codes={sorted(codes)}")
    if resolution: assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))
    return entry


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]: return _L.instrumentation_specs_for(IDENTITY, SPECS)
def instrumentation_spec() -> ExcelInstrumentationSpec: return instrumentation_specs()[0]
def template_definition_payload() -> dict[str, Any]: return _L.template_definition_payload(IDENTITY, SPECS)
def instrumentation_definition_payload() -> dict[str, Any]: return _L.instrumentation_definition_payload(IDENTITY, SPECS)
def authority_model_payload() -> dict[str, Any]: return _L.authority_model_payload(IDENTITY)
def build_contract_payload() -> dict[str, Any]: return _L.build_contract_payload(IDENTITY, SPECS)
def contract_file_path() -> Path: return contract_path_for(ADAPTER_ID)
def load_contract_from_disk() -> SyncContract: return load_contract(ADAPTER_ID)
def assert_contract_file_matches_source() -> SyncContract: return _L.assert_contract_file_matches_source(IDENTITY, build_contract_payload())
def contract_payload_digest() -> str: return canonical_digest(build_contract_payload())
def dump_contract_json() -> str: return _L.dump_contract_json(build_contract_payload())


def build_store_projection(payload: str | bytes | Sequence[Any], *, contract: SyncContract,
                           limits: Any | None = None) -> Any:
    from app.services.workpaper_sync.phase5_row_table_sheet import RowTableStorePayloadError, build_store_projection as engine
    try: return engine(SPEC_L82, payload, contract=contract, limits=limits)
    except RowTableStorePayloadError as exc: raise StorePayloadError(str(exc)) from exc


def merge_projection_into_store_rows(*, projection: Any, base_rows: list[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import merge_projection_into_store_rows as engine
    return engine(SPEC_L82, projection=projection, base_rows=base_rows)


def all_store_item_ids() -> tuple[str, ...]: return (STORE_ITEM_ID,)


@dataclass(frozen=True)
class Phase5Definitions:
    authority_model_definition_id: uuid.UUID; authority_model_definition_sha256: str
    template_definition_id: uuid.UUID; template_definition_sha256: str
    instrumentation_definition_id: uuid.UUID; instrumentation_definition_sha256: str
    contract_definition_id: uuid.UUID; contract_definition_sha256: str
    bundle_id: uuid.UUID; bundle_sha256: str


async def publish_definitions(publisher: Any) -> Phase5Definitions:
    o = await _L.publish_definitions(IDENTITY, SPECS, publisher, contract_payload=build_contract_payload())
    return Phase5Definitions(o["authority"].definition_id, o["authority"].sha256,
        o["template"].definition_id, o["template"].sha256,
        o["instrumentation"].definition_id, o["instrumentation"].sha256,
        o["contract"].definition_id, o["contract"].sha256,
        o["bundle"].bundle_id, o["bundle"].canonical_sha256)


def build_matcher() -> EntryMatcher: return _L.build_matcher(IDENTITY)
def build_registration(*, adapter: Any, bundle: Any, descriptor: DescriptorFacts, room: RoomFacts,
                       contract: SyncContract | None = None) -> AdapterRegistration:
    return _L.build_registration(IDENTITY, adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract)
def register_adapter(registry: WorkpaperSyncAdapterRegistry, *, adapter: Any, bundle: Any,
                     descriptor: DescriptorFacts, room: RoomFacts, contract: SyncContract | None = None) -> AdapterRegistration:
    return _L.register_adapter(registry, IDENTITY, adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract)
def manifest_capability_enabled(manifest: Mapping[str, Any] | None = None) -> bool: return _L.manifest_capability_enabled(IDENTITY, manifest=manifest)
def assert_manifest_capability_enabled(manifest: Mapping[str, Any] | None = None) -> None: _L.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)
async def resolve_published_frozen_definitions(*, session: Any, representation: Any, contract: SyncContract) -> Any:
    return await _L.resolve_published_frozen_definitions(IDENTITY, session=session, representation=representation, contract=contract)
async def attach_adapters(registry: WorkpaperSyncAdapterRegistry, *, session: Any) -> tuple[str, ...]:
    return await _L.attach_l_entry_adapter(registry, IDENTITY, session=session, contract_payload_builder=build_contract_payload)


publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
