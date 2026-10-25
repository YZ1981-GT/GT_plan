"""
Integration test: 知识库检索 → 参照加载返回带引用信息的结果。

Validates: Requirements 8 (RAG Consumer)

2026-09-29 归因（spec knowledge-base-retrieval-and-authz-closure design §9.1 #7–8）：原用例
patch 的 ``reference_doc_service.KnowledgeIndexService`` 当时并不存在（函数内延迟 import），
且期望 ``load_from_knowledge_base`` 返回 dict —— 生产契约是注入 LLM 的 ``list[str]``。
现分两条：结构化 API ``search_knowledge_base`` 返回带引用字段的 dict；字符串 API 把同一批
命中格式化为带文档名的参照文本。真库召回见 ``test_knowledge_doc_search_pg``。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

_MOCK_RESULTS = [
    {
        "source_type": "knowledge_doc",
        "source_id": str(uuid.uuid4()),
        "content": "第二十二号准则规定金融工具的确认和计量...",
        "score": 0.85,
        "chunk_index": 0,
        "doc_version": 1,
        "is_stale": False,
        "document_name": "CAS 22 金融工具确认和计量.pdf",
        "folder_path": "/会计准则库",
        "retrieval": "lexical",
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
        "folder_path": "/审计程序库",
        "retrieval": "lexical",
    },
]


@pytest.mark.asyncio
async def test_search_knowledge_base_returns_results_with_citations():
    """结构化检索：每条带 document_name / folder_path / content / score。"""
    from app.services.reference_doc_service import ReferenceDocService

    with patch("app.services.reference_doc_service.KnowledgeIndexService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.semantic_search = AsyncMock(return_value=_MOCK_RESULTS)
        mock_svc_cls.return_value = mock_svc

        result = await ReferenceDocService.search_knowledge_base(
            uuid.uuid4(), keywords=["金融工具", "确认计量"], db=AsyncMock(),
        )

    assert len(result) == 2
    for doc, raw in zip(result, _MOCK_RESULTS):
        assert doc["content"] == raw["content"]
        assert doc["score"] == raw["score"]
        assert doc["document_name"] == raw["document_name"]
        assert doc["folder_path"] == raw["folder_path"]


@pytest.mark.asyncio
async def test_load_from_knowledge_base_formats_citations_as_text():
    """字符串 API：同一批命中格式化为「【知识库 - 文档名】正文」注入 LLM。"""
    from app.services.reference_doc_service import ReferenceDocService

    with patch("app.services.reference_doc_service.KnowledgeIndexService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.semantic_search = AsyncMock(return_value=_MOCK_RESULTS)
        mock_svc_cls.return_value = mock_svc

        result = await ReferenceDocService.load_from_knowledge_base(
            project_id=uuid.uuid4(), keywords=["金融工具"], db=AsyncMock(),
        )

    assert result[0].startswith("【知识库 - CAS 22 金融工具确认和计量.pdf】\n")
    assert "审计准则第1301号" in result[1]


@pytest.mark.asyncio
async def test_load_from_knowledge_base_empty_when_no_hits():
    """检索无命中 → 空列表。"""
    from app.services.reference_doc_service import ReferenceDocService

    with patch("app.services.reference_doc_service.KnowledgeIndexService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.semantic_search = AsyncMock(return_value=[])
        mock_svc_cls.return_value = mock_svc

        result = await ReferenceDocService.load_from_knowledge_base(
            project_id=uuid.uuid4(), keywords=["不存在的内容"], db=AsyncMock(),
        )

    assert result == []
