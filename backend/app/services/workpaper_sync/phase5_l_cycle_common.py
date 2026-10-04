# -*- coding: utf-8 -*-
"""L 循环（筹资/债务）8 条 entry 的 provider 公共骨架。

spec: `l-cycle-true-adapter-registration` · Task 11（LR-P11 邻域）

═══ 为什么本模块存在，以及为什么它**很薄** ═══

L 域出现第二条 entry 之前必须先抽共性（tasks.md task 11），否则 8 份 provider 各抄一遍
七段流程。对标 `phase5_h_cycle_common.py` —— 但🔴 **不复制它**：现算（2026-10-01 探针）
H 骨架的纯装配段在 L1 上**逐字节**复现 L1 既有产出：

| 段 | 结论 |
|---|---|
| `template_definition_payload` | canonical digest 相同 |
| `instrumentation_definition_payload` | digest 相同（H 填 `sheet_key`、L1 原留 None，**不进 payload**） |
| `sheets_payload` | 与 L1 契约 `sheets` 逐值相等 |

⇒ 这些段由本模块**委派**给 H 骨架（它们只按属性名读 identity，是 duck-typed 的），
再抄一份就是第二个漂移面。本模块只拥有 L 与 H **真不同**的部分：

1. **契约 `review` 段形态** —— L 的 html_store 是单 item（`item_id` + `row_identity_key` +
   `html_only_keys`），且可声明 `derived_readonly_sheet`（如 `审定表L1-1` 全公式只读投影）；
   H 是 `item_ids` 列表 + `payload_column*` + `tb_publish_gate`。
2. **`identity_carriers`** —— L1 册零 definedName，声明 3 载体（无 `defined_name`）；
   H 固定 4 载体。按 entry 声明，默认取 L1 的 3 载体。
3. **manifest 门的口径** —— L1 要求 manifest 的 `adapter_id` **必须等于**本 provider
   （H 版允许空串）；保持 L1 既有语义不放宽。
4. **错误类型** —— L 自己的 `LEntrySelectionError`，错误码前缀 `sync_phase5_l_`。
5. **五环 `publish_definitions`** —— H 骨架无此段，从 L1 原样上提。

🔴 本模块不含任何 wp_code / sheet 名 / 键名字面量 —— 全部经 :class:`LEntryIdentity` 传入。
🔴 回迁判据：L1 回迁到本模块前后，`build_contract_payload()` 的 canonical digest 必须不变
（守卫 `test_l_cycle_common.py`），否则就是改了已发布契约。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h_cycle_common as _H
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION,
    SyncContract,
    load_contract,
    parse_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import (
    Capability,
    DescriptorFacts,
    RoomFacts,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    ExcelInstrumentationSpec,
    build_template_payload,
    normalized_structure_hash,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    DefinitionKind,
    SyncDomainError,
)

__all__ = [
    "LEntrySelectionError",
    "LStorePayloadError",
    "LEntryIdentity",
    "L_AUTHORITY_ROOT",
    "L_DEFAULT_IDENTITY_CARRIERS",
    "excel_carrier_gate",
    "authoritative_template_path",
    "read_authoritative_template",
    "instrumentation_specs_for",
    "template_definition_payload",
    "instrumentation_definition_payload",
    "authority_model_payload",
    "build_contract_payload",
    "assert_contract_file_matches_source",
    "dump_contract_json",
    "manifest_capability_enabled",
    "assert_manifest_capability_enabled",
    "build_matcher",
    "build_registration",
    "register_adapter",
    "resolve_published_frozen_definitions",
    "publish_definitions",
    "attach_l_entry_adapter",
]


class LEntrySelectionError(SyncDomainError):
    """L 循环 entry 的选型必要条件不成立（模板字节 / manifest 事实 / 契约锁）。"""

    error_code = "sync_phase5_l_selection_invalid"


class LStorePayloadError(SyncDomainError):
    """L 循环 HTML store 载荷形态不合法。"""

    error_code = "sync_phase5_l_store_payload_invalid"


L_AUTHORITY_ROOT: Final[str] = "backend/wp_templates"

#: L1 实测：册内零 definedName ⇒ 不声明 `defined_name`；`hidden_sheet` 由 `_GT_SYNC` 注入。
L_DEFAULT_IDENTITY_CARRIERS: Final[tuple[str, ...]] = (
    "hidden_sheet",
    "excel_table",
    "hidden_uuid_column",
)

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_GENERATOR_HINT: Final[str] = (
    "请用 `& d:/GT_plan/.venv/Scripts/python.exe "
    "backend/scripts/gen/generate_phase5_l_contracts.py --apply` 重生成"
)


@dataclass(frozen=True)
class LEntryIdentity:
    """一条 L entry 的冻结身份（属性名与 `HEntryIdentity` 对齐 ⇒ 可直接喂 H 骨架的装配段）。

    :param wp_codes: manifest 冻结的**幻影码**（matcher 域，FC-2）。
    :param primary_store_item_id: 契约 `review.html_store.item_id`（L 是单 item 形态）。
    :param row_identity_store_key: 行对象里承载稳定身份的键（如 `rowId`）。
    :param html_only_keys: 前端有、模板无、**不入契约**的行键（登记原因见 html_store_note）。
    :param derived_readonly_sheet: 只读投影 sheet 的声明（`{excel_name, reason}`）；无则 None。
    """

    entry_id: str
    adapter_id: str
    phase5_wave: str
    wp_codes: frozenset[str]
    template_relative_path: str
    template_sha256: str
    primary_store_item_id: str
    row_identity_store_key: str
    html_store_note: str
    reviewed_basis: str
    authority_model: AuthorityModel = AuthorityModel.projection_contract
    expected_profile_id: str = "xlsx.editable.shared.single.room_service_wired.v1"
    identity_carriers: tuple[str, ...] = L_DEFAULT_IDENTITY_CARRIERS
    html_only_keys: tuple[str, ...] = ()
    derived_readonly_sheet: Mapping[str, str] | None = None
    #: 契约 `review` 段的额外键（追加在既有键之后，不得覆盖既有键）。
    extra_review: Mapping[str, Any] = dc_field(default_factory=dict)

    @property
    def template_file_name(self) -> str:
        return self.template_relative_path.rsplit("/", 1)[-1]


# ═══════════════════════════════════════════════════════════════════════════
# 模板 / instrumentation（装配委派 H 骨架；读字节用 L 自己的错误类型）
# ═══════════════════════════════════════════════════════════════════════════


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    return ExcelIdentityCarrierGate.load()


def authoritative_template_path(identity: LEntryIdentity) -> Path:
    return excel_carrier_gate().assert_template_under_authority(identity.template_relative_path)


def read_authoritative_template(identity: LEntryIdentity) -> bytes:
    data = authoritative_template_path(identity).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != identity.template_sha256:
        raise LEntrySelectionError(
            f"权威模板字节已变: {identity.template_relative_path} 实测 sha256={digest}，"
            f"冻结哨兵={identity.template_sha256} —— `backend/wp_templates/` 运行时只读"
        )
    return data


def instrumentation_specs_for(
    identity: LEntryIdentity, specs: Sequence[Any]
) -> tuple[ExcelInstrumentationSpec, ...]:
    return _H.instrumentation_specs_for(identity, specs)  # type: ignore[arg-type]


def template_definition_payload(identity: LEntryIdentity, specs: Sequence[Any]) -> dict[str, Any]:
    """与 H 同算法，但模板字节经本模块读（错误类型是 L 的）。"""
    if not specs:
        raise LEntrySelectionError(f"{identity.entry_id} 当前无受管 sheet")
    data = read_authoritative_template(identity)
    return build_template_payload(
        spec=instrumentation_specs_for(identity, specs)[0],
        template_sha256=identity.template_sha256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload(
    identity: LEntryIdentity, specs: Sequence[Any]
) -> dict[str, Any]:
    from app.services.workpaper_sync.excel_instrumentation import (
        build_instrumentation_payload_for_sheets,
    )

    return build_instrumentation_payload_for_sheets(
        specs=instrumentation_specs_for(identity, specs),
        template_definition_sha256=canonical_digest(template_definition_payload(identity, specs)),
        template_sha256=identity.template_sha256,
        gate=excel_carrier_gate(),
    )


def authority_model_payload(identity: LEntryIdentity) -> dict[str, Any]:
    return {
        "schema_version": "authority-model-definition:v1",
        "authority_model": identity.authority_model.value,
        "content_authority": "structured_projection",
        "merge_model": "stable_field_three_way",
        "required_slots": [
            BundleSlot.template.value,
            BundleSlot.instrumentation.value,
            BundleSlot.contract.value,
        ],
        "entry_id": identity.entry_id,
        "pilot_class": identity.phase5_wave,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 契约装配（L 独有的 review 形态）
# ═══════════════════════════════════════════════════════════════════════════


def build_contract_payload(identity: LEntryIdentity, specs: Sequence[Any]) -> dict[str, Any]:
    template_payload = template_definition_payload(identity, specs)
    sheets = _H.sheets_payload(specs)
    if not sheets:
        raise LEntrySelectionError(f"{identity.entry_id} 当前无受管 sheet")
    html_store: dict[str, Any] = {
        "table": "checklist_responses",
        "item_id": identity.primary_store_item_id,
        "row_identity_key": identity.row_identity_store_key,
        "shape": "json_array_of_row_objects",
        "html_only_keys": list(identity.html_only_keys),
        "note": identity.html_store_note,
    }
    review: dict[str, Any] = {
        "entry_id": identity.entry_id,
        "pilot_class": identity.phase5_wave,
        "authority_root": L_AUTHORITY_ROOT,
        "html_store": html_store,
    }
    if identity.derived_readonly_sheet is not None:
        review["derived_readonly_sheet"] = dict(identity.derived_readonly_sheet)
    review["reviewed_basis"] = identity.reviewed_basis
    clash = sorted(set(identity.extra_review) & set(review))
    if clash:
        raise LEntrySelectionError(f"extra_review 不得覆盖既有 review 键：{clash}")
    review.update(dict(identity.extra_review))
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": identity.adapter_id,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": canonical_digest(template_payload),
        "instrumentation_definition_sha256": canonical_digest(
            instrumentation_definition_payload(identity, specs)
        ),
        "template": {
            "relative_path": identity.template_relative_path,
            "template_sha256": identity.template_sha256,
            "normalized_structure_hash": template_payload["normalized_structure_hash"],
        },
        "identity_carriers": list(identity.identity_carriers),
        "sheets": sheets,
        "review": review,
    }


def assert_contract_file_matches_source(
    identity: LEntryIdentity, expected: Mapping[str, Any]
) -> SyncContract:
    on_disk = load_contract(identity.adapter_id)
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise LEntrySelectionError(
            "磁盘 per-entry contract 与 provider 现算 payload 不一致 —— "
            f"disk={canonical_digest(on_disk.canonical_payload)} "
            f"source={canonical_digest(expected)}；{_GENERATOR_HINT}"
        )
    parse_contract(dict(expected), adapter_id=identity.adapter_id)
    return on_disk


def dump_contract_json(payload: Mapping[str, Any]) -> str:
    """生成器落盘文本（2 空格缩进 + 排序键 + 尾换行，与既有契约文件同形态）。"""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# ═══════════════════════════════════════════════════════════════════════════
# manifest 门 / matcher / 注册
# ═══════════════════════════════════════════════════════════════════════════


def manifest_capability_enabled(
    identity: LEntryIdentity, *, manifest: Mapping[str, Any] | None = None
) -> bool:
    """🔴 比 H 严：manifest 的 adapter_id **必须等于**本 provider（空串也不放行）。"""
    payload = manifest if manifest is not None else load_entry_manifest()
    entry = manifest_entries_by_id(payload).get(identity.entry_id)
    if entry is None:
        return False
    if str(entry.get("capability") or "") != Capability.bidirectional.value:
        return False
    return str(entry.get("adapter_id") or "") == identity.adapter_id


def assert_manifest_capability_enabled(
    identity: LEntryIdentity, *, manifest: Mapping[str, Any] | None = None
) -> None:
    if not manifest_capability_enabled(identity, manifest=manifest):
        raise LEntrySelectionError(
            f"manifest 尚未把 {identity.entry_id!r} 裁决成 bidirectional + "
            f"adapter_id={identity.adapter_id!r} —— 发布链第⑤环走完后须重生成 manifest 再注册"
        )


def build_matcher(identity: LEntryIdentity) -> EntryMatcher:
    return EntryMatcher(document_type="xlsx", wp_codes=frozenset(identity.wp_codes))


def build_registration(
    identity: LEntryIdentity,
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return AdapterRegistration(
        adapter=adapter,
        entry_id=identity.entry_id,
        matcher=build_matcher(identity),
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        declared_capability=Capability.bidirectional,
        contract=contract if contract is not None else load_contract(identity.adapter_id),
    )


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    identity: LEntryIdentity,
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    registration = build_registration(
        identity, adapter=adapter, bundle=bundle, descriptor=descriptor, room=room,
        contract=contract,
    )
    registry.register(registration)
    return registration


async def resolve_published_frozen_definitions(
    identity: LEntryIdentity, *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    try:
        return await _H.resolve_published_frozen_definitions(
            identity,  # type: ignore[arg-type]
            session=session, representation=representation, contract=contract,
        )
    except _H.HEntrySelectionError as exc:
        raise LEntrySelectionError(str(exc)) from exc


# ═══════════════════════════════════════════════════════════════════════════
# 五环发布 + attach
# ═══════════════════════════════════════════════════════════════════════════


async def publish_definitions(
    identity: LEntryIdentity,
    specs: Sequence[Any],
    publisher: Any,
    *,
    contract_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """template → instrumentation → contract → bundle（顺序不可颠倒）。返回各段 id/digest。"""
    contract = assert_contract_file_matches_source(identity, contract_payload)
    aid = identity.adapter_id
    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=authority_model_payload(identity),
        logical_id=f"{aid}.authority-model",
        semantic_version="1.0.0",
    )
    template_payload = template_definition_payload(identity, specs)
    template = await publisher.publish_definition(
        kind=DefinitionKind.template,
        payload=template_payload,
        logical_id=f"{aid}.template",
        semantic_version="1.0.0",
        blob_bytes=read_authoritative_template(identity),
        structure_hash=template_payload["normalized_structure_hash"],
    )
    instrumentation = await publisher.publish_definition(
        kind=DefinitionKind.instrumentation,
        payload=instrumentation_definition_payload(identity, specs),
        logical_id=f"{aid}.instrumentation",
        semantic_version="1.0.0",
    )
    contract_definition = await publisher.publish_definition(
        kind=DefinitionKind.contract,
        payload=dict(contract.canonical_payload),
        logical_id=aid,
        semantic_version=contract.semantic_version,
    )
    if template.sha256 != contract.template_definition_sha256:
        raise LEntrySelectionError(
            f"已发布 template digest {template.sha256} 与契约声明 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        raise LEntrySelectionError(
            f"已发布 instrumentation digest {instrumentation.sha256} 与契约声明 "
            f"{contract.instrumentation_definition_sha256} 不一致 —— 单向引用断裂"
        )

    def _slot(defn: Any) -> dict[str, str]:
        return {"type": "definition", "ref": f"definition:{defn.definition_id}", "digest": defn.sha256}

    bundle = await publisher.publish_bundle(
        authority_model_definition_id=authority.definition_id,
        authority_model=identity.authority_model,
        authority_model_definition_sha256=authority.sha256,
        slots={
            BundleSlot.template: _slot(template),
            BundleSlot.instrumentation: _slot(instrumentation),
            BundleSlot.contract: _slot(contract_definition),
        },
    )
    return {
        "authority": authority,
        "template": template,
        "instrumentation": instrumentation,
        "contract": contract_definition,
        "bundle": bundle,
    }


async def attach_l_entry_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    identity: LEntryIdentity,
    *,
    session: Any,
    contract_payload_builder: Any,
) -> tuple[str, ...]:
    """三道前置缺一即返回空元组（启动期 attach 对「还没供给」必须容忍，不伪造通过）。"""
    if identity.adapter_id in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled(identity):
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import WorkpaperContentRepresentation
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    representation_id = await resolve_visible_current_representation_id(
        session, entry_id=identity.entry_id
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

    resolution = CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND_ROOT))
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = assert_contract_file_matches_source(identity, contract_payload_builder())
    entry = manifest_entries_by_id(load_entry_manifest())[identity.entry_id]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise LEntrySelectionError(
            f"entry {identity.entry_id} 的宿主实测不可达（产不出 descriptor 事实）—— "
            "不可达入口不得注册 adapter"
        )
    observation = await resolve_published_frozen_definitions(
        identity, session=session, representation=representation, contract=contract
    )
    register_adapter(
        registry,
        identity,
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
    return (identity.adapter_id,)
