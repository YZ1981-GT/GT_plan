# -*- coding: utf-8 -*-
"""F2 合同履约成本册（F2-55 至 F2-58）—— Phase 5 lane P provider。

spec: f2-sync-coverage-four-entry-lanes · Task 22

═══ F2I 幻影码 + sheet_keys（F2-H1 解 RG-3）═══

与 main/valuation 共用 F2I，各自声明互不相交的 sheet_keys。
special lane 的受管 sheet 全部是 dict 子数组载荷。

canary = F2-57 合同履约成本减值准备测算表（dict 最简，单级表头）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration, EntryMatcher, WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION, SyncContract, contract_path_for, load_contract,
)
from app.services.workpaper_sync.entry_profile import (
    Capability, DescriptorFacts, RoomFacts, capability_of,
    load_entry_manifest, manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate, ExcelInstrumentationSpec,
    build_instrumentation_payload_for_sheets, build_template_payload,
    normalized_structure_hash,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.sheet_geometry import col_index


class EntrySelectionError(SyncDomainError):
    error_code = "sync_phase5_f2_special_selection_invalid"


PHASE5_WAVE: Final[str] = "phase5_f2_inventory_special"
ENTRY_ID: Final[str] = "xlsx/gt-f2-inventory-special"
ADAPTER_ID: Final[str] = "f2.inventory_special"
WP_CODES: Final[frozenset[str]] = frozenset({"F2I"})
TEMPLATE_RELATIVE_PATH: Final[str] = "F/F2-55至F2-58 合同履约成本.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "b9ea248198217827a7b3d142dccca9ab5769c17867d1454ffd9105eaa9cb6c21"
)
STORE_ITEM_ID: Final[str] = "F2-57-rows"
ROW_IDENTITY_STORE_KEY: Final[str] = "id"
_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    return ExcelIdentityCarrierGate.load()

def authoritative_template_path() -> Path:
    return excel_carrier_gate().assert_template_under_authority(TEMPLATE_RELATIVE_PATH)

def read_authoritative_template() -> bytes:
    path = authoritative_template_path()
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != TEMPLATE_SHA256:
        raise EntrySelectionError(f"权威模板字节已变: {TEMPLATE_RELATIVE_PATH}")
    return data

def assert_entry_selectable(*, manifest: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(f"{ENTRY_ID!r} 不在 manifest 里")
    if not entry.get("independent_entry"):
        raise EntrySelectionError(f"{ENTRY_ID!r} 非独立 entry")
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 灰度开关
# ═══════════════════════════════════════════════════════════════════════════

_INCLUDE_F257: Final[bool] = True   # canary
_INCLUDE_F258: Final[bool] = False
_INCLUDE_F255: Final[bool] = False
_INCLUDE_F256: Final[bool] = False  # 需先修 id 生成（Task 6 已修）


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_F257:
        from app.services.workpaper_sync.phase5_f2_special_55_58 import SPEC_F257
        specs.append(SPEC_F257)
    if _INCLUDE_F258:
        from app.services.workpaper_sync.phase5_f2_special_55_58 import SPEC_F258
        specs.append(SPEC_F258)
    if _INCLUDE_F255:
        from app.services.workpaper_sync.phase5_f2_special_55_58 import SPEC_F255
        specs.append(SPEC_F255)
    if _INCLUDE_F256:
        from app.services.workpaper_sync.phase5_f2_special_55_58 import SPEC_F256
        specs.append(SPEC_F256)
    return tuple(specs)

def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for s in managed_row_table_specs():
        if s.store_item_id and s.store_item_id not in items:
            items.append(s.store_item_id)
    return tuple(items)

def all_managed_sheet_keys() -> frozenset[str]:
    return frozenset(s.sheet_key for s in managed_row_table_specs())

def _managed_last_col_of(spec: Any) -> str:
    return max((r[1] for r in spec.field_specs), key=col_index) if spec.field_specs else "A"

def _instrumentation_of(spec: Any) -> ExcelInstrumentationSpec:
    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID, template_id=spec.template_id,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=spec.managed_sheet,
        first_data_row=spec.first_data_row, last_data_row=spec.last_data_row,
        footer_row=spec.footer_row, managed_last_col=_managed_last_col_of(spec),
        uuid_col=spec.uuid_col, table_name=spec.table_name,
        sheet_key=spec.sheet_key,
    )


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    return tuple(_instrumentation_of(s) for s in managed_row_table_specs())


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    specs = managed_row_table_specs()
    if not specs:
        raise EntrySelectionError("F2 special 当前无受管 sheet")
    return build_template_payload(
        spec=_instrumentation_of(specs[0]),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    return build_instrumentation_payload_for_sheets(
        specs=instrumentation_specs(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256, gate=excel_carrier_gate(),
    )


def build_contract_payload() -> dict[str, Any]:
    """从受管 spec 清单自动派生契约 payload。"""
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        spec_to_contract_sheet_payload,
    )

    template_payload = template_definition_payload()
    row_specs = managed_row_table_specs()
    if not row_specs:
        raise EntrySelectionError("F2 special 当前无受管 sheet")
    sheets: list[dict[str, Any]] = []
    for spec in row_specs:
        sheet_payload = spec_to_contract_sheet_payload(spec)
        sheet_payload["locator"] = {"anchor": TABLE_SHEET_ANCHOR}
        sheets.append(sheet_payload)
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": ADAPTER_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": canonical_digest(template_payload),
        "instrumentation_definition_sha256": canonical_digest(
            instrumentation_definition_payload()
        ),
        "template": {
            "relative_path": TEMPLATE_RELATIVE_PATH,
            "template_sha256": TEMPLATE_SHA256,
            "normalized_structure_hash": template_payload["normalized_structure_hash"],
        },
        "identity_carriers": [
            "hidden_sheet", "defined_name", "excel_table", "hidden_uuid_column",
        ],
        "sheets": sheets,
        "review": {
            "entry_id": ENTRY_ID,
            "pilot_class": PHASE5_WAVE,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_ids": list(all_store_item_ids()),
                "shape": "json_array_of_row_objects",
            },
        },
    }


def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    return load_contract(ADAPTER_ID)


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    try:
        entry = manifest_entries_by_id(
            manifest if manifest is not None else load_entry_manifest()
        ).get(ENTRY_ID)
        return entry is not None and capability_of(entry) is Capability.bidirectional
    except Exception:
        return False


def build_matcher() -> EntryMatcher:
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES, sheet_keys=all_managed_sheet_keys())

def build_registration(*, adapter: Any, bundle: Any, descriptor: DescriptorFacts,
                       room: RoomFacts, contract: SyncContract | None = None) -> AdapterRegistration:
    return AdapterRegistration(
        adapter=adapter, entry_id=ENTRY_ID, matcher=build_matcher(),
        bundle=bundle, descriptor=descriptor, room=room,
        declared_capability=Capability.bidirectional,
        contract=contract if contract is not None else load_contract(ADAPTER_ID),
    )

async def attach_pilot_adapters(registry: WorkpaperSyncAdapterRegistry, *, session: Any) -> tuple[str, ...]:
    if ADAPTER_ID in {r.adapter_id for r in registry.registrations()}:
        return ()
    if not manifest_capability_enabled():
        return ()
    import sqlalchemy as sa
    from app.models.workpaper_sync_models import WorkpaperContentRepresentation
    from app.services.workpaper_sync.projection_target_resolution import resolve_visible_current_representation_id
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.published_identity_observer import observe_published_frozen_definitions

    rep_id = await resolve_visible_current_representation_id(session, entry_id=ENTRY_ID)
    if rep_id is None:
        return ()
    rep = (await session.execute(
        sa.select(WorkpaperContentRepresentation).where(WorkpaperContentRepresentation.id == rep_id)
    )).scalar_one_or_none()
    if rep is None or rep.definition_bundle_id is None:
        return ()
    resolution = CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND_ROOT))
    bundle = await resolution.load_bundle_snapshot(rep.definition_bundle_id)
    contract = load_contract(ADAPTER_ID)
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(f"entry {ENTRY_ID} 宿主不可达")
    observation = await observe_published_frozen_definitions(
        session=session, resolution=resolution, representation=rep,
        correlation_id=f"{ADAPTER_ID}@{getattr(rep, 'id', None)}",
    )
    reg = build_registration(
        adapter=build_excel_adapter(
            definitions=observation.definitions,
            binding=observation.identity_binding, direction="html_to_oo",
        ),
        bundle=bundle, descriptor=descriptor,
        room=facts.observe_room_facts(entry), contract=contract,
    )
    registry.register(reg)
    return (ADAPTER_ID,)


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    """读已发布的冻结身份（照同册 `phase5_f2_inventory_main` 逐字同构）。

    🔴 **2026-09-27 补漏**：本模块的台账条目早已登记，但漏了这个函数 ⇒
    `test_task75_published_identity_observer.py::TestDebtRemovedWithRealImpl` 的四条判据
    （`function_node()` 按固定符号名取 AST）自登记起就红。同族三条一次补齐。

    🔴 **不得**抄 loader 九步（`ExcelEntryDefinitionLoader` / `assert_no_structure_drift` /
    `parse_identity_inventory` / `structure_fingerprint`）—— 观测器是唯一真源。
    contract digest 比对的 `raise` 必须留在**条件分支**里（顶层 raise 会被判「中间形态①」）。
    """
    from app.services.workpaper_sync.artifacts import (
        CanonicalArtifactRepository,
    )
    from app.services.workpaper_sync.published_identity_observer import (
        observe_published_frozen_definitions,
    )
    from app.services.workpaper_sync.resolution import (
        CanonicalResolutionService,
    )

    observation = await observe_published_frozen_definitions(
        session=session,
        resolution=CanonicalResolutionService(
            session, CanonicalArtifactRepository(_BACKEND_ROOT)
        ),
        representation=representation,
        correlation_id=(
            f"{ADAPTER_ID}@{getattr(representation, 'id', None)}"
        ),
    )
    if (
        observation.definitions.contract.canonical_sha256
        != contract.canonical_sha256
    ):
        raise EntrySelectionError(
            f"entry {ENTRY_ID}: 观测器读出的契约 digest "
            f"{observation.definitions.contract.canonical_sha256} "
            f"与本模块 source-locked 的 "
            f"{contract.canonical_sha256} 不一致"
        )
    return observation
