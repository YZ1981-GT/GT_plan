"""
Property-Based Test: 阶段 2 综合 PBT — R1 召回降级 + R2 权限隔离 + R3 联动幂等

**Validates: Requirements 5.2**

属性 R1：向量召回失败时 semantic_search 降级 ilike 返回非空（双保险不崩）
属性 R2：semantic_search 带 user 时只返回该 user 有权访问的知识文件
属性 R3：同一 KnowledgeDocument 多次 incremental_update 向量索引收敛一致（幂等可重建）

附加：ai_chat_service 既有行为零回归（C 现有消费方调用 search 无 scope/user）
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.knowledge_index_service import KnowledgeIndexService, _chunk_text
from app.models.ai_models import KnowledgeSourceType


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def uuid_strategy(draw):
    """生成有效 UUID。"""
    return UUID(int=draw(st.integers(min_value=1, max_value=2**128 - 1)))


@st.composite
def query_strategy(draw):
    """生成非空查询字符串（中英文混合）。"""
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


@st.composite
def content_strategy(draw):
    """生成非空文档内容（用于 R3 幂等测试）。"""
    text = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=10,
        max_size=200,
    ))
    return text.strip() or "默认内容"


@st.composite
def repeat_count_strategy(draw):
    """生成重复调用次数（2~5 次）。"""
    return draw(st.integers(min_value=2, max_value=5))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ===========================================================================
# R1: 召回降级 — 向量失败时 ilike 兜底
# ===========================================================================

class TestR1RecallFallback:
    """PBT R1: 向量召回失败时降级 ilike 返回非空

    **Validates: Requirements 5.2**
    属性: R1
    """

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        query=query_strategy(),
        scope=scope_strategy(),
    )
    @pytest.mark.asyncio
    async def test_fallback_returns_results_when_matching_content_exists(
        self, project_id: UUID, query: str, scope: str
    ):
        """
        R1: embedding 服务不可用时，semantic_search 降级 ilike，
        若数据库中存在匹配内容则返回非空结果。

        **Validates: Requirements 5.2**
        """
        mock_db = AsyncMock()

        matching_chunk = _make_chunk(
            KnowledgeSourceType.trial_balance,
            f"包含查询 {query} 的内容",
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [matching_chunk]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)

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

        # R1: 降级后返回非空
        assert len(results) > 0
        # ilike 降级时 score 为 0.0
        assert results[0]["score"] == 0.0

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        query=query_strategy(),
        scope=scope_strategy(),
    )
    @pytest.mark.asyncio
    async def test_fallback_never_raises(
        self, project_id: UUID, query: str, scope: str
    ):
        """
        R1 补充: 无论向量/ilike 是否有匹配，semantic_search 绝不抛异常。

        **Validates: Requirements 5.2**
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

            results = await service.semantic_search(
                project_id=project_id,
                query=query,
                top_k=10,
                scope=scope,
            )

        assert isinstance(results, list)


# ===========================================================================
# R2: 权限隔离 — 只返回 user 有权访问的知识文件
# ===========================================================================

class TestR2PermissionIsolation:
    """PBT R2: semantic_search 带 user 时只返回有权访问的知识文件

    **Validates: Requirements 5.2**
    属性: R2
    """

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_private_docs_invisible_to_non_owner(self, project_id: UUID):
        """
        R2: private 文档只对创建者可见，其他用户看不到。

        **Validates: Requirements 5.2**
        """
        mock_db = AsyncMock()
        owner_id = uuid4()
        other_user_id = uuid4()

        doc_chunk = _make_chunk(KnowledgeSourceType.knowledge_doc, "私有文档")

        # 向量搜索返回该 chunk
        mock_vector_result = MagicMock()
        mock_vector_scalars = MagicMock()
        mock_vector_scalars.all.return_value = [doc_chunk]
        mock_vector_result.scalars.return_value = mock_vector_scalars

        # 权限查询返回 private + owner
        mock_perm_row = (
            doc_chunk.source_id,
            MagicMock(value="private"),
            None,
            owner_id,
            MagicMock(value="public"),
            None,
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

        other_user = MagicMock()
        other_user.id = other_user_id

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            results = await service.semantic_search(
                project_id=project_id,
                query="文档",
                top_k=10,
                scope="knowledge_doc",
                user=other_user,
            )

        # R2: 非创建者看不到 private 文档
        assert len(results) == 0

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_public_docs_visible_to_any_user(self, project_id: UUID):
        """
        R2: public 文档对所有用户可见。

        **Validates: Requirements 5.2**
        """
        mock_db = AsyncMock()

        doc_chunk = _make_chunk(KnowledgeSourceType.knowledge_doc, "公开文档")

        mock_vector_result = MagicMock()
        mock_vector_scalars = MagicMock()
        mock_vector_scalars.all.return_value = [doc_chunk]
        mock_vector_result.scalars.return_value = mock_vector_scalars

        mock_perm_row = (
            doc_chunk.source_id,
            MagicMock(value="public"),
            None,
            uuid4(),
            MagicMock(value="public"),
            None,
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

        any_user = MagicMock()
        any_user.id = uuid4()

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            results = await service.semantic_search(
                project_id=project_id,
                query="文档",
                top_k=10,
                scope="knowledge_doc",
                user=any_user,
            )

        # R2: public 文档对所有用户可见
        assert len(results) == 1
        assert results[0]["content"] == "公开文档"


# ===========================================================================
# R3: 联动幂等 — 同一文档多次 incremental_update 收敛一致
# ===========================================================================

class TestR3IdempotentUpdate:
    """PBT R3: 同一 KnowledgeDocument 多次 incremental_update 向量索引收敛一致

    **Validates: Requirements 5.2**
    属性: R3
    """

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        doc_id=uuid_strategy(),
        content=content_strategy(),
        repeat_count=repeat_count_strategy(),
    )
    @pytest.mark.asyncio
    async def test_multiple_updates_same_content_converge(
        self, project_id: UUID, doc_id: UUID, content: str, repeat_count: int
    ):
        """
        R3: 同一文档同一内容多次 incremental_update，
        每次产生的 chunk 数量和内容完全一致（upsert 幂等）。

        **Validates: Requirements 5.2**
        """
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        service = KnowledgeIndexService(mock_db)

        # 固定 embedding 返回值确保确定性
        fixed_embedding = [0.1] * 768

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = fixed_embedding

            # 多次调用 incremental_update
            for _ in range(repeat_count):
                mock_db.execute.reset_mock()
                mock_db.commit.reset_mock()

                await service.incremental_update(
                    project_id=project_id,
                    source_type="knowledge_doc",
                    source_id=doc_id,
                    content=content,
                )

        # R3 验证：chunk 分割确定性
        expected_chunks = _chunk_text(content)
        expected_chunk_count = len(expected_chunks)

        # 每次 incremental_update 调用 embedding 次数 = chunk 数
        # 总调用次数 = repeat_count * expected_chunk_count
        assert mock_embed.call_count == repeat_count * expected_chunk_count

        # 每次调用的 embedding 输入相同（同一 content 分割结果一致）
        if expected_chunk_count > 0:
            # 取第一轮和最后一轮的 embedding 调用参数
            first_round_args = [
                mock_embed.call_args_list[i][0][0]
                for i in range(expected_chunk_count)
            ]
            last_round_start = (repeat_count - 1) * expected_chunk_count
            last_round_args = [
                mock_embed.call_args_list[last_round_start + i][0][0]
                for i in range(expected_chunk_count)
            ]
            # 幂等：每轮输入完全一致
            assert first_round_args == last_round_args

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        doc_id=uuid_strategy(),
        content=content_strategy(),
    )
    @pytest.mark.asyncio
    async def test_chunk_determinism(
        self, project_id: UUID, doc_id: UUID, content: str
    ):
        """
        R3 补充: _chunk_text 对同一内容多次调用结果完全一致（纯函数确定性）。

        **Validates: Requirements 5.2**
        """
        chunks_1 = _chunk_text(content)
        chunks_2 = _chunk_text(content)
        chunks_3 = _chunk_text(content)

        # 纯函数：同输入同输出
        assert chunks_1 == chunks_2
        assert chunks_2 == chunks_3

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        doc_id=uuid_strategy(),
        content=content_strategy(),
    )
    @pytest.mark.asyncio
    async def test_upsert_uses_consistent_chunk_index(
        self, project_id: UUID, doc_id: UUID, content: str
    ):
        """
        R3 补充: incremental_update 使用 (project_id, source_id, chunk_index) 作为
        upsert 键，确保重复调用覆盖而非追加。

        **Validates: Requirements 5.2**
        """
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        service = KnowledgeIndexService(mock_db)

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.1] * 768

            # 第一次调用
            await service.incremental_update(
                project_id=project_id,
                source_type="knowledge_doc",
                source_id=doc_id,
                content=content,
            )

            first_call_count = mock_db.execute.call_count

            # 第二次调用（同内容）
            await service.incremental_update(
                project_id=project_id,
                source_type="knowledge_doc",
                source_id=doc_id,
                content=content,
            )

            second_call_count = mock_db.execute.call_count - first_call_count

        # 两次调用产生相同数量的 DB 操作（upsert 次数一致）
        assert first_call_count == second_call_count


# ===========================================================================
# ai_chat_service 零回归：C 现有消费方调用 search 无 scope/user
# ===========================================================================

class TestAIChatServiceRegression:
    """ai_chat_service 既有行为零回归 — 调用 search() 无 scope/user 参数

    **Validates: Requirements 5.2**
    NFR-1: ai_chat_service（C 现有消费方）行为不变
    """

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        query=query_strategy(),
    )
    @pytest.mark.asyncio
    async def test_search_alias_works_without_scope_user(
        self, project_id: UUID, query: str
    ):
        """
        零回归: ai_chat_service 调用 service.search(project_id, query)
        等价于 semantic_search(project_id, query, top_k=10, scope='all', user=None)。

        **Validates: Requirements 5.2**
        """
        mock_db = AsyncMock()

        chunk = _make_chunk(KnowledgeSourceType.trial_balance, f"业务数据 {query}")
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [chunk]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            # ai_chat_service 的调用方式：search(project_id, query)
            results = await service.search(
                project_id=project_id,
                query=query,
                top_k=10,
            )

        # 零回归：返回所有类型（scope=all），无权限过滤（user=None）
        assert len(results) == 1
        assert results[0]["source_type"] == "trial_balance"

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        query=query_strategy(),
    )
    @pytest.mark.asyncio
    async def test_search_without_user_returns_knowledge_docs_unfiltered(
        self, project_id: UUID, query: str
    ):
        """
        零回归: 无 user 时 knowledge_doc 类型结果也不被过滤。

        **Validates: Requirements 5.2**
        """
        mock_db = AsyncMock()

        doc_chunk = _make_chunk(KnowledgeSourceType.knowledge_doc, f"知识文档 {query}")
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [doc_chunk]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = [0.5] * 768

            # 无 user 参数
            results = await service.search(
                project_id=project_id,
                query=query,
                top_k=10,
            )

        # 零回归：knowledge_doc 也返回（无权限过滤）
        assert len(results) == 1
        assert results[0]["source_type"] == "knowledge_doc"
