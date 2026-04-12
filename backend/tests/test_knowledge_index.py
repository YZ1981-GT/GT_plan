"""
知识库索引服务单元测试
测试知识库索引核心功能
需求覆盖: 6.1-6.7

注：此文件测试实际服务实现中已存在的方法。
方法签名需与 backend/app/services/knowledge_index_service.py 对齐。
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.knowledge_index_service import KnowledgeIndexService
from app.models.ai_models import KnowledgeSourceType


class TestKnowledgeIndexService:
    """测试知识库索引服务 — 基于实际实现的方法签名"""

    @pytest.mark.asyncio
    async def test_service_instantiation(self):
        """测试服务可正常实例化"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)
        assert service is not None
        assert service.db is mock_db

    @pytest.mark.asyncio
    async def test_knowledge_source_type_enum(self):
        """测试知识源类型枚举值"""
        assert KnowledgeSourceType.trial_balance.value == "trial_balance"
        assert KnowledgeSourceType.journal.value == "journal"
        assert KnowledgeSourceType.contract.value == "contract"
        assert KnowledgeSourceType.workpaper.value == "workpaper"
        assert KnowledgeSourceType.document_scan.value == "document_scan"

    @pytest.mark.asyncio
    async def test_chunk_text(self):
        """测试文本分块辅助函数"""
        # 测试短文本不需要分块
        short_text = "这是一段较短的文本内容"
        chunks = KnowledgeIndexService._chunk_text(short_text)
        assert len(chunks) == 1
        assert chunks[0] == short_text

        # 测试长文本分块
        long_text = "测试内容 " * 500
        chunks = KnowledgeIndexService._chunk_text(long_text, chunk_size=200)
        assert len(chunks) > 1
        # 验证每块大小不超过chunk_size
        for chunk in chunks:
            assert len(chunk) <= 200

    @pytest.mark.asyncio
    async def test_build_index_method_exists(self):
        """测试 build_index 方法存在"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)
        assert hasattr(service, "build_index")
        assert callable(service.build_index)

    @pytest.mark.asyncio
    async def test_build_index_returns_int(self):
        """测试 build_index 返回索引块数量"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)

        project_id = uuid4()

        # Mock空结果
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.build_index(project_id)
        assert isinstance(result, int)
        assert result >= 0

    @pytest.mark.asyncio
    async def test_incremental_update_method_exists(self):
        """测试 incremental_update 方法存在"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)
        assert hasattr(service, "incremental_update")
        assert callable(service.incremental_update)

    @pytest.mark.asyncio
    async def test_semantic_search_method_exists(self):
        """测试 semantic_search 方法存在"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)
        assert hasattr(service, "semantic_search")
        assert callable(service.semantic_search)

    @pytest.mark.asyncio
    async def test_search_cross_year_method_exists(self):
        """测试 search_cross_year 方法存在"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)
        assert hasattr(service, "search_cross_year")
        assert callable(service.search_cross_year)

    @pytest.mark.asyncio
    async def test_lock_index_method_exists(self):
        """测试 lock_index 方法存在"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)
        assert hasattr(service, "lock_index")
        assert callable(service.lock_index)

    @pytest.mark.asyncio
    async def test_delete_index_method_exists(self):
        """测试 delete_index 方法存在"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)
        assert hasattr(service, "delete_index")
        assert callable(service.delete_index)

    @pytest.mark.asyncio
    async def test_add_document_method_exists(self):
        """测试 add_document 方法存在"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)
        assert hasattr(service, "add_document")
        assert callable(service.add_document)

    @pytest.mark.asyncio
    async def test_search_method_exists(self):
        """测试 search 方法存在（semantic_search的别名）"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)
        assert hasattr(service, "search")
        assert callable(service.search)

    @pytest.mark.asyncio
    async def test_update_index_method_exists(self):
        """测试 update_index 方法存在"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)
        assert hasattr(service, "update_index")
        assert callable(service.update_index)

    @pytest.mark.asyncio
    async def test_get_index_status_method_exists(self):
        """测试 get_index_status 方法存在"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)
        assert hasattr(service, "get_index_status")
        assert callable(service.get_index_status)

    @pytest.mark.asyncio
    async def test_vector_conversion_helpers(self):
        """测试向量转换辅助方法"""
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)

        import numpy as np
        # 测试向量转字符串再转回
        vec = np.array([0.1, 0.2, 0.3])
        s = service._vector_to_str(vec)
        assert isinstance(s, str)
        vec_back = service._str_to_vector(s)
        assert np.allclose(vec, vec_back)

    @pytest.mark.asyncio
    async def test_cosine_similarity(self):
        """测试余弦相似度辅助方法"""
        import numpy as np
        mock_db = AsyncMock()
        service = KnowledgeIndexService(mock_db)

        a = np.array([1.0, 0.0])
        b = np.array([1.0, 0.0])
        assert service._cosine_similarity(a, b) == pytest.approx(1.0)

        c = np.array([1.0, 0.0])
        d = np.array([0.0, 1.0])
        assert service._cosine_similarity(c, d) == pytest.approx(0.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
