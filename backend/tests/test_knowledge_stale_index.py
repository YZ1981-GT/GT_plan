"""P2-2 知识引用与索引 stale 测试

验证：
- P2-2.1: AI 引用返回文档版本、段落、引用位置
- P2-2.2: 文档更新后标记旧索引 stale
- P2-2.3: 重建索引后解除 stale
- P2-2.4: 旧索引不可作为 confirmed AI 来源
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai_content_gate import (
    AiContentStatus,
    can_enter_formal_output,
    validate_citations_freshness,
)
from app.services.knowledge_index_service import KnowledgeIndexService


# ---------------------------------------------------------------------------
# P2-2.4: 旧索引不可作为 confirmed AI 来源
# ---------------------------------------------------------------------------


class TestStaleSourceCitationValidation:
    """测试 stale 来源不可用于 confirmed AI 内容。"""

    def test_all_citations_stale_blocks_confirmation(self):
        """所有引用来源均 stale 时，不允许确认。"""
        citations = [
            {"source_type": "knowledge_doc", "source_id": str(uuid.uuid4()),
             "is_stale": True, "doc_version": 1},
            {"source_type": "knowledge_doc", "source_id": str(uuid.uuid4()),
             "is_stale": True, "doc_version": 2},
        ]
        valid, msg = validate_citations_freshness(citations)
        assert valid is False
        assert "过期" in msg

    def test_at_least_one_fresh_allows_confirmation(self):
        """至少有一条 fresh 来源时，允许确认。"""
        citations = [
            {"source_type": "knowledge_doc", "source_id": str(uuid.uuid4()),
             "is_stale": True, "doc_version": 1},
            {"source_type": "knowledge_doc", "source_id": str(uuid.uuid4()),
             "is_stale": False, "doc_version": 3},
        ]
        valid, msg = validate_citations_freshness(citations)
        assert valid is True
        assert msg is None

    def test_all_fresh_allows_confirmation(self):
        """所有来源均 fresh 时，允许确认。"""
        citations = [
            {"source_type": "knowledge_doc", "source_id": str(uuid.uuid4()),
             "is_stale": False, "doc_version": 2},
        ]
        valid, msg = validate_citations_freshness(citations)
        assert valid is True

    def test_no_citations_allows_confirmation(self):
        """无引用来源时，不阻断确认（纯 LLM 生成场景）。"""
        valid, msg = validate_citations_freshness([])
        assert valid is True

    def test_stale_source_combined_with_strict_gate(self):
        """stale 来源 + strict=True 下，confirmed 不应通过双重校验。

        验证 confirmed 状态的 AI 内容在 stale 来源下应被二次阻断。
        """
        # AI 内容已是 confirmed，但来源全 stale
        # 第一重：状态机允许
        allowed, _ = can_enter_formal_output("confirmed", strict=True)
        assert allowed is True

        # 第二重：来源校验阻断
        citations = [
            {"source_type": "knowledge_doc", "source_id": str(uuid.uuid4()),
             "is_stale": True, "doc_version": 1},
        ]
        valid, msg = validate_citations_freshness(citations)
        assert valid is False


# ---------------------------------------------------------------------------
# P2-2.2: 文档更新后标记旧索引 stale
# ---------------------------------------------------------------------------


class TestMarkIndexStale:
    """测试 mark_index_stale 方法。"""

    @pytest.mark.asyncio
    async def test_mark_stale_updates_rows(self):
        """mark_index_stale 应将匹配的 chunk 标记为 stale。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)
        count = await service.mark_index_stale(uuid.uuid4())

        assert count == 3
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_stale_no_existing_chunks(self):
        """无匹配 chunk 时 mark_index_stale 返回 0。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)
        count = await service.mark_index_stale(uuid.uuid4())

        assert count == 0


# ---------------------------------------------------------------------------
# P2-2.3: 重建索引后解除 stale
# ---------------------------------------------------------------------------


class TestClearIndexStale:
    """测试 clear_index_stale 方法。"""

    @pytest.mark.asyncio
    async def test_clear_stale_updates_rows(self):
        """clear_index_stale 应清除匹配 chunk 的 stale 标记。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)
        count = await service.clear_index_stale(uuid.uuid4())

        assert count == 5
        mock_db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# P2-2.1: AI 引用返回文档版本、段落、引用位置
# ---------------------------------------------------------------------------


class TestCitationWithVersion:
    """测试 Citation 包含文档版本和 stale 信息。"""

    def test_citation_has_version_fields(self):
        """Citation dataclass 应包含 doc_version 和 is_stale 字段。"""
        from app.services.doc_ai_context_builder import Citation

        citation = Citation(
            source_type="knowledge_doc",
            source_id=str(uuid.uuid4()),
            source_name="测试文档.pdf",
            paragraph_index=3,
            excerpt="这是第三段内容",
            doc_version=2,
            is_stale=False,
        )
        assert citation.doc_version == 2
        assert citation.is_stale is False
        assert citation.paragraph_index == 3

    def test_citation_stale_default_false(self):
        """Citation 的 is_stale 默认为 False。"""
        from app.services.doc_ai_context_builder import Citation

        citation = Citation(
            source_type="knowledge_doc",
            source_id=str(uuid.uuid4()),
            source_name="文档",
            paragraph_index=0,
        )
        assert citation.is_stale is False
        assert citation.doc_version is None

    def test_search_hit_has_version_fields(self):
        """SearchHit dataclass 应包含 doc_version 和 is_stale 字段。"""
        from app.services.doc_ai_context_builder import SearchHit

        hit = SearchHit(
            source_type="knowledge_doc",
            source_id=str(uuid.uuid4()),
            content="索引内容",
            score=0.85,
            chunk_index=1,
            source_name="参照文档",
            doc_version=3,
            is_stale=True,
        )
        assert hit.doc_version == 3
        assert hit.is_stale is True


# ---------------------------------------------------------------------------
# P2-2.2+P2-2.3: is_source_stale 综合判断
# ---------------------------------------------------------------------------


class TestIsSourceStale:
    """测试 is_source_stale 方法。"""

    @pytest.mark.asyncio
    async def test_source_with_only_stale_chunks_is_stale(self):
        """所有 chunk 都 stale 时返回 True。"""
        mock_db = AsyncMock()
        # stale_count=3, fresh_count=0
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = (3, 0)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)
        assert await service.is_source_stale(uuid.uuid4()) is True

    @pytest.mark.asyncio
    async def test_source_with_fresh_chunks_not_stale(self):
        """存在 fresh chunk 时返回 False。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = (2, 5)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)
        assert await service.is_source_stale(uuid.uuid4()) is False

    @pytest.mark.asyncio
    async def test_source_with_no_chunks_not_stale(self):
        """无 chunk 时返回 False。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)
        assert await service.is_source_stale(uuid.uuid4()) is False
