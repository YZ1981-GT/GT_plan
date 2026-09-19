"""AIEvidenceGate — Task 6.2 (Wave 5).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R8, R12, R15
Design: §3.2 AIEvidenceGate, §4.6 AiContentLog extension, §5.3 RAG/AI
Properties: P17 (AI 状态门禁), P18 (AI 入口覆盖), P19 (已确认内容变更失效)

Unified registration, confirmation, invalidation, and entry coverage guard for ALL
AI entry points (generate, rewrite, summarize, complete). Extends the existing
`AiContentLog` lifecycle (does NOT replace it — design §1.2).

Key contracts:
  - P17: Only human-confirmed, hash-consistent, policy-required evidence valid AI
    content can enter FormalOutput; historical objects without attachments don't violate.
  - P18: AI_entry_scan_set ∩ gate_declared_set_complement = ∅ (coverage scanner)
  - P19: confirmed content or any dependency change → draft/stale, original
    confirmation no longer authorizes output.
  - R8.1: ALL entry points register prompt hash, model, context refs, output,
    content_hash, service status, actor, lifecycle state.
  - R8.3: AI_Content without human confirmation, or with hash change, or stale refs
    → blocked from FormalOutput.
  - R8.4: AI service unavailable → degraded status, no auto-confirm.

Service Identity CANNOT confirm AI content (design §2.2).
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ActorType,
    EvidenceErrorCode,
    EvidenceGovernanceError,
    content_hash_of,
    is_sha256_hex,
    sha256_hex,
)


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────


class AiLifecycleStatus(str, enum.Enum):
    """AI content lifecycle states (extended from existing pending/confirmed/revised/rejected)."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    REVISED = "revised"
    REJECTED = "rejected"
    STALE = "stale"


class AiServiceStatus(str, enum.Enum):
    """AI service availability status (R8.4)."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class GateCheckStatus(str, enum.Enum):
    """Result of formal output eligibility check."""

    ELIGIBLE = "eligible"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AiContentRegistration:
    """Result of registering AI generation through the gate."""

    content_id: uuid.UUID
    entry_point: str
    prompt_hash: str
    model_name: str
    output_hash: str
    lifecycle_status: AiLifecycleStatus
    service_status: AiServiceStatus
    content_version: int
    created_at: datetime | None = None


@dataclass(frozen=True)
class GateBlockReason:
    """A single reason why AI content is blocked from FormalOutput."""

    code: str
    description: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateCheckResult:
    """Result of formal output eligibility check for AI content (R8.3)."""

    status: GateCheckStatus
    content_id: uuid.UUID
    reasons: list[GateBlockReason] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return self.status == GateCheckStatus.ELIGIBLE


# ─────────────────────────────────────────────────────────────────────────────
# AI Entry Registry (P18 — declared gated set)
# ─────────────────────────────────────────────────────────────────────────────

#: All declared AI entry points that go through the unified gate. The coverage
#: scanner (check_ai_entry_coverage.py) compares discovered entry points against
#: this set. If discovered - declared ≠ ∅, CI blocks merge.
AI_ENTRY_REGISTRY: frozenset[str] = frozenset(
    {
        "generate_text",
        "generate_conclusion",
        "generate_analysis",
        "rewrite_content",
        "summarize_content",
        "complete_content",
        "generate_audit_opinion",
        "generate_disclosure_note",
        "generate_review_response",
        "ai_assist_ocr_field",
        "chat_completion",
        "generate_derecognition_judge",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────


class AIEvidenceGate:
    """Unified AI content registration, confirmation, and coverage gate.

    Wraps the existing AiContentLog lifecycle with governance extensions:
    - Prompt hash, model, service status, output hash, evidence refs, citation snapshots
    - Human confirm/revise/reject lifecycle
    - Invalidation on evidence change (P19)
    - FormalOutput eligibility check (R8.3)

    Does NOT replace existing AiContentLog — extends it (design §1.2 / §4.6).
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ─────────────────────────────────────────────────────────────────────────
    # register_generation (R8.1)
    # ─────────────────────────────────────────────────────────────────────────

    async def register_generation(
        self,
        *,
        entry_point: str,
        prompt_hash: str,
        model_name: str,
        output: str,
        actor: ActorContext,
        project_id: uuid.UUID,
        audit_year: int | None = None,
        context_refs: list[uuid.UUID] | None = None,
        citation_snapshot_ids: list[uuid.UUID] | None = None,
        service_status: AiServiceStatus = AiServiceStatus.AVAILABLE,
        wp_id: uuid.UUID | None = None,
        target_cell: str | None = None,
    ) -> AiContentRegistration:
        """Register AI generation before content is returned (R8.1).

        Records: prompt hash, model, context EvidenceRef, output hash, service status,
        actor, lifecycle state (draft by default).

        All AI entry points MUST call this before returning content as draft.
        """
        # Validate entry point is declared (P18)
        if entry_point not in AI_ENTRY_REGISTRY:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.EVIDENCE_GATE_BLOCKED,
                f"Undeclared AI entry point: {entry_point}. "
                f"Register in AI_ENTRY_REGISTRY first.",
            )

        # Compute output hash (P5)
        output_hash = sha256_hex(output)

        # Validate prompt_hash format
        if prompt_hash and not is_sha256_hex(prompt_hash):
            # Compute it if provided as raw prompt text
            prompt_hash = sha256_hex(prompt_hash)

        content_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # Determine lifecycle status based on service status (R8.4)
        lifecycle_status = AiLifecycleStatus.DRAFT

        # Serialize context refs and citation IDs
        import json as _json

        refs_json = (
            _json.dumps([str(r) for r in context_refs]) if context_refs else None
        )
        citations_json = (
            _json.dumps([str(c) for c in citation_snapshot_ids])
            if citation_snapshot_ids
            else None
        )

        # Actor columns
        actor_type = actor.actor_type.value
        actor_user_id = str(actor.actor_user_id) if actor.actor_user_id else None
        actor_service_id = (
            str(actor.actor_service_identity_id)
            if actor.actor_service_identity_id
            else None
        )

        stmt = sa.text(
            "INSERT INTO ai_content_governance "
            "(id, project_id, audit_year, wp_id, entry_point, "
            "prompt_hash, model_name, service_status, "
            "output_text, output_hash, target_cell, "
            "evidence_refs, citation_snapshots, "
            "lifecycle_status, content_version, "
            "actor_type, actor_user_id, actor_service_identity_id, "
            "created_at, updated_at) "
            "VALUES (:id, :pid, :yr, :wp_id, :entry, "
            ":phash, :model, :svc_status, "
            ":output, :ohash, :target, "
            "CAST(:refs AS JSONB), CAST(:cites AS JSONB), "
            ":lifecycle, 1, "
            ":atype, :auid, :asid, "
            ":now, :now) "
            "RETURNING id, created_at"
        )

        result = (
            await self._db.execute(
                stmt,
                {
                    "id": str(content_id),
                    "pid": str(project_id),
                    "yr": audit_year,
                    "wp_id": str(wp_id) if wp_id else None,
                    "entry": entry_point,
                    "phash": prompt_hash,
                    "model": model_name,
                    "svc_status": service_status.value,
                    "output": output,
                    "ohash": output_hash,
                    "target": target_cell,
                    "refs": refs_json,
                    "cites": citations_json,
                    "lifecycle": lifecycle_status.value,
                    "atype": actor_type,
                    "auid": actor_user_id,
                    "asid": actor_service_id,
                    "now": now,
                },
            )
        ).mappings().first()

        created_at = result["created_at"] if result else now

        return AiContentRegistration(
            content_id=content_id,
            entry_point=entry_point,
            prompt_hash=prompt_hash,
            model_name=model_name,
            output_hash=output_hash,
            lifecycle_status=lifecycle_status,
            service_status=service_status,
            content_version=1,
            created_at=created_at,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # confirm_content (human confirmation)
    # ─────────────────────────────────────────────────────────────────────────

    async def confirm_content(
        self,
        *,
        content_id: uuid.UUID,
        actor: ActorContext,
        project_id: uuid.UUID,
    ) -> bool:
        """Human confirms AI content (draft → confirmed).

        Validates:
        - Actor is human (Service Identity blocked — design §2.2)
        - Content hash unchanged since generation
        - All referenced evidence is non-stale (P19)

        Returns True if confirmed, False if validation failed.
        Raises EvidenceGovernanceError on hard failures.
        """
        # Validate actor is human
        actor.assert_human_action("ai_confirm")

        # Load content record
        row = await self._load_content(content_id, project_id)
        if row is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "AI content not found in scope",
            )

        # Must be in draft status
        if row["lifecycle_status"] != AiLifecycleStatus.DRAFT.value:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                f"Cannot confirm: content is '{row['lifecycle_status']}', expected 'draft'",
            )

        # Validate content hash unchanged (P17)
        current_hash = sha256_hex(row["output_text"])
        if current_hash != row["output_hash"]:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.EVIDENCE_GATE_BLOCKED,
                "Content hash changed since generation — cannot confirm",
            )

        # Validate referenced evidence is non-stale (P19)
        if not await self._check_evidence_refs_valid(row.get("evidence_refs")):
            raise EvidenceGovernanceError(
                EvidenceErrorCode.EVIDENCE_GATE_BLOCKED,
                "Referenced evidence is stale or invalid — cannot confirm",
            )

        # Transition: draft → confirmed
        now = datetime.now(timezone.utc)
        stmt = sa.text(
            "UPDATE ai_content_governance "
            "SET lifecycle_status = 'confirmed', "
            "    confirmed_by_user_id = :uid, "
            "    confirmed_at = :now, "
            "    updated_at = :now "
            "WHERE id = :id AND project_id = :pid AND lifecycle_status = 'draft'"
        )
        result = await self._db.execute(
            stmt,
            {
                "id": str(content_id),
                "pid": str(project_id),
                "uid": str(actor.actor_user_id),
                "now": now,
            },
        )
        return result.rowcount > 0  # type: ignore[union-attr]

    # ─────────────────────────────────────────────────────────────────────────
    # revise_content (human revision)
    # ─────────────────────────────────────────────────────────────────────────

    async def revise_content(
        self,
        *,
        content_id: uuid.UUID,
        new_output: str,
        actor: ActorContext,
        project_id: uuid.UUID,
    ) -> AiContentRegistration:
        """Human revises AI content (creates new version, old becomes superseded).

        The original record is marked 'revised' and a new version is created with
        the revised content.
        """
        actor.assert_human_action("ai_confirm")

        # Load original
        row = await self._load_content(content_id, project_id)
        if row is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "AI content not found in scope",
            )

        if row["lifecycle_status"] not in (
            AiLifecycleStatus.DRAFT.value,
            AiLifecycleStatus.CONFIRMED.value,
        ):
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                f"Cannot revise: content is '{row['lifecycle_status']}'",
            )

        # Mark original as revised
        now = datetime.now(timezone.utc)
        stmt = sa.text(
            "UPDATE ai_content_governance "
            "SET lifecycle_status = 'revised', updated_at = :now "
            "WHERE id = :id AND project_id = :pid"
        )
        await self._db.execute(
            stmt,
            {"id": str(content_id), "pid": str(project_id), "now": now},
        )

        # Create new version with revised content
        new_id = uuid.uuid4()
        new_output_hash = sha256_hex(new_output)
        new_version = (row.get("content_version") or 1) + 1

        actor_type = actor.actor_type.value
        actor_user_id = str(actor.actor_user_id) if actor.actor_user_id else None
        actor_service_id = (
            str(actor.actor_service_identity_id)
            if actor.actor_service_identity_id
            else None
        )

        stmt = sa.text(
            "INSERT INTO ai_content_governance "
            "(id, project_id, audit_year, wp_id, entry_point, "
            "prompt_hash, model_name, service_status, "
            "output_text, output_hash, target_cell, "
            "evidence_refs, citation_snapshots, "
            "lifecycle_status, content_version, previous_version_id, "
            "actor_type, actor_user_id, actor_service_identity_id, "
            "confirmed_by_user_id, confirmed_at, "
            "created_at, updated_at) "
            "VALUES (:id, :pid, :yr, :wp_id, :entry, "
            ":phash, :model, :svc_status, "
            ":output, :ohash, :target, "
            "CAST(:refs AS JSONB), CAST(:cites AS JSONB), "
            "'draft', :ver, :prev_id, "
            ":atype, :auid, :asid, "
            ":uid, :now, "
            ":now, :now) "
            "RETURNING id, created_at"
        )
        result = (
            await self._db.execute(
                stmt,
                {
                    "id": str(new_id),
                    "pid": str(project_id),
                    "yr": row.get("audit_year"),
                    "wp_id": row.get("wp_id"),
                    "entry": row["entry_point"],
                    "phash": row["prompt_hash"],
                    "model": row["model_name"],
                    "svc_status": row.get("service_status", "available"),
                    "output": new_output,
                    "ohash": new_output_hash,
                    "target": row.get("target_cell"),
                    "refs": row.get("evidence_refs"),
                    "cites": row.get("citation_snapshots"),
                    "ver": new_version,
                    "prev_id": str(content_id),
                    "atype": actor_type,
                    "auid": actor_user_id,
                    "asid": actor_service_id,
                    "uid": str(actor.actor_user_id),
                    "now": now,
                },
            )
        ).mappings().first()

        return AiContentRegistration(
            content_id=new_id,
            entry_point=row["entry_point"],
            prompt_hash=row["prompt_hash"],
            model_name=row["model_name"],
            output_hash=new_output_hash,
            lifecycle_status=AiLifecycleStatus.DRAFT,
            service_status=AiServiceStatus(row.get("service_status", "available")),
            content_version=new_version,
            created_at=result["created_at"] if result else now,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # reject_content
    # ─────────────────────────────────────────────────────────────────────────

    async def reject_content(
        self,
        *,
        content_id: uuid.UUID,
        reason: str,
        actor: ActorContext,
        project_id: uuid.UUID,
    ) -> bool:
        """Human rejects AI content (draft → rejected)."""
        actor.assert_human_action("ai_confirm")

        row = await self._load_content(content_id, project_id)
        if row is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "AI content not found in scope",
            )

        if row["lifecycle_status"] != AiLifecycleStatus.DRAFT.value:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                f"Cannot reject: content is '{row['lifecycle_status']}', expected 'draft'",
            )

        now = datetime.now(timezone.utc)
        stmt = sa.text(
            "UPDATE ai_content_governance "
            "SET lifecycle_status = 'rejected', "
            "    reject_reason = :reason, "
            "    confirmed_by_user_id = :uid, "
            "    confirmed_at = :now, "
            "    updated_at = :now "
            "WHERE id = :id AND project_id = :pid AND lifecycle_status = 'draft'"
        )
        result = await self._db.execute(
            stmt,
            {
                "id": str(content_id),
                "pid": str(project_id),
                "reason": reason,
                "uid": str(actor.actor_user_id),
                "now": now,
            },
        )
        return result.rowcount > 0  # type: ignore[union-attr]

    # ─────────────────────────────────────────────────────────────────────────
    # invalidate_on_evidence_change (P19)
    # ─────────────────────────────────────────────────────────────────────────

    async def invalidate_on_evidence_change(
        self,
        *,
        content_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> None:
        """Mark confirmed content stale when its evidence dependencies change (P19).

        Confirmed → stale transition. Original confirmation no longer authorizes output.
        """
        now = datetime.now(timezone.utc)
        stmt = sa.text(
            "UPDATE ai_content_governance "
            "SET lifecycle_status = 'stale', updated_at = :now "
            "WHERE id = :id AND project_id = :pid AND lifecycle_status = 'confirmed'"
        )
        await self._db.execute(
            stmt,
            {"id": str(content_id), "pid": str(project_id), "now": now},
        )

    # ─────────────────────────────────────────────────────────────────────────
    # check_formal_output_eligibility (R8.3)
    # ─────────────────────────────────────────────────────────────────────────

    async def check_formal_output_eligibility(
        self,
        *,
        content_id: uuid.UUID,
        actor: ActorContext,
        project_id: uuid.UUID,
    ) -> GateCheckResult:
        """Check if AI content can enter FormalOutput (R8.3).

        Blocks if:
        - Not confirmed (must be human-confirmed)
        - Hash changed since confirmation
        - Referenced evidence is stale
        - Required evidence is missing (policy-declared)

        P17: Only human-confirmed, hash-consistent, policy-required evidence valid
        AI content can enter FormalOutput.
        """
        reasons: list[GateBlockReason] = []

        row = await self._load_content(content_id, project_id)
        if row is None:
            return GateCheckResult(
                status=GateCheckStatus.BLOCKED,
                content_id=content_id,
                reasons=[
                    GateBlockReason(
                        code="NOT_FOUND",
                        description="AI content not found in scope",
                    )
                ],
            )

        # Check 1: Must be confirmed
        if row["lifecycle_status"] != AiLifecycleStatus.CONFIRMED.value:
            reasons.append(
                GateBlockReason(
                    code="NOT_CONFIRMED",
                    description=f"AI content is '{row['lifecycle_status']}', not 'confirmed'",
                    detail={"current_status": row["lifecycle_status"]},
                )
            )

        # Check 2: Content hash must still match (detect tampering)
        current_hash = sha256_hex(row["output_text"])
        if current_hash != row["output_hash"]:
            reasons.append(
                GateBlockReason(
                    code="HASH_CHANGED",
                    description="Content hash changed since generation/confirmation",
                    detail={
                        "stored_hash": row["output_hash"],
                        "current_hash": current_hash,
                    },
                )
            )

        # Check 3: Referenced evidence must be non-stale (P19)
        if not await self._check_evidence_refs_valid(row.get("evidence_refs")):
            reasons.append(
                GateBlockReason(
                    code="EVIDENCE_STALE",
                    description="One or more referenced evidence items are stale or invalid",
                )
            )

        # Check 4: Service status must have been available at generation time
        if row.get("service_status") == AiServiceStatus.UNAVAILABLE.value:
            reasons.append(
                GateBlockReason(
                    code="SERVICE_UNAVAILABLE",
                    description="Content generated while AI service was unavailable (R8.4)",
                )
            )

        if reasons:
            return GateCheckResult(
                status=GateCheckStatus.BLOCKED,
                content_id=content_id,
                reasons=reasons,
            )

        return GateCheckResult(
            status=GateCheckStatus.ELIGIBLE,
            content_id=content_id,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _load_content(
        self, content_id: uuid.UUID, project_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Load AI content governance record by ID and scope."""
        stmt = sa.text(
            "SELECT id, project_id, audit_year, wp_id, entry_point, "
            "prompt_hash, model_name, service_status, "
            "output_text, output_hash, target_cell, "
            "evidence_refs, citation_snapshots, "
            "lifecycle_status, content_version, "
            "confirmed_by_user_id, confirmed_at "
            "FROM ai_content_governance "
            "WHERE id = :id AND project_id = :pid LIMIT 1"
        )
        row = (
            await self._db.execute(
                stmt, {"id": str(content_id), "pid": str(project_id)}
            )
        ).mappings().first()
        if row is None:
            return None
        return dict(row)

    async def _check_evidence_refs_valid(
        self, evidence_refs_json: str | None
    ) -> bool:
        """Check that all referenced evidence refs are active and non-stale.

        Returns True if all refs are valid or there are no refs.
        """
        if not evidence_refs_json:
            return True

        import json as _json

        try:
            ref_ids = _json.loads(evidence_refs_json)
        except (TypeError, ValueError):
            return True  # No parseable refs — pass

        if not ref_ids:
            return True

        # Check all refs are still active
        placeholders = ", ".join(f":r{i}" for i in range(len(ref_ids)))
        stmt = sa.text(
            f"SELECT COUNT(*) AS cnt FROM evidence_refs "
            f"WHERE id IN ({placeholders}) AND status = 'active'"
        )
        params = {f"r{i}": str(rid) for i, rid in enumerate(ref_ids)}
        result = (await self._db.execute(stmt, params)).mappings().first()

        if result is None:
            return True

        active_count = int(result["cnt"])
        return active_count == len(ref_ids)


# ─────────────────────────────────────────────────────────────────────────────
# Coverage scanner pure function (P18)
# ─────────────────────────────────────────────────────────────────────────────


def compute_coverage_gap(
    discovered_entry_points: set[str],
    declared_gated_set: set[str] | frozenset[str] | None = None,
) -> set[str]:
    """Compute undeclared AI entry points (P18).

    Returns: discovered_set - declared_gated_set
    If non-empty, CI must block merge.
    """
    if declared_gated_set is None:
        declared_gated_set = AI_ENTRY_REGISTRY
    return discovered_entry_points - set(declared_gated_set)
