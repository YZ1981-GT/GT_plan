"""Tests for ReferenceDocService.load_from_knowledge_base — semantic_search 主路径 + ilike 降级。

验证 Task 6: reference_doc_service 改调 semantic_search(scope=knowledge_doc)，ilike 降级。
**Validates: Requirements 2.3**
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.reference_doc_service import ReferenceDocService


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


class TestLoadFromKnowledgeBaseSemanticSearch:
    """验证 load_from_knowledge_base 优先走 semantic_search。"""

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self):
        """db=None 时直接返回空列表。"""
        result = await ReferenceDocService.load_from_knowledge_base(
            project_id=uuid4(), keywords=["测试"], db=None
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_semantic_search_primary_path(self, mock_db):
        """有 keywords 时优先调 semantic_search(scope=knowledge_doc)。"""
        project_id = uuid4()
        doc_id = str(uuid4())

        mock_semantic_results = [
            {
                "source_type": "knowledge_doc",
                "source_id": doc_id,
                "content": "这是知识库文档内容",
                "score": 0.85,
                "chunk_index": 0,
            }
        ]

        # Mock name lookup
        mock_name_row = MagicMock()
        mock_name_row.__getitem__ = lambda self, idx: [doc_id, "测试文档.pdf"][idx]
        mock_name_result = MagicMock()
        mock_name_result.all.return_value = [(doc_id, "测试文档.pdf")]
        mock_db.execute = AsyncMock(return_value=mock_name_result)

        with patch(
            "app.services.knowledge_index_service.KnowledgeIndexService.semantic_search",
            new_callable=AsyncMock,
            return_value=mock_semantic_results,
        ) as mock_search:
            result = await ReferenceDocService.load_from_knowledge_base(
                project_id=project_id,
                keywords=["测试"],
                max_docs=3,
                db=mock_db,
            )

            mock_search.assert_called_once_with(
                project_id, "测试", top_k=3, scope="knowledge_doc"
            )

        assert len(result) == 1
        assert "知识库" in result[0]
        assert "测试文档.pdf" in result[0]
        assert "这是知识库文档内容" in result[0]

    @pytest.mark.asyncio
    async def test_semantic_search_empty_falls_back_to_ilike(self, mock_db):
        """semantic_search 返回空时降级到 ilike。"""
        project_id = uuid4()

        # ilike fallback mock
        mock_ilike_result = MagicMock()
        mock_ilike_result.all.return_value = [("准则文档.pdf", "准则内容文本")]
        mock_db.execute = AsyncMock(return_value=mock_ilike_result)

        with patch(
            "app.services.knowledge_index_service.KnowledgeIndexService.semantic_search",
            new_callable=AsyncMock,
            return_value=[],  # 空结果
        ):
            result = await ReferenceDocService.load_from_knowledge_base(
                project_id=project_id,
                keywords=["准则"],
                category="notes",
                db=mock_db,
            )

        assert len(result) == 1
        assert "准则文档.pdf" in result[0]
        assert "准则内容文本" in result[0]

    @pytest.mark.asyncio
    async def test_semantic_search_exception_falls_back_to_ilike(self, mock_db):
        """semantic_search 抛异常时降级到 ilike。"""
        project_id = uuid4()

        # ilike fallback mock
        mock_ilike_result = MagicMock()
        mock_ilike_result.all.return_value = [("降级文档.pdf", "降级内容")]
        mock_db.execute = AsyncMock(return_value=mock_ilike_result)

        with patch(
            "app.services.knowledge_index_service.KnowledgeIndexService.semantic_search",
            new_callable=AsyncMock,
            side_effect=RuntimeError("embedding service unavailable"),
        ):
            result = await ReferenceDocService.load_from_knowledge_base(
                project_id=project_id,
                keywords=["降级"],
                category="notes",
                db=mock_db,
            )

        assert len(result) == 1
        assert "降级文档.pdf" in result[0]
        assert "降级内容" in result[0]

    @pytest.mark.asyncio
    async def test_no_keywords_skips_semantic_search(self, mock_db):
        """无 keywords 时跳过 semantic_search，直接走 ilike（无关键词过滤）。"""
        project_id = uuid4()

        mock_ilike_result = MagicMock()
        mock_ilike_result.all.return_value = [("全量文档.pdf", "全量内容")]
        mock_db.execute = AsyncMock(return_value=mock_ilike_result)

        with patch(
            "app.services.knowledge_index_service.KnowledgeIndexService.semantic_search",
            new_callable=AsyncMock,
        ) as mock_search:
            result = await ReferenceDocService.load_from_knowledge_base(
                project_id=project_id,
                keywords=None,
                category="notes",
                db=mock_db,
            )
            # semantic_search 不应被调用
            mock_search.assert_not_called()

        assert len(result) == 1
        assert "全量文档.pdf" in result[0]

    @pytest.mark.asyncio
    async def test_content_truncated_to_2000(self, mock_db):
        """内容截断到 2000 字符。"""
        project_id = uuid4()
        doc_id = str(uuid4())
        long_content = "A" * 5000

        mock_semantic_results = [
            {
                "source_type": "knowledge_doc",
                "source_id": doc_id,
                "content": long_content,
                "score": 0.9,
                "chunk_index": 0,
            }
        ]

        mock_name_result = MagicMock()
        mock_name_result.all.return_value = [(doc_id, "长文档.pdf")]
        mock_db.execute = AsyncMock(return_value=mock_name_result)

        with patch(
            "app.services.knowledge_index_service.KnowledgeIndexService.semantic_search",
            new_callable=AsyncMock,
            return_value=mock_semantic_results,
        ):
            result = await ReferenceDocService.load_from_knowledge_base(
                project_id=project_id,
                keywords=["长"],
                db=mock_db,
            )

        # 标题 + \n + 2000 字符内容
        content_part = result[0].split("\n", 1)[1]
        assert len(content_part) == 2000

    @pytest.mark.asyncio
    async def test_multiple_keywords_joined(self, mock_db):
        """多个 keywords 用空格拼接为 query_text。"""
        project_id = uuid4()
        doc_id = str(uuid4())

        mock_semantic_results = [
            {
                "source_type": "knowledge_doc",
                "source_id": doc_id,
                "content": "内容",
                "score": 0.8,
                "chunk_index": 0,
            }
        ]

        mock_name_result = MagicMock()
        mock_name_result.all.return_value = [(doc_id, "文档.pdf")]
        mock_db.execute = AsyncMock(return_value=mock_name_result)

        with patch(
            "app.services.knowledge_index_service.KnowledgeIndexService.semantic_search",
            new_callable=AsyncMock,
            return_value=mock_semantic_results,
        ) as mock_search:
            await ReferenceDocService.load_from_knowledge_base(
                project_id=project_id,
                keywords=["货币", "资金", "审计"],
                db=mock_db,
            )

            # 验证 query_text 是空格拼接
            mock_search.assert_called_once_with(
                project_id, "货币 资金 审计", top_k=3, scope="knowledge_doc"
            )

    @pytest.mark.asyncio
    async def test_method_signature_unchanged(self):
        """方法签名保持向后兼容。"""
        import inspect

        sig = inspect.signature(ReferenceDocService.load_from_knowledge_base)
        params = list(sig.parameters.keys())
        assert params == ["project_id", "category", "keywords", "max_docs", "db"]
