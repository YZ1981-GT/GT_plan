"""Tests for Archive Adapter + Offline Manifest Verifier — Task 7.2 (Wave 6).

Validates: Requirements R11
Properties: P23, P24

Coverage:
  1. Adapter contract verification (shape, not engine duplication)
  2. Offline verification success path
  3. Offline verification failure paths (tampered member, tampered manifest, missing entries)
  4. Machine-readable difference output format
  5. Serialization round-trip

Uses the global fast Hypothesis profile (max_examples=5).
The offline verifier MUST NOT import any database session/connection modules.
"""

from __future__ import annotations

import inspect
import json
import sys
import uuid
from datetime import datetime, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.evidence_governance.archive_adapter import (
    ArchiveJobResult,
    ArchiveOrchestratorAdapter,
    DeliverableArchiveResult,
    DeliverableServiceAdapter,
    DeliverableVersion,
    InMemoryArchiveOrchestratorAdapter,
    InMemoryDeliverableServiceAdapter,
)
from app.services.evidence_governance.archive_manifest_service import (
    ArchiveManifest,
    ArchiveManifestService,
    ArchivePhase,
    ManifestEntry,
    ManifestEntryType,
    ManifestEdge,
    SealedPackage,
    verify_package_offline,
)
from app.services.evidence_governance.formal_output_gate import FormalOutputGate
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    content_hash_of,
)
from app.services.evidence_governance.offline_manifest_verifier import (
    DifferenceType,
    OfflineManifestVerifier,
    OfflineVerificationResult,
    VerificationDifference,
    VerificationStatus,
    serialize_sealed_package,
)
from app.services.evidence_governance.unified_graph_builder import GraphScope


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
def verifier() -> OfflineManifestVerifier:
    return OfflineManifestVerifier()


@pytest.fixture
def archive_adapter() -> InMemoryArchiveOrchestratorAdapter:
    return InMemoryArchiveOrchestratorAdapter()


@pytest.fixture
def deliverable_adapter() -> InMemoryDeliverableServiceAdapter:
    return InMemoryDeliverableServiceAdapter()


@pytest.fixture
def sealed_package(actor: ActorContext) -> SealedPackage:
    """Create a valid sealed package for testing."""
    manifest = ArchiveManifest(
        project_id=str(uuid.uuid4()),
        audit_year=2025,
        version=1,
        watermark="test-watermark",
        actor=actor,
    )
    manifest.entries.append(ManifestEntry(
        entry_id="entry-1",
        entry_type=ManifestEntryType.ATTACHMENT_VERSION,
        object_id="obj-1",
        version="3",
        content_hash="a" * 64,
        state="available",
    ))
    manifest.entries.append(ManifestEntry(
        entry_id="entry-2",
        entry_type=ManifestEntryType.OCR_RESULT,
        object_id="obj-2",
        version="1",
        content_hash="b" * 64,
        state="confirmed",
    ))
    manifest.edges.append(ManifestEdge(
        edge_hash="edge-hash-1",
        source_key="attachment_version:obj-1",
        target_key="workpaper:wp-1",
        provenance="evidence_dependency",
    ))
    manifest.seal()

    package = SealedPackage(
        manifest=manifest,
        version=1,
        actor=actor,
    )
    package.package_hash = package.compute_package_hash()
    return package


# ─────────────────────────────────────────────────────────────────────────────
# 1. Adapter Contract Verification (shape, not engine duplication)
# ─────────────────────────────────────────────────────────────────────────────


class TestAdapterContracts:
    """Verify adapter protocol shapes match frozen contracts.

    These tests verify the adapter interface shape is correct without
    duplicating the actual engine implementation.
    """

    def test_archive_orchestrator_adapter_has_required_methods(self):
        """ArchiveOrchestratorAdapter protocol declares orchestrate/retry/get_job."""
        # Verify protocol has the required methods from adapter_contract_manifest
        assert hasattr(ArchiveOrchestratorAdapter, "orchestrate")
        assert hasattr(ArchiveOrchestratorAdapter, "retry")
        assert hasattr(ArchiveOrchestratorAdapter, "get_job")

    def test_deliverable_service_adapter_has_required_methods(self):
        """DeliverableServiceAdapter protocol declares version/archive/confirm."""
        assert hasattr(DeliverableServiceAdapter, "get_version_chain")
        assert hasattr(DeliverableServiceAdapter, "archive_project_deliverables")
        assert hasattr(DeliverableServiceAdapter, "confirm_deliverable")

    def test_in_memory_archive_adapter_satisfies_protocol(self):
        """InMemoryArchiveOrchestratorAdapter satisfies the adapter protocol."""
        adapter = InMemoryArchiveOrchestratorAdapter()
        assert isinstance(adapter, ArchiveOrchestratorAdapter)

    def test_in_memory_deliverable_adapter_satisfies_protocol(self):
        """InMemoryDeliverableServiceAdapter satisfies the adapter protocol."""
        adapter = InMemoryDeliverableServiceAdapter()
        assert isinstance(adapter, DeliverableServiceAdapter)

    @pytest.mark.asyncio
    async def test_archive_adapter_orchestrate_returns_job_result(
        self, archive_adapter: InMemoryArchiveOrchestratorAdapter
    ):
        """orchestrate() returns an ArchiveJobResult with expected fields."""
        result = await archive_adapter.orchestrate(
            project_id="proj-1",
            scope={"audit_year": 2025},
        )
        assert isinstance(result, ArchiveJobResult)
        assert result.project_id == "proj-1"
        assert result.status == "completed"
        assert result.job_id != ""

    @pytest.mark.asyncio
    async def test_archive_adapter_get_job(
        self, archive_adapter: InMemoryArchiveOrchestratorAdapter
    ):
        """get_job() returns the job status."""
        job = await archive_adapter.orchestrate("proj-1", {"year": 2025})
        fetched = await archive_adapter.get_job(job.job_id)
        assert fetched.job_id == job.job_id
        assert fetched.is_completed

    @pytest.mark.asyncio
    async def test_archive_adapter_retry(
        self, archive_adapter: InMemoryArchiveOrchestratorAdapter
    ):
        """retry() re-triggers a failed job."""
        job = await archive_adapter.orchestrate("proj-1", {"year": 2025})
        retried = await archive_adapter.retry(job.job_id)
        assert retried.is_completed

    @pytest.mark.asyncio
    async def test_deliverable_adapter_get_version_chain(
        self, deliverable_adapter: InMemoryDeliverableServiceAdapter
    ):
        """get_version_chain() returns a list of DeliverableVersion."""
        chain = await deliverable_adapter.get_version_chain("task-1")
        assert isinstance(chain, list)

    @pytest.mark.asyncio
    async def test_deliverable_adapter_archive_project(
        self, deliverable_adapter: InMemoryDeliverableServiceAdapter
    ):
        """archive_project_deliverables() returns DeliverableArchiveResult."""
        result = await deliverable_adapter.archive_project_deliverables("proj-1")
        assert isinstance(result, DeliverableArchiveResult)
        assert result.success is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. Offline Verification — Success Path
# ─────────────────────────────────────────────────────────────────────────────


class TestOfflineVerificationSuccess:
    """Test offline verification succeeds for valid sealed packages."""

    def test_valid_package_passes(
        self, verifier: OfflineManifestVerifier, sealed_package: SealedPackage
    ):
        """Valid sealed package passes offline verification."""
        package_data = serialize_sealed_package(sealed_package)
        result = verifier.verify_package(package_data)

        assert result.status == VerificationStatus.PASSED
        assert result.is_valid is True
        assert result.difference_count == 0
        assert result.member_count == 2
        assert result.edge_count == 1

    def test_valid_package_hashes_match(
        self, verifier: OfflineManifestVerifier, sealed_package: SealedPackage
    ):
        """Recomputed hashes match stored hashes for valid package."""
        package_data = serialize_sealed_package(sealed_package)
        result = verifier.verify_package(package_data)

        assert result.recomputed_manifest_hash == result.stored_manifest_hash
        assert result.recomputed_package_hash == result.stored_package_hash

    def test_empty_manifest_passes(
        self, verifier: OfflineManifestVerifier, actor: ActorContext
    ):
        """Empty manifest (no entries/edges) still passes if hashes are correct."""
        manifest = ArchiveManifest(
            project_id="proj-empty",
            audit_year=2025,
            version=1,
            watermark="wm",
            actor=actor,
        )
        manifest.seal()
        package = SealedPackage(manifest=manifest, version=1, actor=actor)
        package.package_hash = package.compute_package_hash()

        package_data = serialize_sealed_package(package)
        result = verifier.verify_package(package_data)

        assert result.status == VerificationStatus.PASSED
        assert result.member_count == 0
        assert result.edge_count == 0

    @pytest.mark.asyncio
    async def test_full_archive_flow_then_offline_verify(self):
        """Full archive flow produces a package that passes offline verification.

        **Validates: Requirements R11**
        """
        gate = FormalOutputGate()
        service = ArchiveManifestService(gate=gate)
        scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
        actor = ActorContext.for_user(uuid.uuid4())

        # Run two-phase archive
        manifest = await service.preflight(scope, actor)
        await service.build_manifest(
            manifest,
            evidence_items=[
                {"id": "e1", "type": "attachment_version", "object_id": "o1",
                 "version": "1", "content_hash": "x" * 64, "state": "available"},
            ],
        )
        result = await service.finalize(manifest, actor)
        assert result.success
        assert result.sealed_package is not None

        # Offline verify
        verifier = OfflineManifestVerifier()
        package_data = serialize_sealed_package(result.sealed_package)
        verification = verifier.verify_package(package_data)
        assert verification.is_valid


# ─────────────────────────────────────────────────────────────────────────────
# 3. Offline Verification — Failure Paths
# ─────────────────────────────────────────────────────────────────────────────


class TestOfflineVerificationFailures:
    """Test offline verification detects tampering."""

    def test_tampered_manifest_hash(
        self, verifier: OfflineManifestVerifier, sealed_package: SealedPackage
    ):
        """Tampered manifest hash is detected."""
        package_data = serialize_sealed_package(sealed_package)
        package_data["manifest"]["manifest_hash"] = "tampered" + "0" * 57

        result = verifier.verify_package(package_data)

        assert result.status == VerificationStatus.FAILED
        assert not result.is_valid
        # Should detect both manifest hash mismatch and package hash mismatch
        types = {d.difference_type for d in result.differences}
        assert DifferenceType.MANIFEST_HASH_MISMATCH in types

    def test_tampered_entry_content(
        self, verifier: OfflineManifestVerifier, sealed_package: SealedPackage
    ):
        """Tampered entry content causes manifest hash mismatch."""
        package_data = serialize_sealed_package(sealed_package)
        # Tamper with an entry's content_hash
        package_data["manifest"]["entries"][0]["content_hash"] = "z" * 64

        result = verifier.verify_package(package_data)

        assert result.status == VerificationStatus.FAILED
        types = {d.difference_type for d in result.differences}
        assert DifferenceType.MANIFEST_HASH_MISMATCH in types

    def test_tampered_package_hash(
        self, verifier: OfflineManifestVerifier, sealed_package: SealedPackage
    ):
        """Tampered package hash is detected."""
        package_data = serialize_sealed_package(sealed_package)
        package_data["package_hash"] = "tampered_pkg_hash" + "0" * 47

        result = verifier.verify_package(package_data)

        assert result.status == VerificationStatus.FAILED
        types = {d.difference_type for d in result.differences}
        assert DifferenceType.PACKAGE_HASH_MISMATCH in types

    def test_missing_manifest(self, verifier: OfflineManifestVerifier):
        """Missing manifest is detected."""
        package_data = {"package_id": "p1", "manifest": None}

        result = verifier.verify_package(package_data)

        assert result.status == VerificationStatus.FAILED
        types = {d.difference_type for d in result.differences}
        assert DifferenceType.MANIFEST_MISSING in types

    def test_unsealed_manifest(self, verifier: OfflineManifestVerifier):
        """Unsealed manifest is detected."""
        package_data = {
            "package_id": "p1",
            "package_hash": "hash",
            "version": 1,
            "manifest": {
                "manifest_id": "m1",
                "project_id": "proj",
                "audit_year": 2025,
                "version": 1,
                "sealed": False,
                "manifest_hash": "",
                "entries": [],
                "edges": [],
            },
        }

        result = verifier.verify_package(package_data)

        assert result.status == VerificationStatus.FAILED
        types = {d.difference_type for d in result.differences}
        assert DifferenceType.MANIFEST_NOT_SEALED in types

    def test_extra_entry_added_after_seal(
        self, verifier: OfflineManifestVerifier, sealed_package: SealedPackage
    ):
        """Adding an extra entry after sealing causes hash mismatch."""
        package_data = serialize_sealed_package(sealed_package)
        # Add a new entry that wasn't there at seal time
        package_data["manifest"]["entries"].append({
            "entry_id": "injected-entry",
            "entry_type": "attachment_version",
            "object_id": "injected-obj",
            "version": "99",
            "content_hash": "f" * 64,
            "state": "available",
        })

        result = verifier.verify_package(package_data)

        assert result.status == VerificationStatus.FAILED
        types = {d.difference_type for d in result.differences}
        assert DifferenceType.MANIFEST_HASH_MISMATCH in types

    def test_removed_entry_after_seal(
        self, verifier: OfflineManifestVerifier, sealed_package: SealedPackage
    ):
        """Removing an entry after sealing causes hash mismatch."""
        package_data = serialize_sealed_package(sealed_package)
        # Remove an entry
        package_data["manifest"]["entries"].pop(0)

        result = verifier.verify_package(package_data)

        assert result.status == VerificationStatus.FAILED
        types = {d.difference_type for d in result.differences}
        assert DifferenceType.MANIFEST_HASH_MISMATCH in types

    def test_invalid_json_input(self, verifier: OfflineManifestVerifier):
        """Invalid JSON input is handled gracefully."""
        result = verifier.verify_from_json("not valid json {{{")

        assert result.status == VerificationStatus.ERROR
        types = {d.difference_type for d in result.differences}
        assert DifferenceType.STRUCTURAL_ERROR in types


# ─────────────────────────────────────────────────────────────────────────────
# 4. Machine-Readable Difference Output Format
# ─────────────────────────────────────────────────────────────────────────────


class TestMachineReadableOutput:
    """Test the machine-readable output format."""

    def test_success_output_format(
        self, verifier: OfflineManifestVerifier, sealed_package: SealedPackage
    ):
        """Successful verification produces well-formed machine-readable output."""
        package_data = serialize_sealed_package(sealed_package)
        result = verifier.verify_package(package_data)

        mr = result.to_machine_readable()

        assert mr["verification_status"] == "passed"
        assert mr["is_valid"] is True
        assert mr["summary"]["difference_count"] == 0
        assert mr["hashes"]["manifest"]["match"] is True
        assert mr["hashes"]["package"]["match"] is True
        assert mr["differences"] == []

    def test_failure_output_format(
        self, verifier: OfflineManifestVerifier, sealed_package: SealedPackage
    ):
        """Failed verification produces machine-readable differences."""
        package_data = serialize_sealed_package(sealed_package)
        package_data["manifest"]["manifest_hash"] = "wrong" * 13  # 65 chars

        result = verifier.verify_package(package_data)
        mr = result.to_machine_readable()

        assert mr["verification_status"] == "failed"
        assert mr["is_valid"] is False
        assert mr["summary"]["difference_count"] > 0
        assert len(mr["differences"]) > 0

        # Each difference has required fields
        for diff in mr["differences"]:
            assert "type" in diff
            assert "location" in diff
            assert "description" in diff
            assert "severity" in diff

    def test_output_is_valid_json(
        self, verifier: OfflineManifestVerifier, sealed_package: SealedPackage
    ):
        """Machine-readable output serializes to valid JSON."""
        package_data = serialize_sealed_package(sealed_package)
        result = verifier.verify_package(package_data)

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert parsed["verification_status"] == "passed"
        assert isinstance(parsed["differences"], list)

    def test_difference_types_are_all_strings(
        self, verifier: OfflineManifestVerifier, sealed_package: SealedPackage
    ):
        """All difference type values are strings (machine-parseable)."""
        package_data = serialize_sealed_package(sealed_package)
        package_data["package_hash"] = "wrong"

        result = verifier.verify_package(package_data)
        mr = result.to_machine_readable()

        for diff in mr["differences"]:
            assert isinstance(diff["type"], str)
            # Type should be one of the known enum values
            assert diff["type"] in [dt.value for dt in DifferenceType]


# ─────────────────────────────────────────────────────────────────────────────
# 5. No-DB-Import Constraint
# ─────────────────────────────────────────────────────────────────────────────


class TestNoDbImport:
    """Verify the offline verifier does NOT import database modules."""

    def test_offline_verifier_has_no_db_imports(self):
        """The offline_manifest_verifier module must not import DB modules.

        Design §5.5: "离线 verifier 不连接业务库"
        """
        import app.services.evidence_governance.offline_manifest_verifier as mod

        source = inspect.getsource(mod)

        # Must not import any database session/connection modules
        forbidden_imports = [
            "sqlalchemy",
            "asyncpg",
            "AsyncSession",
            "create_async_engine",
            "SessionLocal",
            "get_db",
            "async_session",
            "database",
        ]
        for forbidden in forbidden_imports:
            assert f"import {forbidden}" not in source, (
                f"offline_manifest_verifier must not import '{forbidden}'"
            )
            assert f"from {forbidden}" not in source, (
                f"offline_manifest_verifier must not import from '{forbidden}'"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Property-Based Tests (fast profile, max_examples=5)
# ─────────────────────────────────────────────────────────────────────────────


class TestOfflineVerifierProperties:
    """Property-based tests for offline verifier correctness.

    **Validates: Requirements R11**

    Uses the global fast Hypothesis profile (max_examples=5).
    """

    @given(
        n_entries=st.integers(min_value=0, max_value=8),
        n_edges=st.integers(min_value=0, max_value=8),
    )
    def test_valid_package_always_passes(self, n_entries: int, n_edges: int):
        """Property: Any correctly sealed package passes offline verification.

        **Validates: Requirements R11**
        """
        manifest = ArchiveManifest(
            project_id="p1",
            audit_year=2025,
            version=1,
            watermark="wm",
        )
        for i in range(n_entries):
            manifest.entries.append(ManifestEntry(
                entry_id=f"e-{i}",
                entry_type=ManifestEntryType.ATTACHMENT_VERSION,
                object_id=f"obj-{i}",
                version=str(i),
                content_hash=f"{i:064d}",
                state="available",
            ))
        for i in range(n_edges):
            manifest.edges.append(ManifestEdge(
                edge_hash=f"edge-{i}",
                source_key=f"src-{i}",
                target_key=f"tgt-{i}",
                provenance="evidence_dependency",
            ))

        manifest.seal()
        package = SealedPackage(manifest=manifest, version=1)
        package.package_hash = package.compute_package_hash()

        verifier = OfflineManifestVerifier()
        package_data = serialize_sealed_package(package)
        result = verifier.verify_package(package_data)

        assert result.status == VerificationStatus.PASSED
        assert result.difference_count == 0

    @given(
        tamper_index=st.integers(min_value=0, max_value=2),
    )
    def test_any_tampered_entry_detected(self, tamper_index: int):
        """Property: Tampering with any entry is always detected.

        **Validates: Requirements R11**
        """
        manifest = ArchiveManifest(
            project_id="p1",
            audit_year=2025,
            version=1,
            watermark="wm",
        )
        for i in range(3):
            manifest.entries.append(ManifestEntry(
                entry_id=f"e-{i}",
                entry_type=ManifestEntryType.ATTACHMENT_VERSION,
                object_id=f"obj-{i}",
                version=str(i),
                content_hash=f"{i:064d}",
                state="available",
            ))

        manifest.seal()
        package = SealedPackage(manifest=manifest, version=1)
        package.package_hash = package.compute_package_hash()

        # Tamper with one entry after sealing
        package_data = serialize_sealed_package(package)
        package_data["manifest"]["entries"][tamper_index]["content_hash"] = "TAMPERED"

        verifier = OfflineManifestVerifier()
        result = verifier.verify_package(package_data)

        assert result.status == VerificationStatus.FAILED
        assert result.difference_count > 0

    @given(
        n_entries=st.integers(min_value=1, max_value=5),
    )
    def test_machine_readable_output_always_valid_json(self, n_entries: int):
        """Property: Machine-readable output is always valid JSON.

        **Validates: Requirements R11**
        """
        manifest = ArchiveManifest(
            project_id="p1",
            audit_year=2025,
            version=1,
            watermark="wm",
        )
        for i in range(n_entries):
            manifest.entries.append(ManifestEntry(
                entry_id=f"e-{i}",
                entry_type=ManifestEntryType.ATTACHMENT_VERSION,
                object_id=f"obj-{i}",
            ))
        manifest.seal()
        package = SealedPackage(manifest=manifest, version=1)
        package.package_hash = package.compute_package_hash()

        verifier = OfflineManifestVerifier()
        package_data = serialize_sealed_package(package)
        result = verifier.verify_package(package_data)

        # Output is always valid JSON
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert "verification_status" in parsed
        assert "differences" in parsed
        assert isinstance(parsed["differences"], list)
