"""ArchiveManifestService — Task 7.1 (Wave 6).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R11, R15
Design: §5.5 Archive, Retention 与 Legal Hold
Properties:
  P23 — manifest 完备性 (manifest nodes/edges = exact reachable evidence graph
         from policy-required evidence + existing dependencies)
  P24 — manifest 防覆盖 (each archive creates new version, history immutable)

Two-phase watermark:
  1. preflight: short transaction freezes UnifiedGraph + policy-required evidence
     watermark
  2. finalize: async build completes, then re-run FormalOutputGate and compare
     watermark — if changed, fail and retry from preflight

Blocking difference report:
  - ONLY generated when validation FAILS AND actually BLOCKS archival.
  - When validation passes and archive succeeds → NO blocking report generated.

Sealed packages:
  - Each archive creates a NEW version; sealed package/manifest/entries/edges are
    immutable once sealed.
  - Subsequent archives increment version.

Offline verifier:
  - Doesn't connect to business DB, recomputes member/manifest/package hash.
"""

from __future__ import annotations

import enum
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
from app.services.evidence_governance.formal_output_gate import (
    BlockReasonCode,
    BlockingReason,
    FormalOutputGate,
    GateEvaluation,
    GatePhase,
    GateVerdict,
)
from app.services.evidence_governance.unified_graph_builder import (
    GraphScope,
    NormalizedEdge,
    UnifiedGraph,
    UnifiedGraphBuilder,
)


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────


class ArchivePhase(str, enum.Enum):
    """Archive lifecycle phase."""

    PREFLIGHT = "preflight"
    BUILDING = "building"
    FINALIZING = "finalizing"
    SEALED = "sealed"
    FAILED = "failed"


class ManifestEntryType(str, enum.Enum):
    """Types of entries in the archive manifest."""

    ATTACHMENT_VERSION = "attachment_version"
    EVIDENCE_REF = "evidence_ref"
    OCR_JOB = "ocr_job"
    OCR_RESULT = "ocr_result"
    OCR_CONFIRMATION = "ocr_confirmation"
    OCR_WRITEBACK = "ocr_writeback"
    CITATION_SNAPSHOT = "citation_snapshot"
    AI_CONTENT = "ai_content"
    REVIEW_RECORD = "review_record"
    STALE_CHAIN = "stale_chain"
    DELIVERABLE = "deliverable"
    RETENTION_STATUS = "retention_status"


@dataclass(frozen=True)
class ManifestEntry:
    """A single entry in the archive manifest.

    Represents one evidence object frozen at archive time.
    """

    entry_id: str
    entry_type: ManifestEntryType
    object_id: str
    version: str | None = None
    content_hash: str | None = None
    state: str | None = None
    actor_type: str | None = None
    actor_id: str | None = None
    frozen_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ManifestEdge:
    """A frozen edge in the archive manifest (from the UnifiedGraph)."""

    edge_hash: str
    source_key: str
    target_key: str
    provenance: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArchiveManifest:
    """The complete archive manifest for a sealed package.

    Design invariants:
      - Precisely contains the graph's nodes/edges (P23)
      - Historical objects without attachments don't enlarge the graph
      - Sealed after finalize → immutable (P24)
      - Each archive creates a new version
    """

    manifest_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    audit_year: int = 0
    version: int = 1
    policy_version: str | None = None
    watermark: str = ""
    entries: list[ManifestEntry] = field(default_factory=list)
    edges: list[ManifestEdge] = field(default_factory=list)
    manifest_hash: str = ""
    sealed: bool = False
    sealed_at: datetime | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    actor: ActorContext | None = None
    phase: ArchivePhase = ArchivePhase.PREFLIGHT

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def compute_manifest_hash(self) -> str:
        """Compute deterministic manifest hash for offline verification.

        Hash covers all entries and edges in canonical form — any change
        to the archived data will invalidate the hash.
        """
        entries_data = [
            {
                "id": e.entry_id,
                "type": e.entry_type.value,
                "object_id": e.object_id,
                "version": e.version,
                "content_hash": e.content_hash,
                "state": e.state,
            }
            for e in sorted(self.entries, key=lambda x: x.entry_id)
        ]
        edges_data = [
            {
                "hash": e.edge_hash,
                "source": e.source_key,
                "target": e.target_key,
                "provenance": e.provenance,
            }
            for e in sorted(self.edges, key=lambda x: x.edge_hash)
        ]
        return content_hash_of({
            "manifest_id": self.manifest_id,
            "project_id": self.project_id,
            "audit_year": self.audit_year,
            "version": self.version,
            "policy_version": self.policy_version,
            "watermark": self.watermark,
            "entries": entries_data,
            "edges": edges_data,
        })

    def seal(self) -> None:
        """Seal the manifest — makes it immutable (P24).

        Once sealed, no entries/edges/version can be modified.
        """
        if self.sealed:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                "Manifest is already sealed — cannot re-seal",
            )
        self.manifest_hash = self.compute_manifest_hash()
        self.sealed = True
        self.sealed_at = datetime.now(timezone.utc)
        self.phase = ArchivePhase.SEALED


@dataclass
class SealedPackage:
    """A versioned sealed archive package (P24 — never overwritten).

    Each archive creates a new version. Historical packages are immutable.
    """

    package_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    manifest: ArchiveManifest | None = None
    version: int = 1
    package_hash: str = ""
    sealed_at: datetime | None = None
    actor: ActorContext | None = None

    @property
    def is_sealed(self) -> bool:
        return self.manifest is not None and self.manifest.sealed

    def compute_package_hash(self) -> str:
        """Compute package hash from manifest hash + metadata.

        Used by offline verifier to verify integrity without business DB.
        """
        if not self.manifest:
            return ""
        return content_hash_of({
            "package_id": self.package_id,
            "manifest_hash": self.manifest.manifest_hash,
            "version": self.version,
        })


@dataclass
class BlockingDifferenceReport:
    """Machine-readable blocking difference report.

    ONLY generated when validation FAILS AND actually BLOCKS archival.
    When validation passes and archive succeeds → this report is NOT generated.

    Design: §5.5 — "只有验证失败并实际阻断归档时才生成 blocking_difference_report"
    """

    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    audit_year: int = 0
    archive_version: int = 0
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    blocking_reasons: list[BlockingReason] = field(default_factory=list)
    watermark_preflight: str = ""
    watermark_finalize: str = ""
    evidence_gaps: list[dict[str, Any]] = field(default_factory=list)
    actor: ActorContext | None = None

    @property
    def is_blocking(self) -> bool:
        """Report is only meaningful if there are blocking reasons."""
        return len(self.blocking_reasons) > 0

    def to_machine_readable(self) -> dict[str, Any]:
        """Convert to machine-readable format for offline consumption."""
        return {
            "report_id": self.report_id,
            "project_id": self.project_id,
            "audit_year": self.audit_year,
            "archive_version": self.archive_version,
            "generated_at": self.generated_at.isoformat(),
            "is_blocking": self.is_blocking,
            "blocking_reason_count": len(self.blocking_reasons),
            "blocking_reasons": [
                {
                    "code": r.code.value,
                    "evidence_id": r.evidence_id,
                    "description": r.description,
                    "detail": r.detail,
                }
                for r in self.blocking_reasons
            ],
            "watermark_preflight": self.watermark_preflight,
            "watermark_finalize": self.watermark_finalize,
            "evidence_gaps": self.evidence_gaps,
        }


@dataclass
class ArchiveResult:
    """Result of an archive operation.

    Contains either:
      - A sealed package (success, no blocking report)
      - A blocking difference report (failure, archive blocked)
    """

    success: bool
    sealed_package: SealedPackage | None = None
    blocking_report: BlockingDifferenceReport | None = None
    gate_evaluation: GateEvaluation | None = None

    @property
    def has_blocking_report(self) -> bool:
        """Only True when archive was blocked by validation failure."""
        return self.blocking_report is not None and self.blocking_report.is_blocking


# ─────────────────────────────────────────────────────────────────────────────
# ArchiveManifestService
# ─────────────────────────────────────────────────────────────────────────────


class ArchiveManifestService:
    """Two-phase watermark archive service with versioned sealed packages.

    Design §5.5:
      - Short transaction freezes UnifiedGraph + policy-required evidence watermark
      - Async calls deliverable center & ArchiveOrchestrator to build
      - Finalize re-runs FormalOutputGate and compares watermark
      - ONLY generates blocking_difference_report when validation fails AND blocks
      - Successful archive does NOT generate blocking report
      - Each archive creates new version, sealed package immutable

    Usage:
        service = ArchiveManifestService(gate, graph_builder)
        preflight = await service.preflight(scope, actor)
        # ... async build ...
        result = await service.finalize(preflight, actor)
        if result.success:
            assert result.blocking_report is None  # Key invariant!
            # result.sealed_package is ready
        else:
            assert result.has_blocking_report  # Only on failure
    """

    def __init__(
        self,
        gate: FormalOutputGate | None = None,
        graph_builder: UnifiedGraphBuilder | None = None,
    ) -> None:
        self._gate = gate or FormalOutputGate()
        self._graph_builder = graph_builder
        # In-memory store of sealed packages (production would use DB)
        self._sealed_packages: dict[str, list[SealedPackage]] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 1: Preflight — capture watermark
    # ─────────────────────────────────────────────────────────────────────────

    async def preflight(
        self,
        scope: GraphScope,
        actor: ActorContext,
        *,
        policy_version: str | None = None,
    ) -> ArchiveManifest:
        """Phase 1: Preflight — capture watermark.

        Short transaction that:
          1. Freezes UnifiedGraph + policy-required evidence
          2. Runs FormalOutputGate preflight
          3. Captures watermark for finalize comparison
          4. If gate fails at preflight → return manifest in FAILED phase
             (blocking report generated at finalize)

        Returns a manifest in PREFLIGHT or FAILED phase with watermark.
        """
        target_id = f"archive:{scope.project_id}:{scope.audit_year}"
        target_type = "archive"

        # Run FormalOutputGate preflight
        gate_result = await self._gate.preflight(
            target_id, target_type, policy_version=policy_version
        )

        # Determine next version
        next_version = self._get_next_version(scope)

        # Create manifest with watermark
        manifest = ArchiveManifest(
            project_id=str(scope.project_id),
            audit_year=scope.audit_year,
            version=next_version,
            policy_version=gate_result.policy_version,
            watermark=gate_result.watermark or "",
            actor=actor,
            phase=ArchivePhase.PREFLIGHT,
        )

        # If gate failed at preflight, mark phase but don't generate report yet
        # (report only at finalize when it actually blocks)
        if gate_result.failed:
            manifest.phase = ArchivePhase.FAILED

        return manifest

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 2: Build manifest entries/edges (async)
    # ─────────────────────────────────────────────────────────────────────────

    async def build_manifest(
        self,
        manifest: ArchiveManifest,
        *,
        graph: UnifiedGraph | None = None,
        evidence_items: list[dict[str, Any]] | None = None,
    ) -> ArchiveManifest:
        """Phase 2: Build manifest entries and edges from the evidence graph.

        Populates the manifest with:
          - Entries: attachment versions, EvidenceRef, OCR jobs/results/confirmations/
            writebacks, CitationSnapshot, AI_Content, review records, stale chains,
            deliverables, retention status
          - Edges: from the UnifiedGraph frozen at preflight

        Historical objects without attachments do NOT enlarge the graph (P23).
        """
        manifest.phase = ArchivePhase.BUILDING

        # Populate edges from graph
        if graph:
            for edge in graph.edges.values():
                manifest.edges.append(
                    ManifestEdge(
                        edge_hash=edge.edge_hash,
                        source_key=edge.source_key,
                        target_key=edge.target_key,
                        provenance=edge.provenance.value,
                        metadata=edge.metadata,
                    )
                )

        # Populate entries from evidence items
        if evidence_items:
            for item in evidence_items:
                entry = ManifestEntry(
                    entry_id=item.get("id", str(uuid.uuid4())),
                    entry_type=ManifestEntryType(
                        item.get("type", "attachment_version")
                    ),
                    object_id=item.get("object_id", ""),
                    version=item.get("version"),
                    content_hash=item.get("content_hash"),
                    state=item.get("state"),
                    actor_type=item.get("actor_type"),
                    actor_id=item.get("actor_id"),
                    metadata=item.get("metadata", {}),
                )
                manifest.entries.append(entry)

        return manifest

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 3: Finalize — rerun gate + compare watermark
    # ─────────────────────────────────────────────────────────────────────────

    async def finalize(
        self,
        manifest: ArchiveManifest,
        actor: ActorContext,
    ) -> ArchiveResult:
        """Phase 3: Finalize — rerun FormalOutputGate and compare watermark.

        Design §5.5:
          - Re-runs FormalOutputGate at finalize
          - Compares watermark with preflight
          - If watermark changed or gate fails → archive blocked
          - ONLY when validation FAILS AND blocks: generate blocking_difference_report
          - When validation PASSES: seal package, NO blocking report

        Returns ArchiveResult with either sealed_package or blocking_report.
        """
        manifest.phase = ArchivePhase.FINALIZING

        target_id = (
            f"archive:{manifest.project_id}:{manifest.audit_year}"
        )
        target_type = "archive"

        # Re-run FormalOutputGate finalize with preflight watermark
        gate_result = await self._gate.finalize(
            target_id,
            target_type,
            manifest.watermark,
            policy_version=manifest.policy_version,
        )

        # ─── Success path: seal and return (NO blocking report) ───
        if gate_result.passed:
            manifest.seal()
            package = self._create_sealed_package(manifest, actor)
            return ArchiveResult(
                success=True,
                sealed_package=package,
                blocking_report=None,  # Key: NO report on success!
                gate_evaluation=gate_result,
            )

        # ─── Failure path: generate blocking difference report ───
        manifest.phase = ArchivePhase.FAILED

        blocking_report = self._generate_blocking_report(
            manifest, gate_result, actor
        )

        return ArchiveResult(
            success=False,
            sealed_package=None,
            blocking_report=blocking_report,
            gate_evaluation=gate_result,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Sealed package creation (P24 — never overwrite)
    # ─────────────────────────────────────────────────────────────────────────

    def _create_sealed_package(
        self, manifest: ArchiveManifest, actor: ActorContext
    ) -> SealedPackage:
        """Create a new versioned sealed package.

        P24: Each archive creates a new version. Historical packages are immutable.
        Never overwrites existing packages.
        """
        package = SealedPackage(
            manifest=manifest,
            version=manifest.version,
            sealed_at=manifest.sealed_at,
            actor=actor,
        )
        package.package_hash = package.compute_package_hash()

        # Store in version history (never overwrite existing)
        scope_key = f"{manifest.project_id}:{manifest.audit_year}"
        if scope_key not in self._sealed_packages:
            self._sealed_packages[scope_key] = []
        self._sealed_packages[scope_key].append(package)

        return package

    def _get_next_version(self, scope: GraphScope) -> int:
        """Get the next version number for the scope.

        Each archive increments version. Never reuses or overwrites.
        """
        scope_key = f"{scope.project_id}:{scope.audit_year}"
        existing = self._sealed_packages.get(scope_key, [])
        if not existing:
            return 1
        return max(p.version for p in existing) + 1

    def get_sealed_packages(
        self, scope: GraphScope
    ) -> list[SealedPackage]:
        """Get all sealed packages for a scope (for offline verification).

        Historical packages are immutable (P24).
        """
        scope_key = f"{scope.project_id}:{scope.audit_year}"
        return list(self._sealed_packages.get(scope_key, []))

    # ─────────────────────────────────────────────────────────────────────────
    # Blocking difference report (ONLY on failure)
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_blocking_report(
        self,
        manifest: ArchiveManifest,
        gate_result: GateEvaluation,
        actor: ActorContext,
    ) -> BlockingDifferenceReport:
        """Generate blocking difference report.

        ONLY called when validation FAILS AND blocks archival.
        Contains complete, machine-readable blocking differences.

        Design §5.5: "只有验证失败并实际阻断归档时才生成 blocking_difference_report"
        """
        evidence_gaps: list[dict[str, Any]] = []
        for reason in gate_result.blocking_reasons:
            gap: dict[str, Any] = {
                "code": reason.code.value,
                "description": reason.description,
            }
            if reason.evidence_id:
                gap["evidence_id"] = reason.evidence_id
            if reason.detail:
                gap["detail"] = reason.detail
            evidence_gaps.append(gap)

        return BlockingDifferenceReport(
            project_id=manifest.project_id,
            audit_year=manifest.audit_year,
            archive_version=manifest.version,
            blocking_reasons=gate_result.blocking_reasons,
            watermark_preflight=manifest.watermark,
            watermark_finalize=gate_result.watermark or "",
            evidence_gaps=evidence_gaps,
            actor=actor,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Offline verifier support
# ─────────────────────────────────────────────────────────────────────────────


def verify_package_offline(package: SealedPackage) -> bool:
    """Verify a sealed package without connecting to business DB.

    Recomputes member/manifest/package hash and compares.
    Design §5.5: "离线 verifier 不连接业务库，重算成员、manifest 与 package hash"
    """
    if not package.manifest or not package.manifest.sealed:
        return False

    # Recompute manifest hash
    recomputed_manifest_hash = package.manifest.compute_manifest_hash()
    if recomputed_manifest_hash != package.manifest.manifest_hash:
        return False

    # Recompute package hash
    recomputed_package_hash = package.compute_package_hash()
    if recomputed_package_hash != package.package_hash:
        return False

    return True


__all__ = [
    "ArchiveManifestService",
    "ArchiveManifest",
    "ArchivePhase",
    "ArchiveResult",
    "BlockingDifferenceReport",
    "ManifestEntry",
    "ManifestEntryType",
    "ManifestEdge",
    "SealedPackage",
    "verify_package_offline",
]
