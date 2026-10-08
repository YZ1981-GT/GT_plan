# -*- coding: utf-8 -*-
"""N3 递延所得税负债 —— 双向回写 provider（照 N4 范式）。

spec: n-cycle-sync-continuation
entry: xlsx/gt-n3-deferred-tax-liabilities
科目: 2901 递延所得税负债（贷方/负债类）
受管 sheet: 递延所得税负债明细表N3-2
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import (
    SyncContract,
    contract_path_for,
    load_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import (
    DescriptorFacts,
    RoomFacts,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    ExcelInstrumentationSpec,
)
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec


class StorePayloadError(SyncDomainError):
    error_code = "sync_phase5_n3_store_payload_invalid"


from app.services.workpaper_sync.phase5_n3_sheets import (  # noqa: F401,E402
    ADAPTER_ID,
    AUTHORITY_MODEL,
    DERIVED_SHEET,
    EMPTY_STORE_PAYLOAD,
    ENTRY_ID,
    EXPECTED_PROFILE_ID,
    FIRST_DATA_ROW,
    FOOTER_MARKER,
    FOOTER_ROW,
    FOOTER_SEARCH_COLUMN,
    FORMULA_COLUMNS,
    FORMULA_MASK,
    FORMULA_TEMPLATES,
    HTML_ONLY_ROW_KEYS,
    LAST_DATA_ROW,
    MANAGED_FIELD_SPECS,
    MANAGED_FIELD_SPECS_7,
    MANAGED_LAST_COL,
    MANAGED_SHEET,
    PHASE5_WAVE,
    ROW_IDENTITY_STORE_KEY,
    ROWS_TABLE_KEY,
    SHEET_KEY,
    SPEC_N32,
    STORE_ITEM_ID,
    TABLE_NAME,
    TEMPLATE_ID,
    TEMPLATE_RELATIVE_PATH,
    TEMPLATE_SHA256,
    UUID_COL,
    WP_CODES,
    _HTML_STORE_NOTE,
    _REVIEWED_BASIS,
)

from app.services.workpaper_sync import phase5_l_cycle_common as _L  # noqa: E402

IDENTITY: Final[_L.LEntryIdentity] = _L.LEntryIdentity(
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    phase5_wave=PHASE5_WAVE,
    wp_codes=frozenset(WP_CODES),
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    primary_store_item_id=STORE_ITEM_ID,
    row_identity_store_key=ROW_IDENTITY_STORE_KEY,
    html_store_note=_HTML_STORE_NOTE,
    reviewed_basis=_REVIEWED_BASIS,
    authority_model=AUTHORITY_MODEL,
    expected_profile_id=EXPECTED_PROFILE_ID,
    html_only_keys=tuple(HTML_ONLY_ROW_KEYS),
    derived_readonly_sheet={
        "excel_name": DERIVED_SHEET,
        "reason": (
            "r7~r13 全公式（SUMIF 引用明细表N3-2 + 加总 + 裸 IF 变动率），一格不写"
        ),
    },
)
SPECS: Final[tuple[RowTableSheetSpec, ...]] = (SPEC_N32,)

EntrySelectionError = _L.LEntrySelectionError
_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    return _L.excel_carrier_gate()


def authoritative_template_path() -> Path:
    return _L.authoritative_template_path(IDENTITY)


def read_authoritative_template() -> bytes:
    return _L.read_authoritative_template(IDENTITY)


@dataclass(frozen=True)
class TemplateResolutionFacts:
    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


def assert_no_implicit_template_fallback(
    resolution: TemplateResolutionFacts, *, wp_codes: frozenset[str]
) -> None:
    missing = sorted(wp_codes - set(resolution.by_wp_code))
    if missing:
        raise EntrySelectionError(f"缺少 wp_code {missing} 的 finder 实测结果")
    leaked = {
        code: [str(item) for item in hits if item]
        for code, hits in resolution.by_wp_code.items()
        if any(hits)
    }
    if leaked:
        raise EntrySelectionError(f"wp_code {sorted(leaked)} 在 finder 上命中 {leaked}")
    resolved = resolution.parent_resolved_path
    if resolved is None or Path(str(resolved)).resolve() != authoritative_template_path().resolve():
        raise EntrySelectionError(
            f"父码解析落在 {resolved}，非冻结权威模板 {TEMPLATE_RELATIVE_PATH!r}"
        )


def assert_entry_selectable(
    *, resolution: TemplateResolutionFacts | None = None, manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    payload = manifest if manifest is not None else load_entry_manifest()
    entry = manifest_entries_by_id(payload).get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(f"{ENTRY_ID!r} 不在 manifest 里")
    if str(entry.get("document_type") or "") != "xlsx":
        raise EntrySelectionError(f"{ENTRY_ID!r} document_type 非 xlsx")
    if not entry.get("independent_entry"):
        raise EntrySelectionError(f"{ENTRY_ID!r} 非独立 entry")
    return entry


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    return _L.instrumentation_specs_for(IDENTITY, SPECS)


def instrumentation_spec() -> ExcelInstrumentationSpec:
    specs = instrumentation_specs()
    if len(specs) != 1:
        raise EntrySelectionError(f"N3 应有 1 条 instrumentation spec，实际 {len(specs)}")
    return specs[0]


def template_definition_payload() -> dict[str, Any]:
    return _L.template_definition_payload(IDENTITY, SPECS)


def instrumentation_definition_payload() -> dict[str, Any]:
    return _L.instrumentation_definition_payload(IDENTITY, SPECS)


def authority_model_payload() -> dict[str, Any]:
    return _L.authority_model_payload(IDENTITY)


def build_contract_payload() -> dict[str, Any]:
    return _L.build_contract_payload(IDENTITY, SPECS)


def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    return _L.assert_contract_file_matches_source(IDENTITY, build_contract_payload())


def build_store_projection(
    payload: str | bytes | Sequence[Any], *, contract: SyncContract, limits: Any | None = None,
) -> Any:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableStorePayloadError,
        build_store_projection as _engine_build_store_projection,
    )
    try:
        return _engine_build_store_projection(SPEC_N32, payload, contract=contract, limits=limits)
    except RowTableStorePayloadError as exc:
        raise StorePayloadError(str(exc)) from exc


def merge_projection_into_store_rows(
    *, projection: Any, base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )
    return _engine_merge(SPEC_N32, projection=projection, base_rows=base_rows)


def all_store_item_ids() -> tuple[str, ...]:
    return (STORE_ITEM_ID,)


@dataclass(frozen=True)
class Phase5Definitions:
    authority_model_definition_id: uuid.UUID
    authority_model_definition_sha256: str
    template_definition_id: uuid.UUID
    template_definition_sha256: str
    instrumentation_definition_id: uuid.UUID
    instrumentation_definition_sha256: str
    contract_definition_id: uuid.UUID
    contract_definition_sha256: str
    bundle_id: uuid.UUID
    bundle_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": ENTRY_ID, "adapter_id": ADAPTER_ID,
            "authority_model": AUTHORITY_MODEL.value,
            "authority_model_definition_id": str(self.authority_model_definition_id),
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "template_definition_id": str(self.template_definition_id),
            "template_definition_sha256": self.template_definition_sha256,
            "instrumentation_definition_id": str(self.instrumentation_definition_id),
            "instrumentation_definition_sha256": self.instrumentation_definition_sha256,
            "contract_definition_id": str(self.contract_definition_id),
            "contract_definition_sha256": self.contract_definition_sha256,
            "definition_bundle_id": str(self.bundle_id),
            "definition_bundle_sha256": self.bundle_sha256,
        }


async def publish_definitions(publisher: Any) -> Phase5Definitions:
    out = await _L.publish_definitions(IDENTITY, SPECS, publisher, contract_payload=build_contract_payload())
    return Phase5Definitions(
        authority_model_definition_id=out["authority"].definition_id,
        authority_model_definition_sha256=out["authority"].sha256,
        template_definition_id=out["template"].definition_id,
        template_definition_sha256=out["template"].sha256,
        instrumentation_definition_id=out["instrumentation"].definition_id,
        instrumentation_definition_sha256=out["instrumentation"].sha256,
        contract_definition_id=out["contract"].definition_id,
        contract_definition_sha256=out["contract"].sha256,
        bundle_id=out["bundle"].bundle_id,
        bundle_sha256=out["bundle"].canonical_sha256,
    )


def build_matcher() -> EntryMatcher:
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)


def build_registration(*, adapter: Any, bundle: Any, descriptor: DescriptorFacts, room: RoomFacts, contract: SyncContract | None = None) -> AdapterRegistration:
    from app.services.workpaper_sync.entry_profile import Capability
    return AdapterRegistration(adapter=adapter, entry_id=ENTRY_ID, matcher=build_matcher(), bundle=bundle, descriptor=descriptor, room=room, declared_capability=Capability.bidirectional, contract=contract)


def register_adapter(registry: WorkpaperSyncAdapterRegistry, *, adapter: Any, bundle: Any, descriptor: DescriptorFacts, room: RoomFacts, contract: SyncContract | None = None) -> AdapterRegistration:
    reg = build_registration(adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract)
    registry.register(reg)
    return reg


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except EntrySelectionError:
        return False
    return True


def assert_manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> None:
    from app.services.workpaper_sync.entry_profile import Capability, capability_of
    entry = manifest_entries_by_id(manifest if manifest is not None else load_entry_manifest()).get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(f"{ENTRY_ID} 不在 manifest 里")
    if capability_of(entry) is not Capability.bidirectional:
        raise EntrySelectionError(f"{ENTRY_ID} capability 非 bidirectional")


async def resolve_published_frozen_definitions(*, session: Any, representation: Any, contract: Any) -> Any:
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import observe_published_frozen_definitions
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    obs = await observe_published_frozen_definitions(
        session=session,
        resolution=CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND_ROOT)),
        representation=representation,
        correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if obs.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise EntrySelectionError(f"digest mismatch {obs.definitions.contract.canonical_sha256} vs {contract.canonical_sha256}")
    return obs


async def attach_adapters(registry: WorkpaperSyncAdapterRegistry, *, session: Any) -> tuple[str, ...]:
    return await _L.attach_adapters(IDENTITY, SPECS, registry, session=session, build_contract_payload_fn=build_contract_payload, store_payload_error_cls=StorePayloadError)


publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
