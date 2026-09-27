# -*- coding: utf-8 -*-
"""F1 预付账款 —— Phase 5 entry 模块（从零建，照 D3/E1 同构）。

spec: f1-sync-coverage-and-first-canary · Task 7

═══ 与 D3 同构（预收↔预付）、与 E1 同级（连 provider 都没有）═══

本模块持有冻结身份常量、选型守卫、契约装配、发布链编排。
受管 sheet 清单与灰度开关内联（不另建伴生 expansion 模块——F1 只有 1 册 7 个受管区，
比 D3 的 7 个受管区相当，但 F1 没有「另 6 本拆分工作簿」的复杂度）。

canary = F1-6 关联方及交易检查表（裁决 F1-H1：单级表头 / 无账龄 / 3 行 / 无口径分歧）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
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
    """冻结的 canary entry 不再满足选型必要条件。"""
    error_code = "sync_phase5_f1_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法。"""
    error_code = "sync_phase5_f1_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_prepayment"
ENTRY_ID: Final[str] = "xlsx/gt-f1-prepayment"
ADAPTER_ID: Final[str] = "f1.prepayment_detail"

#: 🔴 manifest 冻结的幻影码（FC-2：matcher 域用幻影码，provisioning 用真码）
WP_CODES: Final[frozenset[str]] = frozenset({"F1P"})
EXPECTED_PROFILE_ID: Final[str] = (
    "xlsx.editable.shared.single.room_service_wired.v1"
)
TEMPLATE_RELATIVE_PATH: Final[str] = "F/F1 预付账款.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "f30055cbebc7daedec6d073e983e7ada5375c3edf50b49880c7aa571846510dd"
)

#: canary store item（F1-6 关联方，裁决 F1-H1）
STORE_ITEM_ID: Final[str] = "F1-rp-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"


_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
# ═══════════════════════════════════════════════════════════════════════════


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    return ExcelIdentityCarrierGate.load()


def authoritative_template_path() -> Path:
    return excel_carrier_gate().assert_template_under_authority(
        TEMPLATE_RELATIVE_PATH
    )


def read_authoritative_template() -> bytes:
    path = authoritative_template_path()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != TEMPLATE_SHA256:
        raise EntrySelectionError(
            f"权威模板字节已变: {TEMPLATE_RELATIVE_PATH} 实测 sha256={digest}，"
            f"冻结哨兵={TEMPLATE_SHA256}"
        )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件（照 D3 同签名：resolution 必填、无关闭开关）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TemplateResolutionFacts:
    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


def assert_no_implicit_template_fallback(
    resolution: TemplateResolutionFacts,
    *,
    wp_codes: frozenset[str],
) -> None:
    missing = sorted(wp_codes - set(resolution.by_wp_code))
    if missing:
        raise EntrySelectionError(
            f"缺少 wp_code {missing} 的 finder 实测结果"
        )
    leaked = {
        code: [str(item) for item in hits if item]
        for code, hits in resolution.by_wp_code.items()
        if any(hits)
    }
    if leaked:
        raise EntrySelectionError(
            f"幻影码 {sorted(leaked)} 在 finder 里意外命中真模板 "
            f"—— 零回退判据要求幻影码不得命中：{leaked}"
        )


def assert_entry_selectable(
    *,
    resolution: TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """对真 manifest 核四条事实 + 零回退（FC-2：不留关闭开关）。"""
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(
            f"冻结的 entry {ENTRY_ID!r} 不在 manifest 里"
        )
    if str(entry.get("document_type") or "") != "xlsx":
        raise EntrySelectionError(
            f"{ENTRY_ID!r} document_type 非 xlsx"
        )
    if not entry.get("independent_entry"):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} independent_entry={entry.get('independent_entry')!r}"
        )
    profile_id = str(
        (entry.get("scenario_profile") or {}).get("profile_id") or ""
    )
    if profile_id != EXPECTED_PROFILE_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID!r} profile_id={profile_id!r} "
            f"与冻结的 {EXPECTED_PROFILE_ID!r} 不符"
        )
    codes = {
        str(c)
        for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()
    }
    if codes != set(WP_CODES):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} wp_code_patterns={sorted(codes)} "
            f"与冻结的 {sorted(WP_CODES)} 不一致"
        )
    assert_no_implicit_template_fallback(
        resolution, wp_codes=frozenset(codes)
    )
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 4. 灰度开关与受管 sheet 清单
# ═══════════════════════════════════════════════════════════════════════════

#: canary：F1-6 关联方及交易检查表（裁决 F1-H1）
_INCLUDE_F106: Final[bool] = True
#: F1-5 长期挂款检查表
_INCLUDE_F105: Final[bool] = False
#: F1-7 预付账款检查表（三区）
_INCLUDE_F107: Final[bool] = False
#: F1-4 实质性分析区④ suppliers
_INCLUDE_F104: Final[bool] = False
#: F1-2 明细表（两级表头 + nested 账龄）
_INCLUDE_F102: Final[bool] = False
#: F1-1 审定表（AdjudicationSheetSpec，最后接）
_INCLUDE_F101: Final[bool] = False


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。"""
    specs: list[Any] = []
    if _INCLUDE_F106:
        from app.services.workpaper_sync import (
            phase5_f1_06_related_party as _f106,
        )
        specs.append(_f106.SPEC_F106)
    if _INCLUDE_F105:
        from app.services.workpaper_sync import (
            phase5_f1_05_long_term as _f105,
        )
        specs.append(_f105.SPEC_F105)
    if _INCLUDE_F107:
        from app.services.workpaper_sync import (
            phase5_f1_07_voucher_check as _f107,
        )
        specs.extend((
            _f107.SPEC_F107_CURRENT,
            _f107.SPEC_F107_CREDIT,
            _f107.SPEC_F107_POST,
        ))
    if _INCLUDE_F104:
        from app.services.workpaper_sync import (
            phase5_f1_04_analysis as _f104,
        )
        specs.append(_f104.SPEC_F104_SUPPLIERS)
    if _INCLUDE_F102:
        from app.services.workpaper_sync import (
            phase5_f1_02_detail as _f102,
        )
        specs.append(_f102.SPEC_F102)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部 store item（单一口径，出/回两方向都从它取）。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def all_managed_sheet_names() -> tuple[str, ...]:
    """本 entry 全部受管 sheet 的 Excel 名称（含审定表）。"""
    names: list[str] = []
    seen: set[str] = set()
    for s in managed_row_table_specs():
        if s.managed_sheet not in seen:
            names.append(s.managed_sheet)
            seen.add(s.managed_sheet)
    adj = adjudication_spec()
    if adj is not None and adj.managed_sheet not in seen:
        names.append(adj.managed_sheet)
    return tuple(names)


def adjudication_spec() -> Any:
    """F1-1 审定表 AdjudicationSheetSpec（按灰度开关）。"""
    if not _INCLUDE_F101:
        return None
    from app.services.workpaper_sync.phase5_f1_01_adjudication import (
        SPEC_F101,
    )
    return SPEC_F101


def _managed_last_col_of(spec: Any) -> str:
    if not spec.field_specs:
        raise EntrySelectionError(
            f"{spec.managed_sheet} 未声明任何受管字段"
        )
    return max((row[1] for row in spec.field_specs), key=col_index)


def _instrumentation_of(spec: Any) -> ExcelInstrumentationSpec:
    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID,
        template_id=spec.template_id,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=spec.managed_sheet,
        first_data_row=spec.first_data_row,
        last_data_row=spec.last_data_row,
        footer_row=spec.footer_row,
        managed_last_col=_managed_last_col_of(spec),
        uuid_col=spec.uuid_col,
        table_name=spec.table_name,
        sheet_key=spec.sheet_key,
    )


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    """本 entry 的全部 instrumentation 声明（复数）。"""
    return tuple(_instrumentation_of(s) for s in managed_row_table_specs())


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    first_spec = managed_row_table_specs()
    if not first_spec:
        raise EntrySelectionError("F1 当前无受管 sheet")
    return build_template_payload(
        spec=_instrumentation_of(first_spec[0]),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    return build_instrumentation_payload_for_sheets(
        specs=instrumentation_specs(),
        template_definition_sha256=canonical_digest(
            template_definition_payload()
        ),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 契约装配
# ═══════════════════════════════════════════════════════════════════════════

_HTML_STORE_NOTE: Final[str] = (
    "F1 预付账款的结构化 Tab 行数据存成 checklist_responses 的 remark "
    "JSON 数组。本契约按 stable field + rowId 拆开。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 F/F1 预付账款.xlsx + 前端 useF1*.ts 按值 grep"
)


def _rows_table_payload(spec: Any) -> dict[str, Any]:
    """一个行表 spec → 契约 table payload。

    🔴 修复：原手写 payload 缺 `anchor`/`header_rows`/`delete_policy` 等必填字段，
    `parse_contract` 抛 `ContractSchemaError: table anchor 必须是 A1 单元格，实得 None`。
    改为委托框架层 `spec_to_contract_sheet_payload`（与 F3/F4/F5 三个 provider 同构），
    它从 `RowTableSheetSpec` 自动派生全部字段（含 anchor/header_rows/delete_policy/
    字段的 cell/json_pointer/source_ref/header_source_ref/store_item_id）。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        spec_to_contract_sheet_payload,
    )
    sheet_payload = spec_to_contract_sheet_payload(spec)
    # spec_to_contract_sheet_payload 返回整个 sheet（含 tables 数组），取第一个 table。
    return sheet_payload["tables"][0]


def build_contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    template_payload = template_definition_payload()
    row_specs = managed_row_table_specs()
    if not row_specs:
        raise EntrySelectionError("F1 当前无受管 sheet")

    sheets: list[dict[str, Any]] = []
    for spec in row_specs:
        sheets.append({
            "sheet_key": spec.sheet_key,
            "excel_name": spec.managed_sheet,
            "locator": {"anchor": TABLE_SHEET_ANCHOR},
            "tables": [_rows_table_payload(spec)],
        })

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
            "normalized_structure_hash": template_payload[
                "normalized_structure_hash"
            ],
        },
        "identity_carriers": [
            "hidden_sheet",
            "defined_name",
            "excel_table",
            "hidden_uuid_column",
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
                "note": _HTML_STORE_NOTE,
            },
            "reviewed_basis": _REVIEWED_BASIS,
        },
    }


def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    expected = build_contract_payload()
    on_disk = load_contract_from_disk()
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise EntrySelectionError(
            "磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
            f"disk={canonical_digest(on_disk.canonical_payload)} "
            f"source={canonical_digest(expected)}；"
            "请用 generate_phase5_f1_contract.py --apply 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. store 投影/合并（薄转发框架层）
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> Any:
    """store item → 受管 spec。未登记即抛。"""
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise EntrySelectionError(
        f"store item {store_item_id!r} 不在 F1 受管清单里；"
        f"已受管：{sorted(all_store_item_ids())}"
    )


def build_store_projection(
    store_item_id: str,
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _engine,
    )
    spec = _spec_of_store_item(store_item_id)
    return _engine(spec, payload, contract=contract, limits=limits)


def merge_projection_into_store_rows(
    store_item_id: str,
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )
    spec = _spec_of_store_item(store_item_id)
    return _engine_merge(
        spec, projection=projection, base_rows=base_rows
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. manifest capability 检查
# ═══════════════════════════════════════════════════════════════════════════


def manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> bool:
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except EntrySelectionError:
        return False
    return True


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    entry = manifest_entries_by_id(
        manifest if manifest is not None else load_entry_manifest()
    ).get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(f"{ENTRY_ID} 不在 manifest 里")
    cap = capability_of(entry)
    if cap is not Capability.bidirectional:
        raise EntrySelectionError(
            f"{ENTRY_ID} capability={cap!r}，期望 bidirectional"
        )
    # 🔴 R3 安全补丁（D4 同款）：overlay 裁决 bidirectional 后 adapter_id 必须回写
    aid = str(entry.get("adapter_id") or "")
    if aid and aid != ADAPTER_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID} adapter_id={aid!r} 与本 provider 的 "
            f"{ADAPTER_ID!r} 不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. adapter 注册与宿主接线（照 D3:830）
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)


def build_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return AdapterRegistration(
        adapter=adapter,
        entry_id=ENTRY_ID,
        matcher=build_matcher(),
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        declared_capability=Capability.bidirectional,
        contract=(
            contract if contract is not None
            else load_contract_from_disk()
        ),
    )


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    registration = build_registration(
        adapter=adapter,
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        contract=contract,
    )
    registry.register(registration)
    return registration


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
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


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach F1 adapter（照 D3 同构）。"""
    if ADAPTER_ID in {
        reg.adapter_id for reg in registry.registrations()
    }:
        return ()
    if not manifest_capability_enabled():
        return ()

    import sqlalchemy as sa
    from app.models.workpaper_sync_models import (
        WorkpaperContentRepresentation,
    )
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import (
        build_excel_adapter,
    )
    from app.services.workpaper_sync.artifacts import (
        CanonicalArtifactRepository,
    )
    from app.services.workpaper_sync.resolution import (
        CanonicalResolutionService,
    )

    representation_id = (
        await resolve_visible_current_representation_id(
            session, entry_id=ENTRY_ID
        )
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
    if (
        representation is None
        or representation.definition_bundle_id is None
    ):
        return ()

    resolution = CanonicalResolutionService(
        session, CanonicalArtifactRepository(_BACKEND_ROOT)
    )
    bundle = await resolution.load_bundle_snapshot(
        representation.definition_bundle_id
    )
    contract = assert_contract_file_matches_source()
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的宿主实测不可达"
        )
    observation = await resolve_published_frozen_definitions(
        session=session,
        representation=representation,
        contract=contract,
    )
    register_adapter(
        registry,
        adapter=build_excel_adapter(
            definitions=observation.definitions,
            binding=observation.identity_binding,
            direction="html_to_oo",
        ),
        bundle=bundle,
        descriptor=descriptor,
        room=facts.observe_room_facts(entry),
        contract=contract,
    )
    return (ADAPTER_ID,)
