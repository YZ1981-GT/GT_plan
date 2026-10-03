# -*- coding: utf-8 -*-
"""F2 存货 main 册（审定明细表类）—— Phase 5 lane M provider。

spec: f2-sync-coverage-four-entry-lanes · Task 7

═══ 与 F1 同构（F2-H1 用 sheet_keys 解 RG-3 同码冲突）═══

本模块持有 lane M 的冻结身份常量、选型守卫、灰度开关、契约装配、发布链编排。
受管 sheet 声明在伴生 phase5_f2_main_detail_sheets.py（F2-3/4/6/8/9 共享
useF2DetailSheet 的 config 驱动形态）以及后续扩展文件。

🔴 与 F1 的唯一结构差异：`build_matcher()` 带 `sheet_keys`（F2-H1 裁决），因为
main / valuation / special 三个 entry 共用幻影码 F2I（RG-3 冲突已在 Task 3 证明）。

canary = F2-6 四、自制半成品明细表（裁决 F2-H4：明细表族最小失败面）。
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
from dataclasses import dataclass
from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.definitions import DefinitionKind
from app.services.workpaper_sync.definitions import BundleSlot


class EntrySelectionError(SyncDomainError):
    """冻结的 entry 不再满足选型必要条件。"""
    error_code = "sync_phase5_f2_main_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法。"""
    error_code = "sync_phase5_f2_main_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_f2_inventory_main"
ENTRY_ID: Final[str] = "xlsx/gt-f2-inventory-main"
ADAPTER_ID: Final[str] = "f2.inventory_main"

#: 🔴 manifest 冻结的幻影码（FC-2：matcher 域用幻影码，provisioning 用真码）
#: 三个 F2I entry 共用此码，RG-3 冲突靠 sheet_keys 互斥解（F2-H1）。
WP_CODES: Final[frozenset[str]] = frozenset({"F2I"})
EXPECTED_PROFILE_ID: Final[str] = (
    "xlsx.editable.shared.single.room_service_wired.v1"
)
TEMPLATE_RELATIVE_PATH: Final[str] = (
    "F/F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx"
)
TEMPLATE_SHA256: Final[str] = (
    "9e57efd242b47171423e61f63a35be6ae5b46889baa14c246595ea95591fd0d8"
)

#: canary store item（F2-6 自制半成品，裁决 F2-H4）
STORE_ITEM_ID: Final[str] = "F2-6-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "id"

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
            f"权威模板字节已变: {TEMPLATE_RELATIVE_PATH} "
            f"实测 sha256={digest}，冻结哨兵={TEMPLATE_SHA256}"
        )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件（FC-2：默认严格、真 manifest 真调、幻影码为 matcher 域）
# ═══════════════════════════════════════════════════════════════════════════


def assert_entry_selectable(
    *, manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """对真 manifest 核四条事实（entry 存在 / independent=True / profile / wp_code_patterns）。"""
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(
            f"冻结的 entry {ENTRY_ID!r} 不在 manifest 里"
        )
    if str(entry.get("document_type") or "") != "xlsx":
        raise EntrySelectionError(f"{ENTRY_ID!r} document_type 非 xlsx")
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
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 4. 灰度开关与受管 sheet 清单
# ═══════════════════════════════════════════════════════════════════════════

#: canary：F2-6 四、自制半成品明细表（裁决 F2-H4）
_INCLUDE_F206: Final[bool] = True
#: F2-3 原材料（footer B 列，需框架层 footer_search_column 或暂缓）
_INCLUDE_F203: Final[bool] = False
#: F2-4 材料采购
_INCLUDE_F204: Final[bool] = False
#: F2-8 库存商品（+在手订单列 V/W/X）
_INCLUDE_F208: Final[bool] = False
#: F2-9 发出商品
_INCLUDE_F209: Final[bool] = False
#: F2-7 委托加工物资
_INCLUDE_F207: Final[bool] = False
#: F2-12 合同履约成本
_INCLUDE_F212: Final[bool] = False
#: F2-5 周转材料（分组形态，后置）
_INCLUDE_F205: Final[bool] = False
#: F2-10 开发产品 / F2-11 开发成本 / F2-13 生物资产（多块形态，后置）
_INCLUDE_F210_11_13: Final[bool] = False
#: F2-2 明细汇总（HTML-only 候选，核后定）
_INCLUDE_F202: Final[bool] = False
#: F2-14 调整分录（FC-6 默认 single_html）
_INCLUDE_F214: Final[bool] = False
#: F2-1 审定表（最后接，依赖 F2-2 裁决）
_INCLUDE_F201: Final[bool] = False


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。"""
    specs: list[Any] = []
    if _INCLUDE_F206:
        from app.services.workpaper_sync import (
            phase5_f2_main_detail_sheets as _f2det,
        )
        specs.append(_f2det.SPEC_F206)
    if _INCLUDE_F203:
        from app.services.workpaper_sync import (
            phase5_f2_main_detail_sheets as _f2det,
        )
        specs.append(_f2det.SPEC_F203)
    if _INCLUDE_F204:
        from app.services.workpaper_sync import (
            phase5_f2_main_detail_sheets as _f2det,
        )
        specs.append(_f2det.SPEC_F204)
    if _INCLUDE_F208:
        from app.services.workpaper_sync import (
            phase5_f2_main_detail_sheets as _f2det,
        )
        specs.append(_f2det.SPEC_F208)
    if _INCLUDE_F209:
        from app.services.workpaper_sync import (
            phase5_f2_main_detail_sheets as _f2det,
        )
        specs.append(_f2det.SPEC_F209)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部 store item id。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def all_managed_sheet_names() -> tuple[str, ...]:
    """本 entry 全部受管 sheet 的 Excel 名称。"""
    return tuple(s.managed_sheet for s in managed_row_table_specs())


def all_managed_sheet_keys() -> frozenset[str]:
    """本 entry 受管 sheet key 集合（matcher 域，F2-H1）。"""
    return frozenset(s.sheet_key for s in managed_row_table_specs())


# ═══════════════════════════════════════════════════════════════════════════
# 5. instrumentation
# ═══════════════════════════════════════════════════════════════════════════


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
    return tuple(_instrumentation_of(s) for s in managed_row_table_specs())


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    first_spec = managed_row_table_specs()
    if not first_spec:
        raise EntrySelectionError("F2 main 当前无受管 sheet")
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
# 6. 契约装配
# ═══════════════════════════════════════════════════════════════════════════

_HTML_STORE_NOTE: Final[str] = (
    "F2 main 册的明细表族行数据存成 checklist_responses 的 remark "
    "JSON 数组，键由 `${sheetCode}-rows` 模板化拼出。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 F/F2-1至F2-14 + 前端 useF2DetailSheet.ts 按值 grep"
)


def _rows_table_payload(spec: Any) -> dict[str, Any]:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        managed_field_specs,
    )
    fields = managed_field_specs(spec)
    return {
        "table_key": spec.table_key,
        "table_name": spec.table_name,
        "row_identity": {
            "store_key": spec.row_identity_key,
            "column": spec.uuid_col,
            "hidden": True,
        },
        "fields": [
            {
                "stable_field_key": f[0],
                "column": f[1],
                "mode": f[2],
                "value_type": f[3],
                "json_key": f[4],
                "header_text": f[5],
            }
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
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        spec_to_contract_sheet_payload,
    )

    template_payload = template_definition_payload()
    row_specs = managed_row_table_specs()
    if not row_specs:
        raise EntrySelectionError("F2 main 当前无受管 sheet")

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
            "请用 generate_phase5_f2_contract.py --apply 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 7. store 投影/合并（薄转发框架层）
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> Any:
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise EntrySelectionError(
        f"store item {store_item_id!r} 不在 F2 main 受管清单里；"
        f"已受管：{sorted(all_store_item_ids())}"
    )


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _engine,
    )
    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine(spec, payload, contract=contract, limits=limits)


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
    store_item_id: str | None = None,
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )
    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_merge(
        spec, projection=projection, base_rows=base_rows
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. manifest capability 检查
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


# ═══════════════════════════════════════════════════════════════════════════
# 9. adapter 注册（F2-H1：带 sheet_keys 解 RG-3 同码冲突）
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    """构造 matcher。🔴 带 sheet_keys（F2-H1）—— 三个 F2I entry 各自声明互斥 sheet key。"""
    return EntryMatcher(
        document_type="xlsx",
        wp_codes=WP_CODES,
        sheet_keys=all_managed_sheet_keys(),
    )


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
    """发布链编排：attach F2 main adapter（照 D3:830 / F1 同构）。"""
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

AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract


def authority_model_payload() -> dict[str, Any]:
    return {
        "schema_version": "authority-model-definition:v1",
        "entry_id": ENTRY_ID,
        "authority_model": AUTHORITY_MODEL.value,
        "content_authority": "structured_projection",
        "merge_model": "stable_field_three_way",
        "pilot_class": "phase5",
        "reason": (
            f"{ENTRY_ID}：结构化 Tab（HTML store）与 OnlyOffice 共写同一份权威模板，"
            "投影契约是唯一权威 —— 与 D1~D7 / E1 / F3~F5 同型"
        ),
    }


@dataclass(frozen=True)
class Phase5Definitions:
    """发布结果（与 F3/F4/F5/H 系各家同形）。"""
    authority_model_definition_id: Any
    authority_model_definition_sha256: str
    template_definition_id: Any
    template_definition_sha256: str
    instrumentation_definition_id: Any
    instrumentation_definition_sha256: str
    contract_definition_id: Any
    contract_definition_sha256: str
    bundle_id: Any
    bundle_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": ENTRY_ID,
            "adapter_id": ADAPTER_ID,
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
    """发布五个 definition + bundle（照 F3/D3 范式）。"""
    contract = assert_contract_file_matches_source()
    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=authority_model_payload(),
        logical_id=f"{ADAPTER_ID}.authority-model",
        semantic_version="1.0.0",
    )
    template_payload = template_definition_payload()
    template = await publisher.publish_definition(
        kind=DefinitionKind.template,
        payload=template_payload,
        logical_id=f"{ADAPTER_ID}.template",
        semantic_version="1.0.0",
        blob_bytes=read_authoritative_template(),
        structure_hash=template_payload["normalized_structure_hash"],
    )
    instrumentation = await publisher.publish_definition(
        kind=DefinitionKind.instrumentation,
        payload=instrumentation_definition_payload(),
        logical_id=f"{ADAPTER_ID}.instrumentation",
        semantic_version="1.0.0",
    )
    contract_definition = await publisher.publish_definition(
        kind=DefinitionKind.contract,
        payload=dict(contract.canonical_payload),
        logical_id=ADAPTER_ID,
        semantic_version=contract.semantic_version,
    )
    if template.sha256 != contract.template_definition_sha256:
        from app.services.workpaper_sync.adapters.registry import RegistrationError
        raise RegistrationError(
            f"已发布 template digest {template.sha256} 与契约声明 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        from app.services.workpaper_sync.adapters.registry import RegistrationError
        raise RegistrationError(
            f"已发布 instrumentation digest {instrumentation.sha256} 与契约声明 "
            f"{contract.instrumentation_definition_sha256} 不一致 —— 单向引用断裂"
        )
    bundle = await publisher.publish_bundle(
        authority_model_definition_id=authority.definition_id,
        authority_model=AUTHORITY_MODEL,
        authority_model_definition_sha256=authority.sha256,
        slots={
            BundleSlot.template: {
                "type": "definition",
                "ref": f"definition:{template.definition_id}",
                "digest": template.sha256,
            },
            BundleSlot.instrumentation: {
                "type": "definition",
                "ref": f"definition:{instrumentation.definition_id}",
                "digest": instrumentation.sha256,
            },
            BundleSlot.contract: {
                "type": "definition",
                "ref": f"definition:{contract_definition.definition_id}",
                "digest": contract_definition.sha256,
            },
        },
    )
    return Phase5Definitions(
        authority_model_definition_id=authority.definition_id,
        authority_model_definition_sha256=authority.sha256,
        template_definition_id=template.definition_id,
        template_definition_sha256=template.sha256,
        instrumentation_definition_id=instrumentation.definition_id,
        instrumentation_definition_sha256=instrumentation.sha256,
        contract_definition_id=contract_definition.definition_id,
        contract_definition_sha256=contract_definition.sha256,
        bundle_id=bundle.bundle_id,
        bundle_sha256=bundle.canonical_sha256,
    )


publish_pilot_definitions = publish_definitions
