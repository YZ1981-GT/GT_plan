"""FormalOutputGate — Task 6.3 (Wave 5).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R8, R9, R10, R11, R15
Design: §5.3 RAG/AI 与 FormalOutputGate
Properties:
  P17 — AI 状态门禁 (only human-confirmed + hash-consistent + valid evidence)
  P19 — 已确认内容变更失效 (confirmed content/dependency change → stale)
  P29 — 降级安全 (external dependency failure → no terminal state)

FormalOutput preflight/finalize dual gate for:
  底稿结论, 附注, 报告, 签发, QC/EQCR, deliverable 固化, archive

Key design invariant:
  RequiredEvidence(target, policy_version)
    = PolicyDeclaredRequiredEvidence(target, policy_version)
    ∪ ExistingDependencies(target, UnifiedGraph)

Gate validates each item in RequiredEvidence against P0 integrity constraints:
  metadata complete, actor present, version/hash valid, active ref,
  OCR confirmation/writeback, AI human confirmation, citation locatable,
  stale/pending propagation, Blocking Review, hold/retention consistent.

Historical objects without attachments AND without policy requiring them AND without
existing attachment dependencies do NOT produce MISSING_ATTACHMENT.

External dependency (storage/OCR/retrieval/AI) unavailable → fail-closed
(no confirmed/written_back/archived terminal state).

Watermark change between preflight and finalize → failure/retry.
"""

from __future__ import annotations

import enum
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
    canonical_json,
    content_hash_of,
    sha256_hex,
)


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────


class GatePhase(str, enum.Enum):
    """Gate evaluation phase."""

    PREFLIGHT = "preflight"
    FINALIZE = "finalize"


class GateVerdict(str, enum.Enum):
    """Overall gate evaluation result."""

    PASS = "pass"
    FAIL = "fail"


class BlockReasonCode(str, enum.Enum):
    """Standardized blocking reason codes."""

    METADATA_INCOMPLETE = "METADATA_INCOMPLETE"
    ACTOR_MISSING = "ACTOR_MISSING"
    VERSION_HASH_INVALID = "VERSION_HASH_INVALID"
    REF_INACTIVE = "REF_INACTIVE"
    OCR_NOT_CONFIRMED = "OCR_NOT_CONFIRMED"
    OCR_NOT_WRITTEN_BACK = "OCR_NOT_WRITTEN_BACK"
    AI_NOT_CONFIRMED = "AI_NOT_CONFIRMED"
    AI_HASH_CHANGED = "AI_HASH_CHANGED"
    CITATION_NOT_LOCATABLE = "CITATION_NOT_LOCATABLE"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    PENDING_PROPAGATION = "PENDING_PROPAGATION"
    BLOCKING_REVIEW = "BLOCKING_REVIEW"
    HOLD_RETENTION_INCONSISTENT = "HOLD_RETENTION_INCONSISTENT"
    MISSING_REQUIRED_EVIDENCE = "MISSING_REQUIRED_EVIDENCE"
    WATERMARK_CHANGED = "WATERMARK_CHANGED"
    DEPENDENCY_DEGRADED = "DEPENDENCY_DEGRADED"


@dataclass(frozen=True)
class BlockingReason:
    """A single reason why a formal output gate check failed."""

    code: BlockReasonCode
    evidence_id: str | None = None
    description: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceItem:
    """An evidence item in the required evidence set.

    Represents a single piece of evidence that must satisfy P0 constraints.
    """

    evidence_id: str
    evidence_type: str  # attachment_version, ocr_result, ai_content, citation, ref
    source: str  # "policy" or "dependency"
    # P0 constraint fields (nullable — absence checked by gate)
    metadata_complete: bool | None = None
    has_actor: bool | None = None
    version: str | None = None
    content_hash: str | None = None
    is_active_ref: bool | None = None
    ocr_confirmed: bool | None = None
    ocr_written_back: bool | None = None
    ai_human_confirmed: bool | None = None
    ai_hash_consistent: bool | None = None
    citation_locatable: bool | None = None
    is_stale: bool | None = None
    has_pending_propagation: bool | None = None
    has_blocking_review: bool | None = None
    hold_retention_consistent: bool | None = None


@dataclass
class GateEvaluation:
    """Structured result of a FormalOutput gate evaluation."""

    phase: GatePhase
    verdict: GateVerdict
    target_id: str
    target_type: str
    policy_version: str | None = None
    watermark: str | None = None
    blocking_reasons: list[BlockingReason] = field(default_factory=list)
    evidence_count: int = 0
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    degraded: bool = False

    @property
    def passed(self) -> bool:
        return self.verdict == GateVerdict.PASS

    @property
    def failed(self) -> bool:
        return self.verdict == GateVerdict.FAIL


@dataclass(frozen=True)
class ExternalDependencyStatus:
    """Status of an external dependency for degraded detection."""

    name: str  # storage, ocr, retrieval, ai
    available: bool
    last_check: datetime | None = None
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Policy adapter protocol (injected at construction)
# ─────────────────────────────────────────────────────────────────────────────


class PolicyProvider:
    """Protocol for retrieving policy-declared required evidence.

    Implementors return the set of evidence items that the active policy version
    declares as required for a given target.
    """

    async def get_policy_required_evidence(
        self, target_id: str, target_type: str, policy_version: str | None = None
    ) -> list[EvidenceItem]:
        """Return evidence items required by policy for the target."""
        return []

    async def get_policy_version(
        self, target_id: str, target_type: str
    ) -> str | None:
        """Return the active policy version for the target, or None."""
        return None


class UnifiedGraphProvider:
    """Protocol for retrieving existing dependencies from the UnifiedGraph.

    The UnifiedGraph is:
      ActiveEvidenceDependency(scope)
      ∪ Normalize(ACNRActiveEdges(scope))
      ∪ Normalize(LegacyActiveEdges(scope))
    """

    async def get_existing_dependencies(
        self, target_id: str, target_type: str
    ) -> list[EvidenceItem]:
        """Return evidence items that are existing dependencies of the target."""
        return []


class ExternalDependencyChecker:
    """Protocol for checking external dependency availability (P29)."""

    async def check_dependencies(self) -> list[ExternalDependencyStatus]:
        """Return status of all external dependencies (storage, OCR, retrieval, AI)."""
        return [
            ExternalDependencyStatus(name="storage", available=True),
            ExternalDependencyStatus(name="ocr", available=True),
            ExternalDependencyStatus(name="retrieval", available=True),
            ExternalDependencyStatus(name="ai", available=True),
        ]


class BlockingReviewChecker:
    """Protocol for checking whether target has active blocking reviews (R10)."""

    async def has_blocking_reviews(
        self, target_id: str, target_type: str
    ) -> bool:
        """Return True if target has unresolved blocking reviews."""
        return False


# ─────────────────────────────────────────────────────────────────────────────
# FormalOutputGate service
# ─────────────────────────────────────────────────────────────────────────────


class FormalOutputGate:
    """FormalOutput preflight/finalize dual gate.

    Shared by: 底稿结论, 附注, 报告, 签发, QC/EQCR, deliverable 固化, archive.

    Usage:
        gate = FormalOutputGate(policy_provider, graph_provider, dep_checker, review_checker)
        preflight_result = await gate.preflight(target_id, target_type)
        # ... time passes, mutations may occur ...
        finalize_result = await gate.finalize(target_id, target_type, preflight_watermark)
    """

    def __init__(
        self,
        policy_provider: PolicyProvider | None = None,
        graph_provider: UnifiedGraphProvider | None = None,
        dependency_checker: ExternalDependencyChecker | None = None,
        review_checker: BlockingReviewChecker | None = None,
    ) -> None:
        self._policy = policy_provider or PolicyProvider()
        self._graph = graph_provider or UnifiedGraphProvider()
        self._dep_checker = dependency_checker or ExternalDependencyChecker()
        self._review_checker = review_checker or BlockingReviewChecker()

    # ─────────────────────────────────────────────────────────────────────────
    # preflight (first gate check)
    # ─────────────────────────────────────────────────────────────────────────

    async def preflight(
        self,
        target_id: str,
        target_type: str,
        *,
        policy_version: str | None = None,
    ) -> GateEvaluation:
        """First gate check before formal output action.

        Computes RequiredEvidence, validates all P0 constraints, checks for degraded
        external dependencies. Returns GateEvaluation with watermark for finalize.
        """
        # Step 1: Check external dependency availability (P29 — fail-closed)
        degraded, dep_reasons = await self._check_degraded()
        if degraded:
            return GateEvaluation(
                phase=GatePhase.PREFLIGHT,
                verdict=GateVerdict.FAIL,
                target_id=target_id,
                target_type=target_type,
                policy_version=policy_version,
                blocking_reasons=dep_reasons,
                degraded=True,
            )

        # Step 2: Get policy version if not provided
        if policy_version is None:
            policy_version = await self._policy.get_policy_version(
                target_id, target_type
            )

        # Step 3: Build RequiredEvidence set
        required_evidence = await self._build_required_evidence(
            target_id, target_type, policy_version
        )

        # Step 4: Validate each evidence item against P0 constraints
        blocking_reasons = self._validate_evidence_set(required_evidence)

        # Step 5: Check blocking reviews (R10)
        if await self._review_checker.has_blocking_reviews(target_id, target_type):
            blocking_reasons.append(
                BlockingReason(
                    code=BlockReasonCode.BLOCKING_REVIEW,
                    description=(
                        "Target has unresolved blocking reviews "
                        "(severity high/critical)"
                    ),
                )
            )

        # Step 6: Compute watermark for finalize comparison
        watermark = self._compute_watermark(
            target_id, target_type, policy_version, required_evidence
        )

        verdict = GateVerdict.PASS if not blocking_reasons else GateVerdict.FAIL

        return GateEvaluation(
            phase=GatePhase.PREFLIGHT,
            verdict=verdict,
            target_id=target_id,
            target_type=target_type,
            policy_version=policy_version,
            watermark=watermark,
            blocking_reasons=blocking_reasons,
            evidence_count=len(required_evidence),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # finalize (second gate check — watermark comparison)
    # ─────────────────────────────────────────────────────────────────────────

    async def finalize(
        self,
        target_id: str,
        target_type: str,
        preflight_watermark: str,
        *,
        policy_version: str | None = None,
    ) -> GateEvaluation:
        """Second gate check at finalize time.

        Re-evaluates all constraints AND compares watermark with preflight.
        If watermark changed (evidence set mutated between preflight and finalize),
        the gate fails — caller must retry from preflight.
        """
        # Step 1: Check degraded (P29)
        degraded, dep_reasons = await self._check_degraded()
        if degraded:
            return GateEvaluation(
                phase=GatePhase.FINALIZE,
                verdict=GateVerdict.FAIL,
                target_id=target_id,
                target_type=target_type,
                policy_version=policy_version,
                blocking_reasons=dep_reasons,
                degraded=True,
            )

        # Step 2: Get policy version
        if policy_version is None:
            policy_version = await self._policy.get_policy_version(
                target_id, target_type
            )

        # Step 3: Build RequiredEvidence set (fresh)
        required_evidence = await self._build_required_evidence(
            target_id, target_type, policy_version
        )

        # Step 4: Compute current watermark and compare (watermark change → failure)
        current_watermark = self._compute_watermark(
            target_id, target_type, policy_version, required_evidence
        )

        blocking_reasons: list[BlockingReason] = []

        if current_watermark != preflight_watermark:
            blocking_reasons.append(
                BlockingReason(
                    code=BlockReasonCode.WATERMARK_CHANGED,
                    description=(
                        "Evidence set changed between preflight and finalize — "
                        "retry from preflight required"
                    ),
                    detail={
                        "preflight_watermark": preflight_watermark,
                        "finalize_watermark": current_watermark,
                    },
                )
            )

        # Step 5: Validate all P0 constraints (even if watermark changed)
        blocking_reasons.extend(self._validate_evidence_set(required_evidence))

        # Step 6: Check blocking reviews
        if await self._review_checker.has_blocking_reviews(target_id, target_type):
            blocking_reasons.append(
                BlockingReason(
                    code=BlockReasonCode.BLOCKING_REVIEW,
                    description=(
                        "Target has unresolved blocking reviews "
                        "(severity high/critical)"
                    ),
                )
            )

        verdict = GateVerdict.PASS if not blocking_reasons else GateVerdict.FAIL

        return GateEvaluation(
            phase=GatePhase.FINALIZE,
            verdict=verdict,
            target_id=target_id,
            target_type=target_type,
            policy_version=policy_version,
            watermark=current_watermark,
            blocking_reasons=blocking_reasons,
            evidence_count=len(required_evidence),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # RequiredEvidence builder
    # ─────────────────────────────────────────────────────────────────────────

    async def _build_required_evidence(
        self,
        target_id: str,
        target_type: str,
        policy_version: str | None,
    ) -> list[EvidenceItem]:
        """Build RequiredEvidence set:

        RequiredEvidence(target, policy_version)
          = PolicyDeclaredRequiredEvidence(target, policy_version)
          ∪ ExistingDependencies(target, UnifiedGraph)

        Historical objects without attachments AND without policy requiring them
        AND without existing attachment dependencies do NOT produce MISSING_ATTACHMENT.
        """
        # Fetch policy-declared evidence
        policy_evidence = await self._policy.get_policy_required_evidence(
            target_id, target_type, policy_version
        )

        # Fetch existing dependencies from UnifiedGraph
        existing_deps = await self._graph.get_existing_dependencies(
            target_id, target_type
        )

        # Union (deduplicate by evidence_id)
        evidence_map: dict[str, EvidenceItem] = {}
        for item in policy_evidence:
            evidence_map[item.evidence_id] = item
        for item in existing_deps:
            if item.evidence_id not in evidence_map:
                evidence_map[item.evidence_id] = item

        return list(evidence_map.values())

    # ─────────────────────────────────────────────────────────────────────────
    # P0 constraint validation
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_evidence_set(
        self, evidence_items: list[EvidenceItem]
    ) -> list[BlockingReason]:
        """Validate each evidence item against all P0 integrity constraints.

        Any existing or referenced evidence MUST satisfy ALL P0 integrity constraints.
        But historical objects without attachments don't auto-violate when policy
        doesn't require them and they have no existing attachment dependencies.
        """
        reasons: list[BlockingReason] = []

        for item in evidence_items:
            reasons.extend(self._validate_single_evidence(item))

        return reasons

    def _validate_single_evidence(self, item: EvidenceItem) -> list[BlockingReason]:
        """Validate a single evidence item against P0 constraints."""
        reasons: list[BlockingReason] = []

        # Check 1: Metadata complete
        if item.metadata_complete is False:
            reasons.append(
                BlockingReason(
                    code=BlockReasonCode.METADATA_INCOMPLETE,
                    evidence_id=item.evidence_id,
                    description=f"Evidence {item.evidence_type} has incomplete metadata",
                )
            )

        # Check 2: Actor present
        if item.has_actor is False:
            reasons.append(
                BlockingReason(
                    code=BlockReasonCode.ACTOR_MISSING,
                    evidence_id=item.evidence_id,
                    description=f"Evidence {item.evidence_type} has no actor/creator",
                )
            )

        # Check 3: Version/hash valid
        if item.version is not None and item.content_hash is None:
            reasons.append(
                BlockingReason(
                    code=BlockReasonCode.VERSION_HASH_INVALID,
                    evidence_id=item.evidence_id,
                    description=(
                        f"Evidence {item.evidence_type} has version but no content hash"
                    ),
                )
            )

        # Check 4: Active ref
        if item.is_active_ref is False:
            reasons.append(
                BlockingReason(
                    code=BlockReasonCode.REF_INACTIVE,
                    evidence_id=item.evidence_id,
                    description=f"EvidenceRef for {item.evidence_type} is inactive/stopped",
                )
            )

        # Check 5: OCR confirmation (only if applicable — type is ocr_result)
        if item.evidence_type == "ocr_result":
            if item.ocr_confirmed is False:
                reasons.append(
                    BlockingReason(
                        code=BlockReasonCode.OCR_NOT_CONFIRMED,
                        evidence_id=item.evidence_id,
                        description="OCR result not confirmed by human",
                    )
                )
            if item.ocr_written_back is False:
                reasons.append(
                    BlockingReason(
                        code=BlockReasonCode.OCR_NOT_WRITTEN_BACK,
                        evidence_id=item.evidence_id,
                        description="OCR result not written back to target",
                    )
                )

        # Check 6: AI human confirmation (only if applicable)
        if item.evidence_type == "ai_content":
            if item.ai_human_confirmed is False:
                reasons.append(
                    BlockingReason(
                        code=BlockReasonCode.AI_NOT_CONFIRMED,
                        evidence_id=item.evidence_id,
                        description="AI content not confirmed by human (P17)",
                    )
                )
            if item.ai_hash_consistent is False:
                reasons.append(
                    BlockingReason(
                        code=BlockReasonCode.AI_HASH_CHANGED,
                        evidence_id=item.evidence_id,
                        description="AI content hash changed since confirmation (P19)",
                    )
                )

        # Check 7: Citation locatable (only if applicable)
        if item.evidence_type == "citation":
            if item.citation_locatable is False:
                reasons.append(
                    BlockingReason(
                        code=BlockReasonCode.CITATION_NOT_LOCATABLE,
                        evidence_id=item.evidence_id,
                        description="Citation source cannot be located/verified",
                    )
                )

        # Check 8: Stale evidence
        if item.is_stale is True:
            reasons.append(
                BlockingReason(
                    code=BlockReasonCode.STALE_EVIDENCE,
                    evidence_id=item.evidence_id,
                    description=(
                        f"Evidence {item.evidence_type} is stale — "
                        "dependent evidence version/hash/confirmation invalidated"
                    ),
                )
            )

        # Check 9: Pending propagation
        if item.has_pending_propagation is True:
            reasons.append(
                BlockingReason(
                    code=BlockReasonCode.PENDING_PROPAGATION,
                    evidence_id=item.evidence_id,
                    description="Evidence has pending stale propagation",
                )
            )

        # Check 10: Hold/retention consistency
        if item.hold_retention_consistent is False:
            reasons.append(
                BlockingReason(
                    code=BlockReasonCode.HOLD_RETENTION_INCONSISTENT,
                    evidence_id=item.evidence_id,
                    description="Legal hold or retention scope is inconsistent",
                )
            )

        return reasons

    # ─────────────────────────────────────────────────────────────────────────
    # Degraded detection (P29)
    # ─────────────────────────────────────────────────────────────────────────

    async def _check_degraded(self) -> tuple[bool, list[BlockingReason]]:
        """Check if any external dependency is unavailable → fail-closed (P29).

        If storage, OCR, retrieval, or AI is unavailable/timeout/stub, the gate
        must fail — no confirmed/written_back/archived terminal state allowed.
        """
        statuses = await self._dep_checker.check_dependencies()
        reasons: list[BlockingReason] = []

        for status in statuses:
            if not status.available:
                reasons.append(
                    BlockingReason(
                        code=BlockReasonCode.DEPENDENCY_DEGRADED,
                        description=(
                            f"External dependency '{status.name}' is unavailable — "
                            "fail-closed: no terminal state allowed (P29)"
                        ),
                        detail={
                            "dependency": status.name,
                            "error": status.error or "unavailable",
                        },
                    )
                )

        return bool(reasons), reasons

    # ─────────────────────────────────────────────────────────────────────────
    # Watermark computation
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_watermark(
        self,
        target_id: str,
        target_type: str,
        policy_version: str | None,
        evidence_items: list[EvidenceItem],
    ) -> str:
        """Compute a deterministic watermark from the evidence set.

        Used to detect mutations between preflight and finalize. If the evidence
        set, versions, or hashes change, the watermark changes → finalize fails.
        """
        # Build a canonical representation of the evidence set
        evidence_snapshot = []
        for item in sorted(evidence_items, key=lambda e: e.evidence_id):
            evidence_snapshot.append(
                {
                    "id": item.evidence_id,
                    "type": item.evidence_type,
                    "source": item.source,
                    "version": item.version,
                    "hash": item.content_hash,
                    "stale": item.is_stale,
                }
            )

        watermark_input = {
            "target_id": target_id,
            "target_type": target_type,
            "policy_version": policy_version,
            "evidence": evidence_snapshot,
        }

        return content_hash_of(watermark_input)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: target types recognized by the gate
# ─────────────────────────────────────────────────────────────────────────────

#: Target types that use the FormalOutputGate at both preflight and finalize.
FORMAL_OUTPUT_TARGET_TYPES: frozenset[str] = frozenset(
    {
        "workpaper_conclusion",  # 底稿结论
        "disclosure_note",  # 附注
        "report",  # 报告
        "signoff",  # 签发
        "qc_conclusion",  # QC 结论
        "eqcr_conclusion",  # EQCR 结论
        "deliverable",  # 交付件固化
        "archive",  # 归档
    }
)
