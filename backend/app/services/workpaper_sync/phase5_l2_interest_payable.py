# -*- coding: utf-8 -*-
"""L2 应付利息「应付利息检查表 L2-4」—— L 循环第四条真双向 entry（task 12 最后一条）。

spec: l-cycle-true-adapter-registration · Task 12；几何/选型见 `phase5_l2_sheets`。
本模块只声明 IDENTITY+SPECS 与 L2 幻影码选型，流程委派 `phase5_l_cycle_common`。
L2-4 是 L3-9 的孪生表（凭证级检查），结构同序。
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
from app.services.workpaper_sync.phase5_l2_sheets import (  # noqa: F401
    ADAPTER_ID, AUTHORITY_MODEL, EMPTY_STORE_PAYLOAD, ENTRY_ID, EXPECTED_PROFILE_ID,
    FIRST_DATA_ROW, FOOTER_MARKER, FOOTER_ROW, FORMULA_COLUMNS, FORMULA_MASK,
    FORMULA_TEMPLATES, HEADER_GROUP_ROW, HEADER_LEAF_ROW, HTML_ONLY_ROW_KEYS,
    LAST_DATA_ROW, MANAGED_FIELD_SPECS, MANAGED_FIELD_SPECS_7, MANAGED_LAST_COL,
    MANAGED_SHEET, PHASE5_WAVE, ROW_IDENTITY_STORE_KEY, ROWS_TABLE_KEY, SHEET_KEY,
    SPEC_L24, STORE_ITEM_ID, TABLE_NAME, TEMPLATE_ID, TEMPLATE_RELATIVE_PATH,
    TEMPLATE_SHA256, UUID_COL, WP_CODES, _HTML_STORE_NOTE, _REVIEWED_BASIS,
)

IDENTITY: Final[_L.LEntryIdentity] = _L.LEntryIdentity(
    entry_id=ENTRY_ID, adapter_id=ADAPTER_ID, phase5_wave=PHASE5_WAVE,
    wp_codes=frozenset(WP_CODES), template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256, primary_store_item_id=STORE_ITEM_ID,
    row_identity_store_key=ROW_IDENTITY_STORE_KEY, html_store_note=_HTML_STORE_NOTE,
    reviewed_basis=_REVIEWED_BASIS, authority_model=AUTHORITY_MODEL,
    expected_profile_id=EXPECTED_PROFILE_ID, html_only_keys=HTML_ONLY_ROW_KEYS,
    derived_readonly_sheet={
        "excel_name": MANAGED_SHEET,
        "reason": "R25/R26 为引用 L2-2 的本期发生额与检查比例派生行，受管区截止 r23、footer r24",
    },
    extra_review={
        "template_defects_registered": {
            "defined_names": {"total": 0, "broken": 0},
            "bare_if": {"workbook_total": 112, "managed_sheet": 0},
            "note": "不改模板；L2-4 受管表本身零 #REF!/零裸 IF，per-file 中性化仍挂",
        }
    },
)
SPECS: Final[tuple[RowTableSheetSpec, ...]] = (SPEC_L24,)
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
    try: return engine(SPEC_L24, payload, contract=contract, limits=limits)
    except RowTableStorePayloadError as exc: raise StorePayloadError(str(exc)) from exc


def merge_projection_into_store_rows(*, projection: Any, base_rows: list[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import merge_projection_into_store_rows as engine
    return engine(SPEC_L24, projection=projection, base_rows=base_rows)


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
