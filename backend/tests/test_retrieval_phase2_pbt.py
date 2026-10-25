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
from tests._kb_mock_session import make_retrieval_session


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
# R1: 召回降级 — 向量失败时每种 scope 都有对应的兜底来源
#
# spec knowledge-base-retrieval-and-authz-closure Req 4.2：knowledge_doc 部分只用文档正文
# 词法层（不再从索引分块兜底）；project_data 部分沿用 BM25 / ILIKE。
# ===========================================================================


def _doc_hit(content: str, doc_id: UUID | None = None):
    """构造一条文档词法层命中（DocHit），供 patch ``_doc_search.search`` 使用。"""
    from app.services.knowledge_access_policy import KnowledgeResource
    from app.services.knowledge_doc_search import DocHit, DocMeta
    from app.models.knowledge_models import KnowledgeAccessLevel

    public = KnowledgeResource(
        access_level=KnowledgeAccessLevel.public, project_ids=frozenset(), created_by=None
    )
    meta = DocMeta(
        doc_id=doc_id or uuid4(), folder_id=uuid4(), name="准则.md", file_type="md",
        file_size=len(content), version=1, tags=(), created_by=None, created_at=None,
        updated_at=None, document=public, folder=public,
    )
    return DocHit(meta=meta, score=0.9, snippet=content, chunk_index=0, matched_terms=())


def _doc_meta(doc_id: UUID, name: str = "文档.md"):
    import dataclasses

    return dataclasses.replace(_doc_hit("x", doc_id).meta, name=name)


class TestR1RecallFallback:
    """PBT R1: 向量召回失败时降级，且 scope 决定兜底来源

    **Validates: Requirements 5.2 / spec knowledge-base-retrieval-and-authz-closure 4.2**
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
        mock_db = make_retrieval_session()
        business_chunk = _make_chunk(KnowledgeSourceType.trial_balance, f"包含查询 {query} 的内容")
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[business_chunk]))
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)
        doc = _doc_hit(f"知识文档 {query}")

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed, patch.object(
            service._doc_search, "search", new_callable=AsyncMock, return_value=[doc]
        ) as mock_doc_search:
            mock_embed.side_effect = RuntimeError("Embedding service unavailable")

            results = await service.semantic_search(
                project_id=project_id, query=query, top_k=10, scope=scope,
            )

        retrievals = {r["retrieval"] for r in results}
        source_types = {r["source_type"] for r in results}
        assert results, "向量失败后任何 scope 都必须有兜底命中"
        if scope in ("knowledge_doc", "all"):
            mock_doc_search.assert_awaited()
            assert "lexical" in retrievals and "knowledge_doc" in source_types
        else:
            mock_doc_search.assert_not_awaited()
        if scope in ("project_data", "all"):
            assert "trial_balance" in source_types
            assert retrievals & {"bm25", "ilike"}
        else:
            # knowledge_doc：索引分块不再参与兜底（它是文档正文的旧副本）
            assert "trial_balance" not in source_types

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
        """R1 补充: 向量、词法、兜底全部失败时 semantic_search 也不抛异常（返回空列表）。"""
        from app.services import knowledge_index_service as kis

        # BM25 进程级缓存（TTL 60s）会把上一例的命中带进来 —— 本例要看的是「全部失败」
        kis._BM25_CACHE.clear()
        mock_db = make_retrieval_session()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB down"))

        service = KnowledgeIndexService(mock_db)

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.side_effect = RuntimeError("Embedding service unavailable")

            results = await service.semantic_search(
                project_id=project_id, query=query, top_k=10, scope=scope,
            )

        assert results == []


# ===========================================================================
# R2: 权限隔离 — 向量层的 knowledge_doc 命中必须经单一判定面
# ===========================================================================

class TestR2PermissionIsolation:
    """PBT R2: 向量命中按 ``visible_documents``（KnowledgeAccessPolicy.can_retrieve）过滤

    判定本身由 test_knowledge_retrieval_visibility_pbt 全组合穷举、并在真库验证；
    这里钉住「内核真的用判定结果裁剪了向量命中」。
    """

    async def _run(self, project_id: UUID, visible: dict, user):
        mock_db = make_retrieval_session()
        doc_chunk = _make_chunk(KnowledgeSourceType.knowledge_doc, "文档片段")
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[doc_chunk]))
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        service = KnowledgeIndexService(mock_db)
        visible_map = {doc_chunk.source_id: _doc_meta(doc_chunk.source_id, "可见文档.md")} if visible else {}

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock, return_value=[0.5] * 768
        ), patch.object(
            service._doc_search, "search", new_callable=AsyncMock, return_value=[]
        ), patch.object(
            service._doc_search, "visible_documents", new_callable=AsyncMock, return_value=visible_map
        ) as mock_visible:
            results = await service.semantic_search(
                project_id=project_id, query="文档", top_k=10, scope="knowledge_doc", user=user,
            )
        return results, mock_visible

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_private_docs_invisible_to_non_owner(self, project_id: UUID):
        other_user = MagicMock()
        other_user.id = uuid4()
        results, mock_visible = await self._run(project_id, visible=False, user=other_user)
        assert results == []
        kwargs = mock_visible.await_args.kwargs
        assert kwargs["project_id"] == project_id
        assert kwargs["subject"] is not None and kwargs["subject"].user_id == other_user.id

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_public_docs_visible_to_any_user(self, project_id: UUID):
        any_user = MagicMock()
        any_user.id = uuid4()
        results, _ = await self._run(project_id, visible=True, user=any_user)
        assert len(results) == 1
        assert results[0]["content"] == "文档片段"
        assert results[0]["document_name"] == "可见文档.md"
        assert results[0]["retrieval"] == "vector"


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
# search 别名 + 无用户调用（旧消费方 ai_chat_service 已删除，契约见 spec design §十 C1）
# ===========================================================================

class TestAIChatServiceRegression:
    """``search(project_id, query)`` 别名与 ``user=None`` 调用的契约。

    🔁 C1（spec knowledge-base-retrieval-and-authz-closure Req 3.8）：旧契约「无 user 时
    knowledge_doc 不过滤」服务的 ``ai_chat_service`` 已不存在；旧行为会把索引到全局哨兵的
    私有文档暴露给任何调用方。现为 project 模式无用户判定（public + 当前项目组）。
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
        """业务数据命中不受知识文档判定影响（scope=all，user=None）。"""
        mock_db = make_retrieval_session()
        chunk = _make_chunk(KnowledgeSourceType.trial_balance, f"业务数据 {query}")
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[chunk]))
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock, return_value=[0.5] * 768
        ), patch.object(
            service._doc_search, "search", new_callable=AsyncMock, return_value=[]
        ):
            results = await service.search(project_id=project_id, query=query, top_k=10)

        assert len(results) == 1
        assert results[0]["source_type"] == "trial_balance"

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        query=query_strategy(),
        visible=st.booleans(),
    )
    @pytest.mark.asyncio
    async def test_search_without_user_filters_knowledge_docs_by_project_scope(
        self, project_id: UUID, query: str, visible: bool
    ):
        """无 user 时 knowledge_doc 命中按 project 无用户判定裁剪（主体为 None，而非不过滤）。"""
        mock_db = make_retrieval_session()
        doc_chunk = _make_chunk(KnowledgeSourceType.knowledge_doc, f"知识文档 {query}")
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[doc_chunk]))
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = KnowledgeIndexService(mock_db)
        visible_map = {doc_chunk.source_id: _doc_meta(doc_chunk.source_id)} if visible else {}

        with patch.object(
            service._ai_svc, "embedding", new_callable=AsyncMock, return_value=[0.5] * 768
        ), patch.object(
            service._doc_search, "search", new_callable=AsyncMock, return_value=[]
        ), patch.object(
            service._doc_search, "visible_documents", new_callable=AsyncMock, return_value=visible_map
        ) as mock_visible:
            results = await service.search(project_id=project_id, query=query, top_k=10)

        kwargs = mock_visible.await_args.kwargs
        assert kwargs["subject"] is None, "无用户调用必须以『无主体』判定，而不是跳过判定"
        assert kwargs["project_id"] == project_id
        assert len(results) == (1 if visible else 0)
