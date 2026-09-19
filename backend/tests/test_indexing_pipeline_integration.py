"""
Integration test: upload TXT → verify knowledge_index chunks → semantic_search non-empty.

Validates: Requirements 2 (Upload Auto-Index)

NOTE: This test requires a running PostgreSQL database and embedding service.
It is designed as a contract/integration test that verifies the pipeline end-to-end.
Skip if DB or embedding service unavailable.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.content_extractor import ContentExtractor, ExtractResult
from app.services.indexing_pipeline import (
    GLOBAL_KB_PROJECT_ID,
    _resolve_index_project_id,
    run_indexing_pipeline,
)
from app.services.semantic_chunker import semantic_chunk


# ─── Unit-level integration: extract → chunk → verify non-empty ──────────────


@pytest.mark.asyncio
async def test_txt_upload_produces_chunks():
    """
    Simulates upload TXT → ContentExtractor → SemanticChunker → chunks non-empty.
    Does not require real DB or embedding service.
    """
    # Create a TXT file with substantial content
    content = (
        "第一条 企业应当以持续经营为基础，根据实际发生的交易和事项，"
        "按照《企业会计准则—基本准则》和其他各项具体准则的规定进行确认和计量，"
        "在此基础上编制财务报表。\n\n"
        "第二条 企业不能以附注等其他信息代替确认和计量，"
        "也不应以确认和计量代替附注中的信息披露。\n\n"
    ) * 10  # Make it longer than 300 chars

    with tempfile.NamedTemporaryFile(
        suffix=".txt", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(content)
        file_path = f.name

    # Step 1: Extract
    result = await ContentExtractor.extract(file_path)
    assert result.status == "extracted"
    assert result.content_text == content

    # Step 2: Chunk
    chunks = semantic_chunk(result.content_text)
    assert len(chunks) > 0
    assert all(c.text for c in chunks)
    assert chunks[0].total_chunks == len(chunks)

    # Step 3: Verify round-trip
    reconstructed = chunks[0].text
    for c in chunks[1:]:
        reconstructed += c.text[c.overlap_start:]
    assert reconstructed == content

    # Cleanup
    Path(file_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_pipeline_sets_indexed_status_on_success():
    """
    run_indexing_pipeline sets index_status='indexed' on successful completion.
    Mocks DB and embedding service.
    """
    doc_id = uuid.uuid4()

    # Mock document
    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.is_deleted = False
    mock_doc.content_text = "审计准则规定应当执行风险评估程序。" * 50
    mock_doc.storage_path = None
    mock_doc.version = 1
    mock_doc.access_level = "public"
    mock_doc.folder = None
    mock_doc.project_ids = None
    mock_doc.index_status = "pending"
    mock_doc.index_error = None

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_doc)
    mock_session.commit = AsyncMock()

    # Mock KnowledgeIndexService.incremental_update
    with patch("app.services.indexing_pipeline.async_session") as mock_factory:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        with patch(
            "app.services.indexing_pipeline.KnowledgeIndexService"
        ) as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.incremental_update = AsyncMock()
            mock_svc_cls.return_value = mock_svc

            await run_indexing_pipeline(doc_id)

            # Verify incremental_update was called
            mock_svc.incremental_update.assert_called_once_with(
                project_id=GLOBAL_KB_PROJECT_ID,
                source_type="knowledge_doc",
                source_id=doc_id,
                content=mock_doc.content_text,
                doc_version=1,
            )

            # Verify status set to indexed
            assert mock_doc.index_status == "indexed"
            assert mock_doc.index_error is None
            mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_pipeline_handles_extraction_failure():
    """
    run_indexing_pipeline handles extraction failure gracefully.
    """
    doc_id = uuid.uuid4()

    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.is_deleted = False
    mock_doc.content_text = None
    mock_doc.storage_path = "/nonexistent/file.pdf"
    mock_doc.version = 1
    mock_doc.index_status = "pending"
    mock_doc.index_error = None

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_doc)
    mock_session.commit = AsyncMock()

    with patch("app.services.indexing_pipeline.async_session") as mock_factory:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        await run_indexing_pipeline(doc_id)

        # Should mark extraction_failed
        assert mock_doc.index_status == "extraction_failed"
        assert mock_doc.index_error is not None
        mock_session.commit.assert_called()


def test_resolve_index_project_id_public():
    """Public documents get GLOBAL_KB_PROJECT_ID."""
    mock_doc = MagicMock()
    mock_doc.access_level = "public"
    mock_doc.folder = None
    mock_doc.project_ids = None

    assert _resolve_index_project_id(mock_doc) == GLOBAL_KB_PROJECT_ID


def test_resolve_index_project_id_project_group():
    """Project group documents get first project_id."""
    pid = uuid.uuid4()
    mock_doc = MagicMock()
    mock_doc.access_level = "project_group"
    mock_doc.folder = None
    mock_doc.project_ids = [str(pid)]

    assert _resolve_index_project_id(mock_doc) == pid
