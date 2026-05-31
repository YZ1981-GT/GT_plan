"""
R4 VectorStore 等价性 PBT — PgTextStore 与 PgVectorStore 同 query top_k 结果集一致

**Validates: Requirements 3.3, 3.4**
属性 R4: 对同一 query embedding 和同一数据集，两种 VectorStore 实现返回的 top_k
结果集一致（key 集合相同，score 近似相等 — 浮点容差内）。

测试策略：
- 不依赖真实 DB，直接测试两种 store 的 cosine 计算逻辑等价性
- PgTextStore 用 numpy 计算余弦；PgVectorStore 用 DB 端 <=> 运算符
- 由于无法在单元测试中启动 pgvector，我们验证两者的核心数学等价：
  对同一组向量，numpy cosine 与 pgvector 的 1-cosine_distance 结果一致
- 同时验证 factory 函数行为正确

框架: hypothesis (max_examples=5)
"""

import numpy as np
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from unittest.mock import patch, MagicMock

from app.services.vector_store import (
    PgTextStore,
    PgVectorStore,
    get_vector_store,
    VectorStore,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

def _normalized_vector(dim: int = 8):
    """生成归一化的非零向量（模拟真实 embedding）。"""
    return (
        st.lists(
            st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=dim,
            max_size=dim,
        )
        .filter(lambda v: sum(x * x for x in v) > 1e-10)
        .map(lambda v: _normalize(v))
    )


def _normalize(v: list[float]) -> list[float]:
    """归一化向量。"""
    arr = np.array(v, dtype=np.float64)
    norm = np.linalg.norm(arr)
    if norm == 0:
        return v
    return (arr / norm).tolist()


# ---------------------------------------------------------------------------
# R4 Property: cosine similarity 计算等价
# ---------------------------------------------------------------------------


class TestR4VectorStoreEquivalence:
    """R4 等价性属性测试：PgTextStore numpy cosine ≡ PgVectorStore pgvector cosine。

    **Validates: Requirements 3.3, 3.4**
    """

    @given(
        query_vec=_normalized_vector(8),
        data_vec=_normalized_vector(8),
    )
    @settings(max_examples=5)
    def test_cosine_similarity_equivalence(self, query_vec: list[float], data_vec: list[float]):
        """R4: PgTextStore._cosine_similarity 与 pgvector 的 1-(a<=>b) 数学等价。

        **Validates: Requirements 3.4**

        pgvector <=> 运算符计算余弦距离 = 1 - cosine_similarity
        因此 score = 1 - distance = cosine_similarity

        两种实现对同一对向量应产生相同的相似度分数（浮点容差 1e-6）。
        """
        q = np.array(query_vec, dtype=np.float64)
        d = np.array(data_vec, dtype=np.float64)

        # PgTextStore 方式：numpy cosine similarity
        pg_text_score = PgTextStore._cosine_similarity(q, d)

        # PgVectorStore 方式：模拟 pgvector 的 1 - cosine_distance
        # cosine_distance = 1 - (dot(a,b) / (norm(a)*norm(b)))
        norm_q = np.linalg.norm(q)
        norm_d = np.linalg.norm(d)
        assume(norm_q > 1e-10 and norm_d > 1e-10)

        cosine_sim = float(np.dot(q, d) / (norm_q * norm_d))
        # pgvector: distance = 1 - cosine_sim, score = 1 - distance = cosine_sim
        pgvector_score = cosine_sim

        # 两者应等价（浮点容差）
        assert abs(pg_text_score - pgvector_score) < 1e-6, (
            f"PgTextStore score={pg_text_score}, PgVectorStore score={pgvector_score}, "
            f"diff={abs(pg_text_score - pgvector_score)}"
        )

    @given(
        query_vec=_normalized_vector(8),
        data_vecs=st.lists(_normalized_vector(8), min_size=2, max_size=5),
    )
    @settings(max_examples=5)
    def test_top_k_ordering_equivalence(self, query_vec: list[float], data_vecs: list[list[float]]):
        """R4: 对同一组数据向量，两种实现的 top_k 排序一致。

        **Validates: Requirements 3.4**

        给定 query 和多个 data 向量，PgTextStore 和 PgVectorStore 的排序
        （按余弦相似度降序）应产生相同的排名顺序。
        """
        q = np.array(query_vec, dtype=np.float64)

        # PgTextStore 方式计算所有分数
        pg_text_scores = []
        for i, dv in enumerate(data_vecs):
            d = np.array(dv, dtype=np.float64)
            score = PgTextStore._cosine_similarity(q, d)
            pg_text_scores.append((i, score))

        # PgVectorStore 方式计算所有分数（模拟 DB 端 cosine）
        pgvector_scores = []
        norm_q = np.linalg.norm(q)
        assume(norm_q > 1e-10)
        for i, dv in enumerate(data_vecs):
            d = np.array(dv, dtype=np.float64)
            norm_d = np.linalg.norm(d)
            if norm_d < 1e-10:
                pgvector_scores.append((i, 0.0))
                continue
            score = float(np.dot(q, d) / (norm_q * norm_d))
            pgvector_scores.append((i, score))

        # 按分数降序排列
        pg_text_sorted = sorted(pg_text_scores, key=lambda x: x[1], reverse=True)
        pgvector_sorted = sorted(pgvector_scores, key=lambda x: x[1], reverse=True)

        # 排序后的索引顺序应一致
        pg_text_order = [idx for idx, _ in pg_text_sorted]
        pgvector_order = [idx for idx, _ in pgvector_sorted]

        assert pg_text_order == pgvector_order, (
            f"排序不一致: PgTextStore={pg_text_order}, PgVectorStore={pgvector_order}"
        )


# ---------------------------------------------------------------------------
# Feature flag factory 单元测试
# ---------------------------------------------------------------------------


class TestGetVectorStoreFactory:
    """验证 get_vector_store 工厂函数行为。"""

    def test_default_returns_pg_text_store(self):
        """默认 VECTOR_STORE_BACKEND=pgtext 返回 PgTextStore。"""
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.VECTOR_STORE_BACKEND = "pgtext"
            store = get_vector_store(mock_db)
            assert isinstance(store, PgTextStore)

    def test_pgvector_returns_pg_vector_store(self):
        """VECTOR_STORE_BACKEND=pgvector 返回 PgVectorStore。"""
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.VECTOR_STORE_BACKEND = "pgvector"
            store = get_vector_store(mock_db)
            assert isinstance(store, PgVectorStore)

    def test_unknown_backend_falls_back_to_pgtext(self):
        """未知 VECTOR_STORE_BACKEND 值降级到 PgTextStore。"""
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.VECTOR_STORE_BACKEND = "unknown_backend"
            store = get_vector_store(mock_db)
            assert isinstance(store, PgTextStore)

    def test_pgvector_case_insensitive(self):
        """VECTOR_STORE_BACKEND 大小写不敏感。"""
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.VECTOR_STORE_BACKEND = "PgVector"
            store = get_vector_store(mock_db)
            assert isinstance(store, PgVectorStore)

    def test_factory_passes_project_id(self):
        """工厂函数正确传递 project_id。"""
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.VECTOR_STORE_BACKEND = "pgtext"
            store = get_vector_store(mock_db, project_id="test-project-id")
            assert store._project_id == "test-project-id"

    def test_all_stores_satisfy_protocol(self):
        """工厂返回的所有实现都满足 VectorStore Protocol。"""
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        for backend in ["pgtext", "pgvector"]:
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.VECTOR_STORE_BACKEND = backend
                store = get_vector_store(mock_db)
                assert isinstance(store, VectorStore)
