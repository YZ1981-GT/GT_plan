"""Tests for ArchiveManifestService — Task 7.1 (Wave 6).

Validates: Requirements R11, R15
Properties:
  P23 — manifest 完备性
  P24 — manifest 防覆盖

Key invariants tested:
  1. Two-phase watermark: preflight captures, finalize compares
  2. Versioned sealed packages: each archive increments version, never overwrites
  3. Blocking difference report ONLY on validation failure that blocks archival
  4. Successful archival does NOT generate a blocking report
  5. Offline verifier recomputes hash without business DB
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.evidence_governance.archive_manifest_service import (
    ArchiveManifest,
    ArchiveManifestService,
    ArchivePhase,
    ArchiveResult,
    BlockingDifferenceReport,
    ManifestEntry,
    ManifestEntryType,
    ManifestEdge,
    SealedPackage,
    verify_package_offline,
)
from app.services.evidence_governance.formal_output_gate import (
    BlockingReason,
    BlockReasonCode,
    FormalOutputGate,
    GateEvaluation,
    GatePhase,
    GateVerdict,
    EvidenceItem,
    PolicyProvider,
    UnifiedGraphProvider,
    ExternalDependencyChecker,
    BlockingReviewChecker,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ActorType,
    content_hash_of,
)
from app.services.evidence_governance.unified_graph_builder import (
    EdgeProvenance,
    GraphScope,
    NormalizedEdge,
    UnifiedGraph,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def actor() -> ActorContext:
    return ActorContext.for_user(uuid.uuid4())


@pytest.fixture
def scope() -> GraphScope:
    return GraphScope(project_id=uuid.uuid4(), audit_year=2025)


@pytest.fixture
def passing_gate() -> FormalOutputGate:
    """Gate that always passes."""
    return FormalOutputGate()


@pytest.fixture
def failing_gate() -> FormalOutputGate:
    """Gate that always fails with specific blocking reasons."""

    class FailingPolicy(PolicyProvider):
        async def get_policy_required_evidence(self, target_id, target_type, policy_version=None):
            return [
                EvidenceItem(
                    evidence_id="ev-1",
                    evidence_type="attachment_version",
                    source="policy",
                    metadata_complete=False,  # Will trigger METADATA_INCOMPLETE
                    has_actor=True,
                ),
                EvidenceItem(
                    evidence_id="ev-2",
                    evidence_type="ai_content",
                    source="policy",
                    ai_human_confirmed=False,  # Will trigger AI_NOT_CONFIRMED
                    ai_hash_consistent=True,
                ),
            ]

    return FormalOutputGate(policy_provider=FailingPolicy())


@pytest.fixture
def service(passing_gate: FormalOutputGate) -> ArchiveManifestService:
    return ArchiveManifestService(gate=passing_gate)


@pytest.fixture
def failing_service(failing_gate: FormalOutputGate) -> ArchiveManifestService:
    return ArchiveManifestService(gate=failing_gate)


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests: Two-phase watermark
# ─────────────────────────────────────────────────────────────────────────────


class TestTwoPhaseWatermark:
    """Test the two-phase watermark capture and comparison."""

    @pytest.mark.asyncio
    async def test_preflight_captures_watermark(
        self, service: ArchiveManifestService, scope: GraphScope, actor: ActorContext
    ):
        """Preflight captures a non-empty watermark."""
        manifest = await service.preflight(scope, actor)
        assert manifest.watermark != ""
        assert manifest.phase == ArchivePhase.PREFLIGHT

    @pytest.mark.asyncio
    async def test_preflight_assigns_version(
        self, service: ArchiveManifestService, scope: GraphScope, actor: ActorContext
    ):
        """Preflight assigns the correct next version."""
        manifest = await service.preflight(scope, actor)
        assert manifest.version == 1

    @pytest.mark.asyncio
    async def test_finalize_compares_watermark_success(
        self, service: ArchiveManifestService, scope: GraphScope, actor: ActorContext
    ):
        """Finalize succeeds when watermark matches (no mutations between phases)."""
        manifest = await service.preflight(scope, actor)
        result = await service.finalize(manifest, actor)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_finalize_detects_watermark_change(
        self, scope: GraphScope, actor: ActorContext
    ):
        """Finalize fails when watermark changes between preflight and finalize."""
        # Create a gate that returns different watermarks between preflight/finalize
        class MutatingPolicy(PolicyProvider):
            call_count = 0

            async def get_policy_required_evidence(self, target_id, target_type, policy_version=None):
                self.call_count += 1
                if self.call_count <= 1:
                    # Preflight: empty evidence set
                    return []
                else:
                    # Finalize: different evidence set → different watermark
                    return [
                        EvidenceItem(
                            evidence_id="new-ev",
                            evidence_type="attachment_version",
                            source="policy",
                            metadata_complete=True,
                            has_actor=True,
                            version="1",
                            content_hash="abc123" * 10 + "abcd",
                        )
                    ]

        gate = FormalOutputGate(policy_provider=MutatingPolicy())
        service = ArchiveManifestService(gate=gate)

        manifest = await service.preflight(scope, actor)
        result = await service.finalize(manifest, actor)

        # Should fail due to watermark change
        assert result.success is False
        assert result.has_blocking_report is True


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests: Versioned sealed packages (P24)
# ─────────────────────────────────────────────────────────────────────────────


class TestVersionedSealedPackages:
    """Test that each archive creates a new version and never overwrites (P24)."""

    @pytest.mark.asyncio
    async def test_first_archive_is_version_1(
        self, service: ArchiveManifestService, scope: GraphScope, actor: ActorContext
    ):
        """First archive for a scope gets version 1."""
        manifest = await service.preflight(scope, actor)
        result = await service.finalize(manifest, actor)
        assert result.success
        assert result.sealed_package is not None
        assert result.sealed_package.version == 1

    @pytest.mark.asyncio
    async def test_subsequent_archives_increment_version(
        self, service: ArchiveManifestService, scope: GraphScope, actor: ActorContext
    ):
        """Subsequent archives create new versions, incrementing."""
        # First archive
        m1 = await service.preflight(scope, actor)
        r1 = await service.finalize(m1, actor)
        assert r1.success
        assert r1.sealed_package is not None
        assert r1.sealed_package.version == 1

        # Second archive
        m2 = await service.preflight(scope, actor)
        r2 = await service.finalize(m2, actor)
        assert r2.success
        assert r2.sealed_package is not None
        assert r2.sealed_package.version == 2

        # Third archive
        m3 = await service.preflight(scope, actor)
        r3 = await service.finalize(m3, actor)
        assert r3.success
        assert r3.sealed_package is not None
        assert r3.sealed_package.version == 3

    @pytest.mark.asyncio
    async def test_sealed_packages_are_immutable(
        self, service: ArchiveManifestService, scope: GraphScope, actor: ActorContext
    ):
        """Sealed packages cannot be re-sealed (immutability)."""
        manifest = await service.preflight(scope, actor)
        result = await service.finalize(manifest, actor)
        assert result.success
        assert result.sealed_package is not None
        assert result.sealed_package.manifest is not None
        assert result.sealed_package.manifest.sealed is True

        # Attempting to seal again raises error
        from app.services.evidence_governance.frozen_contracts import (
            EvidenceGovernanceError,
        )
        with pytest.raises(EvidenceGovernanceError):
            result.sealed_package.manifest.seal()

    @pytest.mark.asyncio
    async def test_historical_packages_preserved(
        self, service: ArchiveManifestService, scope: GraphScope, actor: ActorContext
    ):
        """Historical sealed packages are preserved and accessible."""
        # Create multiple archives
        for _ in range(3):
            m = await service.preflight(scope, actor)
            await service.finalize(m, actor)

        # All packages accessible
        packages = service.get_sealed_packages(scope)
        assert len(packages) == 3
        assert packages[0].version == 1
        assert packages[1].version == 2
        assert packages[2].version == 3


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests: Blocking difference report (ONLY on failure)
# ─────────────────────────────────────────────────────────────────────────────


class TestBlockingDifferenceReport:
    """Test that blocking reports are ONLY generated on validation failure."""

    @pytest.mark.asyncio
    async def test_success_no_blocking_report(
        self, service: ArchiveManifestService, scope: GraphScope, actor: ActorContext
    ):
        """Successful archive does NOT generate a blocking difference report.

        Key invariant from design §5.5:
        "校验通过并成功归档时不生成阻断差异报告"
        """
        manifest = await service.preflight(scope, actor)
        result = await service.finalize(manifest, actor)

        assert result.success is True
        assert result.blocking_report is None  # KEY: No report on success!
        assert result.has_blocking_report is False

    @pytest.mark.asyncio
    async def test_failure_generates_blocking_report(
        self,
        failing_service: ArchiveManifestService,
        scope: GraphScope,
        actor: ActorContext,
    ):
        """Validation failure that blocks archival generates a full blocking report.

        Key invariant from design §5.5:
        "只有验证失败并实际阻断归档时才生成 blocking_difference_report"
        """
        manifest = await failing_service.preflight(scope, actor)
        result = await failing_service.finalize(manifest, actor)

        assert result.success is False
        assert result.blocking_report is not None
        assert result.has_blocking_report is True
        assert len(result.blocking_report.blocking_reasons) > 0

    @pytest.mark.asyncio
    async def test_blocking_report_is_machine_readable(
        self,
        failing_service: ArchiveManifestService,
        scope: GraphScope,
        actor: ActorContext,
    ):
        """Blocking report has complete machine-readable format."""
        manifest = await failing_service.preflight(scope, actor)
        result = await failing_service.finalize(manifest, actor)

        assert result.blocking_report is not None
        mr = result.blocking_report.to_machine_readable()

        assert "report_id" in mr
        assert "project_id" in mr
        assert "audit_year" in mr
        assert "is_blocking" in mr
        assert mr["is_blocking"] is True
        assert "blocking_reasons" in mr
        assert len(mr["blocking_reasons"]) > 0
        assert "code" in mr["blocking_reasons"][0]
        assert "description" in mr["blocking_reasons"][0]

    @pytest.mark.asyncio
    async def test_blocking_report_contains_evidence_gaps(
        self,
        failing_service: ArchiveManifestService,
        scope: GraphScope,
        actor: ActorContext,
    ):
        """Blocking report includes evidence gaps with specific blocking reasons."""
        manifest = await failing_service.preflight(scope, actor)
        result = await failing_service.finalize(manifest, actor)

        assert result.blocking_report is not None
        assert len(result.blocking_report.evidence_gaps) > 0
        # Each gap has a code and description
        for gap in result.blocking_report.evidence_gaps:
            assert "code" in gap
            assert "description" in gap


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests: Manifest building
# ─────────────────────────────────────────────────────────────────────────────


class TestManifestBuilding:
    """Test manifest entry/edge population from evidence graph."""

    @pytest.mark.asyncio
    async def test_build_populates_entries(
        self, service: ArchiveManifestService, scope: GraphScope, actor: ActorContext
    ):
        """Build populates manifest entries from evidence items."""
        manifest = await service.preflight(scope, actor)
        items = [
            {
                "id": "entry-1",
                "type": "attachment_version",
                "object_id": "av-1",
                "version": "3",
                "content_hash": "abc" * 21 + "a",
                "state": "available",
            },
            {
                "id": "entry-2",
                "type": "ocr_result",
                "object_id": "ocr-1",
                "version": "1",
                "content_hash": "def" * 21 + "d",
                "state": "confirmed",
            },
        ]

        manifest = await service.build_manifest(manifest, evidence_items=items)
        assert manifest.entry_count == 2
        assert manifest.entries[0].entry_type == ManifestEntryType.ATTACHMENT_VERSION
        assert manifest.entries[1].entry_type == ManifestEntryType.OCR_RESULT

    @pytest.mark.asyncio
    async def test_build_populates_edges_from_graph(
        self, service: ArchiveManifestService, scope: GraphScope, actor: ActorContext
    ):
        """Build populates manifest edges from UnifiedGraph."""
        manifest = await service.preflight(scope, actor)

        graph = UnifiedGraph(scope=scope)
        graph.add_edge(NormalizedEdge(
            source_key="attachment_version:av-1",
            target_key="workpaper:wp-1",
            provenance=EdgeProvenance.EVIDENCE_DEPENDENCY,
            edge_hash="hash-1",
        ))
        graph.add_edge(NormalizedEdge(
            source_key="ocr_result:ocr-1",
            target_key="attachment_version:av-1",
            provenance=EdgeProvenance.EVIDENCE_DEPENDENCY,
            edge_hash="hash-2",
        ))

        manifest = await service.build_manifest(manifest, graph=graph)
        assert manifest.edge_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests: Offline verification
# ─────────────────────────────────────────────────────────────────────────────


class TestOfflineVerification:
    """Test that sealed packages can be verified offline (without business DB)."""

    @pytest.mark.asyncio
    async def test_valid_package_verifies_offline(
        self, service: ArchiveManifestService, scope: GraphScope, actor: ActorContext
    ):
        """Valid sealed package passes offline verification."""
        manifest = await service.preflight(scope, actor)
        result = await service.finalize(manifest, actor)
        assert result.success
        assert result.sealed_package is not None

        # Offline verification succeeds
        assert verify_package_offline(result.sealed_package) is True

    def test_tampered_manifest_hash_fails_verification(self, actor: ActorContext):
        """Package with tampered manifest hash fails offline verification."""
        manifest = ArchiveManifest(
            project_id=str(uuid.uuid4()),
            audit_year=2025,
            version=1,
            watermark="wm-123",
            actor=actor,
        )
        manifest.seal()

        package = SealedPackage(
            manifest=manifest,
            version=1,
            actor=actor,
        )
        package.package_hash = package.compute_package_hash()

        # Tamper with manifest hash
        manifest.manifest_hash = "tampered_hash"

        assert verify_package_offline(package) is False

    def test_tampered_package_hash_fails_verification(self, actor: ActorContext):
        """Package with tampered package hash fails offline verification."""
        manifest = ArchiveManifest(
            project_id=str(uuid.uuid4()),
            audit_year=2025,
            version=1,
            watermark="wm-123",
            actor=actor,
        )
        manifest.seal()

        package = SealedPackage(
            manifest=manifest,
            version=1,
            actor=actor,
        )
        package.package_hash = "tampered_hash"

        assert verify_package_offline(package) is False

    def test_unsealed_package_fails_verification(self):
        """Unsealed package fails offline verification."""
        manifest = ArchiveManifest(
            project_id=str(uuid.uuid4()),
            audit_year=2025,
            version=1,
        )
        package = SealedPackage(manifest=manifest)
        assert verify_package_offline(package) is False


# ─────────────────────────────────────────────────────────────────────────────
# Property-Based Tests (Hypothesis fast profile, max_examples=5)
# ─────────────────────────────────────────────────────────────────────────────


class TestArchiveManifestProperties:
    """Property-based tests for archive manifest invariants.

    **Validates: Requirements R11, R15**

    Uses the global fast Hypothesis profile (max_examples=5).
    """

    @given(
        n_archives=st.integers(min_value=1, max_value=5),
    )
    @pytest.mark.asyncio
    async def test_p24_version_strictly_increments(self, n_archives: int):
        """P24: Each archive creates a new version, strictly incrementing.

        **Validates: Requirements R11**
        """
        gate = FormalOutputGate()
        service = ArchiveManifestService(gate=gate)
        scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
        actor = ActorContext.for_user(uuid.uuid4())

        versions: list[int] = []
        for _ in range(n_archives):
            m = await service.preflight(scope, actor)
            r = await service.finalize(m, actor)
            assert r.success
            assert r.sealed_package is not None
            versions.append(r.sealed_package.version)

        # Versions are strictly incrementing from 1
        assert versions == list(range(1, n_archives + 1))

    @given(
        n_entries=st.integers(min_value=0, max_value=10),
        n_edges=st.integers(min_value=0, max_value=10),
    )
    @pytest.mark.asyncio
    async def test_p23_manifest_hash_deterministic(
        self, n_entries: int, n_edges: int
    ):
        """P23: Manifest hash is deterministic — same content = same hash.

        **Validates: Requirements R11**
        """
        manifest = ArchiveManifest(
            project_id="proj-1",
            audit_year=2025,
            version=1,
            watermark="wm-fixed",
        )

        for i in range(n_entries):
            manifest.entries.append(ManifestEntry(
                entry_id=f"e-{i}",
                entry_type=ManifestEntryType.ATTACHMENT_VERSION,
                object_id=f"obj-{i}",
                version=str(i),
                content_hash=f"hash-{i}",
            ))

        for i in range(n_edges):
            manifest.edges.append(ManifestEdge(
                edge_hash=f"edge-{i}",
                source_key=f"src-{i}",
                target_key=f"tgt-{i}",
                provenance="evidence_dependency",
            ))

        hash1 = manifest.compute_manifest_hash()
        hash2 = manifest.compute_manifest_hash()
        assert hash1 == hash2

    @given(st.booleans())
    @pytest.mark.asyncio
    async def test_success_implies_no_blocking_report(self, use_entries: bool):
        """SUCCESS ⟹ no blocking_difference_report.

        **Validates: Requirements R11, R15**

        Design §5.5: "校验通过并成功归档时不生成阻断差异报告"
        """
        gate = FormalOutputGate()  # Default gate passes
        service = ArchiveManifestService(gate=gate)
        scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
        actor = ActorContext.for_user(uuid.uuid4())

        manifest = await service.preflight(scope, actor)

        if use_entries:
            await service.build_manifest(
                manifest,
                evidence_items=[
                    {"id": "e1", "type": "attachment_version", "object_id": "o1"}
                ],
            )

        result = await service.finalize(manifest, actor)
        assert result.success is True
        assert result.blocking_report is None

    @given(st.just(True))
    @pytest.mark.asyncio
    async def test_failure_implies_blocking_report(self, _: bool):
        """FAILURE ⟹ blocking_difference_report generated.

        **Validates: Requirements R11, R15**

        Design §5.5: "只有验证失败并实际阻断归档时才生成 blocking_difference_report"
        """
        class FailPolicy(PolicyProvider):
            async def get_policy_required_evidence(self, target_id, target_type, policy_version=None):
                return [
                    EvidenceItem(
                        evidence_id="fail-ev",
                        evidence_type="attachment_version",
                        source="policy",
                        metadata_complete=False,
                    )
                ]

        gate = FormalOutputGate(policy_provider=FailPolicy())
        service = ArchiveManifestService(gate=gate)
        scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
        actor = ActorContext.for_user(uuid.uuid4())

        manifest = await service.preflight(scope, actor)
        result = await service.finalize(manifest, actor)

        assert result.success is False
        assert result.blocking_report is not None
        assert result.has_blocking_report is True
