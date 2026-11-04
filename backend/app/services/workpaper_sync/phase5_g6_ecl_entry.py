# -*- coding: utf-8 -*-
"""G6-ecl 独立 entry 模块 —— 「其他债权投资三阶段划分G6-11」转置表。

spec: `g4-g6-shared-workbook-three-entry-lanes` · Task 15

与 G6-main 共用 `TEMPLATE_SHA256`（同一册 G6 其他债权投资.xlsx），但有独立的
ENTRY_ID / ADAPTER_ID / build_matcher(sheet_keys={"g611-managed"})。
pointer 靠 `entry_id` 区分（裁决 G46-H2），matcher 靠互斥 sheet_keys 分域（F2-H1）。

只挂一个转置 sheet `g611-managed`，走 `TransposedSheetSpec` / `phase5_transposed_sheet` 引擎。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final, Mapping

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
from app.services.workpaper_sync.models import SyncDomainError

# ── 转置 spec ─────────────────────────────────────────────────────────
from app.services.workpaper_sync.phase5_g6_11_ecl_stage import (
    SPEC_G611,
    MANAGED_SHEET as ECL_MANAGED_SHEET,
    SHEET_KEY as ECL_SHEET_KEY,
    STORE_ITEM_ID as ECL_STORE_ITEM_ID,
    sheet_payload as ecl_sheet_payload,
    compute_mapping_digest as ecl_mapping_digest,
)

# ── 共用常量（同册 G6）──────────────────────────────────────────────────
from app.services.workpaper_sync.phase5_g6_other_bond import (
    TEMPLATE_SHA256,
    TEMPLATE_RELATIVE_PATH,
    WP_CODES,
    EXPECTED_PROFILE_ID,
    excel_carrier_gate,
    read_authoritative_template,
)


class EntrySelectionError(SyncDomainError):
    error_code = "sync_phase5_g6_ecl_selection_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_other_bond_ecl"
ENTRY_ID: Final[str] = "xlsx/gt-g6-other-bond-investment-ecl"
ADAPTER_ID: Final[str] = "g6.ecl_stage"

#: 互斥 sheet_keys（F2-H1 解法）
SHEET_KEYS: Final[frozenset[str]] = frozenset({ECL_SHEET_KEY})

STORE_ITEM_ID: Final[str] = ECL_STORE_ITEM_ID
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "id"

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "dual_write"

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_HTML_STORE_NOTE: Final[str] = (
    "G6-11 ECL 三阶段划分：转置形态（一列=一投资、一行=一评估维度），"
    "payload dual_write；16384 列表 UUID 放第 12 列 L（有效内容列 +1）。"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 spec 与 store
# ═══════════════════════════════════════════════════════════════════════════

def managed_transposed_spec():
    return SPEC_G611


def all_store_item_ids() -> tuple[str, ...]:
    return (ECL_STORE_ITEM_ID,)


def all_managed_sheet_names() -> tuple[str, ...]:
    return (ECL_MANAGED_SHEET,)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 契约
# ═══════════════════════════════════════════════════════════════════════════

def _transposed_sheet_dict() -> dict[str, Any]:
    payload = ecl_sheet_payload()
    return {
        "sheet_key": ECL_SHEET_KEY,
        "excel_name": ECL_MANAGED_SHEET,
        "locator": payload["locator"],
        "tables": payload["tables"],
    }


def build_contract_payload() -> dict[str, Any]:
    template_data = read_authoritative_template()
    from app.services.workpaper_sync.excel_instrumentation import normalized_structure_hash

    structure_hash = normalized_structure_hash(template_data)
    sheet_dict = _transposed_sheet_dict()
    instr_payload = {"transposed_sheets": [ecl_sheet_payload()]}
    template_def = {
        "template_sha256": TEMPLATE_SHA256,
        "relative_path": TEMPLATE_RELATIVE_PATH,
        "normalized_structure_hash": structure_hash,
    }

    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": ADAPTER_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": canonical_digest(template_def),
        "instrumentation_definition_sha256": canonical_digest(instr_payload),
        "template": {
            "relative_path": TEMPLATE_RELATIVE_PATH,
            "template_sha256": TEMPLATE_SHA256,
            "normalized_structure_hash": structure_hash,
        },
        "identity_carriers": [
            "hidden_sheet",
            "defined_name",
            "hidden_uuid_column",
        ],
        "sheets": [sheet_dict],
        "review": {
            "entry_id": ENTRY_ID,
            "pilot_class": PHASE5_WAVE,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_ids": list(all_store_item_ids()),
                "shape": "json_array_of_row_objects",
                "payload_column": PAYLOAD_COLUMN,
                "payload_column_mode": PAYLOAD_COLUMN_MODE,
                "note": _HTML_STORE_NOTE,
            },
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
            "请用 generate_phase5_g6_ecl_contract.py --apply 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 4. manifest capability
# ═══════════════════════════════════════════════════════════════════════════

def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
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
        raise EntrySelectionError(f"{ENTRY_ID} capability={cap!r}，期望 bidirectional")
    aid = str(entry.get("adapter_id") or "")
    if aid and aid != ADAPTER_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID} adapter_id={aid!r} 与本 provider 的 {ADAPTER_ID!r} 不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. matcher + registration
# ═══════════════════════════════════════════════════════════════════════════

def build_matcher() -> EntryMatcher:
    """matcher 域：幻影码 G6O + sheet_keys={g611-managed}（互斥分域）。"""
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES, sheet_keys=SHEET_KEYS)


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
        contract=(contract if contract is not None else load_contract_from_disk()),
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
        adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract,
    )
    registry.register(registration)
    return registration


# ═══════════════════════════════════════════════════════════════════════════
# 已发布冻结身份（`resolve_published_frozen_definitions`）
#
# 🔴 补齐原因（2026-11-04）：本模块的交付台账条目（`g6.ecl_stage`）早已登记，但这个函数一直缺位
#    ⇒ Task 75 的四条判据（真 await 共享观测器 / 真 digest 比对 / 不无条件 raise / 消费 contract）
#    在本 entry 上**没有分母**，等于从未被看过。形态与同册主 entry（`phase5_g6_other_bond`）逐字同构：
#    九步由 `published_identity_observer` 独家承载，本模块只做「观测 + 契约 digest 比对」。
# ═══════════════════════════════════════════════════════════════════════════


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    """读已发布 representation 的冻结定义，并与 provider source-locked 的契约 digest 比对。

    九步（bundle 当前性 / 定义完整性 / 结构漂移 / 身份绑定 …）只在共享观测器里实现一次；
    本函数不得自己抄，否则任一侧被短路都不改变行为（第二真源）。
    """
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
        correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise EntrySelectionError(
            f"entry {ENTRY_ID}: 观测器读出的契约 digest "
            f"{observation.definitions.contract.canonical_sha256} "
            f"与本模块 source-locked 的 {contract.canonical_sha256} 不一致"
        )
    return observation


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach 本 entry 的 adapter（与同册主 entry `phase5_g6_other_bond` 同构）。

    🔴 补齐原因（2026-11-04）：本模块交付了契约与 `build_registration` / `register_adapter`，
    却一直没有 attach 入口 —— 台账把本 entry 记作 delivered per-entry contract，而注册器
    （`register_from_manifest`）按 `provider.attach_pilot_adapters` 逐 entry attach，属性缺位
    就是「交付了但永远接不上」。早退顺序与同族一致：已注册 → capability 未裁决 → 无 published
    representation → 无 definition bundle，每个早退都返回空元组，由 registry 侧换算成显式原因。
    本 entry 的 capability 当前仍是 null（台账 reason 已写明），因此第二道早退会生效 ——
    行为不变，但接线从此是**真的**存在，capability 裁决后无需再改接线。
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
    from app.services.workpaper_sync.entry_profile import (
        load_entry_manifest,
        manifest_entries_by_id,
    )
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
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(f"entry {ENTRY_ID} 的宿主实测不可达")
    observation = await resolve_published_frozen_definitions(
        session=session, representation=representation, contract=contract
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


attach_adapters = attach_pilot_adapters
