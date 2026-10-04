"""
Unit Tests: semantic_search scope + 权限过滤 + 向量不可用时的降级

**Validates: Requirements 1.1, 4.1, 4.2**（spec retrieval-kernel-unification）

2026-09-30 按现契约改写（spec knowledge-base-retrieval-and-authz-closure 改了检索内核，本文件当时漏改，
长期 7 红被当成常态；归因见 spec environment-hygiene-deps-and-scratch-schemas design §一「实测补」）：

- 夹具：内核把每条读 ``knowledge_index`` 的语句包进 ``begin_nested()``（SAVEPOINT），并用
  ``get_bind().dialect`` 判断是否探测 pgvector 列。裸 ``AsyncMock()`` 下 ``async with`` 协程直接
  ``TypeError`` ⇒ 三层检索全部失败返回空。改用 ``tests._kb_mock_session`` 只补形状，不改取数语义。
- 知识文档：可见性一律经 ``_doc_search.visible_documents``（单一判定面，
  ``KnowledgeAccessPolicy.can_retrieve``）；判定本身由 ``test_knowledge_retrieval_visibility_pbt``
  穷举、由真库 ``test_knowledge_doc_search_pg`` 验证。这里只钉「内核真的用判定结果裁剪」。
- 🔴 契约反转（design §十 C1）：``user=None`` 时知识文档**不再**「不过滤」—— 以「无主体」判定，
  private 永不返回。原用例 ``test_default_user_is_none_no_filtering`` 按新契约改写。
- 🔴 契约变更（Req 4.2）：向量不可用时，知识文档改由**文档正文词法层**兜底（``retrieval="lexical"``），
  索引分块只为业务数据（project_data）兜底。原「knowledge_doc 走 ILIKE」用例按此改写。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.knowledge_index_service import KnowledgeIndexService
from app.models.ai_models import KnowledgeSourceType
from tests._kb_mock_session import attach_retrieval_session_shape
from tests.test_retrieval_phase2_pbt import _doc_hit, _doc_meta


@pytest.fixture
def mock_db_session():
    """带检索形状（SAVEPOINT + sqlite bind）的 Mock AsyncSession。"""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return attach_retrieval_session_shape(session)


@pytest.fixture(autouse=True)
def _clear_bm25_cache():
    """BM25 进程级缓存（TTL 60s，键 = project_id + scope）不得把别的用例的分块带进来。"""
    from app.services import knowledge_index_service as kis

    kis._BM25_CACHE.clear()
    yield
    kis._BM25_CACHE.clear()


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


def _index_returns(session, chunks):
    """每次 execute 都返回同一批索引分块（向量层 / BM25 / ILIKE 共用）。"""
    result = MagicMock()
    result.scalars.return_value = MagicMock(all=MagicMock(return_value=list(chunks)))
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)


def _executed_sql(session) -> list[str]:
    """把每次 execute 的语句编译成 SQL 文本（断言 scope 条件真的下推到了 SQL）。"""
    out = []
    for call_ in session.execute.await_args_list:
        stmt = call_.args[0]
        try:
            out.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        except Exception:  # noqa: BLE001 - 探测类语句等无法字面量编译时退回默认形态
            out.append(str(stmt))
    return out


class TestSemanticSearchBackwardCompat:
    """验证默认参数保持向后兼容（ai_chat_service 零改）"""

    @pytest.mark.asyncio
    async def test_default_scope_is_all(self, mock_db_session):
        """默认 scope='all'：业务数据分块照常返回，且文档词法层也会被查询。"""
        service = KnowledgeIndexService(mock_db_session)
        _index_returns(mock_db_session, [_make_chunk(KnowledgeSourceType.trial_balance, "测试内容")])

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock, return_value=[0.5] * 768), \
                patch.object(service._doc_search, "search", new_callable=AsyncMock, return_value=[]) as doc_search:
            # 旧调用方式（无 scope/user）
            results = await service.semantic_search(project_id=uuid4(), query="测试", top_k=10)

        assert [r["source_type"] for r in results] == ["trial_balance"]
        assert results[0]["retrieval"] == "vector"
        doc_search.assert_awaited_once()  # all 含 knowledge_doc ⇒ 文档词法层必须参与

    @pytest.mark.asyncio
    async def test_default_user_none_filters_knowledge_docs_by_project_scope(self, mock_db_session):
        """🔴 契约反转（原 ``test_default_user_is_none_no_filtering``）：user=None 以「无主体」判定。

        判定返回不可见 ⇒ 向量层的知识文档命中被剔除；可见 ⇒ 返回并带文档名。
        """
        for visible in (False, True):
            service = KnowledgeIndexService(mock_db_session)
            chunk = _make_chunk(KnowledgeSourceType.knowledge_doc, "知识文档")
            _index_returns(mock_db_session, [chunk])
            visible_map = {chunk.source_id: _doc_meta(chunk.source_id, "准则.md")} if visible else {}

            with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock, return_value=[0.5] * 768), \
                    patch.object(service._doc_search, "search", new_callable=AsyncMock, return_value=[]), \
                    patch.object(service._doc_search, "visible_documents", new_callable=AsyncMock,
                                 return_value=visible_map) as vis:
                project_id = uuid4()
                results = await service.semantic_search(project_id=project_id, query="知识", top_k=10)

            kwargs = vis.await_args.kwargs
            assert kwargs["subject"] is None, "无用户调用必须以『无主体』判定，而不是跳过判定"
            assert kwargs["project_id"] == project_id
            if visible:
                assert [(r["source_type"], r["document_name"]) for r in results] == [("knowledge_doc", "准则.md")]
            else:
                assert results == []


class TestSemanticSearchScope:
    """验证 scope 过滤逻辑（条件下推到 SQL + 文档词法层按 scope 启停）"""

    @pytest.mark.asyncio
    async def test_scope_project_data_excludes_knowledge_doc(self, mock_db_session):
        """scope='project_data'：SQL 排除 knowledge_doc 分块，且不查询文档词法层。"""
        service = KnowledgeIndexService(mock_db_session)
        _index_returns(mock_db_session, [_make_chunk(KnowledgeSourceType.trial_balance, "业务数据")])

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock, return_value=[0.5] * 768), \
                patch.object(service._doc_search, "search", new_callable=AsyncMock, return_value=[]) as doc_search:
            results = await service.semantic_search(
                project_id=uuid4(), query="业务", top_k=10, scope="project_data",
            )

        assert [r["source_type"] for r in results] == ["trial_balance"]
        doc_search.assert_not_awaited()
        index_sql = [s for s in _executed_sql(mock_db_session) if "knowledge_index" in s]
        assert index_sql and all("source_type !=" in s for s in index_sql), index_sql

    @pytest.mark.asyncio
    async def test_scope_knowledge_doc_only_returns_docs(self, mock_db_session):
        """scope='knowledge_doc'：SQL 只取 knowledge_doc 分块，结果只含知识文档（经判定面）。"""
        service = KnowledgeIndexService(mock_db_session)
        chunk = _make_chunk(KnowledgeSourceType.knowledge_doc, "知识文档内容")
        _index_returns(mock_db_session, [chunk])

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock, return_value=[0.5] * 768), \
                patch.object(service._doc_search, "search", new_callable=AsyncMock, return_value=[]), \
                patch.object(service._doc_search, "visible_documents", new_callable=AsyncMock,
                             return_value={chunk.source_id: _doc_meta(chunk.source_id)}):
            results = await service.semantic_search(
                project_id=uuid4(), query="知识", top_k=10, scope="knowledge_doc",
            )

        assert [r["source_type"] for r in results] == ["knowledge_doc"]
        index_sql = [s for s in _executed_sql(mock_db_session) if "knowledge_index" in s]
        assert index_sql and all("source_type =" in s and "source_type !=" not in s for s in index_sql), index_sql

    @pytest.mark.asyncio
    async def test_scope_cross_year_falls_back_to_all(self, mock_db_session):
        """scope='cross_year' 在 semantic_search 中按 all 处理（需 prior_project_id 才走 search_cross_year）。"""
        service = KnowledgeIndexService(mock_db_session)
        _index_returns(mock_db_session, [_make_chunk(KnowledgeSourceType.contract, "合同数据")])

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock, return_value=[0.5] * 768), \
                patch.object(service._doc_search, "search", new_callable=AsyncMock, return_value=[]) as doc_search:
            results = await service.semantic_search(
                project_id=uuid4(), query="合同", top_k=10, scope="cross_year",
            )

        assert [r["source_type"] for r in results] == ["contract"]
        doc_search.assert_awaited_once()  # 与 all 相同：文档词法层参与
        index_sql = [s for s in _executed_sql(mock_db_session) if "knowledge_index" in s]
        assert index_sql and not any("source_type" in s.split("WHERE", 1)[-1] for s in index_sql), index_sql

    @pytest.mark.asyncio
    async def test_unknown_scope_is_rejected(self, mock_db_session):
        """未知 scope 直接拒绝，而不是静默当成 all。"""
        service = KnowledgeIndexService(mock_db_session)
        with pytest.raises(ValueError, match="不支持的检索范围"):
            await service.semantic_search(project_id=uuid4(), query="x", top_k=10, scope="everything")


class TestSemanticSearchFallback:
    """向量不可用时的降级：业务数据走 BM25 / ILIKE，知识文档走文档正文词法层"""

    @pytest.mark.asyncio
    async def test_embedding_failure_falls_back_for_business_data(self, mock_db_session):
        """embedding 服务不可用 ⇒ 业务数据经 BM25 返回（分数归一到 (0, 1]），不走向量。"""
        service = KnowledgeIndexService(mock_db_session)
        _index_returns(mock_db_session, [_make_chunk(KnowledgeSourceType.trial_balance, "应收账款分析")])

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock,
                          side_effect=Exception("Connection refused")), \
                patch.object(service._doc_search, "search", new_callable=AsyncMock, return_value=[]):
            results = await service.semantic_search(project_id=uuid4(), query="应收账款", top_k=10)

        assert [(r["source_type"], r["retrieval"]) for r in results] == [("trial_balance", "bm25")]
        assert 0.0 < results[0]["score"] <= 1.0

    @pytest.mark.asyncio
    async def test_embedding_failure_uses_ilike_when_bm25_disabled(self, mock_db_session):
        """BM25 开关关闭 ⇒ 业务数据退到 ILIKE（score 恒 0，无相关度可言）。"""
        from app.core.config import settings as app_settings

        service = KnowledgeIndexService(mock_db_session)
        _index_returns(mock_db_session, [_make_chunk(KnowledgeSourceType.trial_balance, "应收账款分析")])

        with patch.object(app_settings, "RETRIEVAL_BM25_FALLBACK_ENABLED", False), \
                patch.object(service._ai_svc, "embedding", new_callable=AsyncMock,
                             side_effect=Exception("Connection refused")), \
                patch.object(service._doc_search, "search", new_callable=AsyncMock, return_value=[]):
            results = await service.semantic_search(project_id=uuid4(), query="应收账款", top_k=10)

        assert [(r["source_type"], r["retrieval"], r["score"]) for r in results] == [("trial_balance", "ilike", 0.0)]

    @pytest.mark.asyncio
    async def test_knowledge_doc_fallback_uses_document_lexical_layer(self, mock_db_session):
        """🔴 契约变更（原 ``test_ilike_fallback_respects_scope``）：向量不可用 + scope=knowledge_doc ⇒
        只由文档正文词法层兜底；索引分块（文档正文的旧副本）不再参与，哪怕库里有匹配分块。
        """
        service = KnowledgeIndexService(mock_db_session)
        _index_returns(mock_db_session, [_make_chunk(KnowledgeSourceType.knowledge_doc, "知识文档")])
        hit = _doc_hit("知识文档正文片段")

        with patch.object(service._ai_svc, "embedding", new_callable=AsyncMock,
                          side_effect=RuntimeError("Service down")), \
                patch.object(service._doc_search, "search", new_callable=AsyncMock, return_value=[hit]) as doc_search:
            results = await service.semantic_search(
                project_id=uuid4(), query="知识", top_k=10, scope="knowledge_doc",
            )

        assert [(r["source_type"], r["retrieval"], r["source_id"]) for r in results] == [
            ("knowledge_doc", "lexical", str(hit.meta.doc_id))
        ]
        doc_search.assert_awaited_once()
        assert not any("knowledge_index" in s for s in _executed_sql(mock_db_session)), (
            "knowledge_doc 范围在向量不可用时不得再读索引分块"
        )
