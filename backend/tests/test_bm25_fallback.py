"""bm25s 单测 + 降级链 PBT — Task 15

测试环境：SQLite in-memory（KnowledgeIndex.content_text=Text,
embedding_vector=String(5000) 均 SQLite 兼容，无需 pg_only）。

Validates: Requirements 5.3
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.ai_models import KnowledgeIndex, KnowledgeSourceType
from app.models.base import Base
from app.services.knowledge_index_service import KnowledgeIndexService

# ---------------------------------------------------------------------------
# Fixtures: 真实 SQLite in-memory session（非 mock，供 BM25 落库查询）
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_ID = uuid.UUID("aaaaaaaa-1111-2222-3333-444444444444")

REQUIRED_KEYS = {"source_type", "source_id", "content", "score", "chunk_index"}


def _make_ki(content_text: str, source_type=KnowledgeSourceType.trial_balance, chunk_index=0):
    """构造 KnowledgeIndex 行。"""
    return KnowledgeIndex(
        id=uuid.uuid4(),
        project_id=_PROJECT_ID,
        source_type=source_type,
        source_id=uuid.uuid4(),
        content_text=content_text,
        embedding_vector=None,
        chunk_index=chunk_index,
        is_deleted=False,
    )


def _make_ki_with_pid(project_id, content_text: str, source_type=KnowledgeSourceType.trial_balance, chunk_index=0):
    """构造指定 project_id 的 KnowledgeIndex 行。"""
    return KnowledgeIndex(
        id=uuid.uuid4(),
        project_id=project_id,
        source_type=source_type,
        source_id=uuid.uuid4(),
        content_text=content_text,
        embedding_vector=None,
        chunk_index=chunk_index,
        is_deleted=False,
    )


# ---------------------------------------------------------------------------
# Test 1: BM25 召回非空且相关 doc 排前
# ---------------------------------------------------------------------------


class TestBm25FallbackRecall:
    """BM25 fallback 召回质量验证。"""

    @pytest.mark.asyncio
    async def test_bm25_recall_nonempty_and_relevant_ranked_first(self, db_session):
        """插入中文测试数据，BM25 召回应非空且最相关文档排第一。"""
        rows = [
            _make_ki("应收账款坏账准备明细表，本年计提比例调整说明"),
            _make_ki("银行存款余额调节表，本月未达账项汇总"),
            _make_ki("固定资产折旧计算表，按年限平均法计提折旧"),
        ]
        db_session.add_all(rows)
        await db_session.flush()

        service = KnowledgeIndexService(db_session)
        results = await service._bm25_fallback(
            project_id=_PROJECT_ID,
            query="坏账准备",
            top_k=3,
            scope="project_data",
        )

        # 非空
        assert len(results) > 0, "BM25 应至少召回 1 条结果"
        # 最相关文档排第一
        assert "坏账" in results[0]["content"], (
            f"最相关文档应含'坏账'，实际: {results[0]['content'][:30]}"
        )
        # 结构完整
        for r in results:
            assert REQUIRED_KEYS <= set(r.keys()), f"缺少字段: {REQUIRED_KEYS - set(r.keys())}"

    @pytest.mark.asyncio
    async def test_bm25_returns_meaningful_scores(self, db_session):
        """BM25 返回非零 score（优于 ilike 的 score=0.0）。"""
        from app.services.knowledge_index_service import _BM25_CACHE

        # 使用独立 project_id 避免缓存污染
        pid = uuid.UUID("bbbbbbbb-1111-2222-3333-444444444444")
        rows = [
            _make_ki_with_pid(pid, "应收票据 银行承兑汇票 商业承兑汇票 到期日管理"),
            _make_ki_with_pid(pid, "应付账款 供应商对账 账龄分析"),
            _make_ki_with_pid(pid, "固定资产折旧计算表 按年限平均法计提折旧"),
            _make_ki_with_pid(pid, "银行存款余额调节表 本月未达账项汇总"),
            _make_ki_with_pid(pid, "管理费用 差旅费 招待费 办公费明细"),
        ]
        db_session.add_all(rows)
        await db_session.flush()

        # 清除该 project 的 BM25 缓存
        _BM25_CACHE.pop((str(pid), "project_data"), None)

        service = KnowledgeIndexService(db_session)
        results = await service._bm25_fallback(
            project_id=pid,
            query="承兑汇票",
            top_k=5,
            scope="project_data",
        )

        assert len(results) > 0
        # 最高分文档 score > 0（BM25 真实分数，归一化后 top-1 = 1.0）
        assert results[0]["score"] > 0, f"BM25 top-1 score 应大于 0, got {results[0]['score']}"
        # 相关文档排前
        assert "承兑" in results[0]["content"]


# ---------------------------------------------------------------------------
# Test 2: BM25 beats ilike for certain queries
# ---------------------------------------------------------------------------


class TestBm25BeatsIlike:
    """构造 BM25 能召回但 ilike 同样能召回的场景，验证 BM25 提供非零 score。"""

    @pytest.mark.asyncio
    async def test_bm25_provides_score_advantage_over_ilike(self, db_session):
        """ilike 对所有匹配 score=0.0，BM25 有真实 TF-IDF 分数区分相关性。"""
        rows = [
            _make_ki("本年度应收账款坏账计提比例调整说明，按账龄分析法"),
            _make_ki("管理费用明细：差旅费、招待费、折旧费汇总"),
            _make_ki("存货跌价准备计提测试，原材料账面与可变现净值"),
        ]
        db_session.add_all(rows)
        await db_session.flush()

        service = KnowledgeIndexService(db_session)

        # BM25 检索
        bm25_results = await service._bm25_fallback(
            project_id=_PROJECT_ID,
            query="坏账计提",
            top_k=3,
            scope="project_data",
        )

        # ilike 检索（对比）
        ilike_results = await service._ilike_fallback(
            project_id=_PROJECT_ID,
            query="坏账计提",
            top_k=3,
            scope="project_data",
        )

        # BM25 有分数区分
        assert len(bm25_results) > 0
        assert bm25_results[0]["score"] > 0, "BM25 应给出非零分数"

        # ilike 所有 score == 0.0
        for r in ilike_results:
            assert r["score"] == 0.0, "ilike 应返回 score=0.0"


# ---------------------------------------------------------------------------
# Test 3: PBT - 降级链结构验证（向量失败 → BM25 返回合法结构）
# ---------------------------------------------------------------------------


class TestDegradationChainPBT:
    """PBT: mock _vector_search 抛异常，验证降级链返回合法结构。

    **Validates: Requirements 5.3**
    """

    @pytest.mark.asyncio
    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(query=st.text(min_size=1, max_size=20))
    async def test_vector_fail_bm25_returns_valid_structure(self, query, db_session):
        """向量失败时 BM25 降级路径返回合法 dict 结构。

        **Validates: Requirements 5.3**
        """
        # 确保有数据可检索
        row = _make_ki(f"测试文档内容 审计底稿 {query[:5]}")
        db_session.add(row)
        await db_session.flush()

        service = KnowledgeIndexService(db_session)

        # Mock _vector_search 抛异常
        with patch.object(service, "_vector_search", side_effect=Exception("embed 不可用")):
            results = await service.semantic_search(
                project_id=_PROJECT_ID,
                query=query,
                top_k=5,
                scope="project_data",
            )

        # 验证返回结构
        assert isinstance(results, list)
        for item in results:
            assert REQUIRED_KEYS <= set(item.keys()), f"缺字段: {REQUIRED_KEYS - set(item.keys())}"
            assert isinstance(item["score"], (int, float))
            assert item["score"] >= 0

    @pytest.mark.asyncio
    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(query=st.text(min_size=1, max_size=20))
    async def test_bm25_import_fail_falls_to_ilike(self, query, db_session):
        """bm25s import 失败时降级 ilike，仍返回合法结构（score=0.0）。

        **Validates: Requirements 5.3**
        """
        # 确保 ilike 能匹配到内容
        content = f"审计测试数据 {query[:3]}"
        row = _make_ki(content)
        db_session.add(row)
        await db_session.flush()

        service = KnowledgeIndexService(db_session)

        # Mock _vector_search 抛异常 + bm25s import 失败
        with patch.object(service, "_vector_search", side_effect=Exception("embed fail")):
            import builtins
            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "bm25s":
                    raise ImportError("mock bm25s not installed")
                return original_import(name, *args, **kwargs)

            with patch.object(builtins, "__import__", side_effect=mock_import):
                results = await service.semantic_search(
                    project_id=_PROJECT_ID,
                    query=query,
                    top_k=5,
                    scope="project_data",
                )

        # 验证返回结构
        assert isinstance(results, list)
        for item in results:
            assert REQUIRED_KEYS <= set(item.keys())
            assert item["score"] == 0.0, "ilike fallback score 应为 0.0"
