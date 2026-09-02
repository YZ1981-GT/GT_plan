# -*- coding: utf-8 -*-
"""RepresentationService：**纯表示升级**的唯一 finalize 边界（不碰 business revision）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 15
Requirements: 2.1, 2.3, 3.6, 6.18, 8.12
Properties: P4（业务版本与 representation generation 正交）/ P5（无悬空可见态）/
P67（upgrader 先 candidate、approved bundle 后 finalize）

═══ 一、为什么它必须与 `ContentMutationService` 分成两个服务 ═══

一次**业务内容应用**与一次**纯定义升级**是两种操作，revision 语义相反：

* 业务应用：`content_revision + 1`，新 content version，新 representation generation；
* 定义升级：`content_revision` **不变**，复用既有 content version，只新增 generation。

把两者写进同一个 `commit()` 再用一个 `is_definition_upgrade` 布尔开关分叉，是本平台
反复吃到的假绿形态：开关默认值一改、或某个调用方漏传，纯表示升级就会推进业务版本，
而「Property 4 全绿」——因为守卫测的是同一个函数、同一条路径。

所以这里是**两个类、两条路径**，且本类拿到的仓储是
:class:`RevisionLockedRepository`（见 `content_mutation.py`）：`bump_content_revision` /
`set_current_content_version` / `create_content_version` 在**构造上**不可达 —— 不是
「注释里禁止」，而是调用即 :class:`~app.services.workpaper_sync.content_mutation.RevisionBumpForbiddenError`。
变异检验 M21 往本模块注入一次 `bump_content_revision(...)`、M23 注入一次
`set_current_content_version(...)`，两条都打红 —— 门面挡的不只是一个方法名，
「纯表示升级不推进 business revision」这条否定式承诺因此可 falsify。

═══ 二、finalize 的五道门都在别处，本模块只负责「按序调用 + 单事务落地」═══

Task 12 已经把判据做完了，本模块**不重写**任何一条：

1. `CanonicalResolutionService.assert_candidate_finalizable()` —— approved per-entry
   contract + approved bundle + authority model + candidate/bundle child compatibility
   + visible-equivalence 报告 + candidate state ∈ {awaiting_contract, ready}；
2. `definitions.assert_publish_order()` —— `template → instrumentation → contract →
   bundle → representation` 的偏序；
3. `repository.create_representation()` → `assert_bundle_usable()` —— typed slots、
   child kind/state/digest、`projection_contract` 三 child 必须 approved 非空；
4. `repository.finalize_candidate()` —— 语义门在前、状态边在后（Task 12 实测过顺序反了
   会把「缺 bundle」永久遮蔽成不可达分支）；
5. V151 的 `trg_wpruc_guard` / `trg_wpcr_identity` / `trg_wpses_pointer` —— DB 层第二道锁，
   其中 `trg_wpruc_guard` 直接锁死「finalize 出的 representation 必须绑定**同一**
   content version」。

本模块新增的只有第 6 条：**candidate 的 staged artifact 必须先物理 publish 成
canonical artifact**，且 publish 前后各校验一次 digest（复用 Task 11 的
`finalize_candidate_artifact`，它刻意是**复制而不是移动** —— candidate 行仍要能作为
rollback target 存在）。

═══ 三、失败语义：原 pointer/revision 不变，留下 non-current candidate/orphan ═══

任一步失败 ⇒ 整个事务回滚 ⇒ entry pointer 仍指旧 generation、`content_revision` 不变、
已 publish 的 canonical 文件成为**无引用 orphan**（由 Task 11 的 reconciliation 收），
candidate 仍是 non-current。这条是 Requirement 9.10 / Property 5 的原文，且**只能**在
真库上证明：`backend/tests/workpaper_sync/test_task15_content_mutation_pg.py`
的 `TestRepresentationFinalizeIsAdditiveOnly` 前后各拍一次快照逐列比对。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventType
from app.models.workpaper_sync_models import (
    WorkpaperContentRepresentation,
    WorkpaperRepresentationUpgradeCandidate,
    WorkpaperSyncEntryState,
)
from app.services.workpaper_sync.artifacts import (
    CanonicalArtifactRepository,
    StagedCandidate,
)
from app.services.workpaper_sync.definitions import PublishStage, assert_publish_order
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    BundleSlot,
    DefinitionState,
    SyncDomainError,
    is_digest,
)
from app.services.workpaper_sync.outbox import DurableEventOutboxService, PendingPublication
from app.services.workpaper_sync.repository import WorkpaperSyncRepository
from app.services.workpaper_sync.resolution import (
    CanonicalResolutionService,
    DefinitionBundleSnapshot,
)

__all__ = [
    "RepresentationError",
    "RepresentationBundleError",
    "RepresentationSlotError",
    "RepresentationFinalizeOutcome",
    "RepresentationService",
    "next_representation_generation",
    "assert_bundle_snapshot_finalizable",
    "REPRESENTATION_FINALIZE_STEPS",
]


# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常（每条拒绝原因一个类型 —— 共用类型会让短路变异被互相遮蔽）
# ═══════════════════════════════════════════════════════════════════════════


class RepresentationError(SyncDomainError):
    error_code = "representation_finalize_failed"


class RepresentationBundleError(RepresentationError):
    """bundle 未 approved / authority model 缺失（immutable definition bundle 本体问题）。"""

    error_code = "representation_bundle_not_approved"


class RepresentationSlotError(RepresentationError):
    """typed slot 缺失、SQL NULL、空串或全零 hash（slot **形态**问题）。

    🔴 与 :class:`RepresentationBundleError` 分成两类是刻意的：Requirement 2.3 把
    「bundle 未 approved」与「slot omission/NULL/空串/全零 hash」列成两条独立禁令。
    共用一个异常类型时，短路掉 slot 形态判据后 approved 判据会顶上来把它遮蔽 ——
    Task 12/13/14 连续三次实测过这个 GREEN 形态。
    """

    error_code = "representation_bundle_slot_invalid"


class RepresentationPointerError(RepresentationError):
    """entry pointer 目标不属于本 candidate 的 scope / 不是新建 generation。"""

    error_code = "representation_pointer_invalid"


#: finalize 事务内必须留下痕迹的步骤。缺任一步都说明有人把写入移出了事务
#: （或删掉了它），由 `_TransactionWitness` 判 :class:`TransactionStepMissingError`。
REPRESENTATION_FINALIZE_STEPS: tuple[str, ...] = (
    "candidate_lock",
    "representation",
    "entry_pointer",
    "outbox",
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 纯判据：bundle 快照可 finalize
# ═══════════════════════════════════════════════════════════════════════════


def assert_bundle_snapshot_finalizable(bundle: DefinitionBundleSnapshot) -> None:
    """frozen bundle 快照是否可用于 finalize 一个 published representation。

    Requirement 2.3 的四条禁令逐条落成**可分辨**的失败：

    * bundle 未 approved                     → :class:`RepresentationBundleError`
    * authority model digest 缺失/非法        → :class:`RepresentationBundleError`
    * 三 typed slot 少一个（omission）        → :class:`RepresentationSlotError`
    * slot type/ref 空串 或 digest 全零/非法  → :class:`RepresentationSlotError`

    `projection_contract` 的 contract slot 还必须是 **approved definition**，
    不得用版本化 typed null marker 冒充（那是 custom/opaque 专用）。
    """
    if bundle.state is not DefinitionState.approved:
        raise RepresentationBundleError(
            f"definition bundle {bundle.bundle_id} state={bundle.state.value}，"
            "只有 approved bundle 可 finalize published representation（Requirement 2.3）"
        )
    if not is_digest(bundle.bundle_sha256):
        raise RepresentationBundleError(
            f"bundle canonical digest 非法（空串/全零/非小写 hex）: {bundle.bundle_sha256!r}"
        )
    if not is_digest(bundle.authority_model_definition_sha256):
        raise RepresentationBundleError(
            "bundle 的 authority model definition digest 非法（空串/全零/非小写 hex）: "
            f"{bundle.authority_model_definition_sha256!r}"
        )

    missing = [slot.value for slot in BundleSlot if slot not in bundle.slots]
    if missing:
        raise RepresentationSlotError(
            f"bundle {bundle.bundle_id} 缺 typed slot {missing} —— slot omission 必须 "
            "fail closed，不得以缺字段代替版本化 typed null marker（Requirement 2.3）"
        )
    for slot in BundleSlot:
        spec = bundle.slots[slot]
        if not (spec.slot_type or "").strip():
            raise RepresentationSlotError(
                f"{slot.value} slot 的 slot_type 为空/空白 —— 禁以 SQL NULL、空串代替 "
                "typed null marker"
            )
        if not (spec.slot_ref or "").strip():
            raise RepresentationSlotError(
                f"{slot.value} slot 的 slot_ref 为空/空白 —— typed slot 必须固定 child identity"
            )
        if not is_digest(spec.slot_digest):
            raise RepresentationSlotError(
                f"{slot.value} slot 的 digest 非法（空串/全零/非小写 hex）: "
                f"{spec.slot_digest!r}"
            )

    if bundle.authority_model.value == "projection_contract":
        contract_slot = bundle.slots[BundleSlot.contract]
        if not contract_slot.is_definition:
            raise RepresentationSlotError(
                "projection_contract 入口的 contract slot 必须是 approved definition child，"
                f"实得 typed null marker {contract_slot.slot_type!r} —— marker 不得冒充 "
                "per-entry contract（Requirement 2.3 / 6.19）"
            )


async def next_representation_generation(
    session: AsyncSession, *, wp_id: uuid.UUID, entry_id: str, content_version_id: uuid.UUID
) -> int:
    """同一 (wp, entry, content version) 的下一个 generation（从 1 起）。

    刻意按 content version 分组：`uq_wpcr_generation` 的唯一键是
    `(wp_id, entry_id, content_version_id, generation)`，按 entry 全局取 max 会在
    多 content version 场景下留出空洞并让「第几代」不可解释。
    """
    current = (
        await session.execute(
            sa.select(sa.func.max(WorkpaperContentRepresentation.generation)).where(
                WorkpaperContentRepresentation.wp_id == wp_id,
                WorkpaperContentRepresentation.entry_id == entry_id,
                WorkpaperContentRepresentation.content_version_id == content_version_id,
            )
        )
    ).scalar_one_or_none()
    return int(current or 0) + 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. 结果
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RepresentationFinalizeOutcome:
    """一次 candidate finalize 的结果。

    `content_revision_before == content_revision_after` 是本服务的**核心承诺**，
    因此它作为字段被返回而不是只写在文档里 —— 调用方与守卫都能直接断言。
    """

    candidate_id: uuid.UUID
    content_version_id: uuid.UUID
    representation_id: uuid.UUID
    representation_generation: int
    artifact_sha256: str
    definition_bundle_id: uuid.UUID
    definition_bundle_sha256: str
    authority_model: str
    content_revision_before: int
    content_revision_after: int
    previous_representation_id: uuid.UUID | None
    entry_pointer_moved: bool
    transaction_ids: tuple[str, ...]
    pending_event: PendingPublication | None

    @property
    def revision_unchanged(self) -> bool:
        return self.content_revision_before == self.content_revision_after

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": str(self.candidate_id),
            "content_version_id": str(self.content_version_id),
            "representation_id": str(self.representation_id),
            "representation_generation": self.representation_generation,
            "artifact_sha256": self.artifact_sha256,
            "definition_bundle_id": str(self.definition_bundle_id),
            "definition_bundle_sha256": self.definition_bundle_sha256,
            "authority_model": self.authority_model,
            "content_revision_before": self.content_revision_before,
            "content_revision_after": self.content_revision_after,
            "revision_unchanged": self.revision_unchanged,
            "previous_representation_id": (
                str(self.previous_representation_id)
                if self.previous_representation_id
                else None
            ),
            "entry_pointer_moved": self.entry_pointer_moved,
            "transaction_ids": list(self.transaction_ids),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3. 服务
# ═══════════════════════════════════════════════════════════════════════════


class RepresentationService:
    """approved bundle → 既有 content version 的新 immutable representation generation。

    **不接受** business projection、**不推进** revision、**不创建** content version。
    这三条不是文档承诺：构造函数只接 :class:`RevisionLockedRepository`（见
    `content_mutation.py`），三个方法在门面层恒抛。
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: WorkpaperSyncRepository,
        artifacts: CanonicalArtifactRepository,
        resolution: CanonicalResolutionService,
        outbox: type[DurableEventOutboxService] = DurableEventOutboxService,
    ) -> None:
        from app.services.workpaper_sync.content_mutation import RevisionLockedRepository

        self._session = session
        # 🔴 无条件包一层：即便调用方传进来的是裸 repository，本服务也拿不到
        #    revision 域写入面。这一行是 Property 4 在**构造上**的实现。
        self._repo = (
            repository
            if isinstance(repository, RevisionLockedRepository)
            else RevisionLockedRepository(repository)
        )
        self._artifacts = artifacts
        self._resolution = resolution
        self._outbox = outbox

    # ─────────────────────────────────────────────────────────────────

    async def finalize_candidate(
        self,
        *,
        project_id: uuid.UUID,
        candidate_id: uuid.UUID,
        staged_candidate: StagedCandidate,
        adapter_id: str,
        adapter_build_digest: str,
        structure_hash: str,
        identity_inventory_sha256: str,
        document_type: str = "xlsx",
        approved_stages: set[PublishStage] | set[str] | None = None,
        switch_entry_pointer: bool = True,
    ) -> RepresentationFinalizeOutcome:
        """为 candidate 所属的**既有** content version finalize 新 representation generation。

        步骤（顺序即判据，不可交换）：

        1. Task 12 的 `assert_candidate_finalizable` —— 五条前置一次校验；
        2. frozen bundle 快照 + `assert_bundle_snapshot_finalizable` —— typed slot 形态；
        3. `assert_publish_order(representation)` —— 发布 DAG 偏序；
        4. **物理 publish**：candidate 字节复制成 canonical artifact（publish 前后各校验 digest）；
        5. 单事务：登记 artifact 行 → 新 representation → 切 entry pointer → outbox → 一次 commit。

        失败时整个事务回滚：`content_revision` 与 entry pointer 均不变，已 publish 的
        canonical 文件成为无引用 orphan，candidate 仍是 non-current。
        """
        from app.services.workpaper_sync.content_mutation import _TransactionWitness

        candidate = await self._resolution.assert_candidate_finalizable(candidate_id)
        cand_wp_id = candidate.wp_id
        cand_entry_id = candidate.entry_id
        cand_version_id = candidate.content_version_id
        cand_bundle_id = candidate.target_definition_bundle_id
        assert cand_bundle_id is not None  # assert_candidate_finalizable 已保证

        bundle = await self._resolution.load_bundle_snapshot(cand_bundle_id)
        assert_bundle_snapshot_finalizable(bundle)
        assert_publish_order(
            stage=PublishStage.representation,
            approved_stages=approved_stages
            or {
                PublishStage.template,
                PublishStage.instrumentation,
                PublishStage.contract,
                PublishStage.bundle,
            },
        )
        for name, value in (
            ("adapter_build_digest", adapter_build_digest),
            ("structure_hash", structure_hash),
            ("identity_inventory_sha256", identity_inventory_sha256),
        ):
            if not is_digest(value):
                raise RepresentationError(
                    f"{name} 必须是非空非全零的 64 位小写 hex，实得 {value!r}"
                )
        # 🔴 判据是 **artifact 身份**（登记的 relative_path + digest），不是 staging 目录
        #    名里的 candidate_id：`.upgrade-candidates/{wp}/{staging_id}/` 的那个 id 只是
        #    命名空间，upgrader 先 stage 再登记时它与 DB 主键本就不同。用目录名当判据会
        #    在真实调用序列下恒红，而真正要防的是「拿另一份 candidate 的字节去 finalize」
        #    —— 那必然表现为 relative_path/digest 与本 candidate 登记的 artifact 不符。
        staged_row = (
            await self._session.execute(
                sa.text(
                    "SELECT relative_path, sha256 FROM working_paper_artifact WHERE id = :a"
                ),
                {"a": str(candidate.staged_artifact_id)},
            )
        ).first()
        if staged_row is None:
            raise RepresentationPointerError(
                f"candidate {candidate_id} 的 staged artifact 行不存在: "
                f"{candidate.staged_artifact_id}"
            )
        if staged_candidate.relative_path != staged_row[0]:
            raise RepresentationPointerError(
                f"staged candidate 的 relative_path {staged_candidate.relative_path!r} 与 "
                f"DB 登记的 {staged_row[0]!r} 不一致 —— 禁止用别的 candidate 字节 finalize"
            )
        if staged_candidate.sha256 != candidate.staged_artifact_sha256 or (
            staged_candidate.sha256 != staged_row[1]
        ):
            raise RepresentationPointerError(
                "staged candidate 的 digest 与 DB 登记的 staged_artifact_sha256 不一致 —— "
                f"{staged_candidate.sha256} != {candidate.staged_artifact_sha256}"
            )

        before = await self._revision_and_pointer(cand_wp_id, cand_entry_id)
        generation = await next_representation_generation(
            self._session,
            wp_id=cand_wp_id,
            entry_id=cand_entry_id,
            content_version_id=cand_version_id,
        )

        # ── 步骤 4：物理 publish（事务外，失败只留 staging/orphan）──────────
        published = self._artifacts.finalize_candidate_artifact(
            candidate=staged_candidate, generation=generation
        )

        # ── 步骤 5：单事务 ────────────────────────────────────────────────
        witness = _TransactionWitness(REPRESENTATION_FINALIZE_STEPS)
        pending: PendingPublication | None = None
        try:
            # candidate 行锁：并发两次 finalize 只有一个能过（第二个撞
            # `staged → finalized` 非法边）。锁在事务内取，commit/rollback 自动释放。
            locked = (
                await self._session.execute(
                    sa.select(WorkpaperRepresentationUpgradeCandidate)
                    .where(WorkpaperRepresentationUpgradeCandidate.id == candidate_id)
                    .with_for_update()
                )
            ).scalar_one()
            await witness.stamp(self._session, "candidate_lock")

            artifact_row = await self._repo.register_artifact(
                project_id=project_id,
                wp_id=cand_wp_id,
                kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=published.relative_path,
                sha256=published.sha256,
                size_bytes=published.size_bytes,
                document_type=published.document_type,
            )
            representation = await self._repo.create_representation(
                project_id=project_id,
                wp_id=cand_wp_id,
                entry_id=cand_entry_id,
                # 🔴 同一 content version：这是「纯表示升级不推进业务版本」的落点。
                #    V151 的 `trg_wpruc_guard` 会在 finalize 时再验一次。
                content_version_id=cand_version_id,
                generation=generation,
                document_type=document_type,
                artifact_id=artifact_row.id,
                artifact_sha256=published.sha256,
                definition_bundle_id=cand_bundle_id,
                authority_model_definition_id=bundle.authority_model_definition_id,
                adapter_id=adapter_id,
                adapter_build_digest=adapter_build_digest,
                structure_hash=structure_hash,
                identity_inventory_sha256=identity_inventory_sha256,
                reason="definition_upgrade",
                parent_representation_id=locked.source_representation_id,
            )
            await witness.stamp(self._session, "representation")

            await self._repo.finalize_candidate(
                candidate_id=candidate_id, finalized_representation_id=representation.id
            )
            pointer_moved = False
            if switch_entry_pointer:
                await self._repo.set_entry_pointer(
                    wp_id=cand_wp_id,
                    entry_id=cand_entry_id,
                    representation_id=representation.id,
                    generation=generation,
                )
                pointer_moved = True
            await witness.stamp(self._session, "entry_pointer")

            pending = await self._outbox.enqueue(
                self._session,
                event_type=EventType.WORKPAPER_CONTENT_UPDATED,
                project_id=project_id,
                payload=self._event_payload(
                    project_id=project_id,
                    wp_id=cand_wp_id,
                    entry_id=cand_entry_id,
                    revision=before["content_revision"],
                    representation=representation,
                    bundle=bundle,
                    adapter_id=adapter_id,
                    artifact_sha256=published.sha256,
                ),
            )
            await witness.stamp(self._session, "outbox")

            witness.assert_single_transaction()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        after = await self._revision_and_pointer(cand_wp_id, cand_entry_id)
        if after["content_revision"] != before["content_revision"]:
            # 到这里已经提交，只能大声报错（Requirement 5.12：不得降级成 warning）。
            raise RepresentationError(
                "纯表示 finalize 推进了 business content revision："
                f"{before['content_revision']} → {after['content_revision']} —— "
                "Property 4 被破坏"
            )
        return RepresentationFinalizeOutcome(
            candidate_id=candidate_id,
            content_version_id=cand_version_id,
            representation_id=representation.id,
            representation_generation=generation,
            artifact_sha256=published.sha256,
            definition_bundle_id=cand_bundle_id,
            definition_bundle_sha256=bundle.bundle_sha256,
            authority_model=bundle.authority_model.value,
            content_revision_before=int(before["content_revision"]),
            content_revision_after=int(after["content_revision"]),
            previous_representation_id=before["pointer_representation_id"],
            entry_pointer_moved=pointer_moved,
            transaction_ids=witness.transaction_ids,
            pending_event=pending,
        )

    # ─────────────────────────────────────────────────────────────────

    async def publish_committed_events(
        self, outcome: RepresentationFinalizeOutcome
    ) -> Mapping[str, Any]:
        """commit **之后**发布耐久事件（Requirement 13.1）。"""
        if outcome.pending_event is None:
            return {"attempted": 0}
        report = await self._outbox.publish_pending(self._session, [outcome.pending_event])
        return report.as_dict()

    # ─────────────────────────────────────────────────────────────────

    async def _revision_and_pointer(
        self, wp_id: uuid.UUID, entry_id: str
    ) -> dict[str, Any]:
        revision = (
            await self._session.execute(
                sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
                {"wp": str(wp_id)},
            )
        ).scalar_one()
        pointer = (
            await self._session.execute(
                sa.select(
                    WorkpaperSyncEntryState.current_representation_id,
                    WorkpaperSyncEntryState.representation_generation,
                ).where(
                    WorkpaperSyncEntryState.wp_id == wp_id,
                    WorkpaperSyncEntryState.entry_id == entry_id,
                )
            )
        ).first()
        return {
            "content_revision": int(revision),
            "pointer_representation_id": pointer[0] if pointer else None,
            "pointer_generation": int(pointer[1]) if pointer else None,
        }

    @staticmethod
    def _event_payload(
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        revision: int,
        representation: WorkpaperContentRepresentation,
        bundle: DefinitionBundleSnapshot,
        adapter_id: str,
        artifact_sha256: str,
    ) -> dict[str, Any]:
        """design §outbox 的 payload + 纯表示升级专属标记。

        `content_revision_advanced=False` 是**给消费方的判据**：同一个
        `workpaper.content.updated` 事件既可能来自业务应用（revision 变了）也可能来自
        纯表示升级（revision 没变），下游若按「收到事件就认为内容变了」去刷新，会把
        一次隐形模板升级当成业务改动推给审计师。
        """
        return {
            "wp_id": str(wp_id),
            "project_id": str(project_id),
            "revision": int(revision),
            "operation_id": None,
            "source": "definition_upgrade",
            "adapter_id": adapter_id,
            "file_sha256": artifact_sha256,
            "entry_id": entry_id,
            "content_version_id": str(representation.content_version_id),
            "representation_id": str(representation.id),
            "representation_generation": int(representation.generation),
            "definition_bundle_id": str(bundle.bundle_id),
            "definition_bundle_sha256": bundle.bundle_sha256,
            "authority_model": bundle.authority_model.value,
            "content_revision_advanced": False,
            "reason": "definition_upgrade",
        }
