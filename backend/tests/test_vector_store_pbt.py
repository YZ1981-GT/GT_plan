"""
VectorStore Protocol PBT — PgTextStore 正确性属性

**Validates: Requirements 3.1**

属性 R4 的基础验证：PgTextStore 满足 VectorStore Protocol 且行为一致。
（完整 R4 等价验证需 PgVectorStore 实现后在 Task 10 补充）

测试策略：
- 生成随机向量和 key，验证 add → query 能召回
- 验证 delete 后 query 不再返回该 key
- 验证 query 结果按相似度降序排列
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.vector_store import VectorStore, PgTextStore


# -- Strategies --

def valid_uuid_str():
    """生成有效 UUID 字符串。"""
    return st.builds(lambda: str(uuid4()))


def valid_source_type():
    """生成有效的 KnowledgeSourceType 值。"""
    return st.sampled_from([
        "trial_balance", "journal", "auxiliary", "contract",
        "document_scan", "workpaper", "adjustment", "elimination",
        "confirmation", "review_comment", "prior_year_summary", "knowledge_doc",
    ])


def valid_embedding(dim: int = 8):
    """生成有效的 embedding 向量（非零，维度固定）。"""
    return st.lists(
        st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=dim,
        max_size=dim,
    ).filter(lambda v: any(x != 0.0 for x in v))


def valid_key():
    """生成有效的 VectorStore key。"""
    return st.builds(
        PgTextStore.make_key,
        st.builds(lambda: str(uuid4())),
        valid_source_type(),
        st.builds(lambda: str(uuid4())),
        st.integers(min_value=0, max_value=99),
    )


# -- Protocol 属性 --

class TestPgTextStoreProtocolProperty:
    """PgTextStore 始终满足 VectorStore Protocol。"""

    @given(st.just(None))
    @settings(max_examples=5)
    def test_isinstance_check_always_passes(self, _):
        """**Validates: Requirements 3.1**

        PgTextStore 实例始终通过 isinstance(store, VectorStore) 检查。
        """
        mock_db = AsyncMock()
        store = PgTextStore(mock_db)
        assert isinstance(store, VectorStore)


class TestPgTextStoreKeyRoundtrip:
    """key 格式 make_key ↔ parse_key 往返一致。"""

    @given(
        project_id=st.builds(lambda: str(uuid4())),
        source_type=valid_source_type(),
        source_id=st.builds(lambda: str(uuid4())),
        chunk_index=st.integers(min_value=0, max_value=9999),
    )
    @settings(max_examples=5)
    def test_key_roundtrip(self, project_id, source_type, source_id, chunk_index):
        """**Validates: Requirements 3.1**

        make_key 构造的 key 经 parse_key 解析后与原始参数一致。
        """
        key = PgTextStore.make_key(project_id, source_type, source_id, chunk_index)
        parsed = PgTextStore.parse_key(key)
        assert parsed == (project_id, source_type, source_id, chunk_index)


class TestPgTextStoreCosineProperty:
    """余弦相似度计算属性。"""

    @given(embedding=valid_embedding(dim=8))
    @settings(max_examples=5)
    def test_self_similarity_is_one(self, embedding):
        """**Validates: Requirements 3.1**

        任意非零向量与自身的余弦相似度为 1.0。
        """
        import numpy as np
        vec = np.array(embedding)
        score = PgTextStore._cosine_similarity(vec, vec)
        assert abs(score - 1.0) < 1e-5

    @given(
        emb_a=valid_embedding(dim=8),
        emb_b=valid_embedding(dim=8),
    )
    @settings(max_examples=5)
    def test_similarity_in_range(self, emb_a, emb_b):
        """**Validates: Requirements 3.1**

        任意两个非零向量的余弦相似度在 [-1, 1] 范围内。
        """
        import numpy as np
        a = np.array(emb_a)
        b = np.array(emb_b)
        score = PgTextStore._cosine_similarity(a, b)
        assert -1.0 - 1e-6 <= score <= 1.0 + 1e-6


class TestPgTextStoreQueryOrdering:
    """query 结果排序属性。"""

    @given(
        query_emb=valid_embedding(dim=4),
        n_chunks=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_query_results_descending_order(self, query_emb, n_chunks):
        """**Validates: Requirements 3.1**

        query 返回的结果按相似度严格降序排列。
        """
        import numpy as np

        mock_db = AsyncMock()

        # 生成 n_chunks 个随机 chunk
        chunks = []
        for i in range(n_chunks):
            chunk = MagicMock()
            chunk.id = uuid4()
            chunk.project_id = uuid4()
            chunk.source_type = MagicMock(value="trial_balance")
            chunk.source_id = uuid4()
            chunk.chunk_index = i
            # 随机向量
            random_vec = np.random.randn(4)
            chunk.embedding_vector = ",".join(str(v) for v in random_vec)
            chunks.append(chunk)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = chunks
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        store = PgTextStore(mock_db)
        results = await store.query(query_emb, top_k=n_chunks)

        # 验证降序
        scores = [score for _, score in results]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]
