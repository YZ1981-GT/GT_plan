"""
Property-Based Test: semantic_search scope + 权限过滤 + ilike 降级 (R1, R2)

**Validates: Requirements 1.1, 4.1, 4.2**

属性 R1：向量召回失败时 semantic_search 降级 ilike 返回非空（双保险不崩）
属性 R2：semantic_search 带 user 时只返回该 user 有权访问的知识文件
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.knowledge_index_service import KnowledgeIndexService
from app.models.ai_models import KnowledgeSourceType


@st.composite
def uuid_strategy(draw):
    """生成有效 UUID。"""
    return UUID(int=draw(st.integers(min_value=0, max_value=2**128 - 1)))


@st.composite
def query_strategy(draw):
    """生成非空查询字符串。"""
    text = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=20,
    ))
    return text


@st.composite
def scope_strategy(draw):
    """生成有效 scope 值。"""
    return draw(st.sampled_from(["project_data", "knowledge_doc", "all"]))


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


def _make_chunk(source_type: KnowledgeSourceType, content: str, query: str = ""):
    """创建 mock KnowledgeIndex chunk，content 包含 query 以确保 ilike 匹配。"""
    chunk = MagicMock()
    chunk.id = uuid4()
    chunk.source_type = source_type
    chunk.source_id = uuid4()
    chunk.content_text = content
    chunk.chunk_index = 0
    chunk.embedding_vector = ",".join(["0.5"] * 768)
    return chunk


class TestIlikeFallbackProperty:
    """PBT R1: 向量召回失败时降级 ilike 返回非空"""

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        query=query_strategy(),
        scope=scope_strategy(),
    )
    @pytest.mark.asyncio
    async def test_ilike_fallback_returns_results_when_content_matches(
        self, project_id: UUID, query: str, scope: str
    ):
        """
        属性 R1：当向量召回失败（embedding 抛异常）且数据库中存在匹配内容时，
        semantic_search 降级 ilike 返回非空结果。

        **Validates: Requirements 1.1, 4.1**
        """
        mock_db = AsyncMock()

        # 创建包含 query 的 chunk（确保 ilike 能匹配）
        matching_chunk = _make_chunk(
            KnowledgeSourceType.trial_balance,
            f"包含查询内容 {query} 的文本",
            query,
        )

        # ilike fallback 查询返回匹配结果
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [matching_chunk]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)

        # 让 embedding 抛异常触发降级
        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.side_effect = RuntimeError("Embedding service unavailable")

            results = await service.semantic_search(
                project_id=project_id,
                query=query,
                top_k=10,
                scope=scope,
            )

        # R1: 降级 ilike 返回非空
        assert len(results) > 0
        assert results[0]["content"] == f"包含查询内容 {query} 的文本"
        # ilike 降级时 score 为 0.0
        assert results[0]["score"] == 0.0

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        query=query_strategy(),
    )
    @pytest.mark.asyncio
    async def test_ilike_fallback_never_crashes(
        self, project_id: UUID, query: str
    ):
        """
        属性 R1 补充：向量召回失败时 semantic_search 绝不崩溃，
        即使 ilike 也无匹配结果，返回空列表。

        **Validates: Requirements 4.1**
        """
        mock_db = AsyncMock()

        # ilike 也无匹配
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.side_effect = RuntimeError("Embedding service unavailable")

            # 不崩溃，返回空列表
            results = await service.semantic_search(
                project_id=project_id,
                query=query,
                top_k=10,
            )

        assert isinstance(results, list)


class TestPermissionFilterProperty:
    """PBT R2: 权限隔离 — 只返回 user 有权访问的知识文件"""

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_private_docs_filtered_for_non_owner(self, project_id: UUID):
        """
        属性 R2：private 文档只对创建者可见，其他用户看不到。

        **Validates: Requirements 4.2**
        """
        mock_db = AsyncMock()
        owner_id = uuid4()
        other_user_id = uuid4()

        # 创建 knowledge_doc chunk
        doc_chunk = _make_chunk(
            KnowledgeSourceType.knowledge_doc,
            "私有知识文档内容",
        )

        # 向量搜索返回该 chunk
        mock_vector_result = MagicMock()
        mock_vector_scalars = MagicMock()
        mock_vector_scalars.all.return_value = [doc_chunk]
        mock_vector_result.scalars.return_value = mock_vector_scalars

        # 权限查询返回 private + owner
        mock_perm_row = (
            doc_chunk.source_id,  # source_id
            MagicMock(value="private"),  # doc access_level
            None,  # doc project_ids
            owner_id,  # created_by
            MagicMock(value="public"),  # folder access_level
            None,  # folder project_ids
        )
        mock_perm_result = MagicMock()
        mock_perm_result.all.return_value = [mock_perm_row]

        call_count = [0]

        async def execute_side_effect(stmt, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # 第一次：向量搜索查 KnowledgeIndex
                return mock_vector_result
            else:
                # 第二次：权限查询
                return mock_perm_result

        mock_db.execute = execute_side_effect

        service = KnowledgeIndexService(mock_db)

        # 非创建者用户
        other_user = MagicMock()
        other_user.id = other_user_id

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            results = await service.semantic_search(
                project_id=project_id,
                query="知识文档",
                top_k=10,
                scope="knowledge_doc",
                user=other_user,
            )

        # R2: 非创建者看不到 private 文档
        assert len(results) == 0

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_public_docs_visible_to_all_users(self, project_id: UUID):
        """
        属性 R2：public 文档对所有用户可见。

        **Validates: Requirements 4.2**
        """
        mock_db = AsyncMock()

        # 创建 knowledge_doc chunk
        doc_chunk = _make_chunk(
            KnowledgeSourceType.knowledge_doc,
            "公开知识文档内容",
        )

        # 向量搜索返回该 chunk
        mock_vector_result = MagicMock()
        mock_vector_scalars = MagicMock()
        mock_vector_scalars.all.return_value = [doc_chunk]
        mock_vector_result.scalars.return_value = mock_vector_scalars

        # 权限查询返回 public
        mock_perm_row = (
            doc_chunk.source_id,  # source_id
            MagicMock(value="public"),  # doc access_level
            None,  # doc project_ids
            uuid4(),  # created_by
            MagicMock(value="public"),  # folder access_level
            None,  # folder project_ids
        )
        mock_perm_result = MagicMock()
        mock_perm_result.all.return_value = [mock_perm_row]

        call_count = [0]

        async def execute_side_effect(stmt, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_vector_result
            else:
                return mock_perm_result

        mock_db.execute = execute_side_effect

        service = KnowledgeIndexService(mock_db)

        # 任意用户
        any_user = MagicMock()
        any_user.id = uuid4()

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            results = await service.semantic_search(
                project_id=project_id,
                query="知识文档",
                top_k=10,
                scope="knowledge_doc",
                user=any_user,
            )

        # R2: public 文档对所有用户可见
        assert len(results) == 1
        assert results[0]["content"] == "公开知识文档内容"

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_non_doc_results_not_filtered(self, project_id: UUID):
        """
        属性 R2 补充：非 knowledge_doc 类型结果不受权限过滤影响。

        **Validates: Requirements 4.2**
        """
        mock_db = AsyncMock()

        # 创建业务数据 chunk（非 knowledge_doc）
        biz_chunk = _make_chunk(
            KnowledgeSourceType.trial_balance,
            "试算表业务数据",
        )

        # 向量搜索返回业务数据 chunk
        mock_vector_result = MagicMock()
        mock_vector_scalars = MagicMock()
        mock_vector_scalars.all.return_value = [biz_chunk]
        mock_vector_result.scalars.return_value = mock_vector_scalars
        mock_db.execute = AsyncMock(return_value=mock_vector_result)

        service = KnowledgeIndexService(mock_db)

        # 带 user 调用
        user = MagicMock()
        user.id = uuid4()

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            results = await service.semantic_search(
                project_id=project_id,
                query="试算表",
                top_k=10,
                scope="project_data",
                user=user,
            )

        # 非 knowledge_doc 不过滤，直接返回
        assert len(results) == 1
        assert results[0]["source_type"] == "trial_balance"
