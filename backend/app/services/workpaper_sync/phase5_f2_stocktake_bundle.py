# -*- coding: utf-8 -*-
"""F2 存货监盘册（F2-21 至 F2-26）—— Phase 5 lane S provider。

spec: f2-sync-coverage-four-entry-lanes · Task 14

═══ 与 lane M 同构但 F2S 独占幻影码（无 RG-3 冲突）═══

stocktake 独占 `F2S`（manifest CamelCase GtF2StocktakeBundle → F2S），
不与 main/valuation/special 的 F2I 冲突（Task 3 已证明）。
本 lane build_matcher() 不需要 sheet_keys。

🔴 BP-9 注意（slice 登记）：两处 Word writer docstring 把 lane 选择理由写成
"manifest 里 F2 的 entry 是 single_onlyoffice" = 把 overlay 默认值当裁决真源
（FC-12）。本 lane 不复制该论证方式。

canary = F2-25 抽盘结果汇总表（双区 + 有合计行）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION,
    SyncContract,
    contract_path_for,
    load_contract,
    parse_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import (
    Capability,
    DescriptorFacts,
    RoomFacts,
    capability_of,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    ExcelInstrumentationSpec,
    build_instrumentation_payload_for_sheets,
    build_template_payload,
    normalized_structure_hash,
)
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.sheet_geometry import col_index


class EntrySelectionError(SyncDomainError):
    error_code = "sync_phase5_f2_stocktake_selection_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_f2_stocktake_bundle"
ENTRY_ID: Final[str] = "xlsx/gt-f2-stocktake-bundle"
ADAPTER_ID: Final[str] = "f2.stocktake_bundle"

#: F2S 独占幻影码，无 RG-3 冲突（Task 3 已证明）
WP_CODES: Final[frozenset[str]] = frozenset({"F2S"})
EXPECTED_PROFILE_ID: Final[str] = (
    "xlsx.editable.shared.single.room_service_wired.v1"
)
TEMPLATE_RELATIVE_PATH: Final[str] = (
    "F/F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx"
)
TEMPLATE_SHA256: Final[str] = (
    "bdfdcf8a804aab1c11db1cc2cd2deaac4f5bbf94c6a60e43a04108f178079bc7"
)

STORE_ITEM_ID: Final[str] = "F2-25-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "id"

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
# ═══════════════════════════════════════════════════════════════════════════

def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    return ExcelIdentityCarrierGate.load()

def authoritative_template_path() -> Path:
    return excel_carrier_gate().assert_template_under_authority(TEMPLATE_RELATIVE_PATH)

def read_authoritative_template() -> bytes:
    path = authoritative_template_path()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != TEMPLATE_SHA256:
        raise EntrySelectionError(
            f"权威模板字节已变: {TEMPLATE_RELATIVE_PATH} "
            f"实测 sha256={digest}，冻结哨兵={TEMPLATE_SHA256}"
        )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型守卫
# ═══════════════════════════════════════════════════════════════════════════

def assert_entry_selectable(
    *, manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(f"冻结的 entry {ENTRY_ID!r} 不在 manifest 里")
    if str(entry.get("document_type") or "") != "xlsx":
        raise EntrySelectionError(f"{ENTRY_ID!r} document_type 非 xlsx")
    if not entry.get("independent_entry"):
        raise EntrySelectionError(f"{ENTRY_ID!r} independent_entry={entry.get('independent_entry')!r}")
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 4. 灰度开关与受管 sheet 清单
# ═══════════════════════════════════════════════════════════════════════════

#: canary：F2-25 抽盘结果汇总表（双区）
_INCLUDE_F225: Final[bool] = True
#: F2-26 区二（日前 F2-26-rows）
_INCLUDE_F226_BEFORE: Final[bool] = False
#: F2-26 区一（日后 F2-26-after-rows，依赖模板覆盖层修 J9）
_INCLUDE_F226_AFTER: Final[bool] = False


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_F225:
        from app.services.workpaper_sync import (
            phase5_f2_stocktake_25_26 as _f225,
        )
        specs.append(_f225.SPEC_F225_EXIST)
        specs.append(_f225.SPEC_F225_FLOOR)
    if _INCLUDE_F226_BEFORE:
        from app.services.workpaper_sync import (
            phase5_f2_stocktake_25_26 as _f226,
        )
        specs.append(_f226.SPEC_F226_BEFORE)
    if _INCLUDE_F226_AFTER:
        from app.services.workpaper_sync import (
            phase5_f2_stocktake_25_26 as _f226a,
        )
        specs.append(_f226a.SPEC_F226_AFTER)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def all_managed_sheet_names() -> tuple[str, ...]:
    return tuple(s.managed_sheet for s in managed_row_table_specs())


# ═══════════════════════════════════════════════════════════════════════════
# 5-7. instrumentation / 契约装配 / store 投影合并（同 lane M 结构）
# ═══════════════════════════════════════════════════════════════════════════

def _managed_last_col_of(spec: Any) -> str:
    if not spec.field_specs:
        raise EntrySelectionError(f"{spec.managed_sheet} 未声明任何受管字段")
    return max((row[1] for row in spec.field_specs), key=col_index)

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
    first_spec = managed_row_table_specs()
    if not first_spec:
        raise EntrySelectionError("F2 stocktake 当前无受管 sheet")
    return build_template_payload(
        spec=_instrumentation_of(first_spec[0]),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )

def instrumentation_definition_payload() -> dict[str, Any]:
    return build_instrumentation_payload_for_sheets(
        specs=instrumentation_specs(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )

_HTML_STORE_NOTE: Final[str] = (
    "F2 stocktake 册行数据存成 checklist_responses 的 remark JSON 数组。"
    "F2-25 双区 F2-25-rows + F2-25-floor-rows，F2-26 双区 F2-26-rows + F2-26-after-rows。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 F/F2-21至F2-26 + 前端 F2TabStocktake*.vue 按值 grep"
)

def _rows_table_payload(spec: Any) -> dict[str, Any]:
    from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs
    fields = managed_field_specs(spec)
    return {
        "table_key": spec.table_key,
        "table_name": spec.table_name,
        "row_identity": {"store_key": spec.row_identity_key, "column": spec.uuid_col, "hidden": True},
        "fields": [
            {"stable_field_key": f[0], "column": f[1], "mode": f[2], "value_type": f[3],
             "json_key": f[4], "header_text": f[5]}
            for f in fields
        ],
        "formula_mask": list(spec.formula_mask),
        "footer": {
            "row_marker": spec.footer_marker,
            "carries_total_formula": spec.footer_carries_total_formula,
        },
    }

def build_contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR
    template_payload = template_definition_payload()
    row_specs = managed_row_table_specs()
    if not row_specs:
        raise EntrySelectionError("F2 stocktake 当前无受管 sheet")
    sheets: list[dict[str, Any]] = []
    for spec in row_specs:
        sheets.append({
            "sheet_key": spec.sheet_key, "excel_name": spec.managed_sheet,
            "locator": {"anchor": TABLE_SHEET_ANCHOR},
            "tables": [_rows_table_payload(spec)],
        })
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION, "contract_id": ADAPTER_ID,
        "semantic_version": "1.0.0", "review_status": "reviewed", "document_type": "xlsx",
        "template_definition_sha256": canonical_digest(template_payload),
        "instrumentation_definition_sha256": canonical_digest(instrumentation_definition_payload()),
        "template": {
            "relative_path": TEMPLATE_RELATIVE_PATH,
            "template_sha256": TEMPLATE_SHA256,
            "normalized_structure_hash": template_payload["normalized_structure_hash"],
        },
        "identity_carriers": ["hidden_sheet", "defined_name", "excel_table", "hidden_uuid_column"],
        "sheets": sheets,
        "review": {
            "entry_id": ENTRY_ID, "pilot_class": PHASE5_WAVE,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_ids": list(all_store_item_ids()),
                "shape": "json_array_of_row_objects",
                "note": _HTML_STORE_NOTE,
            },
            "reviewed_basis": _REVIEWED_BASIS,
        },
    }

def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)

def load_contract_from_disk() -> SyncContract:
    return load_contract(ADAPTER_ID)

def _spec_of_store_item(store_item_id: str) -> Any:
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise EntrySelectionError(
        f"store item {store_item_id!r} 不在 F2 stocktake 受管清单里"
    )

def build_store_projection(store_item_id: str, payload: str | bytes | Sequence[Any],
                           *, contract: SyncContract, limits: Any | None = None) -> Any:
    from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection as _engine
    return _engine(_spec_of_store_item(store_item_id), payload, contract=contract, limits=limits)

def merge_projection_into_store_rows(store_item_id: str, *, projection: Any,
                                     base_rows: list[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import merge_projection_into_store_rows as _engine_merge
    return _engine_merge(_spec_of_store_item(store_item_id), projection=projection, base_rows=base_rows)


# ═══════════════════════════════════════════════════════════════════════════
# 8. manifest capability 检查
# ═══════════════════════════════════════════════════════════════════════════

def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    try:
        entry = manifest_entries_by_id(
            manifest if manifest is not None else load_entry_manifest()
        ).get(ENTRY_ID)
        if entry is None:
            return False
        return capability_of(entry) is Capability.bidirectional
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════
# 9. adapter 注册（F2S 独占，无 sheet_keys）
# ═══════════════════════════════════════════════════════════════════════════

def build_matcher() -> EntryMatcher:
    """F2S 独占幻影码，无 RG-3 冲突，不需要 sheet_keys。"""
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)

def build_registration(*, adapter: Any, bundle: Any, descriptor: DescriptorFacts,
                       room: RoomFacts, contract: SyncContract | None = None) -> AdapterRegistration:
    return AdapterRegistration(
        adapter=adapter, entry_id=ENTRY_ID, matcher=build_matcher(),
        bundle=bundle, descriptor=descriptor, room=room,
        declared_capability=Capability.bidirectional,
        contract=contract if contract is not None else load_contract_from_disk(),
    )

def register_adapter(registry: WorkpaperSyncAdapterRegistry, *, adapter: Any,
                     bundle: Any, descriptor: DescriptorFacts, room: RoomFacts,
                     contract: SyncContract | None = None) -> AdapterRegistration:
    reg = build_registration(adapter=adapter, bundle=bundle, descriptor=descriptor,
                             room=room, contract=contract)
    registry.register(reg)
    return reg

async def attach_pilot_adapters(registry: WorkpaperSyncAdapterRegistry, *, session: Any) -> tuple[str, ...]:
    """发布链编排（照 lane M 同构）。"""
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
    contract = load_contract_from_disk()
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(f"entry {ENTRY_ID} 的宿主实测不可达")

    from app.services.workpaper_sync.published_identity_observer import observe_published_frozen_definitions
    observation = await observe_published_frozen_definitions(
        session=session, resolution=resolution, representation=rep,
        correlation_id=f"{ADAPTER_ID}@{getattr(rep, 'id', None)}",
    )
    register_adapter(
        registry,
        adapter=build_excel_adapter(
            definitions=observation.definitions,
            binding=observation.identity_binding,
            direction="html_to_oo",
        ),
        bundle=bundle, descriptor=descriptor,
        room=facts.observe_room_facts(entry), contract=contract,
    )
    return (ADAPTER_ID,)
