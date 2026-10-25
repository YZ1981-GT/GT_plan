# -*- coding: utf-8 -*-
"""L5 长期应付款「明细表 L5-2」—— L 循环真双向 entry（**两区同键 + flat 账龄**，R24 占位续行作静态骨架）。

spec: l5-true-bidirectional-2026-10-01 · T4；几何/选型见 `phase5_l5_sheets`，T1 架构坐实见
`.agents/tasks/l5-true-bidirectional-2026-10-01/t1-architecture-gate.md`。
🔴 **勘误（用户裁决 A，2026-10-02）**：T1/report 原记「三区同键」，终态收敛为两区（R24「其他」占位
续行走静态骨架，typography 门 BP-21 拒受管）；`SPECS` 现为两段，详见 `phase5_l5_sheets` 模块 docstring。

本模块声明 IDENTITY + 两区 SPECS 与 L5 幻影码选型，身份/契约/发布委派 `phase5_l_cycle_common`
（照 L7），**store 投影/合并/迭代走多区门面** `phase5_l5_store_facade`（照 G9），且
`attach_adapters` 补 sibling binding 覆盖区②（否则真 OO extract 只读区①的 UUID 列，区②消失）。
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
from app.services.workpaper_sync.phase5_l5_sheets import (  # noqa: F401
    ADAPTER_ID, AUTHORITY_MODEL, EMPTY_STORE_PAYLOAD, ENTRY_ID, EXPECTED_PROFILE_ID,
    FORMULA_COLUMNS, FORMULA_TEMPLATES, HEADER_GROUP_ROW, HEADER_LEAF_ROW,
    HTML_ONLY_ROW_KEYS, MANAGED_SHEET, PHASE5_WAVE, ROW_IDENTITY_STORE_KEY, ROW_SECTION_FIELD,
    ROW_SECTION_VALUES, ROWS_TABLE_KEY, SHEET_KEY, SPEC_L52_R1, SPEC_L52_R2, ALL_SPECS_L52,
    STORE_ITEM_ID, TABLE_NAME, TEMPLATE_ID, TEMPLATE_RELATIVE_PATH, TEMPLATE_SHA256,
    UUID_COL, WP_CODES, AGING_GROUPS_L52, _HTML_STORE_NOTE, _REVIEWED_BASIS,
)

IDENTITY: Final[_L.LEntryIdentity] = _L.LEntryIdentity(
    entry_id=ENTRY_ID, adapter_id=ADAPTER_ID, phase5_wave=PHASE5_WAVE,
    wp_codes=frozenset(WP_CODES), template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256, primary_store_item_id=STORE_ITEM_ID,
    row_identity_store_key=ROW_IDENTITY_STORE_KEY, html_store_note=_HTML_STORE_NOTE,
    reviewed_basis=_REVIEWED_BASIS, authority_model=AUTHORITY_MODEL,
    expected_profile_id=EXPECTED_PROFILE_ID, html_only_keys=HTML_ONLY_ROW_KEYS,
    derived_readonly_sheet={
        "excel_name": "审定表L5-1",
        "reason": "R7~R16 全部是跨 sheet 聚合 明细表L5-2 的下游视图，非录入表；受管表选 L5-2",
    },
    extra_review={
        # 🔴 两区同键声明（照 G9 契约 html_store 的 row_section_* 字段，但 l_cycle_common 的
        #    html_store 是单 item 形态 ⇒ 经 extra_review 作顶层 review 键带出，纯声明，引擎行为
        #    由 SPEC 的 row_section_field/value 驱动，不读契约）。
        "row_sections": {
            "field": ROW_SECTION_FIELD,
            "values": list(ROW_SECTION_VALUES),
            "note": (
                "两个受管区（售后租回 R11:15 / 分期付款 R18:22）共用同一 store 键 L5-L5-2-rows，"
                "行区归属由 section 字段表达；契约 sheets[0] 对应两条 tables[]（逐段不同 uuid_col AD/AE）。"
                "R24「其他」段作模板静态骨架不进受管区（typography 门 BP-21 拒 A24='…' 占位续行，用户裁决 A）。"
            ),
        },
        "template_defects_registered": {
            "bare_if": {
                "sheet": "明细表L5-2",
                "managed_sheet_bare_if": 0,
                "note": "受管表零裸 IF（全是本行算术公式 E/L/M/N/O/R/S），不需 neutralize",
            },
            "static_skeleton_rows": {
                "section_title_rows": ["A10 售后租回", "A17 分期付款"],
                "subtotal_rows": ["A16=SUM(B11:B15)", "A23=SUM(B18:B22)"],
                "grand_total_row": "A25=SUM(B16,B23,B24)（非连续枚举 SUM）",
                "other_placeholder_row": "R24 A24='…'(U+2026) 占位续行 + roll-forward 公式骨架（输入格空）",
                "note": (
                    "区标题/小计/合计/R24 其他占位续行作模板静态骨架（is_template_skeleton_identity），"
                    "不进受管区、不进 footer 公式归一化；roll-forward 与 SUM 公式幸存。"
                    "R24 不受管的裁决依据（用户裁决 A，现查坐实）：真库 L5-L5-2-rows 0 行无 section/R24 痕迹 + "
                    "HTML 侧无用户可填的「其他」第三分组 + Excel R24 输入格全空 ⇒ R24 系模板预留占位续行、非业务行；"
                    "平台 typography 门 BP-21（比幽灵行更硬）对纯省略号占位行 fail-closed。零能力损失（两个真实分组全受管）。"
                ),
            },
            "aging_layout": {
                "layout": "flat",
                "buckets": ["6个月以内", "6-12月", "1～2年", "２～3年", "3年以上"],
                "note": "单组 5 桶 T~X，叶子标签用模板全角字符（～=U+FF5E / ２=U+FF12）；L 域首个账龄表",
            },
            "derived_sheet_mirror_dependency": {
                "sheet": "未确认融资费用明细表L5-3",
                "note": "L5-3 的 A 列 ='明细表L5-2'!A{n} 硬行号镜像引用；本轮不受管 L5-3，但真 OO 往返须断言 L5-2 受管区扩行不打坏它",
            },
        },
    },
)
SPECS: Final[tuple[RowTableSheetSpec, ...]] = ALL_SPECS_L52
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


def assert_entry_selectable(*, resolution: TemplateResolutionFacts | None = None,
                            manifest: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    entry = manifest_entries_by_id(manifest if manifest is not None else load_entry_manifest()).get(ENTRY_ID)
    if entry is None or entry.get("document_type") != "xlsx" or not entry.get("independent_entry"):
        raise EntrySelectionError(f"{ENTRY_ID} 非独立 xlsx entry")
    profile = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
    codes = {str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()}
    if profile != EXPECTED_PROFILE_ID or codes != set(WP_CODES):
        raise EntrySelectionError(f"{ENTRY_ID} manifest 身份漂移 profile={profile} codes={sorted(codes)}")
    return entry


# ── 受管 sheet / instrumentation（两区各一条，R24 其他段作静态骨架不建区）──────
def managed_row_table_specs() -> tuple[RowTableSheetSpec, ...]: return SPECS
def section_specs() -> tuple[RowTableSheetSpec, ...]: return tuple(s for s in SPECS if s.row_section_field)
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
    """发布链编排：attach L5 adapter，**带区② sibling binding**。

    🔴 与 `l_cycle_common.attach_l_entry_adapter` 的差异（本模块覆盖它）：L5 是两区同键（R24 其他段
    作静态骨架不建区），每区有独立 uuid_col（AD/AE）。只传主表 binding ⇒ 真 OO extract 只读区① UUID 列，
    区②的受管字段在 roundtrip 后全部消失（I5 实测过同一缺陷）。照 `attach_h_entry_adapter`
    按 contract table_key 与 instrumentation spec 组装 sibling bindings（主表去重，其余逐表保留 UUID 列）。
    """
    if ADAPTER_ID in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled():
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import WorkpaperContentRepresentation
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.excel_extract import ExcelIdentityBinding
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    representation_id = await resolve_visible_current_representation_id(session, entry_id=ENTRY_ID)
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

    resolution = CanonicalResolutionService(session, CanonicalArtifactRepository(_L._BACKEND_ROOT))
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = assert_contract_file_matches_source()
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(f"entry {ENTRY_ID} 的宿主实测不可达")
    observation = await resolve_published_frozen_definitions(
        session=session, representation=representation, contract=contract
    )
    # 🔴 区②③ sibling binding（照 attach_h_entry_adapter）：主表 table_key 去重，其余逐区各保留 UUID 列。
    primary_key = str(observation.identity_binding.table_key)
    sibling_bindings: list[ExcelIdentityBinding] = []
    for spec in SPECS:
        table_key = str(getattr(spec, "table_key", "") or "")
        if not table_key or table_key == primary_key:
            continue
        sibling_bindings.append(
            ExcelIdentityBinding(
                table_name=str(spec.table_name),
                uuid_column=str(spec.uuid_col),
                table_key=table_key,
                metadata_sheet=observation.identity_binding.metadata_sheet,
                defined_name_prefix=str(getattr(spec, "defined_name_prefix", None) or "GT_"),
                tombstoned_row_keys=(),
                dynamic_column_columns={},
            )
        )
    register_adapter(
        registry,
        adapter=build_excel_adapter(
            definitions=observation.definitions,
            binding=observation.identity_binding,
            direction="html_to_oo",
            sibling_bindings=tuple(sibling_bindings),
        ),
        bundle=bundle,
        descriptor=descriptor,
        room=facts.observe_room_facts(entry),
        contract=contract,
    )
    return (ADAPTER_ID,)


# ═══════════════════════════════════════════════════════════════════════════
# store 门面重导出（两区同键，伴生模块 `phase5_l5_store_facade`）
# ═══════════════════════════════════════════════════════════════════════════
from app.services.workpaper_sync.phase5_l5_store_facade import (  # noqa: E402
    build_store_projection,
    iter_store_rows,
    merge_projection_into_store_rows,
    specs_for as _specs_for,
    split_store_payload_by_section,
)

publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES

__all__ = [
    "ENTRY_ID", "ADAPTER_ID", "STORE_ITEM_ID", "SPECS", "IDENTITY",
    "build_store_projection", "merge_projection_into_store_rows", "iter_store_rows",
    "split_store_payload_by_section", "_specs_for",
]
