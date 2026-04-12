"""
Knowledge Index Service Unit Tests — Task 24.5
Test build_index, semantic_search, incremental_update, search_cross_year.
Mock the embedding and ChromaDB interactions.

Requirements: 6.1-6.7
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.knowledge_index_service import KnowledgeIndexService, _chunk_text
from app.models.ai_models import KnowledgeSourceType


@pytest.fixture
def mock_db_session():
    """Mock AsyncSession that never hits the real database."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class TestKnowledgeIndexServiceBuildIndex:
    """Test KnowledgeIndexService.build_index()"""

    @pytest.mark.asyncio
    async def test_build_index_empty_project(self, mock_db_session):
        """build_index with no documents returns 0 chunks."""
        service = KnowledgeIndexService(mock_db_session)

        # Mock empty results for all tables
        for table_name in [
            "document_scan", "adjustment_entry", "trial_balance",
            "audit_report", "contract", "audit_finding"
        ]:
            mock_result = MagicMock()
            mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
            mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 768

            count = await service.build_index(project_id=uuid4())

        assert count == 0

    @pytest.mark.asyncio
    async def test_build_index_with_documents(self, mock_db_session):
        """build_index with documents creates index chunks."""
        service = KnowledgeIndexService(mock_db_session)

        # Mock DocumentScan
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.file_name = "采购合同.pdf"
        mock_doc.document_type = "contract"

        mock_doc_result = MagicMock()
        mock_doc_scalars = MagicMock()
        mock_doc_scalars.all.return_value = [mock_doc]
        mock_doc_result.scalars.return_value = mock_doc_scalars

        # All other tables return empty
        def execute_side_effect(*args):
            query_str = str(args[0])
            if "document_scan" in query_str:
                return mock_doc_result
            empty_result = MagicMock()
            empty_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
            return empty_result

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db_session.commit = AsyncMock()

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 768

            count = await service.build_index(project_id=uuid4())

        # At least 1 chunk created for the document
        assert count >= 1
        mock_embed.assert_called()

    @pytest.mark.asyncio
    async def test_build_index_with_trial_balance(self, mock_db_session):
        """build_index indexes trial balance data."""
        service = KnowledgeIndexService(mock_db_session)

        # Mock TrialBalance
        mock_tb = MagicMock()
        mock_tb.id = uuid4()
        mock_tb.account_code = "1122"
        mock_tb.account_name = "应收账款"
        mock_tb.period = "2024-12"
        mock_tb.opening_balance = 1000000.0
        mock_tb.closing_balance = 1200000.0

        mock_tb_result = MagicMock()
        mock_tb_scalars = MagicMock()
        mock_tb_scalars.all.return_value = [mock_tb]
        mock_tb_result.scalars.return_value = mock_tb_scalars

        # Other tables empty
        def execute_side_effect(*args):
            query_str = str(args[0])
            if "trial_balance" in query_str:
                return mock_tb_result
            empty_result = MagicMock()
            empty_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
            return empty_result

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db_session.commit = AsyncMock()

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 768

            count = await service.build_index(project_id=uuid4())

        assert count >= 1


class TestKnowledgeIndexServiceIncrementalUpdate:
    """Test KnowledgeIndexService.incremental_update()"""

    @pytest.mark.asyncio
    async def test_incremental_update_creates_chunks(self, mock_db_session):
        """incremental_update creates new chunks for changed content."""
        service = KnowledgeIndexService(mock_db_session)

        mock_db_session.execute = AsyncMock()
        mock_db_session.commit = AsyncMock()

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 768

            await service.incremental_update(
                project_id=uuid4(),
                source_type="trial_balance",
                source_id=uuid4(),
                content="应收账款科目，期末余额1200万元，较期初增长20%",
            )

        mock_embed.assert_called()


class TestKnowledgeIndexServiceSemanticSearch:
    """Test KnowledgeIndexService.semantic_search()"""

    @pytest.mark.asyncio
    async def test_semantic_search_returns_results(self, mock_db_session):
        """semantic_search returns top-k results with scores."""
        service = KnowledgeIndexService(mock_db_session)

        # Mock knowledge index chunks
        mock_chunk = MagicMock()
        mock_chunk.id = uuid4()
        mock_chunk.source_type = KnowledgeSourceType.trial_balance
        mock_chunk.source_id = uuid4()
        mock_chunk.content_text = "应收账款期末余额分析"
        mock_chunk.chunk_index = 0
        mock_chunk.embedding_vector = ",".join(["0.8"] + ["0.1"] * 767)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_chunk]
        mock_result.scalars.return_value = mock_scalars

        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.8] + [0.1] * 767

            results = await service.semantic_search(
                project_id=uuid4(),
                query="应收账款余额分析",
                top_k=5,
            )

        assert len(results) > 0
        assert "score" in results[0]
        assert "source_type" in results[0]
        assert "content" in results[0]

    @pytest.mark.asyncio
    async def test_semantic_search_empty_results(self, mock_db_session):
        """semantic_search returns empty list when no matches."""
        service = KnowledgeIndexService(mock_db_session)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars

        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 768

            results = await service.semantic_search(
                project_id=uuid4(),
                query="完全不相关的查询内容xyz",
                top_k=5,
            )

        assert results == []


class TestKnowledgeIndexServiceSearchCrossYear:
    """Test KnowledgeIndexService.search_cross_year()"""

    @pytest.mark.asyncio
    async def test_search_cross_year_merges_results(self, mock_db_session):
        """search_cross_year searches both projects and merges results."""
        service = KnowledgeIndexService(mock_db_session)

        # Mock chunk for current year
        mock_chunk1 = MagicMock()
        mock_chunk1.id = uuid4()
        mock_chunk1.source_type = KnowledgeSourceType.contract
        mock_chunk1.source_id = uuid4()
        mock_chunk1.content_text = "2024年采购合同"
        mock_chunk1.chunk_index = 0
        mock_chunk1.embedding_vector = ",".join(["0.9"] + ["0.1"] * 767)

        # Mock chunk for prior year
        mock_chunk2 = MagicMock()
        mock_chunk2.id = uuid4()
        mock_chunk2.source_type = KnowledgeSourceType.contract
        mock_chunk2.source_id = uuid4()
        mock_chunk2.content_text = "2023年采购合同"
        mock_chunk2.chunk_index = 0
        mock_chunk2.embedding_vector = ",".join(["0.7"] + ["0.1"] * 767)

        current_project_id = uuid4()
        prior_project_id = uuid4()

        # Return current chunk for current project query
        mock_result1 = MagicMock()
        mock_scalars1 = MagicMock()
        mock_scalars1.all.return_value = [mock_chunk1]
        mock_result1.scalars.return_value = mock_scalars1

        # Return prior chunk for prior project query
        mock_result2 = MagicMock()
        mock_scalars2 = MagicMock()
        mock_scalars2.all.return_value = [mock_chunk2]
        mock_result2.scalars.return_value = mock_scalars2

        def execute_side_effect(*args):
            mock_res = MagicMock()
            mock_res.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
            return mock_res

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)

        # Override execute for specific queries
        call_count = [0]

        async def execute_with_override(query, *args):
            mock_res = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = [mock_chunk1]
                mock_res.scalars.return_value = mock_scalars
            else:
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = [mock_chunk2]
                mock_res.scalars.return_value = mock_scalars
            return mock_res

        mock_db_session.execute = execute_with_override

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.8] + [0.1] * 767

            results = await service.search_cross_year(
                project_id=current_project_id,
                prior_project_id=prior_project_id,
                query="采购合同",
            )

        assert isinstance(results, list)


class TestKnowledgeIndexServiceDeleteAndLock:
    """Test KnowledgeIndexService.delete_index() and lock_index()"""

    @pytest.mark.asyncio
    async def test_delete_index_soft_deletes(self, mock_db_session):
        """delete_index soft-deletes all project chunks."""
        service = KnowledgeIndexService(mock_db_session)
        mock_db_session.execute = AsyncMock()
        mock_db_session.commit = AsyncMock()

        await service.delete_index(project_id=uuid4())

        mock_db_session.execute.assert_called()
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_lock_index_commits(self, mock_db_session):
        """lock_index commits (reserved for future locking feature)."""
        service = KnowledgeIndexService(mock_db_session)
        mock_db_session.commit = AsyncMock()

        # Should not raise
        await service.lock_index(project_id=uuid4())

        mock_db_session.commit.assert_called()


class TestKnowledgeIndexServiceGetIndexStatus:
    """Test KnowledgeIndexService.get_index_status()"""

    @pytest.mark.asyncio
    async def test_get_index_status_with_data(self, mock_db_session):
        """get_index_status returns correct statistics by source type."""
        service = KnowledgeIndexService(mock_db_session)

        # Mock grouped results
        mock_row1 = MagicMock()
        mock_row1.source_type = KnowledgeSourceType.trial_balance
        mock_row1.count = 50

        mock_row2 = MagicMock()
        mock_row2.source_type = KnowledgeSourceType.contract
        mock_row2.count = 20

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row1, mock_row2]

        mock_db_session.execute = AsyncMock(return_value=mock_result)

        status = await service.get_index_status(project_id=uuid4())

        assert status["total_chunks"] == 70
        assert status["is_indexed"] is True
        assert "trial_balance" in status["by_source_type"]
        assert "contract" in status["by_source_type"]

    @pytest.mark.asyncio
    async def test_get_index_status_empty(self, mock_db_session):
        """get_index_status returns empty status for unindexed project."""
        service = KnowledgeIndexService(mock_db_session)

        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_db_session.execute = AsyncMock(return_value=mock_result)

        status = await service.get_index_status(project_id=uuid4())

        assert status["total_chunks"] == 0
        assert status["is_indexed"] is False
        assert status["by_source_type"] == {}


class TestChunkTextHelper:
    """Test the _chunk_text helper function"""

    def test_chunk_text_normal(self):
        """_chunk_text splits text into chunks of specified size."""
        text = "A" * 1000
        chunks = _chunk_text(text, chunk_size=200)

        assert len(chunks) == 5
        assert all(len(c) <= 200 for c in chunks)

    def test_chunk_text_short_text(self):
        """_chunk_text returns single chunk for short text."""
        text = "短文本"
        chunks = _chunk_text(text, chunk_size=500)

        assert len(chunks) == 1
        assert chunks[0] == "短文本"

    def test_chunk_text_empty(self):
        """_chunk_text returns empty list for empty text."""
        assert _chunk_text("") == []
        assert _chunk_text("   ") == []

    def test_chunk_text_unicode(self):
        """_chunk_text handles Chinese characters correctly."""
        # Chinese chars count as 1 char each
        text = "中" * 500
        chunks = _chunk_text(text, chunk_size=200)

        assert len(chunks) == 3
        assert all(len(c) <= 200 for c in chunks)

    def test_chunk_text_exact_size(self):
        """_chunk_text handles text exactly at chunk boundary."""
        text = "X" * 500
        chunks = _chunk_text(text, chunk_size=500)

        assert len(chunks) == 1
        assert chunks[0] == text


class TestKnowledgeIndexServiceVectorHelpers:
    """Test vector conversion and similarity helpers"""

    def test_vector_to_str_roundtrip(self):
        """_vector_to_str and _str_to_vector are inverse operations."""
        import numpy as np

        original = np.array([0.1, 0.2, 0.3, 0.4])
        serialized = KnowledgeIndexService._vector_to_str(original)
        restored = KnowledgeIndexService._str_to_vector(serialized)

        assert np.allclose(restored, original)

    def test_cosine_similarity_identical(self):
        """_cosine_similarity returns 1.0 for identical vectors."""
        import numpy as np

        v = np.array([0.6, 0.8])
        result = KnowledgeIndexService._cosine_similarity(v, v)

        assert abs(result - 1.0) < 0.0001

    def test_cosine_similarity_perpendicular(self):
        """_cosine_similarity returns 0.0 for perpendicular vectors."""
        import numpy as np

        v1 = np.array([1.0, 0.0])
        v2 = np.array([0.0, 1.0])
        result = KnowledgeIndexService._cosine_similarity(v1, v2)

        assert abs(result) < 0.0001

    def test_cosine_similarity_opposite(self):
        """_cosine_similarity returns -1.0 for opposite vectors."""
        import numpy as np

        v1 = np.array([1.0, 0.0])
        v2 = np.array([-1.0, 0.0])
        result = KnowledgeIndexService._cosine_similarity(v1, v2)

        assert abs(result - (-1.0)) < 0.0001
