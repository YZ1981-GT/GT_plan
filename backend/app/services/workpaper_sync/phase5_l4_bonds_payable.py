# -*- coding: utf-8 -*-
"""L4 应付债券「划分为金融负债的其他金融工具明细表 L4-3」—— L 循环第二条真双向 entry。

spec: l-cycle-true-adapter-registration · Task 12

只有声明（`IDENTITY` + `SPECS`）与 L4 独有的选型判据；七段流程全部委派
`phase5_l_cycle_common`（task 11）。几何与选型裁决见 `phase5_l4_sheets` 模块 docstring。

🔴 BP-8（L4-7 / L4-8 同尾码折叠）与本受管表无关：L4-3 尾码唯一，`resolve_target_sheet`
strict 模式下直接命中；route A 的 `{尾码}#{bondBranch}` 键留待 L4-7/L4-8 接线时才进契约。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_l_cycle_common as _L
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import SyncContract, contract_path_for, load_contract
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
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec

#: 🔴 整组 re-export：守卫按 `phase5_l4_bonds_payable.<常量>` 读几何真源（F401 是有意的）。
from app.services.workpaper_sync.phase5_l4_sheets import (  # noqa: F401
    PRE_SANITIZE_TEMPLATE_SHA256,
    ADAPTER_ID,
    AUTHORITY_MODEL,
    EMPTY_STORE_PAYLOAD,
    ENTRY_ID,
    EXPECTED_PROFILE_ID,
    FIRST_DATA_ROW,
    FOOTER_LABEL_CELL,
    FOOTER_MARKER,
    FOOTER_ROW,
    FORMULA_COLUMNS,
    FORMULA_MASK,
    FORMULA_TEMPLATES,
    HEADER_GROUP_ROW,
    HEADER_LEAF_ROW,
    HEADER_MID_ROW,
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
    SPEC_L43,
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
    html_only_keys=HTML_ONLY_ROW_KEYS,
    extra_review={
        #: 🔴 BP-8 的 route A 裁决仍是本 entry 的事实（L4-7/L4-8 未受管），从 candidate 继承登记，
        #: 防接线 L4-7/L4-8 时有人改回「取第一张」。
        #: 逐字继承自已删除的 `l4.bonds_payable.candidate.json`（lane spec task 13 的裁决产物），
        #: 外加 `status` 一键说明本契约不受管这两对。
        "bp8_sheet_granularity_collapse": {
            "status": "not_managed_in_this_contract",
            "collapsed_pairs": [
                {
                    "frontend_discriminator": "bondBranch (provide/inject, el-segmented)",
                    "sheet_keys": {
                        "bullet": "L4-7#到期一次还本付息",
                        "installment": "L4-7#分期付息到期一次还本",
                    },
                    "sheet_names": [
                        "应付债券后续计量(到期一次还本付息)L4-7",
                        "应付债券后续计量(分期付息到期一次还本)L4-7",
                    ],
                    "tail_code": "L4-7",
                },
                {
                    "frontend_discriminator": "bondBranch (synced via provide/inject from L4-7)",
                    "note": (
                        "🔴 sheet[1] 名含内部空格（'分期付息到期一次还本) L4-8'），sheet_key 不含该缺陷"
                        "（路线 A 用 bondBranch 值而非 sheet 名）。"
                    ),
                    "sheet_keys": {
                        "bullet": "L4-8#到期一次还本付息",
                        "installment": "L4-8#分期付息到期一次还本",
                    },
                    "sheet_names": [
                        "应付债券账面核对(到期一次还本付息)L4-8",
                        "应付债券账面核对(分期付息到期一次还本) L4-8",
                    ],
                    "tail_code": "L4-8",
                },
            ],
            "problem": (
                "16 权威 sheet → 13 dispatch code。L4-7 一对（后续计量）+ L4-8 一对（账面核对）同尾码。"
                "解析器对同时 endswith 的两张取第一个 → 第二版 sheet 永不可达。"
            ),
            "resolve_target_sheet_note": (
                "🔴 解析层 resolve_target_sheet 须以 strict=True 调用。L4-7/L4-8 在 strict 下返回 None"
                "（歧义），调用方必须额外带 bondBranch 参数。无歧义尾码（L4-1 等）不受影响。"
            ),
            "resolve_target_sheet_strict": True,
            "solution": "路线 A：sheet_key = 尾码#bondBranch 值（契约层区分），不改模板 sheet 名。",
            "template_rename_excluded": (
                "🔴 改名会打断既有 render schema 与 prefill 的 sheet 名匹配，须另立 spec。"
                "本契约只在契约层与解析层区分。"
            ),
        },
        "template_defects_registered": [
            "footer r18 的 T18~W18 为错位交叉公式（如 T18 `=N18+P18-R18`），期初调整列本应 SUM；"
            "只登记不改（模板运行时只读）",
        ],
    },
)
SPECS: Final[tuple[RowTableSheetSpec, ...]] = (SPEC_L43,)

EntrySelectionError = _L.LEntrySelectionError
StorePayloadError = _L.LStorePayloadError
_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


# ═══════════════════════════════════════════════════════════════════════════
# 模板 / 选型
# ═══════════════════════════════════════════════════════════════════════════


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
    """幻影码零命中 + 父码 `L4` 的 canonical resolver 落在权威模板（与 L1 同口径）。"""
    missing = sorted(wp_codes - set(resolution.by_wp_code))
    if missing:
        raise EntrySelectionError(f"缺少 wp_code {missing} 的 finder 实测结果")
    leaked = {c: [str(h) for h in hits if h] for c, hits in resolution.by_wp_code.items() if any(hits)}
    if leaked:
        raise EntrySelectionError(f"幻影码 {sorted(leaked)} 在 finder 上命中了 {leaked}")
    resolved = resolution.parent_resolved_path
    if resolved is None or Path(str(resolved)).resolve() != authoritative_template_path().resolve():
        raise EntrySelectionError(
            f"父码 {resolution.parent_code!r} 的 canonical resolver 落在 {resolved} —— "
            f"与冻结的权威模板 {TEMPLATE_RELATIVE_PATH!r} 不是同一份文件"
        )


def assert_entry_selectable(
    *,
    resolution: TemplateResolutionFacts | None = None,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    payload = manifest if manifest is not None else load_entry_manifest()
    entry = manifest_entries_by_id(payload).get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(f"冻结的 entry {ENTRY_ID!r} 不在 manifest 里")
    if str(entry.get("document_type") or "") != "xlsx" or not entry.get("independent_entry"):
        raise EntrySelectionError(f"{ENTRY_ID!r} 非独立 xlsx entry")
    profile_id = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
    if profile_id != EXPECTED_PROFILE_ID:
        raise EntrySelectionError(f"{ENTRY_ID!r} profile_id={profile_id!r} ≠ {EXPECTED_PROFILE_ID!r}")
    codes = {str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()}
    if codes != set(WP_CODES):
        raise EntrySelectionError(f"{ENTRY_ID!r} wp_code_patterns={sorted(codes)} ≠ {sorted(WP_CODES)}")
    if resolution is not None:
        assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# instrumentation / 契约（委派骨架）
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    return _L.instrumentation_specs_for(IDENTITY, SPECS)


def instrumentation_spec() -> ExcelInstrumentationSpec:
    return instrumentation_specs()[0]


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


def contract_payload_digest() -> str:
    return canonical_digest(build_contract_payload())


def dump_contract_json() -> str:
    return _L.dump_contract_json(build_contract_payload())


# ═══════════════════════════════════════════════════════════════════════════
# HTML store 载荷（行表引擎薄转发）
# ═══════════════════════════════════════════════════════════════════════════


def build_store_projection(
    payload: str | bytes | Sequence[Any], *, contract: SyncContract, limits: Any | None = None
) -> Any:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableStorePayloadError,
        build_store_projection as _engine,
    )

    try:
        return _engine(SPEC_L43, payload, contract=contract, limits=limits)
    except RowTableStorePayloadError as exc:
        raise StorePayloadError(str(exc)) from exc


def merge_projection_into_store_rows(
    *, projection: Any, base_rows: list[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    return _engine_merge(SPEC_L43, projection=projection, base_rows=base_rows)


def all_store_item_ids() -> tuple[str, ...]:
    """只登记本轮真受管的 L4-3；其余 L4 表不得预登记（会让注册门分母失真）。"""
    return (STORE_ITEM_ID,)


# ═══════════════════════════════════════════════════════════════════════════
# 发布 / 注册
# ═══════════════════════════════════════════════════════════════════════════


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


async def publish_definitions(publisher: Any) -> Phase5Definitions:
    out = await _L.publish_definitions(
        IDENTITY, SPECS, publisher, contract_payload=build_contract_payload()
    )
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
    return _L.build_matcher(IDENTITY)


def build_registration(
    *, adapter: Any, bundle: Any, descriptor: DescriptorFacts, room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return _L.build_registration(
        IDENTITY, adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract
    )


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry, *, adapter: Any, bundle: Any,
    descriptor: DescriptorFacts, room: RoomFacts, contract: SyncContract | None = None,
) -> AdapterRegistration:
    return _L.register_adapter(
        registry, IDENTITY, adapter=adapter, bundle=bundle, descriptor=descriptor, room=room,
        contract=contract,
    )


def manifest_capability_enabled(manifest: Mapping[str, Any] | None = None) -> bool:
    return _L.manifest_capability_enabled(IDENTITY, manifest=manifest)


def assert_manifest_capability_enabled(manifest: Mapping[str, Any] | None = None) -> None:
    _L.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    return await _L.resolve_published_frozen_definitions(
        IDENTITY, session=session, representation=representation, contract=contract
    )


async def attach_adapters(registry: WorkpaperSyncAdapterRegistry, *, session: Any) -> tuple[str, ...]:
    return await _L.attach_l_entry_adapter(
        registry, IDENTITY, session=session, contract_payload_builder=build_contract_payload
    )


#: 🔴 provisioning / attach 白名单只认这三个别名（缺任一即「provider 是空壳」）。
publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
