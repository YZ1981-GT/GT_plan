# -*- coding: utf-8 -*-
"""CanonicalResolutionService：config/download/callback/materialize/extract/
rematerialize/retry/rollback/history/evidence 的**唯一** artifact + bundle 解析入口。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 12
Requirements: 2.3, 2.10, 6.2, 6.10, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.8, 9.11, 9.12
Properties: P7 / P28 / P39 / P40 / P41 / P42

═══ 一、为什么「十个意图共用一个函数」是判据本身 ═══

Requirement 2.10 的原文是：这十条路径 **SHALL 通过同一 canonical resolver 返回相同
content version/representation/artifact、非空 immutable definition bundle 与
authoritative model identity**。

若每个意图各有一个解析函数（哪怕内部都调同一个 helper），「相同」这条判据就退化成
「作者记得都调」——正是既有 `wp_onlyoffice_router` 里 `_resolve_wp_file` /
`_resolve_custom_wp_file` / `find_template_file_any` 三条并列 resolver 的成因
（Task 3 清册 `multi_resolver=True` 实测 4 处）。

所以本模块只暴露 :meth:`CanonicalResolutionService.resolve`，意图作为**参数**而不是
分叉；意图只决定「允不允许」（见 :data:`INTENT_POLICY`），不决定「解析到哪」。
Property 7 的守卫因此可以对**全部十个意图**跑同一个断言：同 (content version, entry,
generation) ⇒ 逐字段相等。

═══ 二、historical 读取与 alias 的关系 ═══

`retry / rollback / history / evidence` 四个意图强制 `frozen` 模式：必须显式给出
`representation_id`，禁止走 entry pointer、禁止 alias 解析。Requirement 2.10 后半句
「历史读取不得按当前 registry alias 重组 bundle」在此落成
:class:`HistoricalResolutionError`。

`config / download / callback / materialize / extract / rematerialize` 允许按 entry
pointer 取 current，因为它们本就是「现在打开哪一版」。

═══ 三、candidate 与 incoming 的三层拒绝 ═══

同一条禁令必须在三个层面各有一道门，缺一层就有绕过路径：

1. **DB 层**：V151 的 `trg_wpses_pointer`（entry pointer 只放行 published artifact）
   与 `wpsync_check_candidate_artifact`；
2. **本模块**：:meth:`CanonicalResolutionService.resolve` 显式查 candidate 表并对
   `representation_id` 命中 candidate 的请求抛 :class:`CandidateNotResolvableError`；
3. **文件系统层**：`CanonicalArtifactRepository.assert_canonical_resolvable`
   （kind 专属禁令先行）。

本模块的那一层不是冗余：DB trigger 拦的是「写」，文件系统拦的是「kind/state」，而
「有人拿 candidate 的 id 当 representation_id 传进 resolve」只有这一层能拦 ——
candidate 与 representation 是两张表，id 空间不重叠，但**调用方拿错 id** 时若没有
这道门，就会一路走到 `representation 不存在` 的模糊报错，Requirement 5.12 要求的
error code 定位失效。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperArtifact,
    WorkpaperContentRepresentation,
    WorkpaperContentVersion,
    WorkpaperRepresentationUpgradeCandidate,
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
    WorkpaperSyncEntryState,
)
from app.services.workpaper_sync.artifacts import (
    CandidateNotResolvableError,
    CanonicalArtifactRepository,
)
from app.services.workpaper_sync.canonical_paths import assert_document_type
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleIntegrityError,
    BundleSlot,
    BundleSlotSpec,
    CandidateState,
    DefinitionState,
    SyncDomainError,
    is_digest,
)

# ═══════════════════════════════════════════════════════════════════════════
# 0. 意图与策略
# ═══════════════════════════════════════════════════════════════════════════


class ResolutionIntent(str, Enum):
    """Requirement 2.10 / 9.11 逐条列出的十个解析意图。**封闭枚举**。

    枚举值与 requirements 原文一一对应，守卫按 `set(ResolutionIntent)` 断言无遗漏 ——
    漏掉一个意图（比如某天新增 `preview` 却不登记）会让「全链统一」这条判据出现盲区。
    """

    config = "config"
    download = "download"
    callback = "callback"
    materialize = "materialize"
    extract = "extract"
    rematerialize = "rematerialize"
    retry = "retry"
    rollback = "rollback"
    history = "history"
    evidence = "evidence"


@dataclass(frozen=True)
class IntentPolicy:
    """一个意图的解析策略。

    Attributes:
        allows_current_pointer: 是否可按 entry pointer 取 current representation。
        requires_frozen_identity: 是否**必须**显式给 `representation_id`（历史读取）。
        may_hide_sheets: 是否允许对解析结果做 sheet 可见性调整（Requirement 9.12）。
            只有 `materialize`（生成 room/staged representation）为真。
    """

    allows_current_pointer: bool
    requires_frozen_identity: bool
    may_hide_sheets: bool


#: 十个意图的策略表。历史四意图强制 frozen；其余六个允许 current pointer。
INTENT_POLICY: Final[Mapping[ResolutionIntent, IntentPolicy]] = {
    ResolutionIntent.config: IntentPolicy(True, False, False),
    ResolutionIntent.download: IntentPolicy(True, False, False),
    ResolutionIntent.callback: IntentPolicy(True, False, False),
    # materialize 是唯一「生成 room/staged representation」的意图 ⇒ 唯一允许 sheet 隐藏。
    ResolutionIntent.materialize: IntentPolicy(True, False, True),
    ResolutionIntent.extract: IntentPolicy(True, False, False),
    ResolutionIntent.rematerialize: IntentPolicy(True, False, False),
    ResolutionIntent.retry: IntentPolicy(False, True, False),
    ResolutionIntent.rollback: IntentPolicy(False, True, False),
    ResolutionIntent.history: IntentPolicy(False, True, False),
    ResolutionIntent.evidence: IntentPolicy(False, True, False),
}


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常
# ═══════════════════════════════════════════════════════════════════════════


class ResolutionError(SyncDomainError):
    error_code = "canonical_resolution_failed"


class RepresentationNotFoundError(ResolutionError):
    error_code = "representation_not_found"


class EntryPointerMissingError(ResolutionError):
    """entry 还没有 current representation（还没经过一次 finalize）。"""

    error_code = "entry_pointer_missing"


class HistoricalResolutionError(ResolutionError):
    """历史意图（retry/rollback/history/evidence）没给 frozen representation identity。

    🔴 与 :class:`EntryPointerMissingError` 分成两类：前者是**调用方用法错**
    （历史读取本来就不该问「现在是哪一版」），后者是**数据状态**（这个 entry 还没
    finalize 过）。共用一个异常类型时，把 frozen 门短路掉之后 pointer 分支会抛同一
    类型，变异检验判 GREEN。
    """

    error_code = "historical_resolution_requires_frozen_identity"


class SheetVisibilityForbiddenError(ResolutionError):
    """对 published/current artifact 做 sheet 可见性改写（Requirement 9.12）。"""

    error_code = "sheet_visibility_forbidden"


class CandidateNotFinalizableError(ResolutionError):
    """candidate 缺 approved contract / authority model / bundle / compatibility。"""

    error_code = "candidate_not_finalizable"


#: candidate 不可消费的文案（提成常量，让恒抛禁令保持**单行**、可被变异检验）。
_CANDIDATE_NOT_CONSUMABLE: Final[str] = (
    "upgrade candidate {cid} 永不可用于意图 {intent}：resolver / room / download / "
    "current pointer / application substrate / evidence 全部拒绝 candidate"
    "（Requirement 6.18）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 解析结果
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class DefinitionBundleSnapshot:
    """frozen bundle 快照：id + digest + authority model + 三个 typed slot。

    **所有**字段都来自 DB row 的具体列，没有一项是「按 alias 现算」的。历史 operation
    保存这份快照的 `bundle_id + bundle_sha256` 即可复现整个 identity。
    """

    bundle_id: uuid.UUID
    bundle_sha256: str
    schema_version: str
    state: DefinitionState
    authority_model: AuthorityModel
    authority_model_definition_id: uuid.UUID
    authority_model_definition_sha256: str
    slots: Mapping[BundleSlot, BundleSlotSpec]

    @property
    def typed_slot_inventory(self) -> tuple[tuple[str, str, str], ...]:
        """`(slot, type, digest)` 三元组序列 —— 冻结进 request/operation 的最小形态。"""
        return tuple(
            (s.value, self.slots[s].slot_type, self.slots[s].slot_digest) for s in BundleSlot
        )


@dataclass(frozen=True)
class CanonicalResolution:
    """一次 canonical 解析的**完整**结果。

    Property 7 的判据就是：对同一 (content_version_id, entry_id, generation)，
    十个意图返回的本对象除 `intent` 外**逐字段相等**。
    """

    intent: ResolutionIntent
    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    content_version_id: uuid.UUID
    content_revision: int
    representation_id: uuid.UUID
    representation_generation: int
    document_type: str
    artifact_id: uuid.UUID
    artifact_sha256: str
    artifact_relative_path: str
    artifact_path: Path
    adapter_id: str
    adapter_build_digest: str
    structure_hash: str
    identity_inventory_sha256: str
    bundle: DefinitionBundleSnapshot

    def identity_tuple(self) -> tuple:
        """去掉 `intent` 与 `artifact_path`（绝对路径含机器差异）的可比较身份。"""
        return (
            self.project_id, self.wp_id, self.entry_id,
            self.content_version_id, self.content_revision,
            self.representation_id, self.representation_generation,
            self.document_type, self.artifact_id, self.artifact_sha256,
            self.artifact_relative_path,
            self.adapter_id, self.adapter_build_digest,
            self.structure_hash, self.identity_inventory_sha256,
            self.bundle.bundle_id, self.bundle.bundle_sha256,
            self.bundle.authority_model,
            self.bundle.authority_model_definition_id,
            self.bundle.authority_model_definition_sha256,
            self.bundle.typed_slot_inventory,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 服务
# ═══════════════════════════════════════════════════════════════════════════


class CanonicalResolutionService:
    """十个意图共用的解析服务。只读，不写任何行。"""

    def __init__(self, session: AsyncSession, artifacts: CanonicalArtifactRepository) -> None:
        self._session = session
        self._artifacts = artifacts

    # ─────────────────────────────────────────────────────────────────
    # 3.1 唯一入口
    # ─────────────────────────────────────────────────────────────────

    async def resolve(
        self,
        *,
        intent: ResolutionIntent | str,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        representation_id: uuid.UUID | None = None,
        expected_content_version_id: uuid.UUID | None = None,
        expected_document_type: str | None = None,
    ) -> CanonicalResolution:
        """解析 (content version + entry + representation generation) → 唯一 artifact + bundle。

        顺序刻意固定为：意图策略 → candidate 拒绝 → representation 定位 → scope 归属
        → bundle 校验 → artifact 可见性/路径安全 → 文档类型。

        每一步都在**下一步之前**失败，因此错误码总是指向真正的第一个原因。把
        「bundle 校验」挪到「artifact 路径安全」之后会让 unapproved bundle 的诊断被
        路径错误遮蔽（bundle 不合法时 artifact 往往同样缺失）。
        """
        it = intent if isinstance(intent, ResolutionIntent) else ResolutionIntent(intent)
        policy = INTENT_POLICY[it]

        # ── ① 意图策略：历史读取必须给 frozen identity ──────────────────
        #
        # 🔴 两条判据的**消息必须可区分**（2026-08-25 变异检验实测）：历史四意图同时
        # 满足 `requires_frozen_identity=True` 与 `allows_current_pointer=False`，
        # 所以把第一条短路掉之后第二条会抛**同一异常类型**把它遮蔽 ⇒ 只断言类型的守卫
        # 判 GREEN。守卫因此断言消息里含 `frozen \`representation_id\``，
        # 让「哪一条判据在起作用」可分辨。
        if policy.requires_frozen_identity and representation_id is None:
            raise HistoricalResolutionError(
                f"意图 {it.value} 是历史读取，必须显式给 frozen `representation_id`；"
                "禁止按 entry current pointer 或 registry alias 重组 bundle"
                "（Requirement 2.10）"
            )
        if representation_id is None and not policy.allows_current_pointer:
            raise HistoricalResolutionError(
                f"意图 {it.value} 不允许按 entry current pointer 解析"
            )

        # ── ② candidate 显式拒绝（第二层门；DB/文件系统各有一层）──────────
        if representation_id is not None:
            await self._assert_not_candidate_id(representation_id)

        # ── ③ representation 定位 ───────────────────────────────────────
        rep = (
            await self._load_representation(representation_id)
            if representation_id is not None
            else await self._load_current_representation(wp_id=wp_id, entry_id=entry_id)
        )

        # ── ④ scope 归属：representation 必须属于请求的 wp + entry ────────
        if rep.wp_id != wp_id or rep.entry_id != entry_id:
            raise RepresentationNotFoundError(
                f"representation {rep.id} 属于 wp={rep.wp_id} entry={rep.entry_id!r}，"
                f"与请求 wp={wp_id} entry={entry_id!r} 不符（跨 scope 解析被拒）"
            )
        version = await self._load_version(rep.content_version_id)
        if version.wp_id != wp_id:
            raise RepresentationNotFoundError(
                f"content version {version.id} 不属于 wp={wp_id}"
            )
        if (
            expected_content_version_id is not None
            and rep.content_version_id != expected_content_version_id
        ):
            raise RepresentationNotFoundError(
                f"representation {rep.id} 绑定 content version {rep.content_version_id}，"
                f"与请求的 {expected_content_version_id} 不符"
            )

        # ── ⑤ bundle：approved + 四 typed slot + child kind/state/digest ──
        bundle = await self.load_bundle_snapshot(rep.definition_bundle_id)
        if bundle.authority_model_definition_id != rep.authority_model_definition_id:
            raise BundleIntegrityError(
                "representation 的 authority model 与 frozen bundle child 不一致 —— "
                "两者必须双向锁死（design §working_paper_content_representation）"
            )
        if bundle.bundle_sha256 != (rep.definition_bundle_sha256 or "").strip():
            raise BundleIntegrityError(
                f"representation 保存的 bundle digest {rep.definition_bundle_sha256!r} "
                f"与 bundle row 的 canonical digest {bundle.bundle_sha256!r} 不一致"
            )

        # ── ⑥ artifact 可见性 + 路径安全（Property 42）────────────────────
        artifact = await self._load_artifact(rep.artifact_id)
        if artifact.project_id != project_id or artifact.wp_id != wp_id:
            raise RepresentationNotFoundError(
                f"artifact {artifact.id} 属于 project={artifact.project_id} "
                f"wp={artifact.wp_id}，与请求 scope 不符"
            )
        if (artifact.sha256 or "").strip() != (rep.artifact_sha256 or "").strip():
            raise ResolutionError(
                f"representation 的 artifact_sha256 {rep.artifact_sha256!r} 与 artifact row "
                f"{artifact.sha256!r} 不一致（内容身份漂移）"
            )
        absolute = self._artifacts.resolve_published_artifact(
            project_id=project_id,
            kind=artifact.kind,
            state=artifact.state,
            relative_path=artifact.relative_path,
        )

        # ── ⑦ 文档类型（Property 41 的 resolver 侧）─────────────────────
        declared = (expected_document_type or rep.document_type or "").strip()
        assert_document_type(absolute, declared)
        if rep.document_type != declared:
            raise ResolutionError(
                f"representation.document_type={rep.document_type!r} 与期望 {declared!r} 不符"
            )

        return CanonicalResolution(
            intent=it,
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            content_version_id=rep.content_version_id,
            content_revision=int(version.revision),
            representation_id=rep.id,
            representation_generation=int(rep.generation),
            document_type=rep.document_type,
            artifact_id=artifact.id,
            artifact_sha256=artifact.sha256,
            artifact_relative_path=artifact.relative_path,
            artifact_path=absolute,
            adapter_id=rep.adapter_id,
            adapter_build_digest=rep.adapter_build_digest,
            structure_hash=rep.structure_hash,
            identity_inventory_sha256=rep.identity_inventory_sha256,
            bundle=bundle,
        )

    # ─────────────────────────────────────────────────────────────────
    # 3.2 bundle 快照
    # ─────────────────────────────────────────────────────────────────

    async def load_bundle_snapshot(self, bundle_id: uuid.UUID) -> DefinitionBundleSnapshot:
        """读 bundle row 并逐 child 校验；只有 approved 才返回快照（Property 28）。"""
        bundle = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionBundle).where(
                    WorkpaperSyncDefinitionBundle.id == bundle_id
                )
            )
        ).scalar_one_or_none()
        if bundle is None:
            raise BundleIntegrityError(f"definition bundle 不存在: {bundle_id}")
        if bundle.state != DefinitionState.approved.value:
            raise BundleIntegrityError(
                f"definition bundle state={bundle.state}，只有 approved 可被 resolver/room 使用"
            )
        authority = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id == bundle.authority_model_definition_id
                )
            )
        ).scalar_one_or_none()
        if authority is None:
            raise BundleIntegrityError("bundle 的 authority model definition 不存在")
        if (
            authority.kind != "authority_model"
            or authority.state != DefinitionState.approved.value
        ):
            raise BundleIntegrityError(
                f"authority model child kind={authority.kind} state={authority.state} 非法"
            )
        if (authority.sha256 or "").strip() != (
            bundle.authority_model_definition_sha256 or ""
        ).strip():
            raise BundleIntegrityError("bundle 的 authority model digest 与 child 不一致")
        if not authority.authority_model_type:
            raise BundleIntegrityError("authority_model definition 缺 authority_model_type 枚举")
        try:
            am = AuthorityModel(authority.authority_model_type)
        except ValueError as exc:
            raise BundleIntegrityError(
                f"authority_model_type 未登记: {authority.authority_model_type!r}"
            ) from exc

        slots = {
            BundleSlot.template: BundleSlotSpec(
                BundleSlot.template,
                bundle.template_slot_type,
                bundle.template_slot_ref,
                bundle.template_slot_digest,
            ),
            BundleSlot.instrumentation: BundleSlotSpec(
                BundleSlot.instrumentation,
                bundle.instrumentation_slot_type,
                bundle.instrumentation_slot_ref,
                bundle.instrumentation_slot_digest,
            ),
            BundleSlot.contract: BundleSlotSpec(
                BundleSlot.contract,
                bundle.contract_slot_type,
                bundle.contract_slot_ref,
                bundle.contract_slot_digest,
            ),
        }
        # 复用 Task 12 的 canonicalizer 做 FC-1~FC-14 全量校验：resolver 侧读到的
        # bundle 与发布侧写入的 bundle 必须过**同一套**判据，否则「写得进、读不出」
        # 或反之都会出现第二真源。
        from app.services.workpaper_sync.definitions import (
            build_bundle_canonical_payload,
            canonical_digest,
        )

        payload = build_bundle_canonical_payload(
            authority_model=am,
            authority_model_definition_sha256=bundle.authority_model_definition_sha256,
            slots=slots,
        )
        recomputed = canonical_digest(payload)
        if recomputed != (bundle.canonical_payload_sha256 or "").strip():
            raise BundleIntegrityError(
                "bundle canonical digest 与 typed slots 重算结果不一致："
                f"row={bundle.canonical_payload_sha256!r} recomputed={recomputed!r}"
                "（bundle approved 后不可修改或重组）"
            )
        for slot, spec in slots.items():
            if not spec.is_definition:
                continue
            child_id = uuid.UUID(spec.slot_ref.split(":", 1)[1])
            child = (
                await self._session.execute(
                    sa.select(WorkpaperSyncDefinitionArtifact).where(
                        WorkpaperSyncDefinitionArtifact.id == child_id
                    )
                )
            ).scalar_one_or_none()
            if child is None:
                raise BundleIntegrityError(
                    f"{slot.value} slot 引用的 definition 不存在: {child_id}"
                )
            if child.kind != slot.value:
                raise BundleIntegrityError(
                    f"{slot.value} slot 引用的 definition kind={child.kind} 不符"
                )
            if child.state != DefinitionState.approved.value:
                raise BundleIntegrityError(
                    f"{slot.value} slot 的 definition child state={child.state}，"
                    "只有 approved 可用于 bundle"
                )
            if (child.sha256 or "").strip() != spec.slot_digest.strip():
                raise BundleIntegrityError(
                    f"{slot.value} slot digest 与 definition child sha256 不一致"
                )
        return DefinitionBundleSnapshot(
            bundle_id=bundle.id,
            bundle_sha256=bundle.canonical_payload_sha256,
            schema_version=bundle.schema_version,
            state=DefinitionState.approved,
            authority_model=am,
            authority_model_definition_id=authority.id,
            authority_model_definition_sha256=authority.sha256,
            slots=slots,
        )

    # ─────────────────────────────────────────────────────────────────
    # 3.3 candidate 守卫（register / finalize / 不可消费）
    # ─────────────────────────────────────────────────────────────────

    async def assert_candidate_not_consumable(
        self, *, candidate_id: uuid.UUID, intent: ResolutionIntent | str
    ) -> None:
        """恒抛：candidate 永不可被 resolver/room/download/current/substrate/evidence 使用。

        写成恒抛方法而不是「不提供该能力」的理由与 `release_quarantined()` 同源 ——
        禁令必须有可执行判据，否则变异检验无法证明它被锁住。
        """
        it = intent if isinstance(intent, ResolutionIntent) else ResolutionIntent(intent)
        # 🔴 单行 raise 是刻意的：变异检验只能整行替换，多行语句的首行被替换会破坏
        #    续行语法 ⇒ 文件级 collect ERROR ⇒ 判定退化成 WRONG-TEST。文案见常量。
        raise CandidateNotResolvableError(_CANDIDATE_NOT_CONSUMABLE.format(cid=candidate_id, intent=it.value))

    async def assert_candidate_finalizable(
        self, candidate_id: uuid.UUID
    ) -> WorkpaperRepresentationUpgradeCandidate:
        """finalize 前置：approved per-entry contract + authority model + bundle + compatibility。

        判定顺序刻意是「语义专属判据在前、状态边在后」（与
        `repository.finalize_candidate()` 同一理由）：先跑状态边时，
        `staged → finalized` 这条非法边会先抛，把「缺 approved contract/bundle」
        这条判据永久遮蔽成不可达分支。
        """
        cand = (
            await self._session.execute(
                sa.select(WorkpaperRepresentationUpgradeCandidate).where(
                    WorkpaperRepresentationUpgradeCandidate.id == candidate_id
                )
            )
        ).scalar_one_or_none()
        if cand is None:
            raise CandidateNotFinalizableError(f"upgrade candidate 不存在: {candidate_id}")
        if cand.target_contract_definition_id is None:
            raise CandidateNotFinalizableError(
                f"candidate {candidate_id} 缺 approved per-entry contract —— "
                "Task 36/60 发布 contract 后才可 finalize"
            )
        if cand.target_definition_bundle_id is None:
            raise CandidateNotFinalizableError(
                f"candidate {candidate_id} 缺 approved definition bundle"
            )
        contract = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id == cand.target_contract_definition_id
                )
            )
        ).scalar_one_or_none()
        if contract is None or contract.kind != "contract":
            raise CandidateNotFinalizableError(
                "candidate 的 target contract 不存在或 kind 不是 contract"
            )
        if contract.state != DefinitionState.approved.value:
            raise CandidateNotFinalizableError(
                f"candidate 的 per-entry contract state={contract.state}，必须 approved"
            )
        bundle = await self.load_bundle_snapshot(cand.target_definition_bundle_id)
        # compatibility：bundle 的 contract child 必须正是 candidate 声明的那一份，
        # 且 template/instrumentation child 与 upgrader 冻结的一致。
        contract_spec = bundle.slots[BundleSlot.contract]
        if not contract_spec.is_definition:
            raise CandidateNotFinalizableError(
                "candidate 的 bundle contract slot 是 typed null marker —— "
                "projection 入口不得用 marker 冒充 per-entry contract"
            )
        if uuid.UUID(contract_spec.slot_ref.split(":", 1)[1]) != contract.id:
            raise CandidateNotFinalizableError(
                "candidate 的 bundle contract child 与 target_contract_definition_id 不一致"
            )
        for slot, declared_id in (
            (BundleSlot.template, cand.template_definition_id),
            (BundleSlot.instrumentation, cand.instrumentation_definition_id),
        ):
            spec = bundle.slots[slot]
            if not spec.is_definition:
                continue
            if uuid.UUID(spec.slot_ref.split(":", 1)[1]) != declared_id:
                raise CandidateNotFinalizableError(
                    f"candidate 冻结的 {slot.value} definition 与 bundle child 不一致"
                )
        if not is_digest(cand.visible_equivalence_report_sha256 or ""):
            raise CandidateNotFinalizableError(
                f"candidate {candidate_id} 缺 visible-equivalence 反读等值报告 digest —— "
                "compatibility 未通过不得 finalize（Requirement 9.10）"
            )
        if cand.state not in (CandidateState.ready.value, CandidateState.awaiting_contract.value):
            raise CandidateNotFinalizableError(
                f"candidate state={cand.state}，只有 awaiting_contract/ready 可进入 finalize"
            )
        return cand

    async def _assert_not_candidate_id(self, candidate_or_representation_id: uuid.UUID) -> None:
        hit = (
            await self._session.execute(
                sa.select(WorkpaperRepresentationUpgradeCandidate.id).where(
                    WorkpaperRepresentationUpgradeCandidate.id
                    == candidate_or_representation_id
                )
            )
        ).scalar_one_or_none()
        if hit is not None:
            raise CandidateNotResolvableError(
                f"传入的 id {candidate_or_representation_id} 是 upgrade candidate，"
                "不是 published representation —— canonical resolver 永不解析 candidate"
            )

    # ─────────────────────────────────────────────────────────────────
    # 3.4 sheet 可见性（Requirement 9.12）
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def assert_sheet_visibility_target(
        *,
        intent: ResolutionIntent | str,
        artifact_kind: ArtifactKind | str,
        artifact_state: ArtifactState | str,
    ) -> None:
        """sheet 隐藏/显示只允许作用于 room/staged representation。

        Requirement 9.12：不得用 openpyxl **原地**修改共享 current artifact 来隐藏
        其他 sheet。判据落在 (intent, kind, state) 三元组上：

        * 只有 `materialize` 意图（生成 room/staged representation）允许；
        * artifact 必须是 `state=staged`（`.staging/` 里的本次会话产物）；
        * `published` / `durable` / `candidate` 一律拒绝。
        """
        it = intent if isinstance(intent, ResolutionIntent) else ResolutionIntent(intent)
        k = artifact_kind if isinstance(artifact_kind, ArtifactKind) else ArtifactKind(artifact_kind)
        s = (
            artifact_state
            if isinstance(artifact_state, ArtifactState)
            else ArtifactState(artifact_state)
        )
        if not INTENT_POLICY[it].may_hide_sheets:
            raise SheetVisibilityForbiddenError(
                f"意图 {it.value} 不得改写 sheet 可见性；只有 materialize（room/staged "
                "representation 生成）允许（Requirement 9.12）"
            )
        if s is not ArtifactState.staged:
            raise SheetVisibilityForbiddenError(
                f"sheet 可见性只能改写 state=staged 的 session 专用产物，实得 {s.value} —— "
                "对共享 current artifact 原地 openpyxl 改写会真实改变其他 sheet 的用户底稿"
            )
        if k is ArtifactKind.incoming:
            raise SheetVisibilityForbiddenError(
                "incoming artifact 是只读 substrate，不得改写 sheet 可见性"
            )

    # ─────────────────────────────────────────────────────────────────
    # 3.5 内部装载
    # ─────────────────────────────────────────────────────────────────

    async def _load_representation(
        self, representation_id: uuid.UUID
    ) -> WorkpaperContentRepresentation:
        rep = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation).where(
                    WorkpaperContentRepresentation.id == representation_id
                )
            )
        ).scalar_one_or_none()
        if rep is None:
            raise RepresentationNotFoundError(
                f"published representation 不存在: {representation_id}"
            )
        return rep

    async def _load_current_representation(
        self, *, wp_id: uuid.UUID, entry_id: str
    ) -> WorkpaperContentRepresentation:
        state = (
            await self._session.execute(
                sa.select(WorkpaperSyncEntryState).where(
                    WorkpaperSyncEntryState.wp_id == wp_id,
                    WorkpaperSyncEntryState.entry_id == entry_id,
                )
            )
        ).scalar_one_or_none()
        if state is None:
            raise EntryPointerMissingError(
                f"entry ({wp_id}, {entry_id!r}) 还没有 current representation pointer"
            )
        rep = await self._load_representation(state.current_representation_id)
        if int(rep.generation) != int(state.representation_generation):
            raise ResolutionError(
                f"entry pointer generation={state.representation_generation} 与 "
                f"representation.generation={rep.generation} 不一致"
            )
        return rep

    async def _load_version(self, version_id: uuid.UUID) -> WorkpaperContentVersion:
        cv = (
            await self._session.execute(
                sa.select(WorkpaperContentVersion).where(
                    WorkpaperContentVersion.id == version_id
                )
            )
        ).scalar_one_or_none()
        if cv is None:
            raise ResolutionError(f"content version 不存在: {version_id}")
        return cv

    async def _load_artifact(self, artifact_id: uuid.UUID) -> WorkpaperArtifact:
        art = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(WorkpaperArtifact.id == artifact_id)
            )
        ).scalar_one_or_none()
        if art is None:
            raise ResolutionError(f"artifact 不存在: {artifact_id}")
        return art


__all__ = [
    "ResolutionIntent", "IntentPolicy", "INTENT_POLICY",
    "ResolutionError", "RepresentationNotFoundError", "EntryPointerMissingError",
    "HistoricalResolutionError", "SheetVisibilityForbiddenError",
    "CandidateNotFinalizableError",
    "DefinitionBundleSnapshot", "CanonicalResolution", "CanonicalResolutionService",
]
