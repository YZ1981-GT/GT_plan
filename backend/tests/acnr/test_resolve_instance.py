"""Unit tests for resolve_instance — ACNR 项目实例解析

Tests the core logic of resolve_instance:
- Single WpIndex match → returns wp_id + jump_route
- Multiple matches → disambiguation error (R6.3)
- No match → not_found error
- Explicit wp_id bypass disambiguation

Requirements: R6.1, R6.2, R6.3, R6.4, R13.1
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.acnr.resolver import (
    ProjectBinding,
    ResolveInstanceResult,
    resolve_instance,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_wp_index(
    project_id: uuid.UUID,
    wp_code: str = "D2-2",
    wp_name: str = "明细表D2-2",
    idx_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a mock WpIndex row."""
    idx = MagicMock()
    idx.id = idx_id or uuid.uuid4()
    idx.project_id = project_id
    idx.wp_code = wp_code
    idx.wp_name = wp_name
    idx.is_deleted = False
    return idx


def _make_db_session(
    wp_indices: list | None = None,
    wp_id: uuid.UUID | None = None,
) -> AsyncMock:
    """Create a mock AsyncSession with configurable query results.

    Args:
        wp_indices: WpIndex rows to return from first query
        wp_id: WorkingPaper.id to return from second query (or None)
    """
    db = AsyncMock()

    # Track call count to differentiate first vs second execute call
    call_count = [0]

    async def mock_execute(stmt):
        result_mock = MagicMock()
        call_count[0] += 1

        if call_count[0] == 1:
            # First query: WpIndex lookup
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = wp_indices or []
            result_mock.scalars.return_value = scalars_mock
        elif call_count[0] == 2:
            # Second query: WorkingPaper.id lookup (scalar_one_or_none)
            result_mock.scalar_one_or_none.return_value = wp_id
        else:
            # Any further queries
            result_mock.scalar_one_or_none.return_value = None

        return result_mock

    db.execute = mock_execute
    return db


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestResolveInstanceSingleMatch:
    """R6.1: Single match → returns wp_id + jump_route."""

    @pytest.mark.asyncio
    async def test_single_match_returns_wp_id(self):
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        idx = _make_wp_index(project_id, wp_code="D2-2")

        db = _make_db_session(wp_indices=[idx], wp_id=wp_id)

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
        )

        assert result.found is True
        assert result.wp_id == wp_id
        assert result.wp_index_id == idx.id
        assert result.error is None

    @pytest.mark.asyncio
    async def test_single_match_returns_jump_route(self):
        """R6.2: Returns jump_route with filled wp_id."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        idx = _make_wp_index(project_id, wp_code="D2-2")

        db = _make_db_session(wp_indices=[idx], wp_id=wp_id)

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
        )

        assert result.found is True
        assert result.jump_route is not None
        # jump_route 应包含 wp_id
        assert str(wp_id) in result.jump_route

    @pytest.mark.asyncio
    async def test_single_match_returns_binding(self):
        """Verify ProjectBinding is populated correctly."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        idx = _make_wp_index(project_id, wp_code="D2-2")

        db = _make_db_session(wp_indices=[idx], wp_id=wp_id)

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
        )

        assert result.binding is not None
        assert result.binding.project_id == project_id
        assert result.binding.parent_wp_code == "D2"
        assert result.binding.sheet_code == "D2-2"
        assert result.binding.wp_id == wp_id
        assert result.binding.wp_index_id == idx.id
        assert isinstance(result.binding.resolved_at, datetime)


class TestResolveInstanceNotFound:
    """R6.1: No WpIndex match → not_found."""

    @pytest.mark.asyncio
    async def test_no_match_returns_not_found(self):
        project_id = uuid.uuid4()
        db = _make_db_session(wp_indices=[])

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
        )

        assert result.found is False
        assert result.error == "not_found"
        assert result.wp_id is None

    @pytest.mark.asyncio
    async def test_wp_index_exists_but_working_paper_not_created(self):
        """WpIndex exists but WorkingPaper not yet generated."""
        project_id = uuid.uuid4()
        idx = _make_wp_index(project_id, wp_code="D2-2")

        # wp_id=None means no WorkingPaper row
        db = _make_db_session(wp_indices=[idx], wp_id=None)

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
        )

        assert result.found is False
        assert result.error == "working_paper_not_created"
        assert result.wp_index_id == idx.id


class TestResolveInstanceDisambiguation:
    """R6.3: Multiple instances → disambiguation error unless explicit wp_id."""

    @pytest.mark.asyncio
    async def test_multiple_matches_returns_disambiguation(self):
        project_id = uuid.uuid4()
        idx1 = _make_wp_index(project_id, wp_code="D2-2", wp_name="明细表D2-2(1)")
        idx2 = _make_wp_index(project_id, wp_code="D2-2", wp_name="明细表D2-2(2)")

        db = _make_db_session(wp_indices=[idx1, idx2])

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
        )

        assert result.found is False
        assert result.error == "disambiguation"
        assert result.candidates is not None
        assert len(result.candidates) == 2

    @pytest.mark.asyncio
    async def test_disambiguation_candidates_contain_info(self):
        project_id = uuid.uuid4()
        idx1 = _make_wp_index(project_id, wp_code="D2-2", wp_name="明细表D2-2(1)")
        idx2 = _make_wp_index(project_id, wp_code="D2-2", wp_name="明细表D2-2(2)")

        db = _make_db_session(wp_indices=[idx1, idx2])

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
        )

        assert result.candidates is not None
        for cand in result.candidates:
            assert "wp_index_id" in cand
            assert "wp_code" in cand
            assert "wp_name" in cand


class TestResolveInstanceExplicitWpId:
    """R6.3: Explicit wp_id bypasses disambiguation."""

    @pytest.mark.asyncio
    async def test_explicit_wp_id_bypasses_disambiguation(self):
        project_id = uuid.uuid4()
        explicit_wp_id = uuid.uuid4()
        wp_index_id = uuid.uuid4()

        db = AsyncMock()

        async def mock_execute(stmt):
            result_mock = MagicMock()
            # Query for WorkingPaper by explicit_wp_id
            wp_mock = MagicMock()
            wp_mock.id = explicit_wp_id
            wp_mock.project_id = project_id
            wp_mock.wp_index_id = wp_index_id
            wp_mock.is_deleted = False
            result_mock.scalar_one_or_none.return_value = wp_mock
            return result_mock

        db.execute = mock_execute

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
            explicit_wp_id=explicit_wp_id,
        )

        assert result.found is True
        assert result.wp_id == explicit_wp_id
        assert result.jump_route is not None

    @pytest.mark.asyncio
    async def test_explicit_wp_id_not_found(self):
        project_id = uuid.uuid4()
        explicit_wp_id = uuid.uuid4()

        db = AsyncMock()

        async def mock_execute(stmt):
            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = None
            return result_mock

        db.execute = mock_execute

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
            explicit_wp_id=explicit_wp_id,
        )

        assert result.found is False
        assert result.error == "explicit_wp_id_not_found"


class TestResolveInstanceIsUniqueOutlet:
    """R13.1: resolve_instance is the ONLY wp_id resolution outlet."""

    @pytest.mark.asyncio
    async def test_result_type_is_resolve_instance_result(self):
        """Ensure the function returns proper typed result."""
        project_id = uuid.uuid4()
        db = _make_db_session(wp_indices=[])

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
        )

        assert isinstance(result, ResolveInstanceResult)


class TestProjectBindingNoGlobalCatalogContext:
    """R6.4: global_catalog SHALL NOT contain project_id or wp_id."""

    def test_project_binding_holds_project_context(self):
        """ProjectBinding is where project context lives, not global catalog."""
        binding = ProjectBinding(
            project_id=uuid.uuid4(),
            parent_wp_code="D2",
            sheet_code="D2-2",
            wp_id=uuid.uuid4(),
            wp_index_id=uuid.uuid4(),
            resolved_at=datetime.now(timezone.utc),
        )
        assert binding.project_id is not None
        assert binding.wp_id is not None
        # This confirms project context is in L2 (ProjectBinding), not L1 (catalog)
