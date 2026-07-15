"""EvidenceRefService — 持久 EvidenceRef 创建事务（Task 4.2, Wave 3）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R3, R4, R12
Design: §3.2 EvidenceRefService / §4.4 EvidenceRef 与统一依赖图
Properties: P6 (EvidenceRef 完整性), P7 (EvidenceRef 幂等性)

创建关联时由 ``EvidenceRefService`` 在该命令事务内按需执行四项校验：
  1. 源 scope（source belongs to same project/year）
  2. 目标 scope（target belongs to same project/year）
  3. 源端权限（caller has read on source）
  4. 目标端权限（caller has read on target）
并同时校验目标存在/活动状态、版本和 hash。

该校验是 create-time command guard，不建立持续轮询。创建后状态变化通过
既有 outbox/stale 事件与读取时授权处理。

失败必须留下 NO partial ref/edge/audit/outbox 半成品（原子事务）。

跨项目尝试返回 ``SCOPE_NOT_FOUND_OR_FORBIDDEN``，不泄露目标信息（R4.2）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.evidence_governance.facade import (
    CommandRequest,
    CommandResult,
    CommandTxn,
    EvidenceGovernanceFacade,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ActorType,
    EvidenceErrorCode,
    EvidenceGovernanceError,
    content_hash_of,
)
from app.services.evidence_governance.typed_adapters import (
    ResolvedTarget,
    get_adapter,
)


# ─────────────────────────────────────────────────────────────────────────────
# Input / Output dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CreateEvidenceRefRequest:
    """Input for creating a persistent EvidenceRef."""

    project_id: uuid.UUID
    audit_year: int
    source_type: str
    source_id: str
    source_version: int | None = None
    evidence_type: str = ""
    evidence_id: str = ""
    attachment_version_id: uuid.UUID | None = None
    target_version: int | None = None
    target_hash: str | None = None
    label: str | None = None
    context: str | None = None


@dataclass(frozen=True)
class EvidenceRefResult:
    """Output of a successful EvidenceRef creation."""

    ref_id: uuid.UUID
    intent_hash: str
    idempotent_hit: bool
    dependency_id: uuid.UUID | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────


class EvidenceRefService:
    """EvidenceRef 创建事务：锁定两端、同 scope/权限/版本/hash 校验、幂等引用创建、
    动态依赖边，全部在同一事务内完成。

    All-or-nothing: 如果任何校验失败，不创建 ref/edge/audit/outbox 半成品。
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_ref(
        self,
        *,
        request: CreateEvidenceRefRequest,
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> CommandResult:
        """创建 EvidenceRef + EvidenceDependency 边，经 facade 原子提交。

        四项 create-time command guard：
          1. source scope (same project/year)
          2. target scope (same project/year)
          3. source-end permission (caller can read source)
          4. target-end permission (caller can read target)
        Plus: target exists/active state, version match, hash match.

        失败返回 SCOPE_NOT_FOUND_OR_FORBIDDEN，不泄露目标信息。
        """
        # Compute intent_hash for idempotency (P7)
        intent_hash = _compute_intent_hash(
            source_type=request.source_type,
            source_id=request.source_id,
            evidence_type=request.evidence_type,
            evidence_id=request.evidence_id,
        )

        # Derive idempotency key from intent hash if not provided
        idem_key = idempotency_key or f"evidence_ref:{intent_hash}"

        facade = EvidenceGovernanceFacade(
            self._db,
        )

        async def _business(txn: CommandTxn) -> EvidenceRefResult:
            """Business logic inside the atomic transaction."""
            db = txn.db

            # ── Check for existing active ref with same intent (P7 idempotent) ──
            existing = await _find_active_ref_by_intent(
                db,
                project_id=request.project_id,
                audit_year=request.audit_year,
                intent_hash=intent_hash,
            )
            if existing is not None:
                return EvidenceRefResult(
                    ref_id=existing,
                    intent_hash=intent_hash,
                    idempotent_hit=True,
                )

            # ── 1. Source scope validation ──
            source_adapter = get_adapter(request.source_type)
            source_resolved = await source_adapter.resolve(
                request.source_id,
                project_id=request.project_id,
                audit_year=request.audit_year,
                db=db,
            )
            if source_resolved is None:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                    "source not found or forbidden",
                )

            # ── 2. Target scope validation ──
            target_adapter = get_adapter(request.evidence_type)
            target_resolved = await target_adapter.resolve(
                request.evidence_id,
                project_id=request.project_id,
                audit_year=request.audit_year,
                db=db,
            )
            if target_resolved is None:
                # Cross-project or non-existent → same opaque error (R4.2)
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                    "target not found or forbidden",
                )

            # ── 3. Source-end permission (caller has read on source) ──
            can_read_source = await source_adapter.can_read(
                request.source_id,
                actor=actor,
                project_id=request.project_id,
                db=db,
            )
            if not can_read_source:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                    "source not found or forbidden",
                )

            # ── 4. Target-end permission (caller has read on target) ──
            can_read_target = await target_adapter.can_read(
                request.evidence_id,
                actor=actor,
                project_id=request.project_id,
                db=db,
            )
            if not can_read_target:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                    "target not found or forbidden",
                )

            # ── Version/hash match validation ──
            if request.target_version is not None and target_resolved.target_version is not None:
                if request.target_version != target_resolved.target_version:
                    raise EvidenceGovernanceError(
                        EvidenceErrorCode.VERSION_CONFLICT,
                        "target version mismatch",
                    )
            if request.target_hash is not None and target_resolved.target_hash is not None:
                if request.target_hash != target_resolved.target_hash:
                    raise EvidenceGovernanceError(
                        EvidenceErrorCode.VERSION_CONFLICT,
                        "target hash mismatch",
                    )

            # ── Lock both ends (design §3.2: locks both ends) ──
            await source_adapter.lock_for_update(request.source_id, db=db)
            await target_adapter.lock_for_update(request.evidence_id, db=db)

            # ── Create EvidenceRef row (persistent, NOT a DTO) ──
            ref_id = uuid.uuid4()
            await db.execute(
                sa.text("""
                    INSERT INTO evidence_refs (
                        id, project_id, audit_year,
                        source_type, source_id, source_version,
                        evidence_type, evidence_id, attachment_version_id,
                        target_version, target_hash,
                        label, context, intent_hash, status,
                        actor_type, actor_user_id, actor_service_identity_id,
                        created_at
                    ) VALUES (
                        :id, :project_id, :audit_year,
                        :source_type, :source_id, :source_version,
                        :evidence_type, :evidence_id, :attachment_version_id,
                        :target_version, :target_hash,
                        :label, :context, :intent_hash, 'active',
                        :actor_type, :actor_user_id, :actor_service_identity_id,
                        NOW()
                    )
                """),
                {
                    "id": str(ref_id),
                    "project_id": str(request.project_id),
                    "audit_year": request.audit_year,
                    "source_type": request.source_type,
                    "source_id": request.source_id,
                    "source_version": request.source_version,
                    "evidence_type": request.evidence_type,
                    "evidence_id": request.evidence_id,
                    "attachment_version_id": (
                        str(request.attachment_version_id)
                        if request.attachment_version_id
                        else None
                    ),
                    "target_version": (
                        request.target_version
                        if request.target_version is not None
                        else (target_resolved.target_version if target_resolved else None)
                    ),
                    "target_hash": (
                        request.target_hash
                        if request.target_hash is not None
                        else (target_resolved.target_hash if target_resolved else None)
                    ),
                    "label": request.label,
                    "context": request.context,
                    "intent_hash": intent_hash,
                    "actor_type": actor.actor_type.value,
                    "actor_user_id": (
                        str(actor.actor_user_id) if actor.actor_user_id else None
                    ),
                    "actor_service_identity_id": (
                        str(actor.actor_service_identity_id)
                        if actor.actor_service_identity_id
                        else None
                    ),
                },
            )

            # ── Create EvidenceDependency edge (source→target: source变化使target stale) ──
            dep_id = uuid.uuid4()
            edge_hash = _compute_edge_hash(
                source_type=request.source_type,
                source_id=request.source_id,
                evidence_type=request.evidence_type,
                evidence_id=request.evidence_id,
            )
            await db.execute(
                sa.text("""
                    INSERT INTO evidence_dependencies (
                        id, project_id, audit_year,
                        source_type, source_id,
                        target_type, target_id,
                        source_version, target_version,
                        edge_hash, status,
                        evidence_ref_id,
                        actor_type, actor_user_id, actor_service_identity_id,
                        created_at
                    ) VALUES (
                        :id, :project_id, :audit_year,
                        :source_type, :source_id,
                        :target_type, :target_id,
                        :source_version, :target_version,
                        :edge_hash, 'active',
                        :evidence_ref_id,
                        :actor_type, :actor_user_id, :actor_service_identity_id,
                        NOW()
                    )
                """),
                {
                    "id": str(dep_id),
                    "project_id": str(request.project_id),
                    "audit_year": request.audit_year,
                    "source_type": request.source_type,
                    "source_id": request.source_id,
                    "target_type": request.evidence_type,
                    "target_id": request.evidence_id,
                    "source_version": request.source_version,
                    "target_version": (
                        request.target_version
                        if request.target_version is not None
                        else (target_resolved.target_version if target_resolved else None)
                    ),
                    "edge_hash": edge_hash,
                    "evidence_ref_id": str(ref_id),
                    "actor_type": actor.actor_type.value,
                    "actor_user_id": (
                        str(actor.actor_user_id) if actor.actor_user_id else None
                    ),
                    "actor_service_identity_id": (
                        str(actor.actor_service_identity_id)
                        if actor.actor_service_identity_id
                        else None
                    ),
                },
            )

            await db.flush()

            # ── Record transition audit ──
            await txn.record_transition(
                transition_type="evidence_ref_created",
                to_state="active",
                metadata={
                    "ref_id": str(ref_id),
                    "intent_hash": intent_hash,
                    "source_type": request.source_type,
                    "evidence_type": request.evidence_type,
                },
            )

            # ── Enqueue outbox event for downstream (stale propagation etc.) ──
            await txn.enqueue_outbox(
                event_type="evidence_ref.created",
                payload={
                    "ref_id": str(ref_id),
                    "dependency_id": str(dep_id),
                    "project_id": str(request.project_id),
                    "audit_year": request.audit_year,
                    "source_type": request.source_type,
                    "source_id": request.source_id,
                    "evidence_type": request.evidence_type,
                    "evidence_id": request.evidence_id,
                    "intent_hash": intent_hash,
                },
            )

            return EvidenceRefResult(
                ref_id=ref_id,
                intent_hash=intent_hash,
                idempotent_hit=False,
                dependency_id=dep_id,
            )

        # Execute via facade: scope + capability + short transaction + command-root + outbox
        return await facade.execute(
            CommandRequest(
                command_type="evidence_ref.create",
                idempotency_key=idem_key,
                actor=actor,
                actor_role=actor_role,
                project_id=request.project_id,
                audit_year=request.audit_year,
                capability="evidence_ref.create",
                trace_id=trace_id,
            ),
            _business,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────


def _compute_intent_hash(
    *,
    source_type: str,
    source_id: str,
    evidence_type: str,
    evidence_id: str,
) -> str:
    """Compute intent_hash from source_type+source_id+evidence_type+evidence_id.

    This enables idempotency: same intent submitted repeatedly only creates ONE
    active ref (P7). Uses canonical JSON + SHA-256.
    """
    return content_hash_of({
        "source_type": source_type,
        "source_id": source_id,
        "evidence_type": evidence_type,
        "evidence_id": evidence_id,
    })


def _compute_edge_hash(
    *,
    source_type: str,
    source_id: str,
    evidence_type: str,
    evidence_id: str,
) -> str:
    """Compute canonical edge hash for deduplication in the unified dependency graph."""
    return content_hash_of({
        "edge_source_type": source_type,
        "edge_source_id": source_id,
        "edge_target_type": evidence_type,
        "edge_target_id": evidence_id,
    })


async def _find_active_ref_by_intent(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    audit_year: int,
    intent_hash: str,
) -> uuid.UUID | None:
    """Find an existing active EvidenceRef with the same intent_hash (P7).

    Uses the partial unique index (project_id, audit_year, intent_hash) WHERE status='active'.
    Returns the ref id if found, else None.
    """
    row = (
        await db.execute(
            sa.text("""
                SELECT id FROM evidence_refs
                WHERE project_id = :pid
                  AND audit_year = :yr
                  AND intent_hash = :ih
                  AND status = 'active'
                LIMIT 1
            """),
            {
                "pid": str(project_id),
                "yr": audit_year,
                "ih": intent_hash,
            },
        )
    ).first()
    if row is None:
        return None
    return uuid.UUID(str(row[0]))


__all__ = [
    "EvidenceRefService",
    "CreateEvidenceRefRequest",
    "EvidenceRefResult",
]
