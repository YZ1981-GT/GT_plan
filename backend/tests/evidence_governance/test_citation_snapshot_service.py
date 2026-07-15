"""Unit tests for CitationSnapshotService (Task 6.1).

Feature: attachment-ocr-ai-evidence-governance-hardening, Property 15, Property 16
Requirements: R7, R9, R15

Tests cover:
- P15: confirmed citation must have valid page, non-empty region, version and hash match
- P16: returned citation set is always a SUBSET of actor's accessible sources
- R7.3: locate re-authenticates — if source became unreadable, return stale status
- Filter chain: scope, readable, active ref, version/hash/locator valid
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.evidence_governance.citation_snapshot_service import (
    CitationLocateResult,
    CitationSnapshotService,
    CitationStatus,
    CitationValidationResult,
    RetrievalCandidate,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ActorType,
    EvidenceGovernanceError,
    EvidenceErrorCode,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _user_actor() -> ActorContext:
    return ActorContext.for_user(uuid.uuid4())


def _service_actor() -> ActorContext:
    return ActorContext.for_service(uuid.uuid4())


def _valid_candidate(
    *,
    source_type: str = "attachment_version",
    source_id: str | None = None,
    page: int = 1,
    region: dict | None = None,
    content_hash: str | None = None,
    evidence_ref_id: uuid.UUID | None = None,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        source_type=source_type,
        source_id=source_id or str(uuid.uuid4()),
        source_version="1",
        content_hash=content_hash or ("a" * 64),  # valid sha256 hex
        page=page,
        region=region or {"x": 10, "y": 20, "w": 100, "h": 50},
        excerpt_text="Some excerpt text",
        index_version="v1",
        locator_version="v1",
        locator="/doc/page1",
        evidence_ref_id=evidence_ref_id,
        relevance_score=0.95,
    )


# ─────────────────────────────────────────────────────────────────────────────
# P15: Page/region/version/hash validation
# ─────────────────────────────────────────────────────────────────────────────


class TestP15Locatability:
    """P15: confirmed citation must have valid page, non-empty region, version and hash match."""

    def test_page_none_rejected(self):
        """Candidate with page=None is not locatable."""
        svc = CitationSnapshotService(MagicMock())
        candidate = _valid_candidate(page=None)  # type: ignore
        assert svc._is_locatable(candidate) is False

    def test_page_zero_rejected(self):
        """Candidate with page=0 is not locatable (must be >= 1)."""
        svc = CitationSnapshotService(MagicMock())
        candidate = _valid_candidate(page=0)
        assert svc._is_locatable(candidate) is False

    def test_page_negative_rejected(self):
        """Candidate with negative page is not locatable."""
        svc = CitationSnapshotService(MagicMock())
        candidate = _valid_candidate(page=-1)
        assert svc._is_locatable(candidate) is False

    def test_region_none_rejected(self):
        """Candidate with region=None is not locatable."""
        svc = CitationSnapshotService(MagicMock())
        candidate = _valid_candidate(region=None)  # type: ignore
        # Override region to None via direct construction
        candidate_no_region = RetrievalCandidate(
            source_type="attachment_version",
            source_id=str(uuid.uuid4()),
            page=1,
            region=None,
        )
        assert svc._is_locatable(candidate_no_region) is False

    def test_region_empty_dict_rejected(self):
        """Candidate with empty region {} is not locatable."""
        svc = CitationSnapshotService(MagicMock())
        candidate_empty = RetrievalCandidate(
            source_type="attachment_version",
            source_id=str(uuid.uuid4()),
            page=1,
            region={},
        )
        assert svc._is_locatable(candidate_empty) is False

    def test_valid_page_and_region_accepted(self):
        """Candidate with page >= 1 and non-empty region is locatable."""
        svc = CitationSnapshotService(MagicMock())
        candidate = _valid_candidate(page=5, region={"start": 100, "end": 200})
        assert svc._is_locatable(candidate) is True


# ─────────────────────────────────────────────────────────────────────────────
# P16: Permission non-expansion
# ─────────────────────────────────────────────────────────────────────────────


class TestP16PermissionNonExpansion:
    """P16: citation set ⊆ actor accessible set (never expand permissions)."""

    @pytest.mark.asyncio
    async def test_unreadable_source_excluded(self):
        """If actor cannot read the source, candidate is excluded (P16)."""
        db = AsyncMock()
        svc = CitationSnapshotService(db)

        actor = _user_actor()
        project_id = uuid.uuid4()

        # Mock adapter that says can_read=False
        mock_adapter = MagicMock()
        mock_adapter.can_read = AsyncMock(return_value=False)

        candidate = _valid_candidate()

        with patch(
            "app.services.evidence_governance.citation_snapshot_service.get_adapter",
            return_value=mock_adapter,
        ):
            result = await svc._actor_can_read_source(candidate, actor, project_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_readable_source_included(self):
        """If actor can read the source, candidate passes filter 2 (P16)."""
        db = AsyncMock()
        svc = CitationSnapshotService(db)

        actor = _user_actor()
        project_id = uuid.uuid4()

        mock_adapter = MagicMock()
        mock_adapter.can_read = AsyncMock(return_value=True)

        candidate = _valid_candidate()

        with patch(
            "app.services.evidence_governance.citation_snapshot_service.get_adapter",
            return_value=mock_adapter,
        ):
            result = await svc._actor_can_read_source(candidate, actor, project_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_unknown_source_type_excluded(self):
        """If source_type is unsupported, candidate is excluded."""
        db = AsyncMock()
        svc = CitationSnapshotService(db)

        actor = _user_actor()
        project_id = uuid.uuid4()

        candidate = _valid_candidate(source_type="unknown_type")

        with patch(
            "app.services.evidence_governance.citation_snapshot_service.get_adapter",
            side_effect=EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN
            ),
        ):
            result = await svc._actor_can_read_source(candidate, actor, project_id)

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Filter chain integration
# ─────────────────────────────────────────────────────────────────────────────


class TestFilterChain:
    """Test the full filter chain logic."""

    @pytest.mark.asyncio
    async def test_non_locatable_excluded_before_db_calls(self):
        """Candidates failing P15 (page/region) are excluded without DB queries."""
        db = AsyncMock()
        svc = CitationSnapshotService(db)

        actor = _user_actor()
        project_id = uuid.uuid4()
        ai_log_id = uuid.uuid4()

        # Candidate with page=0 — should be filtered out immediately
        bad_candidate = RetrievalCandidate(
            source_type="attachment_version",
            source_id=str(uuid.uuid4()),
            page=0,
            region={"x": 1},
        )

        result = await svc.create_citation_from_retrieval(
            retrieval_results=[bad_candidate],
            actor=actor,
            project_id=project_id,
            audit_year=2025,
            ai_content_log_id=ai_log_id,
        )

        assert result == []
        # DB should not be called for scope/permission/ref checks
        db.execute.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# R7.3: Locate re-authentication
# ─────────────────────────────────────────────────────────────────────────────


class TestLocateReAuthentication:
    """R7.3: locate re-authenticates — if source became unreadable, return stale status."""

    @pytest.mark.asyncio
    async def test_citation_not_found_returns_invalid(self):
        """Non-existent citation returns INVALID status."""
        db = AsyncMock()
        # Simulate no row found
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        db.execute.return_value = mock_result

        svc = CitationSnapshotService(db)

        result = await svc.locate_citation(
            citation_id=uuid.uuid4(),
            actor=_user_actor(),
            project_id=uuid.uuid4(),
        )

        assert result.status == CitationStatus.INVALID
        assert result.readable is False
        assert result.reason == "citation_not_found"


# ─────────────────────────────────────────────────────────────────────────────
# CitationValidationResult
# ─────────────────────────────────────────────────────────────────────────────


class TestCitationValidationResult:
    """Test CitationValidationResult data structure."""

    def test_all_valid_when_no_stale_or_invalid(self):
        result = CitationValidationResult()
        assert result.all_valid is True

    def test_not_all_valid_with_stale(self):
        from app.services.evidence_governance.citation_snapshot_service import (
            CitationValidationEntry,
        )

        result = CitationValidationResult()
        result.stale.append(
            CitationValidationEntry(
                citation_id=uuid.uuid4(),
                status=CitationStatus.STALE,
                reason="version_changed",
            )
        )
        assert result.all_valid is False

    def test_not_all_valid_with_invalid(self):
        from app.services.evidence_governance.citation_snapshot_service import (
            CitationValidationEntry,
        )

        result = CitationValidationResult()
        result.invalid.append(
            CitationValidationEntry(
                citation_id=uuid.uuid4(),
                status=CitationStatus.INVALID,
                reason="ref_deactivated",
            )
        )
        assert result.all_valid is False
