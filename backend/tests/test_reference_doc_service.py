"""ReferenceDocService.load_from_knowledge_base / search_knowledge_base 单元测试

原 Task 6：reference_doc_service 改调 semantic_search(scope=knowledge_doc)。
2026-09-29（spec knowledge-base-retrieval-and-authz-closure Req 5.1，design §十 C3/C4）：
  * 删除「语义为空/异常 → 无权限过滤 ILIKE」兜底（可读他人私有文档；且其分类只精确匹配
    直属文件夹）。检索内核的文档词法层已内含权限判定与子树分类加分，兜底不再需要；
  * 无关键词 → 空查询列表模式（仍经内核判定），不再旁路直查；
  * 文档名直接取结果的 ``document_name``（不再额外按 source_id 查名字）。
**Validates: Requirements 2.3**
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.reference_doc_service import ReferenceDocService

_SEARCH = "app.services.knowledge_index_service.KnowledgeIndexService.semantic_search"


@pytest.fixture
def mock_db():
    """Mock AsyncSession（参照服务自身不应再发任何 SQL：全部经检索内核）。"""
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


def _hit(content: str, name: str | None = "测试文档.pdf", **extra):
    return {
        "source_type": "knowledge_doc",
        "source_id": str(uuid4()),
        "content": content,
        "score": 0.85,
        "chunk_index": 0,
        "document_name": name,
        "folder_path": "/会计准则库",
        "retrieval": "lexical",
        **extra,
    }


class TestLoadFromKnowledgeBaseSemanticSearch:
    """验证 load_from_knowledge_base 经检索内核取数。"""

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self):
        """db=None 时直接返回空列表。"""
        result = await ReferenceDocService.load_from_knowledge_base(
            project_id=uuid4(), keywords=["测试"], db=None
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_semantic_search_primary_path(self, mock_db):
        """有 keywords 时调 semantic_search(scope=knowledge_doc)，文档名取结果自带的 document_name。"""
        project_id = uuid4()
        with patch(_SEARCH, new_callable=AsyncMock, return_value=[_hit("这是知识库文档内容")]) as mock_search:
            result = await ReferenceDocService.load_from_knowledge_base(
                project_id=project_id, keywords=["测试"], max_docs=3, db=mock_db,
            )
            mock_search.assert_called_once_with(
                project_id, "测试", top_k=3, scope="knowledge_doc", user=None, category="notes"
            )

        assert result == ["【知识库 - 测试文档.pdf】\n这是知识库文档内容"]
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_semantic_search_empty_returns_empty_without_unfiltered_fallback(self, mock_db):
        """检索为空 → 空列表；不得再旁路执行无权限过滤的 ILIKE（C4）。"""
        with patch(_SEARCH, new_callable=AsyncMock, return_value=[]):
            result = await ReferenceDocService.load_from_knowledge_base(
                project_id=uuid4(), keywords=["准则"], category="notes", db=mock_db,
            )
        assert result == []
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_semantic_search_exception_returns_empty(self, mock_db, caplog):
        """检索异常 → 空列表 + WARNING；同样不走无权限 ILIKE。"""
        with patch(_SEARCH, new_callable=AsyncMock, side_effect=RuntimeError("db down")):
            result = await ReferenceDocService.load_from_knowledge_base(
                project_id=uuid4(), keywords=["降级"], category="notes", db=mock_db,
            )
        assert result == []
        mock_db.execute.assert_not_called()
        assert any("知识库参照检索失败" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_no_keywords_uses_list_mode_through_kernel(self, mock_db):
        """无 keywords → 空查询列表模式（仍经内核判定），不再旁路直查文档表。"""
        project_id = uuid4()
        with patch(_SEARCH, new_callable=AsyncMock, return_value=[_hit("全量内容", "全量文档.pdf")]) as mock_search:
            result = await ReferenceDocService.load_from_knowledge_base(
                project_id=project_id, keywords=None, category="notes", db=mock_db,
            )
            mock_search.assert_called_once_with(
                project_id, "", top_k=3, scope="knowledge_doc", user=None, category="notes"
            )
        assert result == ["【知识库 - 全量文档.pdf】\n全量内容"]

    @pytest.mark.asyncio
    async def test_content_truncated_to_2000(self, mock_db):
        """内容截断到 2000 字符。"""
        with patch(_SEARCH, new_callable=AsyncMock, return_value=[_hit("A" * 5000, "长文档.pdf")]):
            result = await ReferenceDocService.load_from_knowledge_base(
                project_id=uuid4(), keywords=["长"], db=mock_db,
            )
        content_part = result[0].split("\n", 1)[1]
        assert len(content_part) == 2000

    @pytest.mark.asyncio
    async def test_non_knowledge_doc_results_are_ignored(self, mock_db):
        """防御：内核若混入业务数据命中，参照加载只取 knowledge_doc。"""
        mixed = [_hit("文档正文"), {**_hit("试算数据"), "source_type": "trial_balance"}]
        with patch(_SEARCH, new_callable=AsyncMock, return_value=mixed):
            result = await ReferenceDocService.load_from_knowledge_base(
                project_id=uuid4(), keywords=["x"], db=mock_db,
            )
        assert result == ["【知识库 - 测试文档.pdf】\n文档正文"]

    @pytest.mark.asyncio
    async def test_multiple_keywords_joined(self, mock_db):
        """多个 keywords 用空格拼接为 query_text（空白关键词丢弃）。"""
        project_id = uuid4()
        with patch(_SEARCH, new_callable=AsyncMock, return_value=[]) as mock_search:
            await ReferenceDocService.load_from_knowledge_base(
                project_id=project_id, keywords=["货币", " ", "资金", "审计"], db=mock_db,
            )
            mock_search.assert_called_once_with(
                project_id, "货币 资金 审计", top_k=3, scope="knowledge_doc", user=None, category="notes"
            )

    @pytest.mark.asyncio
    async def test_method_signature_unchanged(self):
        """方法签名保持向后兼容。"""
        import inspect

        sig = inspect.signature(ReferenceDocService.load_from_knowledge_base)
        params = list(sig.parameters.keys())
        assert params == ["project_id", "category", "keywords", "max_docs", "db"]


class TestSearchKnowledgeBaseStructured:
    @pytest.mark.asyncio
    async def test_returns_structured_dicts_and_passes_user(self, mock_db):
        user = MagicMock()
        project_id = uuid4()
        with patch(_SEARCH, new_callable=AsyncMock, return_value=[_hit("正文")]) as mock_search:
            docs = await ReferenceDocService.search_knowledge_base(
                project_id, keywords=["审计", "CAS"], category="audit_standards", max_docs=5, db=mock_db, user=user,
            )
            mock_search.assert_called_once_with(
                project_id, "审计 CAS", top_k=5, scope="knowledge_doc", user=user, category="audit_standards"
            )
        assert docs[0]["document_name"] == "测试文档.pdf"
        assert docs[0]["folder_path"] == "/会计准则库"
        assert docs[0]["content"] == "正文" and docs[0]["score"] == 0.85
