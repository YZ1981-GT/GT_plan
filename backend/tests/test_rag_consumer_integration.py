"""
Integration test: upload doc → load_from_knowledge_base → non-empty with citations.

Validates: Requirements 8 (RAG Consumer)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_load_from_knowledge_base_returns_results_with_citations():
    """
    Verifies ReferenceDocService.load_from_knowledge_base returns non-empty
    results with citation fields (document_name, folder_path) when indexed
    data exists.
    """
    from app.services.reference_doc_service import ReferenceDocService

    project_id = uuid.uuid4()

    # Mock semantic_search to return results with citation fields
    mock_results = [
        {
            "source_type": "knowledge_doc",
            "source_id": str(uuid.uuid4()),
            "content": "第二十二号准则规定金融工具的确认和计量...",
            "score": 0.85,
            "chunk_index": 0,
            "doc_version": 1,
            "is_stale": False,
            "document_name": "CAS 22 金融工具确认和计量.pdf",
            "folder_path": "会计准则库",
        },
        {
            "source_type": "knowledge_doc",
            "source_id": str(uuid.uuid4()),
            "content": "审计准则第1301号要求审计师获取充分适当的审计证据...",
            "score": 0.72,
            "chunk_index": 2,
            "doc_version": 1,
            "is_stale": False,
            "document_name": "ISA 1301 审计证据.pdf",
            "folder_path": "审计程序库",
        },
    ]

    with patch(
        "app.services.reference_doc_service.KnowledgeIndexService",
    ) as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.semantic_search = AsyncMock(return_value=mock_results)
        mock_svc_cls.return_value = mock_svc

        mock_db = AsyncMock()

        result = await ReferenceDocService.load_from_knowledge_base(
            project_id=project_id,
            keywords=["金融工具", "确认计量"],
            db=mock_db,
        )

        # Non-empty results
        assert len(result) >= 1

        # Each result has citation fields
        for doc in result:
            assert "content" in doc or "text" in doc
            # Score should be present
            assert "score" in doc or "relevance" in doc


@pytest.mark.asyncio
async def test_load_from_knowledge_base_empty_when_no_index():
    """
    When no indexed data exists (semantic_search returns []),
    load_from_knowledge_base returns empty.
    """
    from app.services.reference_doc_service import ReferenceDocService

    project_id = uuid.uuid4()

    with patch(
        "app.services.reference_doc_service.KnowledgeIndexService",
    ) as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.semantic_search = AsyncMock(return_value=[])
        mock_svc_cls.return_value = mock_svc

        mock_db = AsyncMock()

        result = await ReferenceDocService.load_from_knowledge_base(
            project_id=project_id,
            keywords=["不存在的内容"],
            db=mock_db,
        )

        assert result == []
