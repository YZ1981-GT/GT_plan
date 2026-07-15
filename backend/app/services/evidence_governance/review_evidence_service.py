"""ReviewEvidenceService — Task 6.5, Wave 5.

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R9, R10, R12
Design: §4.6 Citation, AI, Review, Manifest, Hold, Audit
        §5.4 stale, Review, unified graph

Implements:
  - ReviewEvidenceSnapshot: freezes ref/version/hash/locator at create/close time
  - close_review gate: requires permission + explanation + non-stale ref
  - auto_reopen: marks opinion re_review_required when evidence replaced/deactivated/stale
  - QC/EQCR/partner completion blocking when any review is re_review_required
  - get_evidence_display: shows version/hash/OCR-AI confirmation/stale path/locator

Properties validated: P21 (Blocking Review 关闭门禁), P22 (复核自动重开)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)


# ─────────────────────────────────────────────────────────────────────────────
# Domain enums
# ─────────────────────────────────────────────────────────────────────────────


class ReviewStatus(str, Enum):
    """Review opinion lifecycle states."""

    open = "open"
    closed = "closed"
    re_review_required = "re_review_required"


class ReviewSeverity(str, Enum):
    """Review opinion severity levels."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


# Blocking review = severity high or critical AND not effectively closed
BLOCKING_SEVERITIES: frozenset[str] = frozenset({"high", "critical"})


# ─────────────────────────────────────────────────────────────────────────────
# ReviewEvidenceSnapshot — immutable at create/close time (design §4.6)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReviewEvidenceSnapshot:
    """Freezes evidence state at the moment an opinion is created or closed.

    Design §4.6: ReviewEvidenceSnapshot 冻结提出/关闭时的 ref/version/hash/locator.
    """

    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    evidence_ref_id: str = ""
    evidence_type: str = ""
    target_version: int = 0
    target_hash: str = ""
    locator: str = ""
    ocr_confirmed: bool = False
    ai_confirmed: bool = False
    stale: bool = False
    snapshot_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ─────────────────────────────────────────────────────────────────────────────
# ReviewOpinion — in-memory representation
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ReviewOpinion:
    """In-memory representation of a review opinion with evidence bindings."""

    opinion_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    audit_year: int = 0
    target_type: str = ""
    target_id: str = ""
    severity: str = "medium"
    status: str = ReviewStatus.open.value
    content: str = ""
    created_by_user_id: str = ""
    closed_by_user_id: Optional[str] = None
    closing_explanation: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    closed_at: Optional[str] = None
    # Snapshots taken at creation time
    evidence_snapshots: list[ReviewEvidenceSnapshot] = field(default_factory=list)
    # Snapshots taken at close time (if closed)
    close_snapshots: list[ReviewEvidenceSnapshot] = field(default_factory=list)
    # History of status transitions
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_blocking(self) -> bool:
        """A Blocking_Review = severity high/critical AND not effectively closed."""
        return (
            self.severity in BLOCKING_SEVERITIES
            and self.status != ReviewStatus.closed.value
        )


# ─────────────────────────────────────────────────────────────────────────────
# Close gate errors — structured results
# ─────────────────────────────────────────────────────────────────────────────


class CloseRejectReason(str, Enum):
    """Specific reasons for rejecting review closure (R10.2)."""

    insufficient_explanation = "INSUFFICIENT_EXPLANATION"
    no_valid_evidence_ref = "NO_VALID_EVIDENCE_REF"
    permission_denied = "PERMISSION_DENIED"
    service_identity_forbidden = "SERVICE_IDENTITY_FORBIDDEN"
    review_not_open = "REVIEW_NOT_OPEN"


@dataclass
class CloseGateResult:
    """Result of attempting to close a Blocking Review."""

    allowed: bool
    reject_reasons: list[CloseRejectReason] = field(default_factory=list)
    message: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Evidence display for QC/EQCR (R10.4)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class EvidenceDisplayItem:
    """Evidence display record for QC/EQCR views (R10.4).

    Shows source version, hash, human confirmation record, stale status,
    and locatable reference — not just excerpt.
    """

    evidence_ref_id: str = ""
    evidence_type: str = ""
    source_version: int = 0
    content_hash: str = ""
    ocr_confirmed: bool = False
    ocr_confirmation_at: Optional[str] = None
    ocr_confirmed_by: Optional[str] = None
    ai_confirmed: bool = False
    ai_confirmation_at: Optional[str] = None
    ai_confirmed_by: Optional[str] = None
    is_stale: bool = False
    stale_path: list[str] = field(default_factory=list)
    locator: str = ""
    locator_type: str = ""  # opaque / download_url / page_region


# ─────────────────────────────────────────────────────────────────────────────
# ReviewEvidenceService — core service
# ─────────────────────────────────────────────────────────────────────────────


class ReviewEvidenceService:
    """Manages review evidence snapshots, close gate, auto-reopen, and QC/EQCR blocking.

    Design §4.6: ReviewEvidenceSnapshot freezes ref/version/hash/locator at create/close.
    Design §5.4: Closing后 Review 依据失效时转 re_review_required，阻断相应 QC/EQCR/partner 完成.

    Properties:
      P21: Blocking Review 仅在权限、充分说明、至少一个有效非 stale ref 同时满足时关闭
      P22: 已关闭意见依据失效后进入待重新复核并阻断 QC/EQCR/partner gate
    """

    # Capability required to close reviews (design §2.2)
    CLOSE_CAPABILITY = "review.close"
    # Capabilities that are blocked when re_review_required exists
    BLOCKED_CAPABILITIES = frozenset({"qc.complete", "eqcr.complete", "partner.complete"})

    def create_snapshot(
        self,
        evidence_ref_id: str,
        evidence_type: str,
        target_version: int,
        target_hash: str,
        locator: str,
        *,
        ocr_confirmed: bool = False,
        ai_confirmed: bool = False,
        stale: bool = False,
    ) -> ReviewEvidenceSnapshot:
        """Create an immutable evidence snapshot (used at opinion create or close time)."""
        return ReviewEvidenceSnapshot(
            evidence_ref_id=evidence_ref_id,
            evidence_type=evidence_type,
            target_version=target_version,
            target_hash=target_hash,
            locator=locator,
            ocr_confirmed=ocr_confirmed,
            ai_confirmed=ai_confirmed,
            stale=stale,
        )

    def create_opinion(
        self,
        *,
        project_id: str,
        audit_year: int,
        target_type: str,
        target_id: str,
        severity: str,
        content: str,
        created_by_user_id: str,
        evidence_refs: list[dict[str, Any]] | None = None,
    ) -> ReviewOpinion:
        """Create a review opinion with frozen evidence snapshots (R10.1).

        When creating, allows linking current accessible EvidenceRef and freezes
        evidence version snapshot.
        """
        snapshots = []
        if evidence_refs:
            for ref_data in evidence_refs:
                snap = self.create_snapshot(
                    evidence_ref_id=ref_data.get("evidence_ref_id", ""),
                    evidence_type=ref_data.get("evidence_type", ""),
                    target_version=ref_data.get("target_version", 0),
                    target_hash=ref_data.get("target_hash", ""),
                    locator=ref_data.get("locator", ""),
                    ocr_confirmed=ref_data.get("ocr_confirmed", False),
                    ai_confirmed=ref_data.get("ai_confirmed", False),
                    stale=ref_data.get("stale", False),
                )
                snapshots.append(snap)

        opinion = ReviewOpinion(
            project_id=project_id,
            audit_year=audit_year,
            target_type=target_type,
            target_id=target_id,
            severity=severity,
            status=ReviewStatus.open.value,
            content=content,
            created_by_user_id=created_by_user_id,
            evidence_snapshots=snapshots,
        )
        opinion.history.append({
            "action": "created",
            "at": opinion.created_at,
            "by": created_by_user_id,
            "status": ReviewStatus.open.value,
        })
        return opinion

    def evaluate_close_gate(
        self,
        opinion: ReviewOpinion,
        *,
        closing_explanation: str,
        closer_user_id: str,
        actor: ActorContext,
        has_close_permission: bool,
        current_evidence_refs: list[dict[str, Any]] | None = None,
    ) -> CloseGateResult:
        """Evaluate whether a Blocking Review can be closed (P21 gate).

        R10.2: IF user closes Blocking_Review without sufficient closing explanation,
        at least one non-stale EvidenceRef, or required permissions → reject close
        and preserve full history.

        Gate conditions (ALL must be met):
          1. Actor is human (not Service Identity)
          2. Actor has review.close permission
          3. Closing explanation is non-empty and sufficient
          4. At least one non-stale EvidenceRef exists
          5. Opinion is currently open or re_review_required (closeable state)

        Uses independent closed_by_user_id NOT NULL (no Service Identity).
        """
        reasons: list[CloseRejectReason] = []

        # 1. Service Identity cannot close reviews (design §2.2)
        if actor.is_service:
            reasons.append(CloseRejectReason.service_identity_forbidden)
            return CloseGateResult(
                allowed=False,
                reject_reasons=reasons,
                message="Service Identity cannot close reviews",
            )

        # 2. Permission check
        if not has_close_permission:
            reasons.append(CloseRejectReason.permission_denied)

        # 3. Sufficient closing explanation (non-empty after strip)
        if not closing_explanation or not closing_explanation.strip():
            reasons.append(CloseRejectReason.insufficient_explanation)

        # 4. At least one non-stale EvidenceRef
        has_valid_ref = False
        if current_evidence_refs:
            for ref_data in current_evidence_refs:
                if not ref_data.get("stale", True):
                    has_valid_ref = True
                    break
        if not has_valid_ref:
            reasons.append(CloseRejectReason.no_valid_evidence_ref)

        # 5. Opinion must be in closeable state
        if opinion.status not in (
            ReviewStatus.open.value,
            ReviewStatus.re_review_required.value,
        ):
            reasons.append(CloseRejectReason.review_not_open)

        if reasons:
            return CloseGateResult(
                allowed=False,
                reject_reasons=reasons,
                message=f"Close rejected: {', '.join(r.value for r in reasons)}",
            )

        return CloseGateResult(allowed=True, message="Close permitted")

    def close_review(
        self,
        opinion: ReviewOpinion,
        *,
        closing_explanation: str,
        closer_user_id: str,
        actor: ActorContext,
        has_close_permission: bool,
        current_evidence_refs: list[dict[str, Any]] | None = None,
    ) -> CloseGateResult:
        """Attempt to close a review opinion (R10.2 / P21).

        On success: mutates opinion to closed state, records close snapshots.
        On failure: preserves full history, returns structured error (R10.2).
        """
        gate_result = self.evaluate_close_gate(
            opinion,
            closing_explanation=closing_explanation,
            closer_user_id=closer_user_id,
            actor=actor,
            has_close_permission=has_close_permission,
            current_evidence_refs=current_evidence_refs,
        )

        if not gate_result.allowed:
            # Preserve full history (R10.2)
            opinion.history.append({
                "action": "close_rejected",
                "at": datetime.now(timezone.utc).isoformat(),
                "by": closer_user_id,
                "reasons": [r.value for r in gate_result.reject_reasons],
            })
            return gate_result

        # Close succeeds — freeze close-time evidence snapshots
        close_snapshots = []
        if current_evidence_refs:
            for ref_data in current_evidence_refs:
                snap = self.create_snapshot(
                    evidence_ref_id=ref_data.get("evidence_ref_id", ""),
                    evidence_type=ref_data.get("evidence_type", ""),
                    target_version=ref_data.get("target_version", 0),
                    target_hash=ref_data.get("target_hash", ""),
                    locator=ref_data.get("locator", ""),
                    ocr_confirmed=ref_data.get("ocr_confirmed", False),
                    ai_confirmed=ref_data.get("ai_confirmed", False),
                    stale=ref_data.get("stale", False),
                )
                close_snapshots.append(snap)

        now = datetime.now(timezone.utc).isoformat()
        opinion.status = ReviewStatus.closed.value
        opinion.closed_by_user_id = closer_user_id
        opinion.closing_explanation = closing_explanation
        opinion.closed_at = now
        opinion.close_snapshots = close_snapshots
        opinion.history.append({
            "action": "closed",
            "at": now,
            "by": closer_user_id,
            "status": ReviewStatus.closed.value,
        })

        return gate_result

    def auto_reopen(
        self,
        opinion: ReviewOpinion,
        *,
        reason: str = "evidence_invalidated",
        invalidated_ref_ids: list[str] | None = None,
    ) -> bool:
        """Auto-reopen a closed opinion when its evidence is invalidated (P22).

        R10.3: When closed opinion's evidence is replaced, deactivated, or marked
        stale → set opinion to re_review_required and block corresponding QC/EQCR/
        partner conclusion completion.

        Returns True if the opinion was reopened, False if it was already open or
        not in a closeable state.
        """
        if opinion.status != ReviewStatus.closed.value:
            return False

        now = datetime.now(timezone.utc).isoformat()
        opinion.status = ReviewStatus.re_review_required.value
        opinion.history.append({
            "action": "auto_reopened",
            "at": now,
            "reason": reason,
            "invalidated_ref_ids": invalidated_ref_ids or [],
            "previous_status": ReviewStatus.closed.value,
        })
        return True

    def check_completion_blocked(
        self,
        opinions: list[ReviewOpinion],
        *,
        target_type: str = "",
        target_id: str = "",
    ) -> bool:
        """Check if QC/EQCR/partner completion is blocked by any re_review_required review.

        R10.3: Block corresponding QC/EQCR/partner conclusion completion when any
        related review is in re_review_required state.

        Returns True if completion is BLOCKED (i.e., cannot proceed).
        """
        for opinion in opinions:
            if opinion.status == ReviewStatus.re_review_required.value:
                # Any re_review_required blocks completion
                if target_type and target_id:
                    if (
                        opinion.target_type == target_type
                        and opinion.target_id == target_id
                    ):
                        return True
                else:
                    return True
        return False

    def get_blocking_reviews(
        self,
        opinions: list[ReviewOpinion],
    ) -> list[ReviewOpinion]:
        """Get all currently blocking reviews (high/critical severity, not closed)."""
        return [op for op in opinions if op.is_blocking]

    def get_evidence_display(
        self,
        opinion: ReviewOpinion,
        *,
        current_evidence_state: list[dict[str, Any]] | None = None,
    ) -> list[EvidenceDisplayItem]:
        """Build evidence display for QC/EQCR views (R10.4).

        Shows source version, hash, human confirmation record, stale status,
        and locatable reference — not just excerpt.
        """
        items: list[EvidenceDisplayItem] = []

        # Use close_snapshots if closed, else creation snapshots, plus current state
        snapshots = opinion.close_snapshots or opinion.evidence_snapshots
        current_map: dict[str, dict[str, Any]] = {}
        if current_evidence_state:
            for ce in current_evidence_state:
                ref_id = ce.get("evidence_ref_id", "")
                if ref_id:
                    current_map[ref_id] = ce

        for snap in snapshots:
            # Merge current state if available for stale/locator updates
            current = current_map.get(snap.evidence_ref_id, {})

            item = EvidenceDisplayItem(
                evidence_ref_id=snap.evidence_ref_id,
                evidence_type=snap.evidence_type,
                source_version=snap.target_version,
                content_hash=snap.target_hash,
                ocr_confirmed=current.get("ocr_confirmed", snap.ocr_confirmed),
                ocr_confirmation_at=current.get("ocr_confirmation_at"),
                ocr_confirmed_by=current.get("ocr_confirmed_by"),
                ai_confirmed=current.get("ai_confirmed", snap.ai_confirmed),
                ai_confirmation_at=current.get("ai_confirmation_at"),
                ai_confirmed_by=current.get("ai_confirmed_by"),
                is_stale=current.get("stale", snap.stale),
                stale_path=current.get("stale_path", []),
                locator=current.get("locator", snap.locator),
                locator_type=current.get("locator_type", "opaque"),
            )
            items.append(item)

        return items
