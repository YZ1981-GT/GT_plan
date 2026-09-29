# -*- coding: utf-8 -*-
"""Phase 5 共享发布编排 —— 五家 D 循环 provider 逐字相同的 22 个函数提成单一实现。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 15/16/17

═══ 为什么提取 ═══

`phase5_d1/d3/d5/d6/d7_*` 五个 provider 各自约 860-1280 行，其中发布编排段
（`Phase5Definitions` / `publish_definitions` / `attach_adapters` / `manifest_capability_enabled`
等 22 个函数/类）**逐字只换常量**（经 context-gatherer 逐函数对比确认，
D3/D5/D6/D7 四个之间完全等价，D1 只多 docstring/错误消息/1 个中间变量）。
五文件合计 ~1835 行重复。

═══ 做法 ═══

不做类继承 —— 用 **`@dataclass(frozen=True)` 配置** + **工厂函数** 返回
`types.SimpleNamespace`，各 provider 从 namespace 导出需要的名字。

registry 白名单按模块路径 `getattr(module, "attach_pilot_adapters")` 取名字 ——
只要 provider 模块上有这个名字就行，不管是本地定义还是 `from ... import`。

═══ 不动什么 ═══

* 常量（ENTRY_ID/ADAPTER_ID/TEMPLATE_SHA256 等）留在各 provider（entry 身份）
* SPEC_D*（RowTableSheetSpec 声明）留在各 provider / 各 sheet 模块
* `_rows_table_payload` / `build_contract_payload`（契约装配）留在各 provider
  （字段面是 entry 特有的）
* `build_store_projection` / `merge_projection_into_store_rows`（引擎薄转发）留在各 provider
* D1 的 combined 投影/静态通路留在 D1 provider（D3/D5/D6/D7 没有）
"""
from __future__ import annotations

import hashlib
import types
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import SyncContract
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
    InstrumentationError,
    build_instrumentation_payload,
    build_template_payload,
    normalized_structure_hash,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    DefinitionKind,
    SyncDomainError,
)

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

__all__ = ["Phase5EntryConfig", "build_orchestration"]


# ═══════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Phase5EntryConfig:
    """一个 Phase 5 entry 的身份常量表。全部 Final —— 运行时不可改。"""

    phase5_wave: str
    entry_id: str
    adapter_id: str
    wp_codes: frozenset[str]
    expected_profile_id: str
    template_relative_path: str
    template_sha256: str
    managed_sheet: str
    template_id: str
    sheet_key: str
    rows_table_key: str
    first_data_row: int
    last_data_row: int
    footer_row: int
    managed_last_col: str
    uuid_col: str
    table_name: str
    authority_model: AuthorityModel
    footer_marker: str
    store_item_id: str
    empty_store_payload: str = "[]"
    row_identity_store_key: str = "rowId"
    #: 错误码前缀（进 `EntrySelectionError.error_code`）。
    error_code_prefix: str = "sync_phase5"
    #: `build_contract_payload` 由各 provider 自己实现（字段面是 entry 特有的），
    #: 工厂只需要一个能拿到契约的 callable（用于 publish/attach）。
    build_contract_payload_fn: Any = None
    #: `load_contract_from_disk` / `assert_contract_file_matches_source` 需要契约文件路径。
    contract_file_path_fn: Any = None
    #: instrumentation spec（本 entry 基线 sheet 的，不含 expansion 声明的多 sheet）。
    instrumentation_spec_fn: Any = None


# ═══════════════════════════════════════════════════════════════════════════
# 工厂
# ═══════════════════════════════════════════════════════════════════════════


def build_orchestration(cfg: Phase5EntryConfig) -> types.SimpleNamespace:
    """根据配置构建该 entry 的全部发布编排函数，返回 namespace 供 provider 逐个导出。

    返回的 namespace 上有：
    - EntrySelectionError / StorePayloadError（类）
    - Phase5Definitions（dataclass）
    - excel_carrier_gate / authoritative_template_path / read_authoritative_template
    - TemplateResolutionFacts / assert_no_implicit_template_fallback / assert_entry_selectable
    - instrumentation_spec / template_definition_payload / instrumentation_definition_payload / authority_model_payload
    - contract_file_path / load_contract_from_disk / assert_contract_file_matches_source
    - publish_definitions / build_matcher / build_registration / register_adapter
    - resolve_published_frozen_definitions / attach_adapters
    - manifest_capability_enabled / assert_manifest_capability_enabled
    - publish_pilot_definitions / attach_pilot_adapters / PILOT_WP_CODES（别名）
    """

    # ── 错误类型（per-entry error_code）──────────────────────────────

    class EntrySelectionError(SyncDomainError):
        error_code = f"{cfg.error_code_prefix}_selection_invalid"

    class StorePayloadError(SyncDomainError):
        error_code = f"{cfg.error_code_prefix}_store_payload_invalid"

    # ── 模板 ────────────────────────────────────────────────────────

    def excel_carrier_gate() -> ExcelIdentityCarrierGate:
        return ExcelIdentityCarrierGate.load()

    def authoritative_template_path() -> Path:
        return excel_carrier_gate().assert_template_under_authority(cfg.template_relative_path)

    def read_authoritative_template() -> bytes:
        path = authoritative_template_path()
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != cfg.template_sha256:
            raise EntrySelectionError(
                f"权威模板字节已变: {cfg.template_relative_path} 实测 sha256={digest}，"
                f"冻结哨兵={cfg.template_sha256} —— `backend/wp_templates/` 运行时只读（Requirement 9.9）"
            )
        return data

    # ── 选型必要条件 ─────────────────────────────────────────────────

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
            raise EntrySelectionError(
                f"缺少 wp_code {missing} 的 finder 实测结果 —— 零回退判据不得对未观测的码放行"
            )
        leaked = {
            code: [str(item) for item in hits if item]
            for code, hits in resolution.by_wp_code.items()
            if any(hits)
        }
        if leaked:
            raise EntrySelectionError(
                f"wp_code {sorted(leaked)} 在 `wp_template_finder` 上解析到了 {leaked} —— "
                "本 canary 的零回退判据要求它们全部解析不到任何文件"
            )
        resolved = resolution.parent_resolved_path
        if resolved is None or Path(str(resolved)).resolve() != authoritative_template_path().resolve():
            raise EntrySelectionError(
                f"父码 {resolution.parent_code!r} 的 canonical resolver 落在 {resolved} —— "
                f"与冻结的权威模板 {cfg.template_relative_path!r} 不是同一份文件"
            )

    def assert_entry_selectable(
        *, resolution: TemplateResolutionFacts, manifest: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        payload = manifest if manifest is not None else load_entry_manifest()
        entries = manifest_entries_by_id(payload)
        entry = entries.get(cfg.entry_id)
        if entry is None:
            raise EntrySelectionError(
                f"冻结的 canary entry {cfg.entry_id!r} 不在 source-backed manifest 里"
            )
        if str(entry.get("document_type") or "") != "xlsx":
            raise EntrySelectionError(f"{cfg.entry_id!r} document_type 非 xlsx")
        if not entry.get("independent_entry"):
            raise EntrySelectionError(
                f"{cfg.entry_id!r} independent_entry={entry.get('independent_entry')!r} —— 重复入口不得注册"
            )
        profile_id = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
        if profile_id != cfg.expected_profile_id:
            raise EntrySelectionError(
                f"{cfg.entry_id!r} profile_id={profile_id!r} 与冻结的 {cfg.expected_profile_id!r} 不符"
            )
        codes = {str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()}
        if codes != set(cfg.wp_codes):
            raise EntrySelectionError(
                f"{cfg.entry_id!r} wp_code_patterns={sorted(codes)} 与冻结的 {sorted(cfg.wp_codes)} 不一致"
            )
        assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))
        return entry

    # ── instrumentation & definition payloads ────────────────────────

    def instrumentation_spec() -> ExcelInstrumentationSpec:
        if cfg.instrumentation_spec_fn is not None:
            return cfg.instrumentation_spec_fn()
        return ExcelInstrumentationSpec(
            entry_id=cfg.entry_id,
            template_id=cfg.template_id,
            template_relative_path=cfg.template_relative_path,
            managed_sheet=cfg.managed_sheet,
            first_data_row=cfg.first_data_row,
            last_data_row=cfg.last_data_row,
            footer_row=cfg.footer_row,
            managed_last_col=cfg.managed_last_col,
            uuid_col=cfg.uuid_col,
            table_name=cfg.table_name,
        )

    def template_definition_payload() -> dict[str, Any]:
        data = read_authoritative_template()
        return build_template_payload(
            spec=instrumentation_spec(),
            template_sha256=cfg.template_sha256,
            structure_hash=normalized_structure_hash(data),
        )

    def instrumentation_definition_payload() -> dict[str, Any]:
        return build_instrumentation_payload(
            spec=instrumentation_spec(),
            template_definition_sha256=canonical_digest(template_definition_payload()),
            template_sha256=cfg.template_sha256,
            gate=excel_carrier_gate(),
        )

    def authority_model_payload() -> dict[str, Any]:
        return {
            "schema_version": "authority-model-definition:v1",
            "authority_model": cfg.authority_model.value,
            "content_authority": "structured_projection",
            "merge_model": "stable_field_three_way",
            "required_slots": [
                BundleSlot.template.value,
                BundleSlot.instrumentation.value,
                BundleSlot.contract.value,
            ],
            "entry_id": cfg.entry_id,
            "pilot_class": cfg.phase5_wave,
        }

    # ── 契约文件 ────────────────────────────────────────────────────

    def contract_file_path() -> Path:
        if cfg.contract_file_path_fn is not None:
            return cfg.contract_file_path_fn()
        return _BACKEND_ROOT / f"backend/data/workpaper_sync_contracts/{cfg.adapter_id}.json"

    def load_contract_from_disk() -> SyncContract:
        from app.services.workpaper_sync.contracts import load_contract
        return load_contract(cfg.adapter_id)

    def assert_contract_file_matches_source() -> SyncContract:
        if cfg.build_contract_payload_fn is None:
            return load_contract_from_disk()
        from app.services.workpaper_sync.contracts import parse_contract
        disk = load_contract_from_disk()
        source = parse_contract(cfg.build_contract_payload_fn(), adapter_id=cfg.adapter_id)
        if disk.canonical_sha256 != source.canonical_sha256:
            raise EntrySelectionError(
                f"磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
                f"disk={disk.canonical_sha256} source={source.canonical_sha256}；"
                f"请运行 `generate_phase5_{cfg.phase5_wave.removeprefix('phase5_')}_contract.py --apply`"
            )
        return disk

    # ── Phase5Definitions & publish ──────────────────────────────────

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
                "entry_id": cfg.entry_id,
                "adapter_id": cfg.adapter_id,
                "authority_model": cfg.authority_model.value,
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
        contract = assert_contract_file_matches_source()
        authority = await publisher.publish_definition(
            kind=DefinitionKind.authority_model,
            payload=authority_model_payload(),
            logical_id=f"{cfg.adapter_id}.authority-model",
            semantic_version="1.0.0",
        )
        tp = template_definition_payload()
        template = await publisher.publish_definition(
            kind=DefinitionKind.template,
            payload=tp,
            logical_id=f"{cfg.adapter_id}.template",
            semantic_version="1.0.0",
            blob_bytes=read_authoritative_template(),
            structure_hash=tp["normalized_structure_hash"],
        )
        instr = await publisher.publish_definition(
            kind=DefinitionKind.instrumentation,
            payload=instrumentation_definition_payload(),
            logical_id=f"{cfg.adapter_id}.instrumentation",
            semantic_version="1.0.0",
        )
        contract_def = await publisher.publish_definition(
            kind=DefinitionKind.contract,
            payload=dict(contract.canonical_payload),
            logical_id=cfg.adapter_id,
            semantic_version=contract.semantic_version,
        )
        if template.sha256 != contract.template_definition_sha256:
            raise EntrySelectionError(
                f"已发布 template digest {template.sha256} 与契约声明 "
                f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
            )
        if instr.sha256 != contract.instrumentation_definition_sha256:
            raise EntrySelectionError(
                f"已发布 instrumentation digest {instr.sha256} 与契约声明 "
                f"{contract.instrumentation_definition_sha256} 不一致 —— 单向引用断裂"
            )
        bundle = await publisher.publish_bundle(
            authority_model_definition_id=authority.definition_id,
            authority_model=cfg.authority_model,
            authority_model_definition_sha256=authority.sha256,
            slots={
                BundleSlot.template: {
                    "type": "definition",
                    "ref": f"definition:{template.definition_id}",
                    "digest": template.sha256,
                },
                BundleSlot.instrumentation: {
                    "type": "definition",
                    "ref": f"definition:{instr.definition_id}",
                    "digest": instr.sha256,
                },
                BundleSlot.contract: {
                    "type": "definition",
                    "ref": f"definition:{contract_def.definition_id}",
                    "digest": contract_def.sha256,
                },
            },
        )
        return Phase5Definitions(
            authority_model_definition_id=authority.definition_id,
            authority_model_definition_sha256=authority.sha256,
            template_definition_id=template.definition_id,
            template_definition_sha256=template.sha256,
            instrumentation_definition_id=instr.definition_id,
            instrumentation_definition_sha256=instr.sha256,
            contract_definition_id=contract_def.definition_id,
            contract_definition_sha256=contract_def.sha256,
            bundle_id=bundle.bundle_id,
            bundle_sha256=bundle.canonical_sha256,
        )

    # ── adapter 注册 ─────────────────────────────────────────────────

    def build_matcher() -> EntryMatcher:
        return EntryMatcher(document_type="xlsx", wp_codes=cfg.wp_codes)

    def build_registration(
        *, adapter: Any, bundle: Any, descriptor: DescriptorFacts,
        room: RoomFacts, contract: SyncContract | None = None,
    ) -> AdapterRegistration:
        return AdapterRegistration(
            adapter=adapter, entry_id=cfg.entry_id, matcher=build_matcher(),
            bundle=bundle, descriptor=descriptor, room=room,
            declared_capability=Capability.bidirectional,
            contract=contract if contract is not None else load_contract_from_disk(),
        )

    def register_adapter(
        registry: WorkpaperSyncAdapterRegistry, *, adapter: Any, bundle: Any,
        descriptor: DescriptorFacts, room: RoomFacts, contract: SyncContract | None = None,
    ) -> AdapterRegistration:
        registration = build_registration(
            adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract
        )
        registry.register(registration)
        return registration

    async def resolve_published_frozen_definitions(
        *, session: Any, representation: Any, contract: SyncContract
    ) -> Any:
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
            correlation_id=f"{cfg.adapter_id}@{getattr(representation, 'id', None)}",
        )
        if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
            raise EntrySelectionError(
                f"entry {cfg.entry_id}: 观测器读出的契约 digest "
                f"{observation.definitions.contract.canonical_sha256} 与本模块 source-locked 的 "
                f"{contract.canonical_sha256} 不一致 —— 冻结身份与生产契约脱钩"
            )
        return observation

    async def attach_adapters(
        registry: WorkpaperSyncAdapterRegistry, *, session: Any
    ) -> tuple[str, ...]:
        if cfg.adapter_id in {reg.adapter_id for reg in registry.registrations()}:
            return ()
        if not manifest_capability_enabled():
            return ()

        import sqlalchemy as sa
        from app.models.workpaper_sync_models import WorkpaperContentRepresentation
        from app.services.workpaper_sync.projection_target_resolution import (
            resolve_visible_current_representation_id,
        )
        from app.services.workpaper_sync import entry_source_facts as facts
        from app.services.workpaper_sync.adapters.excel import build_excel_adapter
        from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
        from app.services.workpaper_sync.resolution import CanonicalResolutionService

        representation_id = await resolve_visible_current_representation_id(
            session, entry_id=cfg.entry_id
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
        entry = manifest_entries_by_id(load_entry_manifest())[cfg.entry_id]
        descriptor = facts.observe_descriptor_facts(entry)
        if descriptor is None:
            raise EntrySelectionError(
                f"entry {cfg.entry_id} 的宿主实测不可达（产不出 descriptor 事实）—— "
                "不可达入口不得注册 adapter"
            )
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
        return (cfg.adapter_id,)

    # ── manifest capability ──────────────────────────────────────────

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
        )[cfg.entry_id]
        capability = capability_of(entry)
        if capability is not Capability.bidirectional:
            raise EntrySelectionError(
                f"entry {cfg.entry_id} 的 manifest capability={capability.value} —— "
                "注册 bidirectional adapter 前必须先由 reviewed overlay 裁决为 bidirectional 并重生成 manifest"
            )
        if str(entry.get("adapter_id") or "") != cfg.adapter_id:
            raise EntrySelectionError(
                f"entry {cfg.entry_id} 的 manifest adapter_id={entry.get('adapter_id')!r} "
                f"与本 canary 的 {cfg.adapter_id!r} 不符"
            )

    def _unused_instrumentation_error_guard() -> type[InstrumentationError]:
        return InstrumentationError

    # ── 组装 namespace ───────────────────────────────────────────────

    ns = types.SimpleNamespace(
        # 类型
        EntrySelectionError=EntrySelectionError,
        StorePayloadError=StorePayloadError,
        Phase5Definitions=Phase5Definitions,
        TemplateResolutionFacts=TemplateResolutionFacts,
        # 模板
        excel_carrier_gate=excel_carrier_gate,
        authoritative_template_path=authoritative_template_path,
        read_authoritative_template=read_authoritative_template,
        # 选型
        assert_no_implicit_template_fallback=assert_no_implicit_template_fallback,
        assert_entry_selectable=assert_entry_selectable,
        # instrumentation & payloads
        instrumentation_spec=instrumentation_spec,
        template_definition_payload=template_definition_payload,
        instrumentation_definition_payload=instrumentation_definition_payload,
        authority_model_payload=authority_model_payload,
        # 契约
        contract_file_path=contract_file_path,
        load_contract_from_disk=load_contract_from_disk,
        assert_contract_file_matches_source=assert_contract_file_matches_source,
        # 发布
        publish_definitions=publish_definitions,
        # 注册
        build_matcher=build_matcher,
        build_registration=build_registration,
        register_adapter=register_adapter,
        resolve_published_frozen_definitions=resolve_published_frozen_definitions,
        attach_adapters=attach_adapters,
        # manifest
        manifest_capability_enabled=manifest_capability_enabled,
        assert_manifest_capability_enabled=assert_manifest_capability_enabled,
        # guard
        _unused_instrumentation_error_guard=_unused_instrumentation_error_guard,
        # 别名（registry 白名单读的名字）
        publish_pilot_definitions=publish_definitions,
        attach_pilot_adapters=attach_adapters,
        PILOT_WP_CODES=cfg.wp_codes,
    )
    return ns
