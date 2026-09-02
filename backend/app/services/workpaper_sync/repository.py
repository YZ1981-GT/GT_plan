# -*- coding: utf-8 -*-
"""同步域仓储层：只 flush 不 commit，wp 串行化 + 乐观锁 + scope 同事务原子写入。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 10
Requirements: 2.1, 2.4, 2.5, 2.9, 4.3, 5.4, 5.5, 5.10, 8.5, 10.5, 10.9, 10.10, 10.11, 13.5, 14.10
Properties: P4 / P5 / P18 / P36 / P43 / P59 / P63 / P64 / P68

═══ 为什么「只 flush 不 commit」是硬边界 ═══

一次业务应用要同时落 content version / representation / entry pointer / room 双基线 /
application result / operation event / outbox。若仓储自己 commit，任一后续步骤失败就会
留下「pointer 指向缺失 artifact」的半成功态（Requirement 5.9 明令禁止）。因此本模块
**不出现任何 `commit()`**，事务边界由调用方（`ContentMutationService` / coordinator）
统一持有；`backend/tests/workpaper_sync/test_task10_repository_pg.py` 用
「repository 写完后 rollback ⇒ 库里零行」作行为判据，而不是 grep `commit`。

═══ 并发正确性由数据库锁决定，不是进程内锁 ═══

`lock_workpaper()` 先取 `pg_advisory_xact_lock`（事务级，commit/rollback 自动释放），
再对 `working_paper` 行取 `FOR UPDATE`。两者都是数据库级，多 worker 下语义一致
（Requirement 10.11 / Property 59）。跨 wp 用不同 advisory key ⇒ 天然并行。

═══ 与数据库约束的关系：双向而不是二选一 ═══

V151 有 215 条 CHECK / 34 触发器。本模块在写入前用
:mod:`app.services.workpaper_sync.models` 的纯函数做同一批校验，目的不是替代 DB，
而是让错误 **fail-visible**（带 error_code/stage），并拦住「先写坏再被 DB 拒绝」导致
的事务级联失败。DB 侧仍是最终防线：绕过本模块的任何写入（psql/脚本）同样被拒。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperArtifact,
    WorkpaperCallbackDelivery,
    WorkpaperCallbackRecoveryCase,
    WorkpaperCallbackRecoveryCaseEvent,
    WorkpaperContentApplication,
    WorkpaperContentApplicationEvent,
    WorkpaperContentRepresentation,
    WorkpaperContentVersion,
    WorkpaperOoClientConfirmation,
    WorkpaperOoCloseIntent,
    WorkpaperOoCloseIntentEvent,
    WorkpaperOoParticipant,
    WorkpaperOoRoom,
    WorkpaperForcesaveRequest,
    WorkpaperPendingMutation,
    WorkpaperRepresentationCandidateEvent,
    WorkpaperRepresentationUpgradeCandidate,
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
    WorkpaperSyncConflict,
    WorkpaperSyncEntryState,
    WorkpaperSyncOperation,
    WorkpaperSyncOperationEvent,
    WorkpaperSyncScopeIndex,
)
from app.services.workpaper_sync.models import (
    CLOSE_INTENT_EDGES,
    ActorType,
    ApplicationEventType,
    ApplicationState,
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleIntegrityError,
    BundleSlot,
    BundleSlotSpec,
    CandidateState,
    CloseIntentState,
    CorrelationResult,
    DeliveryOwnershipError,
    DeliveryState,
    DuplicateLinkError,
    IdempotencyConflictError,
    IdentityError,
    IncomingNotDurableError,
    OperationDirection,
    OperationScope,
    OperationShape,
    OperationState,
    ParticipantState,
    PendingMutationState,
    QuarantinedIncomingError,
    RecoveryCaseState,
    RecoveryReason,
    RequestKind,
    RequestState,
    RevisionConflictError,
    RoomState,
    ScopeIntegrityError,
    ScopeResourceKind,
    assert_delivery_ownership,
    assert_direct_primary,
    assert_supersede,
    assert_transition,
    classify_operation_shape,
    compute_application_key,
    compute_eligibility_digest,
    compute_frozen_request_fingerprint,
    fold_effective_sequence,
    is_digest,
    is_opaque_resource_id,
    is_uuid_text,
    validate_bundle_slots,
    validate_definition_child,
)

#: advisory lock 的命名空间（第一个 int4），避免与平台其他 advisory 用途撞 key。
_ADVISORY_NAMESPACE: int = 0x5753  # 'WS' = Workpaper Sync

#: close-capture partial unique 覆盖的 open 状态（与 V151 的 WHERE 子句同集合）。
_OPEN_CAPTURE_STATES: tuple[str, ...] = ("frozen", "pending", "accepted", "correlated")


def _now() -> datetime:
    """服务端时钟（timestamptz）。

    🔴 必须在 Python 侧构造 aware `datetime` 再交给驱动：asyncpg 按目标列类型编码，
    SQL 层 `CAST(:x AS timestamptz)` 对已按 text 发送的值无效。
    """
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 结果 DTO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ForcesaveRequestOutcome:
    """`create_forcesave_request_with_shell` 的结果。

    `cache_hit=True` 表示逐项等值的幂等重放，返回的是**同一个** request/operation。
    """

    request: WorkpaperForcesaveRequest
    operation: WorkpaperSyncOperation
    cache_hit: bool


@dataclass(frozen=True)
class CorrelationOutcome:
    """durable correlation 结果：winner 绑定 primary，loser 成为 direct terminal duplicate。"""

    application: WorkpaperContentApplication
    operation: WorkpaperSyncOperation
    shape: OperationShape
    created_application: bool
    folded_from_sequence: int | None
    effective_request_sequence: int
    canonical_primary_operation_id: uuid.UUID


@dataclass(frozen=True)
class CloseReconcileOutcome:
    """`reconcile_close_intents` 的幂等结果。"""

    leader_intent_id: uuid.UUID | None
    promoted_request_id: uuid.UUID | None
    capture_created: bool
    eligibility_epoch: int
    eligibility_digest: str | None
    authorization_stale_intent_ids: tuple[uuid.UUID, ...]
    no_successor: bool


@dataclass(frozen=True)
class ConflictWriteOutcome:
    """`record_conflicts` 的结果。三个计数都是可断言的事实，不是日志。

    `superseded` 非零 = 上一轮观测里存在、这一轮不再出现的冲突（rebase 后冲突变少）。
    行**不删**，只打时间戳 —— 审计师要能看到「上一轮有这条」。
    """

    inserted: int
    updated: int
    superseded: int


@dataclass(frozen=True)
class RecoveryClaimOutcome:
    """recovery claim 结果：三实体一次性创建/命中，或幂等返回既有绑定。"""

    case: WorkpaperCallbackRecoveryCase
    request: WorkpaperForcesaveRequest
    operation: WorkpaperSyncOperation
    application: WorkpaperContentApplication
    shape: OperationShape
    cache_hit: bool


# ═══════════════════════════════════════════════════════════════════════════
# 仓储
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperSyncRepository:
    """同步域唯一写入入口。**不 commit**；调用方持有事务边界。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def _flush(self) -> None:
        """把待写对象推到数据库（触发 CHECK/immediate trigger），但不提交。"""
        await self._session.flush()

    # ─────────────────────────────────────────────────────────────────
    # 1. 锁与 business revision 乐观锁
    # ─────────────────────────────────────────────────────────────────

    async def lock_workpaper(self, wp_id: uuid.UUID) -> int:
        """per-wp 串行化：advisory xact lock + `working_paper` 行锁，返回当前 content_revision。

        同 wp 的第二个事务在此阻塞（串行），不同 wp 取不同 advisory key（并行）。
        两者都是数据库级锁：多 worker 下与单 worker 结果一致（Property 59）。
        """
        await self._session.execute(
            sa.text("SELECT pg_advisory_xact_lock(:ns, hashtext(:key))"),
            {"ns": _ADVISORY_NAMESPACE, "key": f"workpaper_sync:{wp_id}"},
        )
        row = (
            await self._session.execute(
                sa.text(
                    "SELECT content_revision FROM working_paper WHERE id = :wp FOR UPDATE"
                ),
                {"wp": str(wp_id)},
            )
        ).first()
        if row is None:
            raise ScopeIntegrityError(f"working_paper 不存在: {wp_id}")
        return int(row[0])

    async def try_lock_workpaper(self, wp_id: uuid.UUID) -> bool:
        """非阻塞尝试取 per-wp advisory lock（用于证明跨 wp 无全局互斥）。"""
        got = (
            await self._session.execute(
                sa.text("SELECT pg_try_advisory_xact_lock(:ns, hashtext(:key))"),
                {"ns": _ADVISORY_NAMESPACE, "key": f"workpaper_sync:{wp_id}"},
            )
        ).scalar_one()
        return bool(got)

    async def assert_expected_revision(self, wp_id: uuid.UUID, expected_revision: int) -> int:
        """读当前 revision 并与 expected 比对（不推进）。"""
        current = await self.lock_workpaper(wp_id)
        if current != expected_revision:
            raise RevisionConflictError(
                f"business revision 乐观锁失败：expected={expected_revision} current={current}"
            )
        return current

    async def bump_content_revision(self, wp_id: uuid.UUID, expected_revision: int) -> int:
        """CAS 推进 business content revision，返回新值；不匹配即 :class:`RevisionConflictError`。

        单条 `UPDATE ... WHERE content_revision = :expected` 就是乐观锁本体：
        并发两个 worker 同 expected 只有一个能命中 1 行。
        """
        row = (
            await self._session.execute(
                sa.text(
                    "UPDATE working_paper SET content_revision = content_revision + 1 "
                    "WHERE id = :wp AND content_revision = :expected "
                    "RETURNING content_revision"
                ),
                {"wp": str(wp_id), "expected": expected_revision},
            )
        ).first()
        if row is None:
            raise RevisionConflictError(
                f"business revision 乐观锁失败：wp={wp_id} expected={expected_revision}"
            )
        return int(row[0])

    async def set_current_content_version(
        self, wp_id: uuid.UUID, content_version_id: uuid.UUID
    ) -> None:
        """把 `working_paper.current_content_version_id` 指向新的 immutable business version。"""
        await self._session.execute(
            sa.text(
                "UPDATE working_paper SET current_content_version_id = :cv WHERE id = :wp"
            ),
            {"cv": str(content_version_id), "wp": str(wp_id)},
        )

    async def lock_room(self, room_id: uuid.UUID) -> WorkpaperOoRoom:
        """room row lock：close barrier / leader / durable fence 的原子决定边界。"""
        room = (
            await self._session.execute(
                sa.select(WorkpaperOoRoom)
                .where(WorkpaperOoRoom.id == room_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if room is None:
            raise ScopeIntegrityError(f"room 不存在: {room_id}")
        return room

    # ─────────────────────────────────────────────────────────────────
    # 2. scope index（authorization-only，与 child 同事务）
    # ─────────────────────────────────────────────────────────────────

    async def register_scope(
        self,
        *,
        resource_kind: ScopeResourceKind | str,
        resource_id: str,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        room_id: uuid.UUID | None = None,
        generation: int | None = None,
    ) -> WorkpaperSyncScopeIndex:
        """与 child 同事务登记 scope row。

        拒绝：非 opaque resource_id（纯数字 numeric revision）、content_version 非 UUID、
        id 复用（含 retired tombstone 复用）、跨 scope 重绑。
        """
        kind = (
            resource_kind
            if isinstance(resource_kind, ScopeResourceKind)
            else ScopeResourceKind(resource_kind)
        )
        rid = str(resource_id)
        if not is_opaque_resource_id(rid):
            raise ScopeIntegrityError(
                f"scope resource_id 必须 opaque（纯数字 numeric revision 禁作 scope key）: {rid!r}"
            )
        if kind is ScopeResourceKind.content_version and not is_uuid_text(rid):
            raise ScopeIntegrityError(
                f"content_version 的 resource_id 只能是 immutable UUID version_id: {rid!r}"
            )
        if not entry_id or not entry_id.strip():
            raise ScopeIntegrityError("scope entry_id 不得为空")

        existing = (
            await self._session.execute(
                sa.select(WorkpaperSyncScopeIndex)
                .where(
                    WorkpaperSyncScopeIndex.resource_kind == kind.value,
                    WorkpaperSyncScopeIndex.resource_id == rid,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is not None:
            same_scope = (
                existing.project_id == project_id
                and existing.wp_id == wp_id
                and existing.entry_id == entry_id
            )
            raise ScopeIntegrityError(
                "scope (resource_kind, resource_id) 永不复用"
                f"（{'同' if same_scope else '跨'} scope 复用同样被拒）: {kind.value}/{rid}"
            )

        row = WorkpaperSyncScopeIndex(
            resource_kind=kind.value,
            resource_id=rid,
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            generation=generation,
        )
        self._session.add(row)
        await self._flush()
        return row

    async def retire_scope(
        self, *, resource_kind: ScopeResourceKind | str, resource_id: str
    ) -> WorkpaperSyncScopeIndex:
        """child 退役只设置 `retired_at`；tombstone 永久保留（防 id 复用）。"""
        kind = (
            resource_kind
            if isinstance(resource_kind, ScopeResourceKind)
            else ScopeResourceKind(resource_kind)
        )
        row = (
            await self._session.execute(
                sa.select(WorkpaperSyncScopeIndex)
                .where(
                    WorkpaperSyncScopeIndex.resource_kind == kind.value,
                    WorkpaperSyncScopeIndex.resource_id == str(resource_id),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise ScopeIntegrityError(f"scope row 不存在，无法退役: {kind.value}/{resource_id}")
        if row.retired_at is None:
            row.retired_at = _now()
            await self._flush()
        return row

    async def resolve_scope(
        self, *, resource_kind: ScopeResourceKind | str, resource_id: str
    ) -> WorkpaperSyncScopeIndex | None:
        """authorization-only 查询：只读 scope index，绝不预读业务 child/cache。

        retired 与不存在走同一 404 oracle（返回 None 时调用方不得区分二者），
        但 tombstone 仍参与防复用。
        """
        kind = (
            resource_kind
            if isinstance(resource_kind, ScopeResourceKind)
            else ScopeResourceKind(resource_kind)
        )
        return (
            await self._session.execute(
                sa.select(WorkpaperSyncScopeIndex).where(
                    WorkpaperSyncScopeIndex.resource_kind == kind.value,
                    WorkpaperSyncScopeIndex.resource_id == str(resource_id),
                    WorkpaperSyncScopeIndex.retired_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def delete_scope(
        self, *, resource_kind: ScopeResourceKind | str, resource_id: str
    ) -> None:
        """恒抛：repository 拒绝物理删除 scope row（DB trigger 是第二道锁）。"""
        raise ScopeIntegrityError(
            "scope index tombstone 永不物理删除 —— 退役请用 retire_scope() 设置 retired_at"
            f"（请求删除 {resource_kind}/{resource_id}）"
        )

    async def clear_scope_tombstone(
        self, *, resource_kind: ScopeResourceKind | str, resource_id: str
    ) -> None:
        """恒抛：repository 拒绝清空 tombstone（否则 retired id 会复活并被复用）。"""
        raise ScopeIntegrityError(
            "scope tombstone 的 retired_at 不得被清空"
            f"（请求清空 {resource_kind}/{resource_id}）"
        )

    # ─────────────────────────────────────────────────────────────────
    # 3. bundle / incoming artifact 校验（与 DB CHECK/trigger 双向）
    # ─────────────────────────────────────────────────────────────────

    async def assert_bundle_usable(
        self, bundle_id: uuid.UUID
    ) -> WorkpaperSyncDefinitionBundle:
        """双向校验 bundle：approved + 四 typed slots + child kind/state/digest。

        `projection_contract` 必须三 child 全 approved definition（marker 不得冒充 contract）。
        """
        bundle = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionBundle).where(
                    WorkpaperSyncDefinitionBundle.id == bundle_id
                )
            )
        ).scalar_one_or_none()
        if bundle is None:
            raise BundleIntegrityError(f"definition bundle 不存在: {bundle_id}")
        if bundle.state != "approved":
            raise BundleIntegrityError(
                f"definition bundle state={bundle.state}，只有 approved 可用于 finalize/room"
            )
        authority = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id
                    == bundle.authority_model_definition_id
                )
            )
        ).scalar_one_or_none()
        if authority is None:
            raise BundleIntegrityError("bundle 的 authority model definition 不存在")
        if authority.kind != "authority_model" or authority.state != "approved":
            raise BundleIntegrityError(
                f"authority model child kind={authority.kind} state={authority.state} 非法"
            )
        if authority.sha256.strip() != bundle.authority_model_definition_sha256.strip():
            raise BundleIntegrityError("bundle 的 authority model digest 与 child 不一致")
        if not authority.authority_model_type:
            raise BundleIntegrityError(
                "authority_model definition 缺 authority_model_type 枚举"
            )

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
        validate_bundle_slots(
            authority_model=AuthorityModel(authority.authority_model_type),
            authority_model_definition_sha256=bundle.authority_model_definition_sha256,
            slots=slots,
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
                raise BundleIntegrityError(f"{slot.value} slot 引用的 definition 不存在: {child_id}")
            validate_definition_child(
                slot=slot,
                child_kind=child.kind,
                child_state=child.state,
                child_sha256=child.sha256,
                slot_digest=spec.slot_digest,
            )
        return bundle

    async def assert_incoming_durable(self, artifact_id: uuid.UUID) -> WorkpaperArtifact:
        """只有 `kind=incoming, state=durable` 的 artifact 可创建/命中 application。

        quarantined incoming 抛 :class:`QuarantinedIncomingError`：Requirement 5.6 明确
        它永不得解除隔离、转 durable、创建 application 或进入 extract/merge/retry/rematerialize。
        """
        art = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(WorkpaperArtifact.id == artifact_id)
            )
        ).scalar_one_or_none()
        if art is None:
            raise IncomingNotDurableError(f"incoming artifact 不存在: {artifact_id}")
        if art.kind != ArtifactKind.incoming.value:
            raise IncomingNotDurableError(
                f"application 的 substrate 必须是 kind=incoming，实得 {art.kind}"
            )
        # 🔴 隔离终态与「尚未 durable」暂态必须是两个异常类型：共用一个类型时，
        # 下面的暂态分支会遮蔽本分支，导致「隔离永不解除」这条判据无法被变异检验证明。
        if art.state == ArtifactState.quarantined.value:
            raise QuarantinedIncomingError(
                "quarantined incoming 永不得创建 application 或进入 engine"
                "（只允许 authorization-first download-only / expire / retention）"
            )
        if art.state != ArtifactState.durable.value or art.durable_at is None:
            raise IncomingNotDurableError(
                f"incoming state={art.state} durable_at={art.durable_at!r}，只有 durable 可用"
            )
        return art

    # ─────────────────────────────────────────────────────────────────
    # 4. 内容域写入
    # ─────────────────────────────────────────────────────────────────

    async def register_artifact(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        kind: ArtifactKind | str,
        state: ArtifactState | str,
        relative_path: str,
        sha256: str,
        size_bytes: int,
        document_type: str,
        retention_class: str = "default",
        source_delivery_id: uuid.UUID | None = None,
        created_by_operation_id: uuid.UUID | None = None,
    ) -> WorkpaperArtifact:
        """登记 artifact 行（文件系统 staging/publish 协议由 Task 11 的 artifacts.py 承担）。

        artifact **不是**用户可寻址 child，故不进 scope index（design §scope index 只覆盖
        room/participant/confirmation/request/... 等可由用户提供 opaque id 定位的 child）。
        """
        k = kind if isinstance(kind, ArtifactKind) else ArtifactKind(kind)
        st = state if isinstance(state, ArtifactState) else ArtifactState(state)
        if not is_digest(sha256):
            raise IdentityError(f"artifact sha256 非法（空串/全零/非小写 hex）: {sha256!r}")
        # 🔴 内容寻址下**同一个文件**必须只有一行（`uq_wpa_relative_path`）。
        # 这不是「容错」而是 rollback 的正常路径：回滚到历史 projection 会重新
        # materialize 出**逐字节相同**的 representation，而文件名是
        # `{generation:09d}-{sha12}`，新 content version 的 generation 又从 1 起 ⇒
        # 目标路径与历史那一份完全一致。文件层 `_publish` 本就把它当同一个不可变对象，
        # DB 层若再插一行就会撞唯一约束（Task 27 在真库上实测到）。
        # 判据严格：路径**与** digest 同时相等才复用；digest 不同 = 同名不同内容，
        # 那是真正的身份漂移，必须抛（下面的 insert 会撞唯一约束并暴露出来）。
        existing = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(
                    WorkpaperArtifact.relative_path == relative_path,
                    WorkpaperArtifact.sha256 == sha256,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if (
                existing.project_id != project_id
                or existing.wp_id != wp_id
                or existing.kind != k.value
                or existing.state != st.value
            ):
                raise IdentityError(
                    f"artifact {relative_path!r} 已存在但身份不同（"
                    f"project={existing.project_id} wp={existing.wp_id} "
                    f"kind={existing.kind} state={existing.state}）—— "
                    "内容寻址路径不得跨 scope/kind/state 复用"
                )
            return existing
        now = _now()
        art = WorkpaperArtifact(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_id=wp_id,
            kind=k.value,
            state=st.value,
            relative_path=relative_path,
            sha256=sha256,
            size_bytes=size_bytes,
            document_type=document_type,
            retention_class=retention_class,
            source_delivery_id=source_delivery_id,
            created_by_operation_id=created_by_operation_id,
            durable_at=now if st is ArtifactState.durable else None,
            quarantined_at=now if st is ArtifactState.quarantined else None,
            published_at=now if st is ArtifactState.published else None,
        )
        self._session.add(art)
        await self._flush()
        return art

    async def create_definition_artifact(
        self,
        *,
        kind: str,
        logical_id: str,
        semantic_version: str,
        blob_artifact_id: uuid.UUID,
        sha256: str,
        source_commit: str,
        structure_hash: str | None = None,
        authority_model_type: str | None = None,
        approved: bool = True,
    ) -> WorkpaperSyncDefinitionArtifact:
        """发布 immutable definition artifact（template/instrumentation/contract/authority_model）。"""
        if not is_digest(sha256):
            raise IdentityError(f"definition sha256 非法: {sha256!r}")
        row = WorkpaperSyncDefinitionArtifact(
            id=uuid.uuid4(),
            kind=kind,
            logical_id=logical_id,
            semantic_version=semantic_version,
            blob_artifact_id=blob_artifact_id,
            sha256=sha256,
            structure_hash=structure_hash,
            authority_model_type=authority_model_type,
            source_commit=source_commit,
            state="approved" if approved else "candidate",
            approved_at=_now() if approved else None,
        )
        self._session.add(row)
        await self._flush()
        return row

    async def create_definition_bundle(
        self,
        *,
        authority_model_definition_id: uuid.UUID,
        slots: dict[BundleSlot, BundleSlotSpec],
        canonical_payload_artifact_id: uuid.UUID,
        canonical_payload_sha256: str,
        approved: bool = True,
    ) -> WorkpaperSyncDefinitionBundle:
        """组 typed definition bundle。repository 侧先校验四 slot，再交 DB trigger 二次锁死。"""
        authority = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id == authority_model_definition_id
                )
            )
        ).scalar_one_or_none()
        if authority is None or authority.kind != "authority_model":
            raise BundleIntegrityError("bundle 必须引用 kind=authority_model 的 definition")
        if not authority.authority_model_type:
            raise BundleIntegrityError("authority_model definition 缺 authority_model_type 枚举")
        validate_bundle_slots(
            authority_model=AuthorityModel(authority.authority_model_type),
            authority_model_definition_sha256=authority.sha256,
            slots=slots,
        )
        row = WorkpaperSyncDefinitionBundle(
            id=uuid.uuid4(),
            authority_model_definition_id=authority_model_definition_id,
            authority_model_definition_sha256=authority.sha256,
            template_slot_type=slots[BundleSlot.template].slot_type,
            template_slot_ref=slots[BundleSlot.template].slot_ref,
            template_slot_digest=slots[BundleSlot.template].slot_digest,
            instrumentation_slot_type=slots[BundleSlot.instrumentation].slot_type,
            instrumentation_slot_ref=slots[BundleSlot.instrumentation].slot_ref,
            instrumentation_slot_digest=slots[BundleSlot.instrumentation].slot_digest,
            contract_slot_type=slots[BundleSlot.contract].slot_type,
            contract_slot_ref=slots[BundleSlot.contract].slot_ref,
            contract_slot_digest=slots[BundleSlot.contract].slot_digest,
            canonical_payload_artifact_id=canonical_payload_artifact_id,
            canonical_payload_sha256=canonical_payload_sha256,
            state="approved" if approved else "candidate",
            approved_at=_now() if approved else None,
        )
        self._session.add(row)
        await self._flush()
        return row

    async def create_room(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        doc_key: str,
        generation: int,
        opened_base_version_id: uuid.UUID,
        ttl: timedelta = timedelta(hours=8),
    ) -> WorkpaperOoRoom:
        """创建 room 并同事务登记 scope（room 是用户可寻址 child）。"""
        room = WorkpaperOoRoom(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            doc_key=doc_key,
            generation=generation,
            opened_base_version_id=opened_base_version_id,
            state=RoomState.opening.value,
            expires_at=_now() + ttl,
        )
        self._session.add(room)
        await self._flush()
        await self.register_scope(
            resource_kind=ScopeResourceKind.room,
            resource_id=str(room.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room.id,
            generation=generation,
        )
        return room

    async def create_participant(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        room_id: uuid.UUID,
        user_id: uuid.UUID,
        mode: str,
        permission_epoch: int,
        lease_token_hash: str,
        ttl: timedelta = timedelta(hours=4),
    ) -> WorkpaperOoParticipant:
        """逐用户 lease：room 共享不代表共享 user_id/mode/permission epoch（Property 63）。"""
        room = await self.lock_room(room_id)
        p = WorkpaperOoParticipant(
            id=uuid.uuid4(),
            room_id=room_id,
            user_id=user_id,
            mode=mode,
            state=ParticipantState.active.value,
            permission_epoch=permission_epoch,
            joined_write_fence_epoch=int(room.write_fence_epoch),
            lease_token_hash=lease_token_hash,
            expires_at=_now() + ttl,
        )
        self._session.add(p)
        await self._flush()
        await self.register_scope(
            resource_kind=ScopeResourceKind.participant,
            resource_id=str(p.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            generation=int(room.generation),
        )
        return p

    async def create_client_confirmation(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        room_id: uuid.UUID,
        participant_id: uuid.UUID,
        representation_id: uuid.UUID,
        content_version_id: uuid.UUID,
        projection_sha256: str,
        bundle_slots_digest: str,
        idempotency_key: str,
    ) -> WorkpaperOoClientConfirmation:
        """DocEditor ready 后的 descriptor 确认：identity 逐项来自 representation/bundle。"""
        room = await self.lock_room(room_id)
        rep = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation).where(
                    WorkpaperContentRepresentation.id == representation_id
                )
            )
        ).scalar_one_or_none()
        if rep is None:
            raise ScopeIntegrityError(f"representation 不存在: {representation_id}")
        await self.assert_bundle_usable(rep.definition_bundle_id)
        conf = WorkpaperOoClientConfirmation(
            id=uuid.uuid4(),
            room_id=room_id,
            participant_id=participant_id,
            generation=int(room.generation),
            doc_key=room.doc_key,
            representation_id=representation_id,
            artifact_sha256=rep.artifact_sha256,
            content_version_id=content_version_id,
            projection_sha256=projection_sha256,
            definition_bundle_id=rep.definition_bundle_id,
            definition_bundle_sha256=rep.definition_bundle_sha256,
            authority_model_definition_sha256=rep.authority_model_definition_sha256,
            bundle_slots_digest=bundle_slots_digest,
            write_fence_epoch=int(room.write_fence_epoch),
            idempotency_key=idempotency_key,
        )
        self._session.add(conf)
        await self._flush()
        await self.register_scope(
            resource_kind=ScopeResourceKind.client_confirmation,
            resource_id=str(conf.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            generation=int(room.generation),
        )
        # room 首个有效 edit confirmation 才从 opening 进入 active
        if RoomState(room.state) is RoomState.opening:
            assert_transition("room", room.state, RoomState.active)
            room.state = RoomState.active.value
            room.updated_at = _now()
            await self._flush()
        return conf

    async def set_room_client_confirmed_baseline(
        self, *, room_id: uuid.UUID, confirmation: WorkpaperOoClientConfirmation
    ) -> WorkpaperOoRoom:
        """把 client-confirmed 五元组作为**整体快照**写入 room（禁半缺）。"""
        room = await self.lock_room(room_id)
        room.client_confirmed_base_version_id = confirmation.content_version_id
        room.client_confirmed_representation_id = confirmation.representation_id
        room.client_confirmed_definition_bundle_id = confirmation.definition_bundle_id
        room.client_confirmed_definition_bundle_sha256 = confirmation.definition_bundle_sha256
        room.client_confirmed_projection_sha256 = confirmation.projection_sha256
        room.updated_at = _now()
        await self._flush()
        return room

    async def create_upgrade_candidate(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        content_version_id: uuid.UUID,
        source_representation_id: uuid.UUID,
        staged_artifact_id: uuid.UUID,
        staged_artifact_sha256: str,
        template_definition_id: uuid.UUID,
        instrumentation_definition_id: uuid.UUID,
        target_contract_definition_id: uuid.UUID | None = None,
        target_definition_bundle_id: uuid.UUID | None = None,
        state: CandidateState = CandidateState.staged,
    ) -> WorkpaperRepresentationUpgradeCandidate:
        """non-current candidate：永不进入 resolver/room/current pointer/evidence。"""
        cand = WorkpaperRepresentationUpgradeCandidate(
            id=uuid.uuid4(),
            wp_id=wp_id,
            content_version_id=content_version_id,
            entry_id=entry_id,
            source_representation_id=source_representation_id,
            staged_artifact_id=staged_artifact_id,
            staged_artifact_sha256=staged_artifact_sha256,
            template_definition_id=template_definition_id,
            instrumentation_definition_id=instrumentation_definition_id,
            target_contract_definition_id=target_contract_definition_id,
            target_definition_bundle_id=target_definition_bundle_id,
            state=state.value,
        )
        self._session.add(cand)
        await self._flush()
        await self.register_scope(
            resource_kind=ScopeResourceKind.upgrade_candidate,
            resource_id=str(cand.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
        )
        return cand

    async def create_content_version(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        revision: int,
        source: str,
        parent_version_id: uuid.UUID | None = None,
        projection_artifact_id: uuid.UUID | None = None,
        projection_sha256: str | None = None,
        authoritative_artifact_id: uuid.UUID | None = None,
        authoritative_artifact_sha256: str | None = None,
        operation_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> WorkpaperContentVersion:
        """创建 immutable content version 并同事务登记 scope（resource_id = opaque UUID）。"""
        cv = WorkpaperContentVersion(
            id=uuid.uuid4(),
            wp_id=wp_id,
            revision=revision,
            parent_version_id=parent_version_id,
            source=source,
            projection_artifact_id=projection_artifact_id,
            projection_sha256=projection_sha256,
            authoritative_artifact_id=authoritative_artifact_id,
            authoritative_artifact_sha256=authoritative_artifact_sha256,
            operation_id=operation_id,
            actor_id=actor_id,
        )
        self._session.add(cv)
        await self._flush()
        await self.register_scope(
            resource_kind=ScopeResourceKind.content_version,
            resource_id=str(cv.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
        )
        return cv

    async def create_representation(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        content_version_id: uuid.UUID,
        generation: int,
        document_type: str,
        artifact_id: uuid.UUID,
        artifact_sha256: str,
        definition_bundle_id: uuid.UUID,
        authority_model_definition_id: uuid.UUID,
        adapter_id: str,
        adapter_build_digest: str,
        structure_hash: str,
        identity_inventory_sha256: str,
        reason: str,
        parent_representation_id: uuid.UUID | None = None,
    ) -> WorkpaperContentRepresentation:
        """finalize 一个 immutable representation generation（强制 approved 非空 bundle）。"""
        bundle = await self.assert_bundle_usable(definition_bundle_id)
        if bundle.authority_model_definition_id != authority_model_definition_id:
            raise BundleIntegrityError(
                "representation 的 authority model 与 bundle child 不一致"
            )
        rep = WorkpaperContentRepresentation(
            id=uuid.uuid4(),
            wp_id=wp_id,
            content_version_id=content_version_id,
            entry_id=entry_id,
            generation=generation,
            parent_representation_id=parent_representation_id,
            document_type=document_type,
            artifact_id=artifact_id,
            artifact_sha256=artifact_sha256,
            definition_bundle_id=definition_bundle_id,
            definition_bundle_sha256=bundle.canonical_payload_sha256,
            authority_model_definition_id=authority_model_definition_id,
            authority_model_definition_sha256=bundle.authority_model_definition_sha256,
            adapter_id=adapter_id,
            adapter_build_digest=adapter_build_digest,
            structure_hash=structure_hash,
            identity_inventory_sha256=identity_inventory_sha256,
            reason=reason,
        )
        self._session.add(rep)
        await self._flush()
        await self.register_scope(
            resource_kind=ScopeResourceKind.content_representation,
            resource_id=str(rep.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
        )
        return rep

    async def set_entry_pointer(
        self, *, wp_id: uuid.UUID, entry_id: str, representation_id: uuid.UUID, generation: int
    ) -> WorkpaperSyncEntryState:
        """切 entry current representation pointer（不改 content revision）。"""
        state = (
            await self._session.execute(
                sa.select(WorkpaperSyncEntryState)
                .where(
                    WorkpaperSyncEntryState.wp_id == wp_id,
                    WorkpaperSyncEntryState.entry_id == entry_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if state is None:
            state = WorkpaperSyncEntryState(
                wp_id=wp_id,
                entry_id=entry_id,
                current_representation_id=representation_id,
                representation_generation=generation,
            )
            self._session.add(state)
        else:
            state.current_representation_id = representation_id
            state.representation_generation = generation
            state.updated_at = _now()
        await self._flush()
        return state

    async def finalize_candidate(
        self,
        *,
        candidate_id: uuid.UUID,
        finalized_representation_id: uuid.UUID,
    ) -> WorkpaperRepresentationUpgradeCandidate:
        """candidate → finalized：只创建新 representation generation，不动 content revision。

        `ready` 之前（缺 approved contract/bundle）不得 finalize；候选永不进入 resolver。
        """
        cand = (
            await self._session.execute(
                sa.select(WorkpaperRepresentationUpgradeCandidate)
                .where(WorkpaperRepresentationUpgradeCandidate.id == candidate_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if cand is None:
            raise BundleIntegrityError(f"upgrade candidate 不存在: {candidate_id}")
        # 🔴 顺序刻意是「语义专属校验在前、状态边在后」：若先跑 assert_transition，
        # `staged → finalized` 这条非法边会先抛 StateTransitionError，把 bundle/contract
        # 缺失这条判据永久遮蔽成不可达分支（变异检验实测判 GREEN）。
        if cand.target_definition_bundle_id is None or cand.target_contract_definition_id is None:
            raise BundleIntegrityError(
                "candidate finalize 前必须补齐 approved contract + bundle"
                f"（contract={cand.target_contract_definition_id!r} "
                f"bundle={cand.target_definition_bundle_id!r}）"
            )
        assert_transition("candidate", cand.state, CandidateState.finalized)
        await self.assert_bundle_usable(cand.target_definition_bundle_id)
        cand.state = CandidateState.finalized.value
        cand.finalized_representation_id = finalized_representation_id
        cand.finalized_at = _now()
        await self._flush()
        return cand

    async def attach_candidate_definitions(
        self,
        *,
        candidate_id: uuid.UUID,
        contract_definition_id: uuid.UUID,
        definition_bundle_id: uuid.UUID,
        correlation_id: str,
        actor_id: uuid.UUID | None = None,
        detail: dict[str, Any] | None = None,
    ) -> tuple[WorkpaperRepresentationUpgradeCandidate, WorkpaperRepresentationCandidateEvent]:
        """把已 approved 的 contract + bundle 绑到 `awaiting_contract` candidate 上（Task 76）。

        ═══ 为什么必须是**新增**方法而不是放宽 `create_upgrade_candidate` ═══

        V151 起本表就允许 `target_contract_definition_id` / `target_definition_bundle_id`
        在**创建时**给值，但两个 instrumentation upgrader（Excel/Word）都恒写 `None` ——
        它们无权发布 contract/bundle。于是仓储上只有 create-with-bundle、**没有** attach：
        approved 供给到位后没有任何受控入口能把它绑上去，`assert_candidate_finalizable`
        永远停在「缺 approved per-entry contract」。本方法就是补这一格。

        ═══ 四条禁令各自落成可分辨的失败 ═══

        * candidate 不存在                     → :class:`BundleIntegrityError`
        * candidate 已 finalize（或非 awaiting_contract）→ :class:`StateTransitionError`
          （经 `assert_transition("candidate", ...)`，`finalized` 出边为空集）
        * contract child 不是 approved contract → :class:`BundleIntegrityError`
        * bundle 未 approved / typed slot 非法   → :class:`BundleIntegrityError`
          （委托 :meth:`assert_bundle_usable`，**不复制**一份 slot 校验）

        判定顺序刻意是「行锁 → 语义专属判据 → 状态边」：与 :meth:`finalize_candidate`
        同一理由，先跑状态边会把「contract/bundle 非 approved」这条判据遮蔽成不可达分支。

        本方法**不**创建 representation、**不**切 entry pointer、**不**碰
        `content_revision`：attach 只把两个 FK 从 NULL 变成 approved 身份并把状态推到
        `ready`，candidate 依旧 non-current（Requirement 6.18 / Property 67）。
        """
        cand = (
            await self._session.execute(
                sa.select(WorkpaperRepresentationUpgradeCandidate)
                .where(WorkpaperRepresentationUpgradeCandidate.id == candidate_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if cand is None:
            raise BundleIntegrityError(f"upgrade candidate 不存在: {candidate_id}")
        contract = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id == contract_definition_id
                )
            )
        ).scalar_one_or_none()
        if contract is None or contract.kind != "contract":
            raise BundleIntegrityError(
                f"attach 的 target contract {contract_definition_id} 不存在或 kind 不是 "
                f"contract（实得 {None if contract is None else contract.kind!r}）"
            )
        if contract.state != "approved":
            raise BundleIntegrityError(
                f"attach 的 per-entry contract state={contract.state}，只有 approved 可绑定"
            )
        bundle = await self.assert_bundle_usable(definition_bundle_id)
        contract_slot_ref = f"definition:{contract_definition_id}"
        if bundle.contract_slot_ref != contract_slot_ref:
            raise BundleIntegrityError(
                f"attach 的 bundle contract slot ref={bundle.contract_slot_ref!r} 与 target "
                f"contract {contract_slot_ref!r} 不一致 —— 不得把 A 的 contract 绑到 B 的 bundle"
            )
        # 状态边最后跑：`finalized` 出边为空集 ⇒ 已 finalize 的 candidate 在此被拒。
        assert_transition("candidate", cand.state, CandidateState.ready)
        from_state = str(cand.state)
        cand.target_contract_definition_id = contract_definition_id
        cand.target_definition_bundle_id = definition_bundle_id
        cand.state = CandidateState.ready.value
        await self._flush()
        event = await self.append_candidate_event(
            candidate_id=candidate_id,
            event_type="contract_bundle_attached",
            from_state=from_state,
            to_state=CandidateState.ready.value,
            contract_definition_id=contract_definition_id,
            definition_bundle_id=definition_bundle_id,
            definition_bundle_sha256=bundle.canonical_payload_sha256,
            correlation_id=correlation_id,
            actor_id=actor_id,
            detail=detail,
        )
        return cand, event

    async def append_candidate_event(
        self,
        *,
        candidate_id: uuid.UUID,
        event_type: str,
        from_state: str,
        to_state: str,
        correlation_id: str,
        contract_definition_id: uuid.UUID | None = None,
        definition_bundle_id: uuid.UUID | None = None,
        definition_bundle_sha256: str | None = None,
        actor_id: uuid.UUID | None = None,
        detail: dict[str, Any] | None = None,
    ) -> WorkpaperRepresentationCandidateEvent:
        """写一条 candidate append-only 审计事件（V153；UPDATE/DELETE 由 DB 触发器拒绝）。"""
        if not correlation_id or not str(correlation_id).strip():
            raise IdentityError(
                "candidate 审计事件必须带 correlation_id —— 无相关性 id 的审计轨无法把"
                "「谁在哪次调用里绑了哪份身份」串起来"
            )
        seq = await self._next_sequence_no(
            WorkpaperRepresentationCandidateEvent,
            WorkpaperRepresentationCandidateEvent.candidate_id,
            candidate_id,
        )
        ev = WorkpaperRepresentationCandidateEvent(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            sequence_no=seq,
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            contract_definition_id=contract_definition_id,
            definition_bundle_id=definition_bundle_id,
            definition_bundle_sha256=definition_bundle_sha256,
            actor_id=actor_id,
            correlation_id=str(correlation_id),
            detail=dict(detail or {}),
        )
        self._session.add(ev)
        await self._flush()
        return ev

    async def create_pending_mutation(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        sheet_key: str,
        user_id: uuid.UUID,
        expected_revision: int,
        payload_artifact_id: uuid.UUID,
        payload_sha256: str,
        idempotency_key: str,
        ttl: timedelta = timedelta(minutes=10),
    ) -> WorkpaperPendingMutation:
        """HTML flush 只创建它 —— **不推进 revision、不建 content version**（Task 15/18）。

        `(wp_id, entry_id, user_id, idempotency_key)` 是唯一键：同 key 重复 flush 命中
        既有行，由 `ContentMutationService` 判「逐项等值即重放、不等值即 409」
        （Property 10）。TTL 由 `ck_wppm_ttl` 强制晚于 `created_at`。
        """
        if not is_digest(payload_sha256):
            raise IdentityError(f"pending mutation payload digest 非法: {payload_sha256!r}")
        if expected_revision < 0:
            raise ScopeIntegrityError(
                f"pending mutation expected_revision 不得为负: {expected_revision}"
            )
        row = WorkpaperPendingMutation(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            sheet_key=sheet_key,
            user_id=user_id,
            expected_revision=expected_revision,
            payload_artifact_id=payload_artifact_id,
            payload_sha256=payload_sha256,
            idempotency_key=idempotency_key,
            state=PendingMutationState.pending.value,
            expires_at=_now() + ttl,
        )
        self._session.add(row)
        await self._flush()
        await self.register_scope(
            resource_kind=ScopeResourceKind.pending_mutation,
            resource_id=str(row.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
        )
        return row

    # ─────────────────────────────────────────────────────────────────
    # 5. request + nullable-application operation shell
    # ─────────────────────────────────────────────────────────────────

    async def create_forcesave_request_with_shell(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        room_id: uuid.UUID,
        kind: RequestKind | str,
        initiated_by_participant_id: uuid.UUID,
        initiator_permission_epoch: int,
        client_edit_epoch: int,
        client_base_version_id: uuid.UUID,
        client_base_representation_id: uuid.UUID,
        client_base_projection_sha256: str,
        definition_bundle_id: uuid.UUID,
        authority_model_definition_id: uuid.UUID,
        adapter_build_digest: str,
        contributor_snapshot_digest: str,
        idempotency_key: str,
        frozen_request_fingerprint: str,
        direction: OperationDirection | str = OperationDirection.oo_to_html,
        created_by: uuid.UUID | None = None,
    ) -> ForcesaveRequestOutcome:
        """Command Service 之前，在**一个事务**里冻结 request + 建 `application_id=NULL` shell。

        幂等语义（Requirement 4.1 / Property 64）：

        * 唯一范围固定 `(room_id, generation, initiated_by_participant_id, kind, idempotency_key)`；
        * cache hit 必须 `frozen_request_fingerprint` **逐项等值**才返回旧 request/operation；
        * 跨 participant / 跨 kind / payload 不等 ⇒ :class:`IdempotencyConflictError`（409），
          且异常里**不携带旧 request/operation id**。
        """
        req_kind = kind if isinstance(kind, RequestKind) else RequestKind(kind)
        if not is_digest(frozen_request_fingerprint):
            raise IdentityError("frozen_request_fingerprint 必须是非空非全零 digest")
        room = await self.lock_room(room_id)
        bundle = await self.assert_bundle_usable(definition_bundle_id)
        if bundle.authority_model_definition_id != authority_model_definition_id:
            raise BundleIntegrityError("request 的 authority model 与 bundle child 不一致")

        # 同 (room, generation, key) 的任何既有 request 都要检查 —— 复合唯一键本身
        # 不会阻止「另一个 participant 复用同 key」，但协议要求那也是 409。
        siblings = (
            (
                await self._session.execute(
                    sa.select(WorkpaperForcesaveRequest)
                    .where(
                        WorkpaperForcesaveRequest.room_id == room_id,
                        WorkpaperForcesaveRequest.generation == room.generation,
                        WorkpaperForcesaveRequest.idempotency_key == idempotency_key,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        for prior in siblings:
            same_slot = (
                prior.initiated_by_participant_id == initiated_by_participant_id
                and prior.kind == req_kind.value
            )
            if not same_slot:
                raise IdempotencyConflictError(
                    "Idempotency-Key 被另一个 participant 或另一种 kind 复用 —— "
                    "唯一范围是 (room, generation, initiator, kind, key)，不得返回旧标识"
                )
            if prior.frozen_request_fingerprint.strip() != frozen_request_fingerprint.strip():
                raise IdempotencyConflictError(
                    "同 Idempotency-Key 但 frozen request fingerprint 不等值"
                    "（confirmation/base/representation/bundle/fence/contributor 至少一项不同）"
                )
            shell = (
                await self._session.execute(
                    sa.select(WorkpaperSyncOperation).where(
                        WorkpaperSyncOperation.forcesave_request_id == prior.id
                    )
                )
            ).scalar_one_or_none()
            if shell is None:
                raise ScopeIntegrityError(
                    f"request {prior.id} 缺 operation shell —— 冻结事务必须同时建 shell"
                )
            return ForcesaveRequestOutcome(request=prior, operation=shell, cache_hit=True)

        request_sequence = int(room.latest_request_sequence) + 1
        req = WorkpaperForcesaveRequest(
            id=uuid.uuid4(),
            room_id=room_id,
            generation=room.generation,
            request_sequence=request_sequence,
            kind=req_kind.value,
            initiated_by_participant_id=initiated_by_participant_id,
            initiator_permission_epoch=initiator_permission_epoch,
            client_edit_epoch=client_edit_epoch,
            write_fence_epoch=room.write_fence_epoch,
            client_base_version_id=client_base_version_id,
            client_base_representation_id=client_base_representation_id,
            client_base_projection_sha256=client_base_projection_sha256,
            definition_bundle_id=definition_bundle_id,
            definition_bundle_sha256=bundle.canonical_payload_sha256,
            authority_model_definition_id=authority_model_definition_id,
            authority_model_definition_sha256=bundle.authority_model_definition_sha256,
            adapter_build_digest=adapter_build_digest,
            contributor_snapshot_digest=contributor_snapshot_digest,
            idempotency_key=idempotency_key,
            frozen_request_fingerprint=frozen_request_fingerprint,
            state=RequestState.frozen.value,
        )
        self._session.add(req)
        await self._flush()
        await self.register_scope(
            resource_kind=ScopeResourceKind.forcesave_request,
            resource_id=str(req.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            generation=room.generation,
        )

        op = WorkpaperSyncOperation(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            forcesave_request_id=req.id,
            application_id=None,
            duplicate_of_operation_id=None,
            initiated_by_participant_id=initiated_by_participant_id,
            direction=(
                direction.value
                if isinstance(direction, OperationDirection)
                else OperationDirection(direction).value
            ),
            state=OperationState.created.value,
            definition_bundle_id=definition_bundle_id,
            definition_bundle_sha256=bundle.canonical_payload_sha256,
            authority_model_definition_id=authority_model_definition_id,
            authority_model_definition_sha256=bundle.authority_model_definition_sha256,
            created_by=created_by,
        )
        self._session.add(op)
        await self._flush()
        # pre-correlation 三态自证：application 与 duplicate 必须都为空
        assert classify_operation_shape(
            application_id=op.application_id,
            duplicate_of_operation_id=op.duplicate_of_operation_id,
            state=op.state,
        ) is OperationShape.pre_correlation
        await self.register_scope(
            resource_kind=ScopeResourceKind.sync_operation,
            resource_id=str(op.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            generation=room.generation,
        )
        await self.append_operation_event(
            operation_id=op.id,
            from_state=None,
            to_state=OperationState.created,
            stage="request_frozen",
            actor_type=ActorType.user,
            actor_id=created_by,
            origin_request_sequence=request_sequence,
        )

        room.latest_request_sequence = request_sequence
        room.updated_at = _now()
        await self._flush()
        return ForcesaveRequestOutcome(request=req, operation=op, cache_hit=False)

    # ─────────────────────────────────────────────────────────────────
    # 6. durable correlation：create-or-hit application
    # ─────────────────────────────────────────────────────────────────

    async def correlate_durable_incoming(
        self,
        *,
        operation_id: uuid.UUID,
        incoming_artifact_id: uuid.UUID,
        current_revision: int,
        adapter_id: str,
        delivery_id: uuid.UUID | None = None,
        actor_type: ActorType = ActorType.callback,
        actor_id: uuid.UUID | None = None,
    ) -> CorrelationOutcome:
        """request-first correlation：durable incoming ⇒ 创建或命中 application。

        winner 把自己的 shell 绑成唯一 primary；loser 保持 `application_id=NULL`、
        写 `duplicate_of_operation_id=<primary>` 与 terminal `duplicate` event，同时
        对 application 原子执行 `effective_request_sequence=GREATEST(...)` 并把 room 的
        `latest_durable_application_id/latest_durable_sequence` 指向该 canonical application。

        并发下的 create-or-hit：`INSERT ... ON CONFLICT (application_key) DO NOTHING`
        后若无返回行，说明别人赢了 —— 再 `SELECT ... FOR UPDATE`（会等对方提交）走 fold 分支。
        """
        op = (
            await self._session.execute(
                sa.select(WorkpaperSyncOperation)
                .where(WorkpaperSyncOperation.id == operation_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if op is None:
            raise ScopeIntegrityError(f"operation 不存在: {operation_id}")
        shape = classify_operation_shape(
            application_id=op.application_id,
            duplicate_of_operation_id=op.duplicate_of_operation_id,
            state=op.state,
        )
        if shape is not OperationShape.pre_correlation:
            raise DuplicateLinkError(
                f"correlation 只接受 pre-correlation shell，实得 {shape.value}"
            )
        if op.forcesave_request_id is None:
            raise ScopeIntegrityError("normal/recovery correlation 必须有 frozen request")

        prior_state = OperationState(op.state)
        req = (
            await self._session.execute(
                sa.select(WorkpaperForcesaveRequest).where(
                    WorkpaperForcesaveRequest.id == op.forcesave_request_id
                )
            )
        ).scalar_one()
        room = await self.lock_room(req.room_id)
        # incoming digest 取自 artifact 本身：DB trigger 也要求二者一致，
        # 让调用方另传一个可能不同步的 sha256 是伪身份入口。
        incoming = await self.assert_incoming_durable(incoming_artifact_id)
        incoming_sha256 = incoming.sha256

        key = compute_application_key(
            wp_id=op.wp_id,
            room_id=req.room_id,
            generation=req.generation,
            frozen_client_base_version_id=req.client_base_version_id,
            frozen_client_base_representation_id=req.client_base_representation_id,
            incoming_sha256=incoming_sha256,
            definition_bundle_sha256=req.definition_bundle_sha256,
            authority_model_definition_sha256=req.authority_model_definition_sha256,
            adapter_build_digest=req.adapter_build_digest,
        )

        app_id = uuid.uuid4()
        now = _now()
        inserted = (
            await self._session.execute(
                pg_insert(WorkpaperContentApplication)
                .values(
                    id=app_id,
                    project_id=op.project_id,
                    wp_id=op.wp_id,
                    entry_id=op.entry_id,
                    room_id=req.room_id,
                    generation=req.generation,
                    origin_request_id=req.id,
                    application_key=key,
                    client_edit_epoch=req.client_edit_epoch,
                    origin_request_sequence=req.request_sequence,
                    effective_request_sequence=req.request_sequence,
                    base_version_id=req.client_base_version_id,
                    base_representation_id=req.client_base_representation_id,
                    current_revision=current_revision,
                    incoming_artifact_id=incoming_artifact_id,
                    incoming_sha256=incoming_sha256,
                    definition_bundle_id=req.definition_bundle_id,
                    definition_bundle_sha256=req.definition_bundle_sha256,
                    authority_model_definition_id=req.authority_model_definition_id,
                    authority_model_definition_sha256=req.authority_model_definition_sha256,
                    adapter_id=adapter_id,
                    adapter_build_digest=req.adapter_build_digest,
                    contributor_snapshot_digest=req.contributor_snapshot_digest,
                    state=ApplicationState.queued.value,
                    created_at=now,
                    durable_at=now,
                )
                .on_conflict_do_nothing(index_elements=["application_key"])
                .returning(WorkpaperContentApplication.id)
            )
        ).first()

        app = (
            await self._session.execute(
                sa.select(WorkpaperContentApplication)
                .where(WorkpaperContentApplication.application_key == key)
                .with_for_update()
            )
        ).scalar_one()
        created = inserted is not None and app.id == app_id

        if created:
            await self.register_scope(
                resource_kind=ScopeResourceKind.content_application,
                resource_id=str(app.id),
                project_id=op.project_id,
                wp_id=op.wp_id,
                entry_id=op.entry_id,
                room_id=req.room_id,
                generation=req.generation,
            )
            op.application_id = app.id
            op.application_bound_at = now
            assert_transition("operation", op.state, OperationState.application_bound)
            op.state = OperationState.application_bound.value
            await self._flush()
            assert classify_operation_shape(
                application_id=op.application_id,
                duplicate_of_operation_id=op.duplicate_of_operation_id,
                state=op.state,
            ) is OperationShape.primary
            await self.append_application_event(
                application_id=app.id,
                event_type=ApplicationEventType.created,
                to_state=ApplicationState.queued,
                origin_request_sequence=app.origin_request_sequence,
                effective_request_sequence=app.effective_request_sequence,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            await self.append_operation_event(
                operation_id=op.id,
                from_state=prior_state,
                to_state=OperationState.application_bound,
                stage="application_bound",
                actor_type=actor_type,
                actor_id=actor_id,
                origin_request_sequence=app.origin_request_sequence,
                effective_request_sequence=app.effective_request_sequence,
            )
            folded_from: int | None = None
            primary_op_id = op.id
            out_shape = OperationShape.primary
        else:
            primary = (
                await self._session.execute(
                    sa.select(WorkpaperSyncOperation)
                    .where(WorkpaperSyncOperation.application_id == app.id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if primary is None:
                raise DuplicateLinkError(
                    f"application {app.id} 已存在但无 primary operation —— stranded shell"
                )
            previous = int(app.effective_request_sequence)
            folded = fold_effective_sequence(previous, int(req.request_sequence))
            folded_from = previous if folded != previous else None
            if folded != previous:
                app.effective_request_sequence = folded
                await self._flush()
                await self.append_application_event(
                    application_id=app.id,
                    event_type=ApplicationEventType.sequence_folded,
                    origin_request_sequence=app.origin_request_sequence,
                    effective_request_sequence=folded,
                    folded_request_id=req.id,
                    room_latest_durable_sequence=folded,
                    actor_type=actor_type,
                    actor_id=actor_id,
                )
            # 同 canonical application 只 fold，不得 self-supersede
            if app.superseded_by_application_id == app.id:
                raise DuplicateLinkError("同 canonical application 不得 self-supersede")

            loser = OperationScope(
                operation_id=op.id,
                project_id=op.project_id,
                wp_id=op.wp_id,
                entry_id=op.entry_id,
                room_id=op.room_id,
                definition_bundle_id=op.definition_bundle_id,
                authority_model_definition_sha256=op.authority_model_definition_sha256,
                application_id=op.application_id,
                duplicate_of_operation_id=op.duplicate_of_operation_id,
                state=prior_state,
            )
            target = OperationScope(
                operation_id=primary.id,
                project_id=primary.project_id,
                wp_id=primary.wp_id,
                entry_id=primary.entry_id,
                room_id=primary.room_id,
                definition_bundle_id=primary.definition_bundle_id,
                authority_model_definition_sha256=primary.authority_model_definition_sha256,
                application_id=primary.application_id,
                duplicate_of_operation_id=primary.duplicate_of_operation_id,
                state=OperationState(primary.state),
            )
            assert_direct_primary(loser=loser, target=target, application_id=app.id)
            assert_transition("operation", op.state, OperationState.duplicate)
            op.duplicate_of_operation_id = primary.id
            op.state = OperationState.duplicate.value
            op.finished_at = now
            await self._flush()
            assert classify_operation_shape(
                application_id=op.application_id,
                duplicate_of_operation_id=op.duplicate_of_operation_id,
                state=op.state,
            ) is OperationShape.duplicate
            await self.append_operation_event(
                operation_id=op.id,
                from_state=prior_state,
                to_state=OperationState.duplicate,
                stage="duplicate_of_primary",
                actor_type=actor_type,
                actor_id=actor_id,
                origin_request_sequence=app.origin_request_sequence,
                effective_request_sequence=app.effective_request_sequence,
                superseded_by=primary.id,
            )
            primary_op_id = primary.id
            out_shape = OperationShape.duplicate

        # room durable fence 与 canonical application 原子同事务更新
        await self.advance_room_durable_fence(
            room=room,
            application_id=app.id,
            effective_request_sequence=int(app.effective_request_sequence),
        )
        req.state = RequestState.correlated.value
        await self._flush()

        if delivery_id is not None:
            await self.bind_delivery_to_application(
                delivery_id=delivery_id,
                incoming_artifact_id=incoming_artifact_id,
                application_id=app.id,
                operation_id=op.id,
                forcesave_request_id=req.id,
                correlation_result=(
                    CorrelationResult.request if created else CorrelationResult.existing_application
                ),
            )

        return CorrelationOutcome(
            application=app,
            operation=op,
            shape=out_shape,
            created_application=created,
            folded_from_sequence=folded_from,
            effective_request_sequence=int(app.effective_request_sequence),
            canonical_primary_operation_id=primary_op_id,
        )

    async def advance_room_durable_fence(
        self,
        *,
        room: WorkpaperOoRoom,
        application_id: uuid.UUID,
        effective_request_sequence: int,
    ) -> None:
        """单调推进 room 的 canonical application + durable sequence（同事务）。

        公开（原为 `_advance_room_durable_fence`）是为了让 Task 21 的
        :meth:`RoomService.advance_server_last_applied` /
        :meth:`RoomService.fold_same_application_request` **委派**它而不是各写一份
        room 侧算术。两份实现必然漂移，而 room fence 只认一份 —— 序号推进的唯一落点
        就在这里（`latest_request_sequence` 的追平也只在这里做）。
        """
        if effective_request_sequence < int(room.latest_durable_sequence):
            return
        room.latest_durable_application_id = application_id
        room.latest_durable_sequence = max(
            int(room.latest_durable_sequence), effective_request_sequence
        )
        if int(room.latest_request_sequence) < int(room.latest_durable_sequence):
            room.latest_request_sequence = int(room.latest_durable_sequence)
        room.updated_at = _now()
        await self._flush()

    async def supersede_application(
        self, *, old_application_id: uuid.UUID, new_application_id: uuid.UUID
    ) -> WorkpaperContentApplication:
        """只有「较新且 canonical application 不同」的 durable snapshot 才可 supersede 旧 application。"""
        old = (
            await self._session.execute(
                sa.select(WorkpaperContentApplication)
                .where(WorkpaperContentApplication.id == old_application_id)
                .with_for_update()
            )
        ).scalar_one()
        new = (
            await self._session.execute(
                sa.select(WorkpaperContentApplication).where(
                    WorkpaperContentApplication.id == new_application_id
                )
            )
        ).scalar_one_or_none()
        if new is None:
            raise ScopeIntegrityError(f"supersede 目标 application 不存在: {new_application_id}")
        assert_supersede(
            old_application_id=old.id,
            new_application_id=new.id,
            old_effective_sequence=int(old.effective_request_sequence),
            new_effective_sequence=int(new.effective_request_sequence),
        )
        assert_transition("application", old.state, ApplicationState.superseded)
        old.superseded_by_application_id = new.id
        old.state = ApplicationState.superseded.value
        old.finished_at = _now()
        await self._flush()
        await self.append_application_event(
            application_id=old.id,
            event_type=ApplicationEventType.superseded,
            to_state=ApplicationState.superseded,
            origin_request_sequence=int(old.origin_request_sequence),
            effective_request_sequence=int(old.effective_request_sequence),
            actor_type=ActorType.system,
        )
        return old

    async def resolve_canonical_operation(
        self, operation_id: uuid.UUID
    ) -> tuple[WorkpaperSyncOperation, OperationShape]:
        """GET/timeline/retry/resolve 的规范化入口：先校验 requested operation，再 canonicalize。

        requested operation 若是 `application_id=NULL` 的 terminal duplicate，必须先通过
        direct-primary invariant 校验，才允许跟随 canonical primary 的 application/result。
        只要求 canonical primary 唯一绑定 application，**不要求** 合法 duplicate 自身绑定。
        """
        op = (
            await self._session.execute(
                sa.select(WorkpaperSyncOperation).where(WorkpaperSyncOperation.id == operation_id)
            )
        ).scalar_one_or_none()
        if op is None:
            raise ScopeIntegrityError(f"operation 不存在: {operation_id}")
        shape = classify_operation_shape(
            application_id=op.application_id,
            duplicate_of_operation_id=op.duplicate_of_operation_id,
            state=op.state,
        )
        if shape is not OperationShape.duplicate:
            return op, shape
        primary = (
            await self._session.execute(
                sa.select(WorkpaperSyncOperation).where(
                    WorkpaperSyncOperation.id == op.duplicate_of_operation_id
                )
            )
        ).scalar_one_or_none()
        if primary is None:
            raise DuplicateLinkError("duplicate 指向不存在的 operation")
        assert_direct_primary(
            loser=OperationScope(
                operation_id=op.id,
                project_id=op.project_id,
                wp_id=op.wp_id,
                entry_id=op.entry_id,
                room_id=op.room_id,
                definition_bundle_id=op.definition_bundle_id,
                authority_model_definition_sha256=op.authority_model_definition_sha256,
                application_id=op.application_id,
                duplicate_of_operation_id=op.duplicate_of_operation_id,
                state=OperationState(op.state),
            ),
            target=OperationScope(
                operation_id=primary.id,
                project_id=primary.project_id,
                wp_id=primary.wp_id,
                entry_id=primary.entry_id,
                room_id=primary.room_id,
                definition_bundle_id=primary.definition_bundle_id,
                authority_model_definition_sha256=primary.authority_model_definition_sha256,
                application_id=primary.application_id,
                duplicate_of_operation_id=primary.duplicate_of_operation_id,
                state=OperationState(primary.state),
            ),
            application_id=primary.application_id,  # type: ignore[arg-type]
        )
        return primary, OperationShape.duplicate

    # ─────────────────────────────────────────────────────────────────
    # 7. callback delivery
    # ─────────────────────────────────────────────────────────────────

    async def record_delivery(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        room_id: uuid.UUID,
        generation: int,
        route_credential_id: uuid.UUID,
        callback_status: int,
        delivery_key: str,
        payload_sha256: str | None = None,
        oo_users_digest: str | None = None,
        forcesave_request_id: uuid.UUID | None = None,
        operation_id: uuid.UUID | None = None,
    ) -> WorkpaperCallbackDelivery:
        """登记一次 callback 投递（pre-durable：零 application/recovery owner）。"""
        if not is_digest(delivery_key):
            raise IdentityError("delivery_key 必须是非空非全零 digest")
        assert_delivery_ownership(
            state=DeliveryState.received,
            durable_at_is_set=False,
            application_id=None,
            callback_recovery_case_id=None,
            forcesave_request_id=forcesave_request_id,
        )
        row = WorkpaperCallbackDelivery(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            generation=generation,
            route_credential_id=route_credential_id,
            callback_status=callback_status,
            delivery_key=delivery_key,
            state=DeliveryState.received.value,
            payload_sha256=payload_sha256,
            oo_users_digest=oo_users_digest,
            forcesave_request_id=forcesave_request_id,
            operation_id=operation_id,
        )
        self._session.add(row)
        await self._flush()
        await self.register_scope(
            resource_kind=ScopeResourceKind.callback_delivery,
            resource_id=str(row.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            generation=generation,
        )
        return row

    async def mark_delivery_downloading(
        self, *, delivery_id: uuid.UUID
    ) -> WorkpaperCallbackDelivery:
        """开始流式下载（仍 pre-durable：零 application/recovery owner）。"""
        row = await self._lock_delivery(delivery_id)
        assert_transition("delivery", row.state, DeliveryState.downloading)
        row.state = DeliveryState.downloading.value
        await self._flush()
        return row

    async def bind_delivery_to_application(
        self,
        *,
        delivery_id: uuid.UUID,
        incoming_artifact_id: uuid.UUID,
        application_id: uuid.UUID,
        operation_id: uuid.UUID,
        forcesave_request_id: uuid.UUID | None,
        correlation_result: CorrelationResult,
    ) -> WorkpaperCallbackDelivery:
        """durable sealing 与 application 归属**同一条 UPDATE** 落库。

        🔴 为什么不能拆成「先 durable，再 bind」：V151 的 `ck_wpcd_durable_exactly_one_owner`
        是行级 CHECK（不是 deferred），`durable_at IS NOT NULL` 的那一刻就必须恰有一个
        owner。因此「durable 但尚未归组」在 schema 里根本不是合法中间态 —— 这正是
        Requirement 5.4「归属只以 immutable durable_at 判定」的落地形态：durable fact
        一出现，delivery 就已经属于 application 或 recovery 二者之一。

        `operation_id` 为 primary 时其自身 application 必须相等；为 duplicate 时以其
        **direct primary** 的 application 校验一致。request 与 application 可同时存在，
        不做 XOR。
        """
        row = await self._lock_delivery(delivery_id)
        if row.durable_at is not None and row.application_id == application_id:
            return row  # 幂等重放
        if row.durable_at is not None:
            raise DeliveryOwnershipError(
                "delivery 的 durable fact 已存在且归属于另一个 owner —— durable_at immutable"
            )
        await self.assert_incoming_durable(incoming_artifact_id)
        canonical, _shape = await self.resolve_canonical_operation(operation_id)
        if canonical.application_id != application_id:
            raise DuplicateLinkError(
                "delivery 绑定的 application 与 operation 的 canonical primary application 不一致"
            )
        assert_delivery_ownership(
            state=DeliveryState.durable,
            durable_at_is_set=True,
            application_id=application_id,
            callback_recovery_case_id=row.callback_recovery_case_id,
            forcesave_request_id=forcesave_request_id,
        )
        assert_transition("delivery", row.state, DeliveryState.durable)
        row.incoming_artifact_id = incoming_artifact_id
        row.durable_at = _now()
        row.application_id = application_id
        row.operation_id = operation_id
        row.forcesave_request_id = forcesave_request_id
        row.correlation_result = correlation_result.value
        row.state = DeliveryState.durable.value
        await self._flush()
        assert_transition("delivery", row.state, DeliveryState.acknowledged)
        row.state = DeliveryState.acknowledged.value
        row.response_error = 0
        row.responded_at = _now()
        await self._flush()
        return row

    async def bind_delivery_to_recovery(
        self,
        *,
        delivery_id: uuid.UUID,
        incoming_artifact_id: uuid.UUID,
        recovery_case_id: uuid.UUID,
    ) -> WorkpaperCallbackDelivery:
        """unmatched/ambiguous：durable sealing 与 recovery 归属同事务；三实体全空。"""
        row = await self._lock_delivery(delivery_id)
        if row.durable_at is not None and row.callback_recovery_case_id == recovery_case_id:
            return row  # 幂等重放
        if row.durable_at is not None:
            raise DeliveryOwnershipError(
                "delivery 的 durable fact 已存在且归属于另一个 owner —— durable_at immutable"
            )
        await self.assert_incoming_durable(incoming_artifact_id)
        assert_delivery_ownership(
            state=DeliveryState.durable,
            durable_at_is_set=True,
            application_id=None,
            callback_recovery_case_id=recovery_case_id,
        )
        assert_transition("delivery", row.state, DeliveryState.durable)
        row.incoming_artifact_id = incoming_artifact_id
        row.durable_at = _now()
        row.forcesave_request_id = None
        row.operation_id = None
        row.application_id = None
        row.callback_recovery_case_id = recovery_case_id
        row.correlation_result = CorrelationResult.unmatched.value
        row.state = DeliveryState.durable.value
        await self._flush()
        assert_transition("delivery", row.state, DeliveryState.unmatched)
        row.state = DeliveryState.unmatched.value
        row.response_error = 0
        row.responded_at = _now()
        await self._flush()
        return row

    async def mark_delivery_pre_durable_failure(
        self, *, delivery_id: uuid.UUID, state: DeliveryState, response_error: int
    ) -> WorkpaperCallbackDelivery:
        """鉴权/下载/校验失败：`durable_at` 保持空，application/recovery owner 均为空。"""
        if state not in (DeliveryState.rejected, DeliveryState.error):
            raise DeliveryOwnershipError(
                f"pre-durable 失败只能落 rejected/error，实得 {state.value}"
            )
        row = await self._lock_delivery(delivery_id)
        if row.durable_at is not None:
            raise DeliveryOwnershipError(
                "delivery 已有 durable fact —— 请用 mark_delivery_post_durable_error() 保留 owner"
            )
        assert_transition("delivery", row.state, state)
        row.state = state.value
        row.application_id = None
        row.callback_recovery_case_id = None
        # 🔴 清掉 operation 指针而保留 request 指针：V151 的
        # `wpsync_check_delivery_operation_link` 规定「未归组的 delivery 不得引用已绑定
        # application 的 primary operation」。失败 delivery 若长期挂着 shell，等同一 shell
        # 被后续重试 delivery 绑定 application 后，这条失败行会在 COMMIT 时被 deferred
        # trigger 打红。request↔shell 是 1:1（`uq_wpso_request`），保留 request 即保留可追溯性。
        row.operation_id = None
        row.response_error = response_error
        row.responded_at = _now()
        assert_delivery_ownership(
            state=state,
            durable_at_is_set=False,
            application_id=None,
            callback_recovery_case_id=None,
            forcesave_request_id=row.forcesave_request_id,
        )
        await self._flush()
        return row

    async def mark_delivery_post_durable_error(
        self, *, delivery_id: uuid.UUID, response_error: int = 0
    ) -> WorkpaperCallbackDelivery:
        """durable 之后的处理失败：**保留**既有 owner（application 或 recovery），仍恰一。"""
        row = await self._lock_delivery(delivery_id)
        if row.durable_at is None:
            raise DeliveryOwnershipError(
                "post-durable error 要求 durable fact 已存在（否则应走 pre-durable 分支）"
            )
        assert_transition("delivery", row.state, DeliveryState.error)
        row.state = DeliveryState.error.value
        row.response_error = response_error
        row.responded_at = _now()
        assert_delivery_ownership(
            state=DeliveryState.error,
            durable_at_is_set=True,
            application_id=row.application_id,
            callback_recovery_case_id=row.callback_recovery_case_id,
            forcesave_request_id=row.forcesave_request_id,
        )
        await self._flush()
        return row

    async def _lock_delivery(self, delivery_id: uuid.UUID) -> WorkpaperCallbackDelivery:
        row = (
            await self._session.execute(
                sa.select(WorkpaperCallbackDelivery)
                .where(WorkpaperCallbackDelivery.id == delivery_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise ScopeIntegrityError(f"callback delivery 不存在: {delivery_id}")
        return row

    # ─────────────────────────────────────────────────────────────────
    # 8. recovery case
    # ─────────────────────────────────────────────────────────────────

    async def create_recovery_case(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        room_id: uuid.UUID,
        generation: int,
        source_delivery_key: str,
        incoming_artifact_id: uuid.UUID,
        reason: RecoveryReason | str,
        ttl: timedelta = timedelta(days=14),
        candidate_confirmation_digest: str | None = None,
        candidate_contributor_digest: str | None = None,
    ) -> WorkpaperCallbackRecoveryCase:
        """durable incoming 无法唯一归组时创建 recovery case；claim 前三实体恒空。"""
        await self.assert_incoming_durable(incoming_artifact_id)
        case = WorkpaperCallbackRecoveryCase(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            generation=generation,
            source_delivery_key=source_delivery_key,
            incoming_artifact_id=incoming_artifact_id,
            reason=(reason.value if isinstance(reason, RecoveryReason) else RecoveryReason(reason).value),
            candidate_confirmation_digest=candidate_confirmation_digest,
            candidate_contributor_digest=candidate_contributor_digest,
            state=RecoveryCaseState.unclaimed.value,
            expires_at=_now() + ttl,
        )
        self._session.add(case)
        await self._flush()
        await self.register_scope(
            resource_kind=ScopeResourceKind.recovery_case,
            resource_id=str(case.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            generation=generation,
        )
        await self.append_recovery_case_event(
            case_id=case.id,
            from_state=None,
            to_state=RecoveryCaseState.unclaimed,
            actor_type=ActorType.callback,
        )
        return case

    async def claim_recovery_case(
        self,
        *,
        case_id: uuid.UUID,
        claiming_participant_id: uuid.UUID,
        prior_confirmation_id: uuid.UUID,
        idempotency_key: str,
        current_revision: int,
        adapter_id: str,
        adapter_build_digest: str,
        contributor_snapshot_digest: str,
        actor_id: uuid.UUID | None = None,
    ) -> RecoveryClaimOutcome:
        """authorization-first claim：一个事务内创建唯一 request + shell，并 create-or-hit application。

        commit 前 shell 必须收敛为绑定 application 的 primary，或保持 `application_id=NULL`
        并成为直指 canonical primary 的 terminal duplicate。**不调用 Command Service**。

        🔴 刻意**不**回绑 delivery：unmatched delivery 在 durable sealing 时已归属 recovery
        case，而 V151 的 `durable_at` immutable + `ck_wpcd_no_double_owner` +
        `wpsync_check_delivery_durable_fact`（post-durable 不得丢弃 recovery owner）三者
        联合决定「recovery 归属对该 delivery row 是终态」。canonical application 的记录点是
        `working_paper_callback_recovery_case.application_id`，不是 delivery。
        """
        case = (
            await self._session.execute(
                sa.select(WorkpaperCallbackRecoveryCase)
                .where(WorkpaperCallbackRecoveryCase.id == case_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if case is None:
            raise ScopeIntegrityError(f"recovery case 不存在: {case_id}")

        if case.state == RecoveryCaseState.application_created.value:
            # 幂等命中：三实体已存在，仍需 idempotency key 逐项等值
            if (case.idempotency_key or "") != idempotency_key:
                raise IdempotencyConflictError(
                    "recovery case 已被另一个 Idempotency-Key 认领"
                )
            req = (
                await self._session.execute(
                    sa.select(WorkpaperForcesaveRequest).where(
                        WorkpaperForcesaveRequest.id == case.recovery_request_id
                    )
                )
            ).scalar_one()
            op = (
                await self._session.execute(
                    sa.select(WorkpaperSyncOperation).where(
                        WorkpaperSyncOperation.id == case.operation_id
                    )
                )
            ).scalar_one()
            app = (
                await self._session.execute(
                    sa.select(WorkpaperContentApplication).where(
                        WorkpaperContentApplication.id == case.application_id
                    )
                )
            ).scalar_one()
            return RecoveryClaimOutcome(
                case=case,
                request=req,
                operation=op,
                application=app,
                shape=classify_operation_shape(
                    application_id=op.application_id,
                    duplicate_of_operation_id=op.duplicate_of_operation_id,
                    state=op.state,
                ),
                cache_hit=True,
            )

        assert_transition("recovery_case", case.state, RecoveryCaseState.claiming)
        incoming = await self.assert_incoming_durable(case.incoming_artifact_id)
        confirmation = (
            await self._session.execute(
                sa.select(WorkpaperOoClientConfirmation).where(
                    WorkpaperOoClientConfirmation.id == prior_confirmation_id
                )
            )
        ).scalar_one_or_none()
        if confirmation is None:
            raise ScopeIntegrityError("prior confirmation 不存在")
        if confirmation.room_id != case.room_id or confirmation.generation != case.generation:
            raise ScopeIntegrityError(
                "prior confirmation 必须属于同 room/generation（错误 prior confirmation 不得产生三实体）"
            )
        if confirmation.invalidated_at is not None:
            raise ScopeIntegrityError("prior confirmation 已失效")
        room = await self.lock_room(case.room_id)
        if int(confirmation.write_fence_epoch) != int(room.write_fence_epoch):
            raise ScopeIntegrityError(
                "prior confirmation 的 write fence 已陈旧（generation/fence 不合法不得产生三实体）"
            )

        case.state = RecoveryCaseState.claiming.value
        case.idempotency_key = idempotency_key
        await self._flush()
        await self.append_recovery_case_event(
            case_id=case.id,
            from_state=RecoveryCaseState.unclaimed,
            to_state=RecoveryCaseState.claiming,
            actor_type=ActorType.user,
            actor_id=actor_id,
            authorization_result="granted",
            prior_confirmation_id=prior_confirmation_id,
            definition_bundle_sha256=confirmation.definition_bundle_sha256,
        )

        fingerprint = compute_frozen_request_fingerprint(
            client_confirmation_id=confirmation.id,
            client_base_version_id=confirmation.content_version_id,
            client_base_representation_id=confirmation.representation_id,
            client_base_projection_sha256=confirmation.projection_sha256,
            definition_bundle_sha256=confirmation.definition_bundle_sha256,
            authority_model_definition_sha256=confirmation.authority_model_definition_sha256,
            adapter_build_digest=adapter_build_digest,
            contributor_snapshot_digest=contributor_snapshot_digest,
            client_edit_epoch=0,
            write_fence_epoch=int(room.write_fence_epoch),
            initiator_permission_epoch=0,
        )
        bundle = await self.assert_bundle_usable(confirmation.definition_bundle_id)
        outcome = await self.create_forcesave_request_with_shell(
            project_id=case.project_id,
            wp_id=case.wp_id,
            entry_id=case.entry_id,
            room_id=case.room_id,
            kind=RequestKind.recovery_claim,
            initiated_by_participant_id=claiming_participant_id,
            initiator_permission_epoch=0,
            client_edit_epoch=0,
            client_base_version_id=confirmation.content_version_id,
            client_base_representation_id=confirmation.representation_id,
            client_base_projection_sha256=confirmation.projection_sha256,
            definition_bundle_id=confirmation.definition_bundle_id,
            authority_model_definition_id=bundle.authority_model_definition_id,
            adapter_build_digest=adapter_build_digest,
            contributor_snapshot_digest=contributor_snapshot_digest,
            idempotency_key=idempotency_key,
            frozen_request_fingerprint=fingerprint,
            direction=OperationDirection.oo_to_html,
            created_by=actor_id,
        )
        corr = await self.correlate_durable_incoming(
            operation_id=outcome.operation.id,
            incoming_artifact_id=incoming.id,
            current_revision=current_revision,
            adapter_id=adapter_id,
            actor_type=ActorType.user,
            actor_id=actor_id,
        )

        case.state = RecoveryCaseState.application_created.value
        case.claimed_by_participant_id = claiming_participant_id
        case.prior_confirmation_id = confirmation.id
        case.recovery_request_id = outcome.request.id
        case.application_id = corr.application.id
        case.operation_id = outcome.operation.id
        case.claimed_definition_bundle_id = confirmation.definition_bundle_id
        case.claimed_definition_bundle_sha256 = confirmation.definition_bundle_sha256
        case.claimed_at = _now()
        await self._flush()
        await self.append_recovery_case_event(
            case_id=case.id,
            from_state=RecoveryCaseState.claiming,
            to_state=RecoveryCaseState.application_created,
            actor_type=ActorType.user,
            actor_id=actor_id,
            authorization_result="granted",
            prior_confirmation_id=confirmation.id,
            definition_bundle_sha256=confirmation.definition_bundle_sha256,
        )
        return RecoveryClaimOutcome(
            case=case,
            request=outcome.request,
            operation=outcome.operation,
            application=corr.application,
            shape=corr.shape,
            cache_hit=False,
        )

    async def terminate_recovery_download_only(
        self, *, case_id: uuid.UUID, actor_id: uuid.UUID | None = None
    ) -> WorkpaperCallbackRecoveryCase:
        """download-only 终结：只记录 actor/authorization/artifact access，永不创建三实体。"""
        case = (
            await self._session.execute(
                sa.select(WorkpaperCallbackRecoveryCase)
                .where(WorkpaperCallbackRecoveryCase.id == case_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if case is None:
            raise ScopeIntegrityError(f"recovery case 不存在: {case_id}")
        # 🔴 顺序同 finalize_candidate：语义专属的「三实体恒空」在前，状态边在后。
        # 反过来写会让 `application_created → download_only` 这条非法边先抛
        # StateTransitionError，把零三实体判据遮蔽成不可达分支。
        # 收成**一个**布尔量再判：写成三段 `or` 时，变异只短路其中一段会被另两段遮蔽，
        # 判定退化成 GREEN（首轮实测）。单一真源布尔让「零三实体」这条判据可被证明。
        has_any_entity = any(
            (case.recovery_request_id, case.application_id, case.operation_id)
        )
        if has_any_entity:
            raise ScopeIntegrityError(
                "download-only case 不得携带 request/application/operation（三实体恒空）"
                f"（request={case.recovery_request_id!r} application={case.application_id!r} "
                f"operation={case.operation_id!r}）"
            )
        assert_transition("recovery_case", case.state, RecoveryCaseState.download_only)
        prior = RecoveryCaseState(case.state)
        case.state = RecoveryCaseState.download_only.value
        await self._flush()
        await self.append_recovery_case_event(
            case_id=case.id,
            from_state=prior,
            to_state=RecoveryCaseState.download_only,
            actor_type=ActorType.user,
            actor_id=actor_id,
            authorization_result="download_only",
        )
        return case

    # ─────────────────────────────────────────────────────────────────
    # 9. close intent / barrier / leader
    # ─────────────────────────────────────────────────────────────────

    async def create_close_intent(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        room_id: uuid.UUID,
        participant_id: uuid.UUID,
        client_confirmation_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> WorkpaperOoCloseIntent:
        """在 room row lock 内把 participant `active→closing` 并推进 close barrier。

        `closing` 不再计入 active confirmed editor 仲裁集合（Requirement 2.6 / 4.10），
        因此后续 intent 看不到已 closing 的 participant 作为 active。
        """
        room = await self.lock_room(room_id)
        participant = (
            await self._session.execute(
                sa.select(WorkpaperOoParticipant)
                .where(WorkpaperOoParticipant.id == participant_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if participant is None:
            raise ScopeIntegrityError(f"participant 不存在: {participant_id}")
        confirmation = (
            await self._session.execute(
                sa.select(WorkpaperOoClientConfirmation).where(
                    WorkpaperOoClientConfirmation.id == client_confirmation_id
                )
            )
        ).scalar_one_or_none()
        if confirmation is None or confirmation.room_id != room_id:
            raise ScopeIntegrityError("close intent 必须引用同 room 的 prior confirmation")
        if confirmation.participant_id != participant_id:
            raise ScopeIntegrityError("close intent 的 confirmation 必须属于该 participant")

        assert_transition("participant", participant.state, ParticipantState.closing)
        participant.state = ParticipantState.closing.value
        participant.updated_at = _now()

        next_seq = int(
            (
                await self._session.execute(
                    sa.select(sa.func.coalesce(sa.func.max(WorkpaperOoCloseIntent.intent_sequence), 0))
                    .where(
                        WorkpaperOoCloseIntent.room_id == room_id,
                        WorkpaperOoCloseIntent.generation == room.generation,
                    )
                )
            ).scalar_one()
        ) + 1
        room.close_barrier_epoch = int(room.close_barrier_epoch) + 1
        if RoomState(room.state) in (RoomState.opening, RoomState.active):
            assert_transition("room", room.state, RoomState.close_barrier)
            room.state = RoomState.close_barrier.value
        room.updated_at = _now()

        intent = WorkpaperOoCloseIntent(
            id=uuid.uuid4(),
            room_id=room_id,
            generation=room.generation,
            participant_id=participant_id,
            client_confirmation_id=client_confirmation_id,
            intent_sequence=next_seq,
            barrier_epoch=int(room.close_barrier_epoch),
            eligibility_epoch=int(room.close_leader_eligibility_epoch),
            state=CloseIntentState.created.value,
        )
        self._session.add(intent)
        await self._flush()
        await self.register_scope(
            resource_kind=ScopeResourceKind.close_intent,
            resource_id=str(intent.id),
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            generation=room.generation,
        )
        await self.append_close_intent_event(
            intent_id=intent.id,
            from_state=None,
            to_state=CloseIntentState.created,
            eligibility_epoch=int(room.close_leader_eligibility_epoch),
            actor_type=ActorType.user,
            actor_id=actor_id,
        )
        return intent

    async def reconcile_close_intents(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        entry_id: str,
        room_id: uuid.UUID,
        adapter_build_digest: str,
        contributor_snapshot_digest: str,
    ) -> CloseReconcileOutcome:
        """幂等 reconciler：在 room lock 下决定 leader / successor / no-successor 终态。

        规则（Requirement 4.10 / Property 63）：

        1. active 首次归零 + 全部 barrier predecessor 安全终结 ⇒ 按最高
           `(intent_sequence, id)` 提升唯一 leader 为 `close_capture` request；
        2. leader 在 promotion **前**失去资格 ⇒ 旧 intent 记 `authorization_stale`，
           eligibility epoch 递增，从仍合法 intents 中按同一 comparator 选 successor；
        3. 无合法 successor ⇒ 不建 request，原子 supersede generation，未终结 intents
           置 `recovery_required`（显式终态，不得永久 blocked，也不得用 route identity）；
        4. **同 eligibility snapshot 重放不得换 leader**，也不得产生第二 capture。
        """
        room = await self.lock_room(room_id)
        intents = (
            (
                await self._session.execute(
                    sa.select(WorkpaperOoCloseIntent)
                    .where(
                        WorkpaperOoCloseIntent.room_id == room_id,
                        WorkpaperOoCloseIntent.generation == room.generation,
                    )
                    .order_by(
                        WorkpaperOoCloseIntent.intent_sequence.desc(),
                        WorkpaperOoCloseIntent.id.desc(),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        if not intents:
            return CloseReconcileOutcome(
                leader_intent_id=None,
                promoted_request_id=None,
                capture_created=False,
                eligibility_epoch=int(room.close_leader_eligibility_epoch),
                eligibility_digest=room.close_leader_eligibility_digest,
                authorization_stale_intent_ids=(),
                no_successor=False,
            )

        participants = {
            p.id: p
            for p in (
                await self._session.execute(
                    sa.select(WorkpaperOoParticipant).where(
                        WorkpaperOoParticipant.room_id == room_id
                    )
                )
            )
            .scalars()
            .all()
        }

        def eligible(intent: WorkpaperOoCloseIntent) -> bool:
            p = participants.get(intent.participant_id)
            if p is None:
                return False
            if ParticipantState(p.state) is not ParticipantState.closing:
                return False
            if p.revoked_at is not None:
                return False
            if p.expires_at is not None and p.expires_at <= _now():
                return False
            return CloseIntentState(intent.state) in (
                CloseIntentState.created,
                CloseIntentState.ordinary_forcesaving,
                CloseIntentState.waiting_barrier,
                CloseIntentState.leader_ready,
                CloseIntentState.retryable_blocked,
                CloseIntentState.successor_selected,
            )

        already_promoted = next(
            (i for i in intents if CloseIntentState(i.state) is CloseIntentState.promoted), None
        )
        if already_promoted is not None:
            # 已 promotion：授权失效只能由最终 fence 走 recovery，绝不再选 successor
            return CloseReconcileOutcome(
                leader_intent_id=already_promoted.id,
                promoted_request_id=already_promoted.promoted_request_id,
                capture_created=False,
                eligibility_epoch=int(room.close_leader_eligibility_epoch),
                eligibility_digest=room.close_leader_eligibility_digest,
                authorization_stale_intent_ids=(),
                no_successor=False,
            )

        stale_ids: list[uuid.UUID] = []
        current_leader = next(
            (i for i in intents if i.id == room.close_leader_intent_id), None
        )
        if current_leader is not None and not eligible(current_leader):
            prior = CloseIntentState(current_leader.state)
            assert_transition("close_intent", prior, CloseIntentState.authorization_stale)
            current_leader.state = CloseIntentState.authorization_stale.value
            current_leader.reconciled_at = _now()
            room.close_leader_intent_id = None
            room.close_leader_eligibility_epoch = int(room.close_leader_eligibility_epoch) + 1
            await self._flush()
            await self.append_close_intent_event(
                intent_id=current_leader.id,
                from_state=prior,
                to_state=CloseIntentState.authorization_stale,
                eligibility_epoch=int(room.close_leader_eligibility_epoch),
                actor_type=ActorType.reconciler,
                authorization_result="stale",
            )
            stale_ids.append(current_leader.id)
            current_leader = None

        eligible_intents = [i for i in intents if eligible(i)]
        digest = compute_eligibility_digest(
            room_id=room_id,
            generation=int(room.generation),
            eligibility_epoch=int(room.close_leader_eligibility_epoch),
            eligible_intent_ids=[i.id for i in eligible_intents],
        )

        if not eligible_intents:
            # 无合法 successor：零 capture + 显式 supersede/recovery-required 终态
            for intent in intents:
                st = CloseIntentState(intent.state)
                if st in (
                    CloseIntentState.recovery_required,
                    CloseIntentState.superseded,
                    CloseIntentState.promoted,
                ):
                    continue
                if CloseIntentState.recovery_required not in CLOSE_INTENT_EDGES[st]:
                    continue
                assert_transition("close_intent", st, CloseIntentState.recovery_required)
                intent.state = CloseIntentState.recovery_required.value
                intent.finished_at = _now()
                await self._flush()
                await self.append_close_intent_event(
                    intent_id=intent.id,
                    from_state=st,
                    to_state=CloseIntentState.recovery_required,
                    eligibility_epoch=int(room.close_leader_eligibility_epoch),
                    actor_type=ActorType.reconciler,
                    authorization_result="no_successor",
                )
            room.close_leader_eligibility_digest = digest
            if room.superseded_at is None:
                room.superseded_at = _now()
            if RoomState(room.state) is not RoomState.recovery_required:
                assert_transition("room", room.state, RoomState.recovery_required)
                room.state = RoomState.recovery_required.value
            room.updated_at = _now()
            await self._flush()
            return CloseReconcileOutcome(
                leader_intent_id=None,
                promoted_request_id=None,
                capture_created=False,
                eligibility_epoch=int(room.close_leader_eligibility_epoch),
                eligibility_digest=digest,
                authorization_stale_intent_ids=tuple(stale_ids),
                no_successor=True,
            )

        # deterministic comparator：最高 `(intent_sequence, id)`。
        #
        # 🔴 「同 eligibility snapshot 重放不得换 leader」由**comparator 的确定性 +
        # eligibility digest**共同保证，而不是靠额外的「digest 相同就沿用旧 leader」分支：
        # eligible 集合不变 ⇒ digest 不变 ⇒ max() 必然选出同一条 intent；eligible 集合一变
        # ⇒ digest 必变（它就是按 eligible id 集合算的）。那条额外分支在行为上不可达，
        # 变异检验实测短路它判 GREEN —— 属于「additive 注入即死代码」，故不保留。
        leader = max(eligible_intents, key=lambda i: (int(i.intent_sequence), str(i.id)))
        room.close_leader_intent_id = leader.id
        room.close_leader_eligibility_digest = digest
        room.updated_at = _now()
        # 🔴 幂等：同 eligibility snapshot 重放不得产生第二个 event（Property 68）。
        # 故 `waiting_barrier` 也算「已就位」，不再回抽成 leader_ready 再落回 waiting_barrier。
        if CloseIntentState(leader.state) not in (
            CloseIntentState.leader_ready,
            CloseIntentState.waiting_barrier,
            CloseIntentState.successor_selected,
        ):
            prior = CloseIntentState(leader.state)
            assert_transition("close_intent", prior, CloseIntentState.leader_ready)
            leader.state = CloseIntentState.leader_ready.value
            leader.reconciled_at = _now()
            await self._flush()
            await self.append_close_intent_event(
                intent_id=leader.id,
                from_state=prior,
                to_state=CloseIntentState.leader_ready,
                eligibility_epoch=int(room.close_leader_eligibility_epoch),
                eligibility_digest=digest,
                actor_type=ActorType.reconciler,
                authorization_result="leader",
            )
        await self._flush()

        active_count = sum(
            1
            for p in participants.values()
            if ParticipantState(p.state) is ParticipantState.active
        )
        predecessors_open = (
            await self._session.execute(
                sa.select(sa.func.count())
                .select_from(WorkpaperForcesaveRequest)
                .where(
                    WorkpaperForcesaveRequest.room_id == room_id,
                    WorkpaperForcesaveRequest.generation == room.generation,
                    WorkpaperForcesaveRequest.kind == RequestKind.forcesave.value,
                    WorkpaperForcesaveRequest.state.in_(_OPEN_CAPTURE_STATES),
                )
            )
        ).scalar_one()
        if active_count > 0 or int(predecessors_open) > 0:
            if CloseIntentState(leader.state) is CloseIntentState.leader_ready:
                assert_transition(
                    "close_intent", leader.state, CloseIntentState.waiting_barrier
                )
                leader.state = CloseIntentState.waiting_barrier.value
                await self._flush()
                await self.append_close_intent_event(
                    intent_id=leader.id,
                    from_state=CloseIntentState.leader_ready,
                    to_state=CloseIntentState.waiting_barrier,
                    eligibility_epoch=int(room.close_leader_eligibility_epoch),
                    eligibility_digest=digest,
                    actor_type=ActorType.reconciler,
                    authorization_result="waiting_barrier",
                )
            return CloseReconcileOutcome(
                leader_intent_id=leader.id,
                promoted_request_id=None,
                capture_created=False,
                eligibility_epoch=int(room.close_leader_eligibility_epoch),
                eligibility_digest=digest,
                authorization_stale_intent_ids=tuple(stale_ids),
                no_successor=False,
            )

        confirmation = (
            await self._session.execute(
                sa.select(WorkpaperOoClientConfirmation).where(
                    WorkpaperOoClientConfirmation.id == leader.client_confirmation_id
                )
            )
        ).scalar_one()
        bundle = await self.assert_bundle_usable(confirmation.definition_bundle_id)
        participant = participants[leader.participant_id]
        fingerprint = compute_frozen_request_fingerprint(
            client_confirmation_id=confirmation.id,
            client_base_version_id=confirmation.content_version_id,
            client_base_representation_id=confirmation.representation_id,
            client_base_projection_sha256=confirmation.projection_sha256,
            definition_bundle_sha256=confirmation.definition_bundle_sha256,
            authority_model_definition_sha256=confirmation.authority_model_definition_sha256,
            adapter_build_digest=adapter_build_digest,
            contributor_snapshot_digest=contributor_snapshot_digest,
            client_edit_epoch=0,
            write_fence_epoch=int(room.write_fence_epoch),
            initiator_permission_epoch=int(participant.permission_epoch),
        )
        outcome = await self.create_forcesave_request_with_shell(
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            room_id=room_id,
            kind=RequestKind.close_capture,
            initiated_by_participant_id=leader.participant_id,
            initiator_permission_epoch=int(participant.permission_epoch),
            client_edit_epoch=0,
            client_base_version_id=confirmation.content_version_id,
            client_base_representation_id=confirmation.representation_id,
            client_base_projection_sha256=confirmation.projection_sha256,
            definition_bundle_id=confirmation.definition_bundle_id,
            authority_model_definition_id=bundle.authority_model_definition_id,
            adapter_build_digest=adapter_build_digest,
            contributor_snapshot_digest=contributor_snapshot_digest,
            idempotency_key=(
                f"close-capture:{room_id}:{room.generation}:"
                f"{room.close_leader_eligibility_epoch}"
            ),
            frozen_request_fingerprint=fingerprint,
            created_by=None,
        )
        prior = CloseIntentState(leader.state)
        assert_transition("close_intent", prior, CloseIntentState.promoted)
        leader.state = CloseIntentState.promoted.value
        leader.promoted_request_id = outcome.request.id
        leader.reconciled_at = _now()
        await self._flush()
        await self.append_close_intent_event(
            intent_id=leader.id,
            from_state=prior,
            to_state=CloseIntentState.promoted,
            eligibility_epoch=int(room.close_leader_eligibility_epoch),
            eligibility_digest=digest,
            actor_type=ActorType.reconciler,
            authorization_result="promoted",
        )
        return CloseReconcileOutcome(
            leader_intent_id=leader.id,
            promoted_request_id=outcome.request.id,
            capture_created=not outcome.cache_hit,
            eligibility_epoch=int(room.close_leader_eligibility_epoch),
            eligibility_digest=digest,
            authorization_stale_intent_ids=tuple(stale_ids),
            no_successor=False,
        )

    # ─────────────────────────────────────────────────────────────────
    # 10. append-only timeline
    # ─────────────────────────────────────────────────────────────────

    async def _next_sequence_no(self, model, parent_column, parent_id: uuid.UUID) -> int:
        return int(
            (
                await self._session.execute(
                    sa.select(sa.func.coalesce(sa.func.max(model.sequence_no), 0)).where(
                        parent_column == parent_id
                    )
                )
            ).scalar_one()
        ) + 1

    async def append_operation_event(
        self,
        *,
        operation_id: uuid.UUID,
        from_state: OperationState | str | None,
        to_state: OperationState | str,
        stage: str | None = None,
        actor_type: ActorType = ActorType.system,
        actor_id: uuid.UUID | None = None,
        error_code: str | None = None,
        correlation_id: uuid.UUID | None = None,
        client_edit_epoch: int | None = None,
        origin_request_sequence: int | None = None,
        effective_request_sequence: int | None = None,
        superseded_by: uuid.UUID | None = None,
        detail_digest: str | None = None,
    ) -> WorkpaperSyncOperationEvent:
        """先写 append-only transition event，再更新 current state projection。"""
        assert_transition("operation", from_state, to_state)
        seq = await self._next_sequence_no(
            WorkpaperSyncOperationEvent, WorkpaperSyncOperationEvent.operation_id, operation_id
        )
        ev = WorkpaperSyncOperationEvent(
            operation_id=operation_id,
            sequence_no=seq,
            from_state=(
                from_state.value if isinstance(from_state, OperationState) else from_state
            ),
            to_state=(to_state.value if isinstance(to_state, OperationState) else to_state),
            stage=stage,
            error_code=error_code,
            actor_type=actor_type.value,
            actor_id=actor_id,
            correlation_id=correlation_id or operation_id,
            client_edit_epoch=client_edit_epoch,
            origin_request_sequence=origin_request_sequence,
            effective_request_sequence=effective_request_sequence,
            superseded_by=superseded_by,
            detail_digest=detail_digest,
        )
        self._session.add(ev)
        await self._flush()
        return ev

    async def append_application_event(
        self,
        *,
        application_id: uuid.UUID,
        event_type: ApplicationEventType,
        origin_request_sequence: int,
        effective_request_sequence: int,
        from_state: ApplicationState | str | None = None,
        to_state: ApplicationState | str | None = None,
        folded_request_id: uuid.UUID | None = None,
        room_latest_durable_sequence: int | None = None,
        actor_type: ActorType = ActorType.system,
        actor_id: uuid.UUID | None = None,
        error_code: str | None = None,
    ) -> WorkpaperContentApplicationEvent:
        """application timeline：`sequence_folded` 必须同时带 folded request 与 room durable fence。"""
        if event_type is ApplicationEventType.sequence_folded:
            if folded_request_id is None or room_latest_durable_sequence is None:
                raise IdentityError(
                    "sequence_folded event 必须记录 folded_request_id 与 room_latest_durable_sequence"
                )
        if to_state is not None:
            assert_transition("application", from_state, to_state)
        seq = await self._next_sequence_no(
            WorkpaperContentApplicationEvent,
            WorkpaperContentApplicationEvent.application_id,
            application_id,
        )
        ev = WorkpaperContentApplicationEvent(
            application_id=application_id,
            sequence_no=seq,
            event_type=event_type.value,
            from_state=(
                from_state.value if isinstance(from_state, ApplicationState) else from_state
            ),
            to_state=(to_state.value if isinstance(to_state, ApplicationState) else to_state),
            folded_request_id=folded_request_id,
            origin_request_sequence=origin_request_sequence,
            effective_request_sequence=effective_request_sequence,
            room_latest_durable_sequence=room_latest_durable_sequence,
            actor_type=actor_type.value,
            actor_id=actor_id,
            error_code=error_code,
        )
        self._session.add(ev)
        await self._flush()
        return ev

    async def append_close_intent_event(
        self,
        *,
        intent_id: uuid.UUID,
        from_state: CloseIntentState | str | None,
        to_state: CloseIntentState | str,
        eligibility_epoch: int,
        eligibility_digest: str | None = None,
        actor_type: ActorType = ActorType.reconciler,
        actor_id: uuid.UUID | None = None,
        authorization_result: str | None = None,
        error_code: str | None = None,
    ) -> WorkpaperOoCloseIntentEvent:
        assert_transition("close_intent", from_state, to_state)
        seq = await self._next_sequence_no(
            WorkpaperOoCloseIntentEvent, WorkpaperOoCloseIntentEvent.intent_id, intent_id
        )
        ev = WorkpaperOoCloseIntentEvent(
            intent_id=intent_id,
            sequence_no=seq,
            from_state=(
                from_state.value if isinstance(from_state, CloseIntentState) else from_state
            ),
            to_state=(to_state.value if isinstance(to_state, CloseIntentState) else to_state),
            eligibility_epoch=eligibility_epoch,
            eligibility_digest=eligibility_digest,
            actor_type=actor_type.value,
            actor_id=actor_id,
            authorization_result=authorization_result,
            error_code=error_code,
        )
        self._session.add(ev)
        await self._flush()
        return ev

    async def append_recovery_case_event(
        self,
        *,
        case_id: uuid.UUID,
        from_state: RecoveryCaseState | str | None,
        to_state: RecoveryCaseState | str,
        actor_type: ActorType = ActorType.system,
        actor_id: uuid.UUID | None = None,
        authorization_result: str | None = None,
        prior_confirmation_id: uuid.UUID | None = None,
        definition_bundle_sha256: str | None = None,
        error_code: str | None = None,
    ) -> WorkpaperCallbackRecoveryCaseEvent:
        """recovery case 的独立 timeline —— claim 前不得借 operation timeline 伪造 operation。"""
        assert_transition("recovery_case", from_state, to_state)
        seq = await self._next_sequence_no(
            WorkpaperCallbackRecoveryCaseEvent,
            WorkpaperCallbackRecoveryCaseEvent.case_id,
            case_id,
        )
        ev = WorkpaperCallbackRecoveryCaseEvent(
            case_id=case_id,
            sequence_no=seq,
            from_state=(
                from_state.value if isinstance(from_state, RecoveryCaseState) else from_state
            ),
            to_state=(to_state.value if isinstance(to_state, RecoveryCaseState) else to_state),
            actor_type=actor_type.value,
            actor_id=actor_id,
            authorization_result=authorization_result,
            prior_confirmation_id=prior_confirmation_id,
            definition_bundle_sha256=definition_bundle_sha256,
            error_code=error_code,
        )
        self._session.add(ev)
        await self._flush()
        return ev


    # ─────────────────────────────────────────────────────────────────
    # 15. 字段级冲突记录（Requirement 8.1 / 8.2 / 8.6）
    # ─────────────────────────────────────────────────────────────────

    async def record_conflicts(
        self,
        *,
        operation_id: uuid.UUID,
        client_edit_epoch: int,
        canonical_application_id: uuid.UUID | None,
        effective_request_sequence: int | None,
        rows: Sequence[Mapping[str, Any]],
        now: datetime | None = None,
    ) -> ConflictWriteOutcome:
        """把一次 merge 的冲突集落成 `working_paper_sync_conflict` 行。

        本方法**只收 `ConflictRecord.to_row()` 的字典**，不 import 冲突域 —— 仓储层不
        参与语义判断，冲突记录的自洽性由 Task 14 的域内 `__post_init__` 保证。

        重跑（retry / rebase / 同一 operation 的第二次 attempt）必须幂等，因为
        `uq_wpsc_field UNIQUE(operation_id, stable_field_key, row_key, oo_location)`：

        * 已存在同 key ⇒ 覆盖三值/元数据并清 `superseded_at`（同一冲突的新一轮观测）；
        * 本轮不再出现的旧 key ⇒ 打 `superseded_at`，**不删行**（AC 8.7 的「不得删除或
          原地改写历史」在冲突记录上同样成立，审计师要能看到「上一轮有这条、这轮没了」）。

        🔴 `resolved_*` 三列不在覆盖范围内：它们是 AC 8.6 的裁决轨迹，重新观测冲突不得
        把「谁在什么时候选了什么」擦掉。
        """
        stamp = now or _now()
        seen: set[tuple[str, str, str]] = set()
        inserted = updated = 0
        existing = {
            (row.stable_field_key, row.row_key or "", row.oo_location or ""): row
            for row in (
                await self._session.execute(
                    sa.select(WorkpaperSyncConflict).where(
                        WorkpaperSyncConflict.operation_id == operation_id
                    )
                )
            ).scalars()
        }
        for payload in rows:
            key = (
                str(payload["stable_field_key"]),
                str(payload.get("row_key") or ""),
                str(payload.get("oo_location") or ""),
            )
            if key in seen:
                raise ScopeIntegrityError(
                    f"同一 operation {operation_id} 的冲突集里出现重复 key {key} —— "
                    "会撞 uq_wpsc_field；冲突集本应在域内已去重"
                )
            seen.add(key)
            row = existing.get(key)
            if row is None:
                row = WorkpaperSyncConflict(
                    operation_id=operation_id,
                    client_edit_epoch=int(client_edit_epoch),
                    canonical_application_id=canonical_application_id,
                    effective_request_sequence=(
                        None
                        if effective_request_sequence is None
                        else int(effective_request_sequence)
                    ),
                    created_at=stamp,
                    **{k: v for k, v in payload.items()},
                )
                self._session.add(row)
                inserted += 1
                continue
            row.client_edit_epoch = int(client_edit_epoch)
            row.canonical_application_id = canonical_application_id
            row.effective_request_sequence = (
                None if effective_request_sequence is None else int(effective_request_sequence)
            )
            for column, value in payload.items():
                setattr(row, column, value)
            row.superseded_at = None
            updated += 1
        superseded = 0
        for key, row in existing.items():
            if key in seen or row.superseded_at is not None:
                continue
            row.superseded_at = stamp
            superseded += 1
        await self._flush()
        return ConflictWriteOutcome(
            inserted=inserted, updated=updated, superseded=superseded
        )

    async def load_conflicts(
        self, *, operation_id: uuid.UUID, include_superseded: bool = False
    ) -> tuple[WorkpaperSyncConflict, ...]:
        """按 sheet/table/row 稳定序读回冲突行（AC 8.2 的分组基础）。"""
        stmt = sa.select(WorkpaperSyncConflict).where(
            WorkpaperSyncConflict.operation_id == operation_id
        )
        if not include_superseded:
            stmt = stmt.where(WorkpaperSyncConflict.superseded_at.is_(None))
        rows = list((await self._session.execute(stmt)).scalars())
        rows.sort(
            key=lambda r: (
                r.sheet_key or "",
                r.table_key or "",
                r.row_key or "",
                r.stable_field_key,
                r.oo_location or "",
            )
        )
        return tuple(rows)

    async def mark_conflicts_resolved(
        self,
        *,
        operation_id: uuid.UUID,
        resolutions: Sequence[Mapping[str, Any]],
        actor_id: uuid.UUID,
        now: datetime | None = None,
    ) -> int:
        """写 AC 8.6 的裁决轨迹：选择结果 + 落地值 + actor + 时间。

        `ck_wpsc_resolution_pair` 要求 `resolved_at` 与 `resolved_by` 同生共死，因此
        `actor_id` 不可空 —— system identity 不得代替用户裁决（AC 8.4）。
        找不到对应冲突行时抛：静默跳过等于「裁决记录不全」，而那正是审计轨迹的价值所在。
        """
        stamp = now or _now()
        index = {
            (row.stable_field_key, row.row_key or "", row.oo_location or ""): row
            for row in await self.load_conflicts(operation_id=operation_id)
        }
        marked = 0
        for payload in resolutions:
            key = (
                str(payload["stable_field_key"]),
                str(payload.get("row_key") or ""),
                str(payload.get("oo_location") or ""),
            )
            row = index.get(key)
            if row is None:
                raise ScopeIntegrityError(
                    f"裁决 {key} 在 operation {operation_id} 的冲突行里不存在 —— "
                    "冲突集可能已被 supersede/rebase，裁决轨迹不得写到别的冲突上"
                )
            row.resolution = payload.get("resolution")
            row.resolved_value = payload.get("resolved_value")
            row.resolved_by = actor_id
            row.resolved_at = stamp
            marked += 1
        await self._flush()
        return marked


__all__ = [
    "WorkpaperSyncRepository",
    "ForcesaveRequestOutcome",
    "CorrelationOutcome",
    "CloseReconcileOutcome",
    "RecoveryClaimOutcome",
    "ConflictWriteOutcome",
]
