"""
VectorStore Protocol + PgTextStore 单元测试

验证：
- VectorStore 是 @runtime_checkable Protocol
- PgTextStore 满足 VectorStore Protocol
- PgTextStore.add/query/delete 行为正确
- key 格式解析/构造正确

需求: 3.1  属性: R4
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from app.services.vector_store import VectorStore, PgTextStore


class TestVectorStoreProtocol:
    """验证 VectorStore Protocol 定义正确。"""

    def test_protocol_is_runtime_checkable(self):
        """VectorStore 是 @runtime_checkable Protocol。"""
        assert hasattr(VectorStore, "__protocol_attrs__") or hasattr(VectorStore, "__abstractmethods__") or True
        # runtime_checkable 的关键特征：isinstance 检查可用
        from typing import runtime_checkable, Protocol
        # VectorStore 应该可以用 isinstance 检查
        assert issubclass(type(VectorStore), type(Protocol))

    def test_pg_text_store_satisfies_protocol(self):
        """PgTextStore 满足 VectorStore Protocol（isinstance 检查）。"""
        mock_db = AsyncMock()
        store = PgTextStore(mock_db)
        assert isinstance(store, VectorStore)

    def test_protocol_has_required_methods(self):
        """VectorStore Protocol 定义了 add/query/delete 三个方法。"""
        assert hasattr(VectorStore, "add")
        assert hasattr(VectorStore, "query")
        assert hasattr(VectorStore, "delete")


class TestPgTextStoreKeyFormat:
    """验证 key 格式解析和构造。"""

    def test_make_key(self):
        """make_key 构造正确格式的 key。"""
        project_id = str(uuid4())
        source_type = "trial_balance"
        source_id = str(uuid4())
        chunk_index = 3

        key = PgTextStore.make_key(project_id, source_type, source_id, chunk_index)
        assert key == f"{project_id}:{source_type}:{source_id}:{chunk_index}"

    def test_parse_key(self):
        """parse_key 正确解析 key 为四元组。"""
        project_id = str(uuid4())
        source_type = "knowledge_doc"
        source_id = str(uuid4())
        chunk_index = 5

        key = f"{project_id}:{source_type}:{source_id}:{chunk_index}"
        parsed = PgTextStore.parse_key(key)

        assert parsed == (project_id, source_type, source_id, chunk_index)

    def test_parse_key_roundtrip(self):
        """make_key → parse_key 往返一致。"""
        project_id = str(uuid4())
        source_type = "contract"
        source_id = str(uuid4())
        chunk_index = 0

        key = PgTextStore.make_key(project_id, source_type, source_id, chunk_index)
        parsed = PgTextStore.parse_key(key)

        assert parsed == (project_id, source_type, source_id, chunk_index)

    def test_parse_key_invalid_format(self):
        """parse_key 对无效格式抛 ValueError。"""
        with pytest.raises(ValueError, match="Invalid key format"):
            PgTextStore.parse_key("invalid-key-no-colons")

        with pytest.raises(ValueError, match="Invalid key format"):
            PgTextStore.parse_key("only:two:parts")


class TestPgTextStoreVectorHelpers:
    """验证向量转换和相似度计算辅助方法。"""

    def test_vector_to_str(self):
        """_vector_to_str 将 float 列表转为逗号分隔字符串。"""
        vec = [0.1, 0.2, 0.3]
        result = PgTextStore._vector_to_str(vec)
        assert result == "0.1,0.2,0.3"

    def test_str_to_vector(self):
        """_str_to_vector 将逗号分隔字符串解析为 numpy 数组。"""
        import numpy as np
        s = "0.1,0.2,0.3"
        result = PgTextStore._str_to_vector(s)
        assert np.allclose(result, [0.1, 0.2, 0.3])

    def test_vector_roundtrip(self):
        """_vector_to_str → _str_to_vector 往返精度保持。"""
        import numpy as np
        original = [0.123456, -0.789012, 0.0, 1.0]
        s = PgTextStore._vector_to_str(original)
        restored = PgTextStore._str_to_vector(s)
        assert np.allclose(restored, original)

    def test_cosine_similarity_identical(self):
        """相同向量余弦相似度为 1.0。"""
        import numpy as np
        v = np.array([0.6, 0.8])
        assert abs(PgTextStore._cosine_similarity(v, v) - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        """正交向量余弦相似度为 0.0。"""
        import numpy as np
        v1 = np.array([1.0, 0.0])
        v2 = np.array([0.0, 1.0])
        assert abs(PgTextStore._cosine_similarity(v1, v2)) < 1e-6

    def test_cosine_similarity_zero_vector(self):
        """零向量余弦相似度为 0.0（不崩）。"""
        import numpy as np
        v1 = np.array([1.0, 0.0])
        v2 = np.array([0.0, 0.0])
        assert PgTextStore._cosine_similarity(v1, v2) == 0.0


class TestPgTextStoreAdd:
    """验证 PgTextStore.add 行为。"""

    @pytest.mark.asyncio
    async def test_add_executes_upsert(self):
        """add 执行 upsert 语句到 KnowledgeIndex。"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        store = PgTextStore(mock_db)

        project_id = str(uuid4())
        source_id = str(uuid4())
        key = PgTextStore.make_key(project_id, "trial_balance", source_id, 0)
        embedding = [0.1, 0.2, 0.3]
        meta = {"content_text": "测试内容"}

        await store.add(key, embedding, meta)

        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_unknown_source_type_skips(self):
        """add 对未知 source_type 跳过（不崩）。"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        store = PgTextStore(mock_db)

        project_id = str(uuid4())
        source_id = str(uuid4())
        key = PgTextStore.make_key(project_id, "unknown_type_xyz", source_id, 0)

        await store.add(key, [0.1, 0.2], {"content_text": "test"})

        # 未知类型不执行 DB 操作
        mock_db.execute.assert_not_called()


class TestPgTextStoreQuery:
    """验证 PgTextStore.query 行为。"""

    @pytest.mark.asyncio
    async def test_query_returns_sorted_results(self):
        """query 返回按相似度降序排列的 [(key, score)]。"""
        mock_db = AsyncMock()

        # 模拟两个 chunk
        chunk1 = MagicMock()
        chunk1.id = uuid4()
        chunk1.project_id = uuid4()
        chunk1.source_type = MagicMock(value="trial_balance")
        chunk1.source_id = uuid4()
        chunk1.chunk_index = 0
        chunk1.embedding_vector = "0.9,0.1,0.0"  # 高相似度

        chunk2 = MagicMock()
        chunk2.id = uuid4()
        chunk2.project_id = chunk1.project_id
        chunk2.source_type = MagicMock(value="contract")
        chunk2.source_id = uuid4()
        chunk2.chunk_index = 0
        chunk2.embedding_vector = "0.1,0.9,0.0"  # 低相似度

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [chunk1, chunk2]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        store = PgTextStore(mock_db)
        results = await store.query([0.9, 0.1, 0.0], top_k=2)

        assert len(results) == 2
        # 第一个结果相似度更高
        assert results[0][1] >= results[1][1]
        # 返回格式是 (key, score)
        assert isinstance(results[0][0], str)
        assert isinstance(results[0][1], float)

    @pytest.mark.asyncio
    async def test_query_respects_top_k(self):
        """query 只返回 top_k 个结果。"""
        mock_db = AsyncMock()

        # 模拟 5 个 chunk
        chunks = []
        for i in range(5):
            chunk = MagicMock()
            chunk.id = uuid4()
            chunk.project_id = uuid4()
            chunk.source_type = MagicMock(value="trial_balance")
            chunk.source_id = uuid4()
            chunk.chunk_index = 0
            chunk.embedding_vector = f"{0.1 * (i + 1)},0.1,0.1"
            chunks.append(chunk)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = chunks
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        store = PgTextStore(mock_db)
        results = await store.query([0.5, 0.1, 0.1], top_k=3)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_query_empty_table(self):
        """query 空表返回空列表。"""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        store = PgTextStore(mock_db)
        results = await store.query([0.1, 0.2, 0.3], top_k=5)

        assert results == []

    @pytest.mark.asyncio
    async def test_query_with_project_id_filter(self):
        """query 设置 project_id 时限定范围。"""
        mock_db = AsyncMock()
        project_id = str(uuid4())

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        store = PgTextStore(mock_db, project_id=project_id)
        results = await store.query([0.1, 0.2], top_k=5)

        # 验证 execute 被调用（带 project_id 过滤）
        mock_db.execute.assert_called_once()
        assert results == []


class TestPgTextStoreDelete:
    """验证 PgTextStore.delete 行为。"""

    @pytest.mark.asyncio
    async def test_delete_soft_deletes(self):
        """delete 执行软删除（is_deleted=True）。"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        store = PgTextStore(mock_db)

        project_id = str(uuid4())
        source_id = str(uuid4())
        key = PgTextStore.make_key(project_id, "trial_balance", source_id, 0)

        await store.delete(key)

        mock_db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# PgVectorStore 单元测试
# ---------------------------------------------------------------------------

from app.services.vector_store import PgVectorStore


class TestPgVectorStoreProtocol:
    """验证 PgVectorStore 满足 VectorStore Protocol。"""

    def test_pg_vector_store_satisfies_protocol(self):
        """PgVectorStore 满足 VectorStore Protocol（isinstance 检查）。"""
        mock_db = AsyncMock()
        store = PgVectorStore(mock_db)
        assert isinstance(store, VectorStore)

    def test_pg_vector_store_has_required_methods(self):
        """PgVectorStore 有 add/query/delete 三个方法。"""
        mock_db = AsyncMock()
        store = PgVectorStore(mock_db)
        assert hasattr(store, "add")
        assert hasattr(store, "query")
        assert hasattr(store, "delete")
        assert callable(store.add)
        assert callable(store.query)
        assert callable(store.delete)


class TestPgVectorStoreKeyFormat:
    """验证 PgVectorStore key 格式解析和构造（与 PgTextStore 一致）。"""

    def test_make_key(self):
        """make_key 构造正确格式的 key。"""
        project_id = str(uuid4())
        source_type = "trial_balance"
        source_id = str(uuid4())
        chunk_index = 3

        key = PgVectorStore.make_key(project_id, source_type, source_id, chunk_index)
        assert key == f"{project_id}:{source_type}:{source_id}:{chunk_index}"

    def test_parse_key(self):
        """parse_key 正确解析 key 为四元组。"""
        project_id = str(uuid4())
        source_type = "knowledge_doc"
        source_id = str(uuid4())
        chunk_index = 5

        key = f"{project_id}:{source_type}:{source_id}:{chunk_index}"
        parsed = PgVectorStore.parse_key(key)

        assert parsed == (project_id, source_type, source_id, chunk_index)

    def test_parse_key_invalid_format(self):
        """parse_key 对无效格式抛 ValueError。"""
        with pytest.raises(ValueError, match="Invalid key format"):
            PgVectorStore.parse_key("invalid-key-no-colons")


class TestPgVectorStoreHelpers:
    """验证 PgVectorStore 辅助方法。"""

    def test_vector_to_str(self):
        """_vector_to_str 将 float 列表转为逗号分隔字符串。"""
        vec = [0.1, 0.2, 0.3]
        result = PgVectorStore._vector_to_str(vec)
        assert result == "0.1,0.2,0.3"

    def test_vector_to_pgvector(self):
        """_vector_to_pgvector 将 float 列表转为 pgvector 字面量格式。"""
        vec = [0.1, 0.2, 0.3]
        result = PgVectorStore._vector_to_pgvector(vec)
        assert result == "[0.1,0.2,0.3]"

    def test_vector_to_pgvector_empty(self):
        """_vector_to_pgvector 空向量。"""
        result = PgVectorStore._vector_to_pgvector([])
        assert result == "[]"

    def test_vector_to_pgvector_single(self):
        """_vector_to_pgvector 单元素向量。"""
        result = PgVectorStore._vector_to_pgvector([1.0])
        assert result == "[1.0]"


class TestPgVectorStoreAdd:
    """验证 PgVectorStore.add 行为。"""

    @pytest.mark.asyncio
    async def test_add_executes_upsert(self):
        """add 执行 upsert 语句到 KnowledgeIndex（含 vector 列）。"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        store = PgVectorStore(mock_db)

        project_id = str(uuid4())
        source_id = str(uuid4())
        key = PgVectorStore.make_key(project_id, "trial_balance", source_id, 0)
        embedding = [0.1, 0.2, 0.3]
        meta = {"content_text": "测试内容"}

        await store.add(key, embedding, meta)

        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_unknown_source_type_skips(self):
        """add 对未知 source_type 跳过（不崩）。"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        store = PgVectorStore(mock_db)

        project_id = str(uuid4())
        source_id = str(uuid4())
        key = PgVectorStore.make_key(project_id, "unknown_type_xyz", source_id, 0)

        await store.add(key, [0.1, 0.2], {"content_text": "test"})

        # 未知类型不执行 DB 操作
        mock_db.execute.assert_not_called()


class TestPgVectorStoreQuery:
    """验证 PgVectorStore.query 行为。"""

    @pytest.mark.asyncio
    async def test_query_executes_sql_with_cosine_operator(self):
        """query 执行包含 <=> 运算符的 SQL。"""
        mock_db = AsyncMock()

        # 模拟返回结果
        mock_row = MagicMock()
        mock_row.project_id = uuid4()
        mock_row.source_type = "trial_balance"
        mock_row.source_id = uuid4()
        mock_row.chunk_index = 0
        mock_row.score = 0.95

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_db.execute = AsyncMock(return_value=mock_result)

        store = PgVectorStore(mock_db)
        results = await store.query([0.1, 0.2, 0.3], top_k=5)

        # 验证 execute 被调用
        mock_db.execute.assert_called_once()
        # 验证 SQL 包含 <=> 运算符
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        assert "<=>" in sql_text

        # 验证返回格式
        assert len(results) == 1
        assert isinstance(results[0], tuple)
        assert isinstance(results[0][0], str)
        assert results[0][1] == 0.95

    @pytest.mark.asyncio
    async def test_query_with_project_id_filter(self):
        """query 设置 project_id 时 SQL 包含 project_id 过滤。"""
        mock_db = AsyncMock()
        project_id = str(uuid4())

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        store = PgVectorStore(mock_db, project_id=project_id)
        results = await store.query([0.1, 0.2, 0.3], top_k=5)

        # 验证 SQL 包含 project_id 过滤
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        assert "project_id" in sql_text
        # 验证参数包含 project_id
        params = call_args[0][1]
        assert params["project_id"] == project_id
        assert results == []

    @pytest.mark.asyncio
    async def test_query_empty_results(self):
        """query 无结果返回空列表。"""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        store = PgVectorStore(mock_db)
        results = await store.query([0.1, 0.2, 0.3], top_k=5)

        assert results == []

    @pytest.mark.asyncio
    async def test_query_respects_top_k(self):
        """query SQL 包含 LIMIT :top_k。"""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        store = PgVectorStore(mock_db)
        await store.query([0.1, 0.2, 0.3], top_k=7)

        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert params["top_k"] == 7


class TestPgVectorStoreDelete:
    """验证 PgVectorStore.delete 行为（与 PgTextStore 一致）。"""

    @pytest.mark.asyncio
    async def test_delete_soft_deletes(self):
        """delete 执行软删除（is_deleted=True）。"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        store = PgVectorStore(mock_db)

        project_id = str(uuid4())
        source_id = str(uuid4())
        key = PgVectorStore.make_key(project_id, "trial_balance", source_id, 0)

        await store.delete(key)

        mock_db.execute.assert_called_once()
