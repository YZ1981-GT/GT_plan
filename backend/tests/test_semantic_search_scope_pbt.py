"""
Property-Based Test: semantic_search scope + 权限过滤 + 向量不可用降级 (R1, R2)

**Validates: Requirements 1.1, 4.1, 4.2**（spec retrieval-kernel-unification）

属性 R1：向量召回失败时 semantic_search 降级返回非空（双保险不崩）
属性 R2：semantic_search 带 user 时只返回该 user 有权访问的知识文件

2026-09-30 按现契约改写（spec knowledge-base-retrieval-and-authz-closure 改检索内核时本文件漏改，
长期 3 红；归因见 spec environment-hygiene-deps-and-scratch-schemas design §一「实测补」）：

- 夹具换 ``tests._kb_mock_session.make_retrieval_session``（补 SAVEPOINT / bind 形状，不改取数语义）。
- R1：业务数据的兜底由 BM25 返回（分数归一到 (0, 1]）；「ILIKE score 恒 0」只在 BM25 开关关闭时成立。
- R2：可见性经 ``_doc_search.visible_documents``（单一判定面）。原用例把「第二次 ``execute`` 的行」当权限数据，
  现内核不再那样取数 —— 改为给判定面喂可见 / 不可见，钉住「内核真的按判定结果裁剪」；判定本身的正确性由
  ``test_knowledge_retrieval_visibility_pbt`` 全组合穷举、真库 ``test_knowledge_doc_search_pg`` 验证。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.config import settings as app_settings
from app.services import knowledge_index_service as kis
from app.services.knowledge_index_service import KnowledgeIndexService
from app.models.ai_models import KnowledgeSourceType
from tests._kb_mock_session import make_retrieval_session
from tests.test_retrieval_phase2_pbt import _doc_meta


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


def _make_chunk(source_type: KnowledgeSourceType, content: str, query: str = ""):
    """创建 mock KnowledgeIndex chunk，content 包含 query 以确保词法兜底能匹配。"""
    chunk = MagicMock()
    chunk.id = uuid4()
    chunk.source_type = source_type
    chunk.source_id = uuid4()
    chunk.content_text = content
    chunk.chunk_index = 0
    chunk.embedding_vector = ",".join(["0.5"] * 768)
    return chunk


def _session_returning(chunks):
    session = make_retrieval_session()
    result = MagicMock()
    result.scalars.return_value = MagicMock(all=MagicMock(return_value=list(chunks)))
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    return session


class TestIlikeFallbackProperty:
    """PBT R1: 向量召回失败时降级返回非空"""

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        query=query_strategy(),
        bm25_enabled=st.booleans(),
    )
    @pytest.mark.asyncio
    async def test_ilike_fallback_returns_results_when_content_matches(
        self, project_id: UUID, query: str, bm25_enabled: bool
    ):
        """
        属性 R1：向量召回失败（embedding 抛异常）且库中存在匹配的业务数据分块时，
        semantic_search（scope=project_data）降级返回非空；BM25 开时分数 ∈ (0, 1]，关时退 ILIKE 分数 0。

        **Validates: Requirements 1.1, 4.1**
        """
        kis._BM25_CACHE.clear()  # 进程级缓存（键 = project_id + scope）不得串例
        content = f"包含查询内容 {query} 的文本"
        mock_db = _session_returning([_make_chunk(KnowledgeSourceType.trial_balance, content, query)])
        service = KnowledgeIndexService(mock_db)

        with patch.object(app_settings, "RETRIEVAL_BM25_FALLBACK_ENABLED", bm25_enabled), \
                patch.object(service._ai_svc, "embedding", new_callable=AsyncMock,
                             side_effect=RuntimeError("Embedding service unavailable")):
            results = await service.semantic_search(
                project_id=project_id, query=query, top_k=10, scope="project_data",
            )

        # R1: 降级返回非空，且内容就是那条业务分块
        assert len(results) > 0
        assert results[0]["content"] == content
        if bm25_enabled:
            assert results[0]["retrieval"] == "bm25"
            assert 0.0 < results[0]["score"] <= 1.0
        else:
            assert results[0]["retrieval"] == "ilike"
            assert results[0]["score"] == 0.0

    @settings(max_examples=5)
    @given(
        project_id=uuid_strategy(),
        query=query_strategy(),
        scope=scope_strategy(),
    )
    @pytest.mark.asyncio
    async def test_ilike_fallback_never_crashes(
        self, project_id: UUID, query: str, scope: str
    ):
        """
        属性 R1 补充：向量召回失败且各层都无匹配时 semantic_search 绝不崩溃，返回空列表。

        **Validates: Requirements 4.1**
        """
        kis._BM25_CACHE.clear()
        mock_db = _session_returning([])
        service = KnowledgeIndexService(mock_db)

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock,
                          side_effect=RuntimeError("Embedding service unavailable")), \
                patch.object(service._doc_search, "search", new_callable=AsyncMock, return_value=[]):
            results = await service.semantic_search(
                project_id=project_id, query=query, top_k=10, scope=scope,
            )

        assert results == []


class TestPermissionFilterProperty:
    """PBT R2: 权限隔离 — 向量层的知识文档命中必须经单一判定面裁剪"""

    async def _run_doc_hit(self, project_id: UUID, *, visible: bool, user):
        doc_chunk = _make_chunk(KnowledgeSourceType.knowledge_doc, "知识文档内容")
        mock_db = _session_returning([doc_chunk])
        service = KnowledgeIndexService(mock_db)
        visible_map = {doc_chunk.source_id: _doc_meta(doc_chunk.source_id, "公开文档.md")} if visible else {}

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock, return_value=[0.5] * 768), \
                patch.object(service._doc_search, "search", new_callable=AsyncMock, return_value=[]), \
                patch.object(service._doc_search, "visible_documents", new_callable=AsyncMock,
                             return_value=visible_map) as vis:
            results = await service.semantic_search(
                project_id=project_id, query="知识文档", top_k=10, scope="knowledge_doc", user=user,
            )
        return results, vis, doc_chunk

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_private_docs_filtered_for_non_owner(self, project_id: UUID):
        """
        属性 R2：判定面判为不可见（如他人私有文档）⇒ 结果为空；判定确实以该用户为主体、在当前项目下执行。

        **Validates: Requirements 4.2**
        """
        other_user = MagicMock()
        other_user.id = uuid4()
        results, vis, _ = await self._run_doc_hit(project_id, visible=False, user=other_user)

        assert results == []
        kwargs = vis.await_args.kwargs
        assert kwargs["project_id"] == project_id
        assert kwargs["subject"] is not None and kwargs["subject"].user_id == other_user.id

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_public_docs_visible_to_all_users(self, project_id: UUID):
        """
        属性 R2：判定面判为可见 ⇒ 任意用户都拿到该文档，且带判定面给出的文档名。

        **Validates: Requirements 4.2**
        """
        any_user = MagicMock()
        any_user.id = uuid4()
        results, vis, chunk = await self._run_doc_hit(project_id, visible=True, user=any_user)

        assert [(r["source_id"], r["content"], r["document_name"]) for r in results] == [
            (str(chunk.source_id), "知识文档内容", "公开文档.md")
        ]
        assert vis.await_args.kwargs["subject"].user_id == any_user.id

    @settings(max_examples=5)
    @given(project_id=uuid_strategy())
    @pytest.mark.asyncio
    async def test_non_doc_results_not_filtered(self, project_id: UUID):
        """
        属性 R2 补充：非 knowledge_doc 结果不经知识文档判定面（业务数据按项目分区，由路由层项目权限隔离）。

        **Validates: Requirements 4.2**
        """
        mock_db = _session_returning([_make_chunk(KnowledgeSourceType.trial_balance, "试算表业务数据")])
        service = KnowledgeIndexService(mock_db)
        user = MagicMock()
        user.id = uuid4()

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock, return_value=[0.5] * 768), \
                patch.object(service._doc_search, "visible_documents", new_callable=AsyncMock,
                             return_value={}) as vis:
            results = await service.semantic_search(
                project_id=project_id, query="试算表", top_k=10, scope="project_data", user=user,
            )

        assert [r["source_type"] for r in results] == ["trial_balance"]
        vis.assert_not_awaited()
