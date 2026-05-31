"""
Unit Tests: semantic_search scope + 权限过滤 + ilike 降级

**Validates: Requirements 1.1, 4.1, 4.2**

测试 semantic_search 新增的 scope/user kwargs：
- scope 过滤（project_data / knowledge_doc / all）
- user 权限过滤
- ilike 降级
- 默认值向后兼容
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.knowledge_index_service import KnowledgeIndexService
from app.models.ai_models import KnowledgeSourceType


@pytest.fixture
def mock_db_session():
    """Mock AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _make_chunk(source_type: KnowledgeSourceType, content: str):
    """创建 mock KnowledgeIndex chunk。"""
    chunk = MagicMock()
    chunk.id = uuid4()
    chunk.source_type = source_type
    chunk.source_id = uuid4()
    chunk.content_text = content
    chunk.chunk_index = 0
    chunk.embedding_vector = ",".join(["0.5"] * 768)
    return chunk


class TestSemanticSearchBackwardCompat:
    """验证默认参数保持向后兼容（ai_chat_service 零改）"""

    @pytest.mark.asyncio
    async def test_default_scope_is_all(self, mock_db_session):
        """默认 scope='all'，不过滤任何 source_type。"""
        service = KnowledgeIndexService(mock_db_session)

        chunk = _make_chunk(KnowledgeSourceType.trial_balance, "测试内容")
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[chunk]))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            # 旧调用方式（无 scope/user）
            results = await service.semantic_search(
                project_id=uuid4(),
                query="测试",
                top_k=10,
            )

        assert len(results) == 1
        assert results[0]["source_type"] == "trial_balance"

    @pytest.mark.asyncio
    async def test_default_user_is_none_no_filtering(self, mock_db_session):
        """默认 user=None，不做权限过滤。"""
        service = KnowledgeIndexService(mock_db_session)

        # knowledge_doc chunk 也应返回（无 user 时不过滤）
        chunk = _make_chunk(KnowledgeSourceType.knowledge_doc, "知识文档")
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[chunk]))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            results = await service.semantic_search(
                project_id=uuid4(),
                query="知识",
                top_k=10,
            )

        assert len(results) == 1
        assert results[0]["source_type"] == "knowledge_doc"


class TestSemanticSearchScope:
    """验证 scope 过滤逻辑"""

    @pytest.mark.asyncio
    async def test_scope_project_data_excludes_knowledge_doc(self, mock_db_session):
        """scope='project_data' 排除 knowledge_doc 类型。"""
        service = KnowledgeIndexService(mock_db_session)

        # 只有业务数据 chunk
        biz_chunk = _make_chunk(KnowledgeSourceType.trial_balance, "业务数据")
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[biz_chunk]))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            results = await service.semantic_search(
                project_id=uuid4(),
                query="业务",
                top_k=10,
                scope="project_data",
            )

        assert len(results) == 1
        assert results[0]["source_type"] == "trial_balance"

    @pytest.mark.asyncio
    async def test_scope_knowledge_doc_only_returns_docs(self, mock_db_session):
        """scope='knowledge_doc' 只返回知识文档。"""
        service = KnowledgeIndexService(mock_db_session)

        doc_chunk = _make_chunk(KnowledgeSourceType.knowledge_doc, "知识文档内容")
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[doc_chunk]))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            results = await service.semantic_search(
                project_id=uuid4(),
                query="知识",
                top_k=10,
                scope="knowledge_doc",
            )

        assert len(results) == 1
        assert results[0]["source_type"] == "knowledge_doc"

    @pytest.mark.asyncio
    async def test_scope_cross_year_falls_back_to_all(self, mock_db_session):
        """scope='cross_year' 在 semantic_search 中降级为 all（需 prior_project_id 走 search_cross_year）。"""
        service = KnowledgeIndexService(mock_db_session)

        chunk = _make_chunk(KnowledgeSourceType.contract, "合同数据")
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[chunk]))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            results = await service.semantic_search(
                project_id=uuid4(),
                query="合同",
                top_k=10,
                scope="cross_year",
            )

        # cross_year 降级为 all，返回所有类型
        assert len(results) == 1


class TestSemanticSearchIlikeFallback:
    """验证 ilike 降级逻辑"""

    @pytest.mark.asyncio
    async def test_embedding_failure_triggers_ilike(self, mock_db_session):
        """embedding 服务不可用时降级 ilike。"""
        service = KnowledgeIndexService(mock_db_session)

        chunk = _make_chunk(KnowledgeSourceType.trial_balance, "应收账款分析")
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[chunk]))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.side_effect = Exception("Connection refused")

            results = await service.semantic_search(
                project_id=uuid4(),
                query="应收账款",
                top_k=10,
            )

        assert len(results) == 1
        assert results[0]["score"] == 0.0  # ilike 无分数

    @pytest.mark.asyncio
    async def test_ilike_fallback_respects_scope(self, mock_db_session):
        """ilike 降级也遵守 scope 过滤。"""
        service = KnowledgeIndexService(mock_db_session)

        doc_chunk = _make_chunk(KnowledgeSourceType.knowledge_doc, "知识文档")
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[doc_chunk]))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.side_effect = RuntimeError("Service down")

            results = await service.semantic_search(
                project_id=uuid4(),
                query="知识",
                top_k=10,
                scope="knowledge_doc",
            )

        assert len(results) == 1
        assert results[0]["source_type"] == "knowledge_doc"
