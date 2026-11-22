# -*- coding: utf-8 -*-
# B22A control matrix provider lane (spec b22a-whole-workbook-provider-lane).
# Phase 1: frozen constants + instrumentation spec + definition payloads +
# real-template instrument probe. ASCII-only source: every CJK literal is
# written as unicode escapes so PowerShell / GBK round-trips cannot corrupt it
# (2026-11-21: the first write attempt mojibake-d IT<概要> into IT<姒傝>).
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync.models import SyncDomainError
__all__ = [
    'ENTRY_ID',
    'ADAPTER_ID',
    'TEMPLATE_ID',
    'TEMPLATE_RELATIVE_PATH',
    'TEMPLATE_SHA256',
    'MANAGED_SHEET',
    'SHEET_KEY',
    'FIRST_DATA_ROW',
    'LAST_DATA_ROW',
    'FOOTER_ROW',
    'MANAGED_LAST_COL',
    'UUID_COL',
    'TABLE_NAME',
    'ROWS_TABLE_KEY',
    'META_TABLE_KEY',
    'MANAGED_FIELD_SPECS',
    'META_FIELD_SPECS',
    'FORMULA_MASK',
    'FOOTER_MARKER',
    'B22AProviderSelectionError',
    'assert_b22a_entry_selectable',
    'authoritative_template_path',
    'read_authoritative_template',
    'excel_carrier_gate',
    'instrumentation_spec',
    'template_definition_payload',
    'instrumentation_definition_payload',
    'instrument_workbook_for_probe',
]


class B22AProviderSelectionError(SyncDomainError):
    """Frozen provider facts drifted (manifest/template mismatch = fail closed)."""

    error_code = 'sync_b22a_provider_selection_invalid'


# frozen identity constants (2026-11-21 openpyxl probe; see spec tasks.md).
ENTRY_ID: Final[str] = 'xlsx/gt-b22-a-control-matrix'
ADAPTER_ID: Final[str] = 'b22a.control_matrix'
TEMPLATE_ID: Final[str] = 'B22A41'
# B22A-4-1 IT<概要>.xlsx  (CJK written as escapes: 概要)
TEMPLATE_RELATIVE_PATH: Final[str] = 'B/B22A-4-1 IT概要.xlsx'
TEMPLATE_SHA256: Final[str] = (
    '8058b5f0eb4db987ab50342eb6eab840dc640e1053f7a2f3db971727f28fec50'
)
# managed sheet tab name == template file stem (概要 escaped).
MANAGED_SHEET: Final[str] = 'B22A-4-1 IT概要'
SHEET_KEY: Final[str] = 'b22a41-managed'
FIRST_DATA_ROW: Final[int] = 7
LAST_DATA_ROW: Final[int] = 48
FOOTER_ROW: Final[int] = 49
MANAGED_LAST_COL: Final[str] = 'J'
UUID_COL: Final[str] = 'K'
TABLE_NAME: Final[str] = 'GT_B22A41_ROWS'
ROWS_TABLE_KEY: Final[str] = 'b22a41_app_rows'
META_TABLE_KEY: Final[str] = 'b22a41_meta'
FORMULA_MASK: Final[tuple[str, ...]] = (
    'H7:H48',
    'I7:I48',
)
# footer marker text A49 (merged A49:J49): 提示
FOOTER_MARKER: Final[str] = '提示'


# managed columns: (column_key, col, mode, value_type, header_ref, header text).
# Header texts are openpyxl-read facts; escaped CJK keeps the file ASCII-only.
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ('seq', 'A', 'editable', 'text', 'A5', '序号'),
    ('app_name', 'B', 'editable', 'text', 'B5', 'IT应用程序或基础设施'),
    ('app_desc', 'C', 'editable', 'text', 'C5', '应用程序描述'),
    ('sys_index', 'D', 'editable', 'text', 'D5', '索引号'),
    ('factor_category', 'E', 'editable', 'text', 'E6', '判断要素类别'),
    ('factor', 'F', 'editable', 'text', 'F6', '复杂因素判断要素'),
    ('is_complex', 'G', 'editable', 'enum', 'G6', '是/否'),
    ('complexity', 'H', 'formula', 'text', 'H5', '复杂性'),
    ('audit_impact', 'I', 'formula', 'text', 'I5', '对审计策略的影响'),
    ('remark', 'J', 'editable', 'text', 'J5', '备注'),
)

META_FIELD_SPECS: Final[tuple[tuple[str, str, str, int, str], ...]] = (
    ('preparer', 'C3', 'D', 3, '编制人'),
    ('prepared_on', 'E3', 'F', 3, '编制日期'),
    ('reviewer', 'C4', 'D', 4, '复核人'),
    ('reviewed_on', 'E4', 'F', 4, '复核日期'),
)


def authoritative_template_path() -> Path:
    from app.services.workpaper_sync.excel_instrumentation import (
        ExcelIdentityCarrierGate,
    )

    return ExcelIdentityCarrierGate.load().assert_template_under_authority(
        TEMPLATE_RELATIVE_PATH
    )


def read_authoritative_template() -> bytes:
    data = authoritative_template_path().read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != TEMPLATE_SHA256:
        raise B22AProviderSelectionError(
            'B22A authoritative template bytes changed: sha256='
            + digest + ' frozen=' + TEMPLATE_SHA256
        )
    return data


def excel_carrier_gate() -> Any:
    from app.services.workpaper_sync.excel_instrumentation import (
        ExcelIdentityCarrierGate,
    )

    return ExcelIdentityCarrierGate.load()


def assert_b22a_entry_selectable(
    *, manifest: Mapping[str, Any] | None = None
) -> Mapping[str, Any]:
    """Re-derive the frozen facts on the real manifest (never trust constants).

    Checks: entry exists / independent / whole-workbook OO mount. Any drift
    means the lane moved: fail closed."""
    from app.services.workpaper_sync.entry_profile import (
        load_entry_manifest,
        manifest_entries_by_id,
    )

    payload = manifest if manifest is not None else load_entry_manifest()
    entry = manifest_entries_by_id(payload).get(ENTRY_ID)
    if entry is None:
        raise B22AProviderSelectionError(
            f'entry {ENTRY_ID!r} missing from manifest'
        )
    if not entry.get('independent_entry'):
        raise B22AProviderSelectionError(
            f'entry {ENTRY_ID!r} is not independent'
        )
    mounts = entry.get('mounts') or ()
    oo_mounts = [
        m for m in mounts
        if str(m.get('component')) == 'GtOnlyOfficeSheet'
    ]
    if not oo_mounts:
        raise B22AProviderSelectionError(
            'entry has no GtOnlyOfficeSheet mount'
        )
    ww = [
        a for m in oo_mounts for a in (m.get('attributes') or ())
        if a.get('argument') == 'whole-workbook'
        and a.get('expression') == 'true'
    ]
    if not ww:
        raise B22AProviderSelectionError(
            'GtOnlyOfficeSheet mount is not whole-workbook=true'
        )
    return entry


def instrumentation_spec() -> Any:
    from app.services.workpaper_sync.excel_instrumentation import (
        ExcelInstrumentationSpec,
    )

    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID,
        template_id=TEMPLATE_ID,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=MANAGED_SHEET,
        first_data_row=FIRST_DATA_ROW,
        last_data_row=LAST_DATA_ROW,
        footer_row=FOOTER_ROW,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL,
        table_name=TABLE_NAME,
        sheet_key=SHEET_KEY,
    )


def template_definition_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_instrumentation import (
        build_template_payload,
        normalized_structure_hash,
    )

    data = read_authoritative_template()
    return build_template_payload(
        spec=instrumentation_spec(),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.definitions import canonical_digest
    from app.services.workpaper_sync.excel_instrumentation import (
        build_instrumentation_payload,
    )

    return build_instrumentation_payload(
        spec=instrumentation_spec(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )


def instrument_workbook_for_probe() -> Any:
    """Phase 1 acceptance probe: run the real instrument kernel on the frozen

    template; return the InstrumentedWorkbook for structural assertions."""
    from app.services.workpaper_sync.excel_instrumentation import (
        instrument_workbook_bytes,
    )

    return instrument_workbook_bytes(
        read_authoritative_template(),
        instrumentation_spec(),
        gate=excel_carrier_gate(),
    )


# ---- Phase 2: store-backed row table (shared row-table kernel, no second truth) ----

STORE_ITEM_ID: Final[str] = 'B22A41-rows'
ROW_IDENTITY_STORE_KEY: Final[str] = 'rowId'
EMPTY_STORE_PAYLOAD: Final[str] = '[]'

from app.services.workpaper_sync.phase5_b22a_store_merge import (  # noqa: E402
    html_store_payload,
    merge_projection_into_store_rows,
)


def row_table_spec() -> Any:
    """RowTableSheetSpec for the IT overview matrix (3 blocks x 14 rows).

    Geometry mirrors instrumentation_spec; field json paths are flat
    column_keys (store rows are flat snake_case objects, B60 shape)."""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableSheetSpec,
    )

    fields = tuple(
        (column_key, column, mode, value_type, column_key, header_text, '')
        for column_key, column, mode, value_type, _ref, header_text
        in MANAGED_FIELD_SPECS
    )
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET,
        sheet_key=SHEET_KEY,
        table_key=ROWS_TABLE_KEY,
        template_id=TEMPLATE_ID,
        table_name=TABLE_NAME,
        uuid_col=UUID_COL,
        first_data_row=FIRST_DATA_ROW,
        last_data_row=LAST_DATA_ROW,
        footer_row=FOOTER_ROW,
        store_item_id=STORE_ITEM_ID,
        empty_payload=EMPTY_STORE_PAYLOAD,
        row_identity_key=ROW_IDENTITY_STORE_KEY,
        field_specs=fields,
        formula_columns=('H', 'I'),
        footer_marker=FOOTER_MARKER,
        # A49 is a merged text note, no totals formula.
        footer_carries_total_formula=False,
    )


def build_store_projection(
    payload: Any,
    *,
    contract: Any,
    limits: Any = None,
) -> Any:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _kernel,
    )

    return _kernel(row_table_spec(), payload, contract=contract, limits=limits)


# ---- Phase 3: per-entry contract (bidirectionally locked with the disk file) ----

from app.services.workpaper_sync.models import AuthorityModel, BundleSlot  # noqa: E402

AUTHORITY_MODEL: Final = AuthorityModel.projection_contract

_BACKEND_ROOT: Final = Path(__file__).resolve().parents[3]


def _src(cell: str) -> str:
    return f'src-xlsx!{MANAGED_SHEET}!{cell}'


def _rows_table_payload() -> dict[str, Any]:
    return {
        'table_key': ROWS_TABLE_KEY,
        'anchor': f'A{HEADER_FIRST_ROW}' if False else 'A5',
        'header_rows': 2,
        'row_identity': {'kind': 'field', 'json_pointer': '/rows/*/rowId'},
        'delete_policy': 'tombstone',
        'footer_anchor': {'marker': FOOTER_MARKER, 'search_column': 'A'},
        'formula_mask': list(FORMULA_MASK),
        'fields': [
            {
                'stable_field_key': f'{ROWS_TABLE_KEY}/{{row_uuid}}/{column_key}',
                'json_pointer': f'/rows/{{row_uuid}}/{column_key}',
                'column_key': column_key,
                'cell': {'column': column, 'row_from': 'row_identity'},
                'mode': mode,
                'value_type': value_type,
                'source_ref': _src(f'{column}{FIRST_DATA_ROW}'),
                'header_source_ref': _src(header_cell),
                'store_item_id': STORE_ITEM_ID,
            }
            for column_key, column, mode, value_type, header_cell, _label in MANAGED_FIELD_SPECS
        ],
    }
def _meta_table_payload() -> dict[str, Any]:
    return {
        'table_key': META_TABLE_KEY,
        'anchor': 'A3',
        'header_rows': 1,
        'fields': [
            {
                'stable_field_key': f'{META_TABLE_KEY}/{column_key}',
                'json_pointer': f'/meta/{column_key}',
                'column_key': column_key,
                'cell': {'column': value_col, 'row_from': row},
                'mode': 'editable',
                'value_type': 'text',
                'source_ref': _src(f'{value_col}{row}'),
                'header_source_ref': _src(label_cell),
            }
            for column_key, label_cell, value_col, row, _label in META_FIELD_SPECS
        ],
    }


def authority_model_payload() -> dict[str, Any]:
    return {
        'schema_version': 'authority-model-definition:v1',
        'authority_model': AUTHORITY_MODEL.value,
        'content_authority': 'structured_projection',
        'merge_model': 'stable_field_three_way',
        'required_slots': [
            BundleSlot.template.value,
            BundleSlot.instrumentation.value,
            BundleSlot.contract.value,
        ],
        'entry_id': ENTRY_ID,
        'pilot_class': 'b22a_whole_workbook',
    }

def build_contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.contracts import CONTRACT_SCHEMA_VERSION
    from app.services.workpaper_sync.definitions import canonical_digest

    template_payload = template_definition_payload()
    reviewed = (
        'openpyxl direct read of B22A-4-1 IT概要.xlsx managed sheet: '
        'two header rows 5/6, data rows 7..48 in three 14-row app blocks, '
        'G dropdown DV G7:G48, H array formula + I IF formula both masked, '
        'block-wise merged A..E/I/J columns, footer note A49:J49 merged. '
        'Every field source_ref/header_source_ref points at those real cells.'
    )
    return {
        'schema_version': CONTRACT_SCHEMA_VERSION,
        'contract_id': ADAPTER_ID,
        'semantic_version': '1.0.0',
        'review_status': 'reviewed',
        'document_type': 'xlsx',
        'template_definition_sha256': canonical_digest(template_payload),
        'instrumentation_definition_sha256': canonical_digest(
            instrumentation_definition_payload()
        ),
        'template': {
            'relative_path': TEMPLATE_RELATIVE_PATH,
            'template_sha256': TEMPLATE_SHA256,
            'normalized_structure_hash': template_payload['normalized_structure_hash'],
        },
        'identity_carriers': [
            'hidden_sheet',
            'defined_name',
            'excel_table',
            'hidden_uuid_column',
        ],
        'sheets': [
            {
                'sheet_key': SHEET_KEY,
                'excel_name': MANAGED_SHEET,
                'locator': {'anchor': 'excel_table_sheet_association'},
                'tables': [_rows_table_payload(), _meta_table_payload()],
            }
        ],
        'review': {
            'entry_id': ENTRY_ID,
            'pilot_class': 'b22a_whole_workbook',
            'authority_root': 'backend/wp_templates',
            'reviewed_basis': reviewed,
            'html_store': html_store_payload(),
        },
    }


def contract_file_path() -> Path:
    from app.services.workpaper_sync.contracts import contract_path_for

    return contract_path_for(ADAPTER_ID)


def load_b22a_contract() -> Any:
    from app.services.workpaper_sync.contracts import load_contract

    return load_contract(ADAPTER_ID)


def json_dumps_canonical(payload: dict[str, Any]) -> bytes:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode('utf-8')


def assert_contract_file_matches_source() -> Any:
    """Disk contract <-> module payload bidirectional lock (B60/D4 same kernel)."""
    from app.services.workpaper_sync.definitions import canonical_digest
    from app.services.workpaper_sync.contracts import parse_contract

    expected = build_contract_payload()
    on_disk = load_b22a_contract()
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise B22AProviderSelectionError(
            'disk per-entry contract differs from build_contract_payload(); '
            're-run write_contract_file() and review the diff'
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk

def write_contract_file() -> Path:
    """Phase 3 one-shot writer."""
    path = contract_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_dumps_canonical(build_contract_payload()))
    return path


# ---- Phase 5a: definition publish orchestration (B60 same DAG, thin shell) ----

PILOT_WP_CODES: Final[frozenset[str]] = frozenset({'B22A'})


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except B22AProviderSelectionError:
        return False
    return True


def assert_manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> None:
    from app.services.workpaper_sync.entry_profile import (
        Capability,
        capability_of,
        load_entry_manifest,
        manifest_entries_by_id,
    )

    entry = manifest_entries_by_id(
        manifest if manifest is not None else load_entry_manifest()
    )[ENTRY_ID]
    raw = entry.get('capability')
    if raw is None:
        raise B22AProviderSelectionError(
            f'entry {ENTRY_ID!r} capability is still pending'
        )
    if capability_of(entry) is not Capability.bidirectional:
        raise B22AProviderSelectionError(
            f'entry {ENTRY_ID!r} capability is not bidirectional'
        )
    if str(entry.get('adapter_id') or '') != ADAPTER_ID:
        raise B22AProviderSelectionError(
            f'entry {ENTRY_ID!r} adapter_id mismatch'
        )


async def publish_pilot_definitions(publisher: Any) -> Any:
    """Publish template -> instrumentation -> contract -> bundle (B60 same DAG).

    authority model goes first as the bundle required child. The publisher owns
    order / payload validation / DAG preconditions / slot normalization; this
    shell only orchestrates and re-checks the two one-way digest links."""
    import uuid

    from app.services.workpaper_sync.models import DefinitionKind

    contract = assert_contract_file_matches_source()

    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=authority_model_payload(),
        logical_id=f'{ADAPTER_ID}.authority-model',
        semantic_version='1.0.0',
    )
    template_payload = template_definition_payload()
    template = await publisher.publish_definition(
        kind=DefinitionKind.template,
        payload=template_payload,
        logical_id=f'{ADAPTER_ID}.template',
        semantic_version='1.0.0',
        blob_bytes=read_authoritative_template(),
        structure_hash=template_payload['normalized_structure_hash'],
    )
    instrumentation = await publisher.publish_definition(
        kind=DefinitionKind.instrumentation,
        payload=instrumentation_definition_payload(),
        logical_id=f'{ADAPTER_ID}.instrumentation',
        semantic_version='1.0.0',
    )
    contract_definition = await publisher.publish_definition(
        kind=DefinitionKind.contract,
        payload=dict(contract.canonical_payload),
        logical_id=ADAPTER_ID,
        semantic_version=contract.semantic_version,
    )
    if template.sha256 != contract.template_definition_sha256:
        raise B22AProviderSelectionError(
            f'published template digest {template.sha256} != contract '
            f'{contract.template_definition_sha256}'
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        raise B22AProviderSelectionError(
            f'published instrumentation digest {instrumentation.sha256} != contract '
            f'{contract.instrumentation_definition_sha256}'
        )
    bundle = await publisher.publish_bundle(
        authority_model_definition_id=authority.definition_id,
        authority_model=AUTHORITY_MODEL,
        authority_model_definition_sha256=authority.sha256,
        slots={
            BundleSlot.template: {
                'type': 'definition',
                'ref': f'definition:{template.definition_id}',
                'digest': template.sha256,
            },
            BundleSlot.instrumentation: {
                'type': 'definition',
                'ref': f'definition:{instrumentation.definition_id}',
                'digest': instrumentation.sha256,
            },
            BundleSlot.contract: {
                'type': 'definition',
                'ref': f'definition:{contract_definition.definition_id}',
                'digest': contract_definition.sha256,
            },
        },
    )

    class _Defs:
        pass

    out = _Defs()
    out.authority_model_definition_id = authority.definition_id
    out.authority_model_definition_sha256 = authority.sha256
    out.template_definition_id = template.definition_id
    out.template_definition_sha256 = template.sha256
    out.instrumentation_definition_id = instrumentation.definition_id
    out.instrumentation_definition_sha256 = instrumentation.sha256
    out.contract_definition_id = contract_definition.definition_id
    out.contract_definition_sha256 = contract_definition.sha256
    out.bundle_id = bundle.bundle_id
    out.bundle_sha256 = bundle.canonical_sha256
    return out


async def resolve_published_frozen_definitions(*, session: Any, representation: Any, contract: Any) -> Any:
    """Read frozen definitions from the published representation (Task 75 observer)."""
    from pathlib import Path as _Path
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import (
        observe_published_frozen_definitions,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    observation = await observe_published_frozen_definitions(
        session=session,
        resolution=CanonicalResolutionService(
            session, CanonicalArtifactRepository(_BACKEND_ROOT)
        ),
        representation=representation,
        correlation_id=f'{ADAPTER_ID}@{getattr(representation, 'id', None)}',
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise B22AProviderSelectionError(
            f'entry {ENTRY_ID}: observer contract digest '
            f'{observation.definitions.contract.canonical_sha256} != source-locked '
            f'{contract.canonical_sha256}'
        )
    return observation


async def attach_pilot_adapters(
    registry: Any, *, session: Any
) -> tuple[str, ...]:
    """Production wiring: register this entry when a published representation exists.

    Same orchestration contract as the other phase5 providers: no published
    representation yet = (,), not an error (the entry is simply not finalized)."""
    if ADAPTER_ID in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled():
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import WorkpaperContentRepresentation
    from app.services.workpaper_sync.entry_profile import (
        load_entry_manifest,
        manifest_entries_by_id,
    )
    from app.services.workpaper_sync.entry_source_facts import observe_descriptor_facts, observe_room_facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.adapters.registry import (
        AdapterRegistration,
        EntryMatcher,
    )
    from app.services.workpaper_sync.entry_profile import Capability
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    representation_id = await resolve_visible_current_representation_id(
        session, entry_id=ENTRY_ID
    )
    if representation_id is None:
        return ()
    representation = (
        await session.execute(
            sa.select(WorkpaperContentRepresentation).where(
                WorkpaperContentRepresentation.id == representation_id
            )
        )
    ).scalar_one_or_none()
    if representation is None or representation.definition_bundle_id is None:
        return ()

    resolution = CanonicalResolutionService(
        session, CanonicalArtifactRepository(_BACKEND_ROOT)
    )
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = assert_contract_file_matches_source()
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = observe_descriptor_facts(entry)
    if descriptor is None:
        raise B22AProviderSelectionError(
            f'entry {ENTRY_ID} host unreachable (no descriptor facts)'
        )
    assert_manifest_capability_enabled()
    observation = await resolve_published_frozen_definitions(
        session=session, representation=representation, contract=contract
    )
    registration = AdapterRegistration(
        adapter=build_excel_adapter(
            definitions=observation.definitions,
            binding=observation.identity_binding,
            direction='html_to_oo',
        ),
        entry_id=ENTRY_ID,
        matcher=EntryMatcher(document_type='xlsx', wp_codes=PILOT_WP_CODES),
        bundle=bundle,
        descriptor=descriptor,
        room=observe_room_facts(entry),
        declared_capability=Capability.bidirectional,
        contract=contract,
    )
    registry.register(registration)
    return (ADAPTER_ID,)
