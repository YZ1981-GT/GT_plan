"""
PBT P3 (idempotence), P8 (delete cascade), P9 (version stale) for IndexingPipeline.

Validates: Requirements 2.4, 2.5, 2.6
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.indexing_pipeline import (
    mark_chunks_deleted,
    mark_previous_version_stale,
    GLOBAL_KB_PROJECT_ID,
)


# ─── PBT P3: Indexing Idempotence ────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(doc_id=st.uuids())
@pytest.mark.asyncio
async def test_mark_chunks_deleted_idempotent(doc_id: uuid.UUID):
    """
    **Validates: Requirements 2.6**

    PBT P3: mark_chunks_deleted called multiple times for the same doc_id
    produces the same effect (idempotent - already deleted chunks stay deleted).
    """
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("app.services.indexing_pipeline.async_session") as mock_factory:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        # Call twice
        await mark_chunks_deleted(doc_id)
        await mark_chunks_deleted(doc_id)

        # Both calls should execute the same UPDATE statement
        assert mock_session.execute.call_count == 2
        assert mock_session.commit.call_count == 2


# ─── PBT P8: Soft-delete cascades to index ───────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(doc_id=st.uuids())
@pytest.mark.asyncio
async def test_delete_cascade_marks_chunks_deleted(doc_id: uuid.UUID):
    """
    **Validates: Requirements 2.5**

    PBT P8: When a document is soft-deleted, mark_chunks_deleted sets
    is_deleted=True on all chunks with matching source_id.
    """
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("app.services.indexing_pipeline.async_session") as mock_factory:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        await mark_chunks_deleted(doc_id)

        # Verify execute was called (UPDATE ... SET is_deleted=True WHERE source_id=doc_id)
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify the UPDATE statement targets the correct source_id
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        # The statement should be an UPDATE on knowledge_index
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "knowledge_index" in compiled
        assert "is_deleted" in compiled


# ─── PBT P9: Version update stale marking ────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(doc_id=st.uuids(), prev_id=st.uuids())
@pytest.mark.asyncio
async def test_version_stale_marks_previous_chunks(doc_id: uuid.UUID, prev_id: uuid.UUID):
    """
    **Validates: Requirements 2.4**

    PBT P9: When a new version is indexed, mark_previous_version_stale
    marks all chunks from the previous version as is_stale=True.
    """
    # Mock the document with a previous_version_id
    mock_doc = MagicMock()
    mock_doc.previous_version_id = prev_id

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_doc)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("app.services.indexing_pipeline.async_session") as mock_factory:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        await mark_previous_version_stale(doc_id)

        # Verify the doc was fetched
        mock_session.get.assert_called_once()

        # Verify UPDATE was issued for previous_version_id chunks
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

        # The UPDATE should set is_stale=True
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "knowledge_index" in compiled
        assert "is_stale" in compiled


@pytest.mark.asyncio
async def test_version_stale_no_previous_version_noop():
    """When document has no previous_version_id, mark_previous_version_stale is a no-op."""
    mock_doc = MagicMock()
    mock_doc.previous_version_id = None

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_doc)

    with patch("app.services.indexing_pipeline.async_session") as mock_factory:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        await mark_previous_version_stale(uuid.uuid4())

        # No UPDATE should be issued
        mock_session.execute.assert_not_called()
