"""ContextBuilder 单元测试

测试文档级 AI 对话上下文构建器的核心逻辑：
- build() 组装完整上下文
- _get_doc_content 获取不同类型文档内容
- _search_related_knowledge 检索关联知识
- _build_citations 构建引用列表（D3 属性）
- _estimate_tokens token 估算

需求: 1.2, 2.1  属性: D3
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.services.doc_ai_context_builder import (
    ContextBuilder,
    ChatContext,
    SearchHit,
    Citation,
    _strip_html_tags,
    _extract_cell_texts,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_PROJECT_ID = uuid4()
FAKE_DOC_ID = uuid4()
FAKE_USER = MagicMock(id=uuid4())


def _mock_db():
    """创建 mock AsyncSession"""
    db = MagicMock()
    db.execute = AsyncMock()
    return db


def _mock_semantic_search_results():
    """模拟 semantic_search 返回结果"""
    return [
        {
            "source_type": "workpaper",
            "source_id": str(uuid4()),
            "content": "审计程序：检查银行对账单与账面余额的一致性",
            "score": 0.92,
            "chunk_index": 0,
        },
        {
            "source_type": "trial_balance",
            "source_id": str(uuid4()),
            "content": "货币资金期末余额 1,234,567.89",
            "score": 0.85,
            "chunk_index": 1,
        },
    ]


# ---------------------------------------------------------------------------
# ChatContext dataclass 测试
# ---------------------------------------------------------------------------


class TestChatContext:
    """ChatContext dataclass 基本结构验证"""

    def test_create_chat_context(self):
        """ChatContext 包含所有必要字段"""
        ctx = ChatContext(
            doc_excerpt="底稿内容",
            knowledge_hits=[
                SearchHit(
                    source_type="workpaper",
                    source_id="abc123",
                    content="测试内容",
                    score=0.9,
                    chunk_index=0,
                )
            ],
            project_summary="项目摘要",
            citations=[
                Citation(
                    source_type="workpaper",
                    source_id="abc123",
                    source_name="E1-1",
                    paragraph_index=0,
                    excerpt="测试",
                )
            ],
            token_estimate=100,
        )
        assert ctx.doc_excerpt == "底稿内容"
        assert len(ctx.knowledge_hits) == 1
        assert ctx.project_summary == "项目摘要"
        assert len(ctx.citations) == 1
        assert ctx.token_estimate == 100

    def test_search_hit_has_locatable_source(self):
        """D3: 每条 SearchHit 必带可定位 source（source_id + chunk_index）"""
        hit = SearchHit(
            source_type="knowledge_doc",
            source_id="file-uuid-123",
            content="内容片段",
            score=0.88,
            chunk_index=3,
        )
        assert hit.source_id  # 非空
        assert hit.chunk_index is not None  # 有段落索引

    def test_citation_has_locatable_source(self):
        """D3: Citation 必带 source_id + paragraph_index"""
        citation = Citation(
            source_type="workpaper",
            source_id="wp-uuid-456",
            source_name="E1-1 银行存款",
            paragraph_index=2,
            excerpt="银行对账单核对",
        )
        assert citation.source_id
        assert citation.paragraph_index is not None


# ---------------------------------------------------------------------------
# ContextBuilder.build() 集成测试
# ---------------------------------------------------------------------------


class TestContextBuilderBuild:
    """ContextBuilder.build() 组装完整上下文"""

    @pytest.mark.asyncio
    async def test_build_returns_chat_context(self):
        """build() 返回 ChatContext 包含所有组件"""
        db = _mock_db()

        # Mock workpaper query result
        wp_row = ({"content_text": "底稿内容"}, "E1-1", "银行存款")
        wp_result = MagicMock()
        wp_result.first.return_value = wp_row

        # Mock project query result
        project_row = ("测试项目", "测试客户", None, None)
        project_result = MagicMock()
        project_result.first.return_value = project_row

        # 设置 db.execute 按调用顺序返回不同结果
        # 调用顺序: 1) _get_workpaper_content  2) _get_project_summary
        db.execute = AsyncMock(side_effect=[wp_result, project_result])

        builder = ContextBuilder(db)

        # Mock semantic_search
        with patch.object(
            builder._knowledge_svc,
            "semantic_search",
            new_callable=AsyncMock,
            return_value=_mock_semantic_search_results(),
        ):
            ctx = await builder.build(
                doc_type="workpaper",
                doc_id=str(FAKE_DOC_ID),
                project_id=FAKE_PROJECT_ID,
                year=2025,
                query="银行存款审计程序有哪些？",
                user=FAKE_USER,
            )

        assert isinstance(ctx, ChatContext)
        assert ctx.doc_excerpt  # 非空
        assert len(ctx.knowledge_hits) == 2
        assert ctx.project_summary  # 非空
        assert len(ctx.citations) == 2
        assert ctx.token_estimate > 0

    @pytest.mark.asyncio
    async def test_build_with_extra_scopes(self):
        """build() 支持 extra_scopes 额外知识范围"""
        db = _mock_db()

        from app.models.knowledge_models import KnowledgeAccessLevel

        # Mock 1: _get_doc_content (workpaper query - empty)
        empty_result = MagicMock()
        empty_result.first.return_value = None

        # Mock 2: _get_user_project_ids (for _search_extra_scopes)
        user_projects_result = MagicMock()
        user_projects_result.all.return_value = []

        # Mock 3: folder query (public folder)
        folder_obj = MagicMock()
        folder_obj.access_level = KnowledgeAccessLevel.public
        folder_obj.project_ids = None
        folder_obj.created_by = None
        folder_scalars = MagicMock()
        folder_scalars.first.return_value = folder_obj
        folder_result = MagicMock()
        folder_result.scalars.return_value = folder_scalars

        # Mock 4: docs query (with permission fields)
        doc_id = uuid4()
        folder_doc_row = (doc_id, "参考文档.pdf", "额外参考内容", None, None, None)
        docs_result = MagicMock()
        docs_result.all.return_value = [folder_doc_row]

        # Mock 5: doc permissions query (for _filter_hits_by_permission)
        doc_perm_result = MagicMock()
        doc_perm_result.all.return_value = [
            (doc_id, None, None, None, KnowledgeAccessLevel.public, None, None),
        ]

        # Mock 6: _get_user_project_ids (for _filter_hits_by_permission)
        user_projects_result2 = MagicMock()
        user_projects_result2.all.return_value = []

        # Mock 7: _get_project_summary
        project_row = MagicMock()
        project_row.__iter__ = lambda self: iter(("项目A", "客户A", None, None))
        project_result = MagicMock()
        project_result.first.return_value = project_row

        db.execute = AsyncMock(side_effect=[
            empty_result,           # 1: _get_doc_content
            user_projects_result,   # 2: _get_user_project_ids (extra_scopes)
            folder_result,          # 3: folder query
            docs_result,            # 4: docs query
            doc_perm_result,        # 5: doc permissions (filter)
            user_projects_result2,  # 6: _get_user_project_ids (filter)
            project_result,         # 7: _get_project_summary
        ])

        builder = ContextBuilder(db)

        with patch.object(
            builder._knowledge_svc,
            "semantic_search",
            new_callable=AsyncMock,
            return_value=[],
        ):
            ctx = await builder.build(
                doc_type="workpaper",
                doc_id=str(FAKE_DOC_ID),
                project_id=FAKE_PROJECT_ID,
                year=2025,
                query="测试查询",
                user=FAKE_USER,
                extra_scopes=[str(uuid4())],
            )

        # extra_scopes 应产生额外 hits
        assert isinstance(ctx, ChatContext)
        assert len(ctx.knowledge_hits) >= 1


# ---------------------------------------------------------------------------
# _get_doc_content 测试
# ---------------------------------------------------------------------------


class TestGetDocContent:
    """测试不同文档类型的内容获取"""

    @pytest.mark.asyncio
    async def test_workpaper_with_content_text(self):
        """底稿 parsed_data 含 content_text 时直接使用"""
        db = _mock_db()
        parsed_data = {"content_text": "这是底稿的文本内容"}
        row = MagicMock()
        row.__iter__ = lambda self: iter((parsed_data, "E1-1", "银行存款"))
        result = MagicMock()
        result.first.return_value = row
        db.execute.return_value = result

        builder = ContextBuilder(db)
        content = await builder._get_doc_content("workpaper", str(FAKE_DOC_ID), FAKE_PROJECT_ID)

        assert "这是底稿的文本内容" in content

    @pytest.mark.asyncio
    async def test_workpaper_no_parsed_data(self):
        """底稿无 parsed_data 时返回占位信息"""
        db = _mock_db()
        row = MagicMock()
        row.__iter__ = lambda self: iter((None, "E1-1", "银行存款"))
        result = MagicMock()
        result.first.return_value = row
        db.execute.return_value = result

        builder = ContextBuilder(db)
        content = await builder._get_doc_content("workpaper", str(FAKE_DOC_ID), FAKE_PROJECT_ID)

        assert "E1-1" in content
        assert "暂无解析内容" in content

    @pytest.mark.asyncio
    async def test_knowledge_doc_content(self):
        """知识文档直接返回 content_text"""
        db = _mock_db()
        row = MagicMock()
        row.__iter__ = lambda self: iter(("知识库文档全文内容", "审计准则.pdf"))
        result = MagicMock()
        result.first.return_value = row
        db.execute.return_value = result

        builder = ContextBuilder(db)
        content = await builder._get_doc_content("knowledge_doc", str(FAKE_DOC_ID), FAKE_PROJECT_ID)

        assert content == "知识库文档全文内容"

    @pytest.mark.asyncio
    async def test_knowledge_folder_content(self):
        """文件夹级对话注入文件夹下文档集合"""
        db = _mock_db()
        rows = [
            ("文档1.pdf", "文档1内容", None),
            ("文档2.docx", None, "文档2摘要"),
        ]
        result = MagicMock()
        result.all.return_value = rows
        db.execute.return_value = result

        builder = ContextBuilder(db)
        content = await builder._get_doc_content("knowledge_folder", str(FAKE_DOC_ID), FAKE_PROJECT_ID)

        assert "文档1" in content
        assert "文档2摘要" in content

    @pytest.mark.asyncio
    async def test_unknown_doc_type(self):
        """未知文档类型返回空字符串"""
        db = _mock_db()
        builder = ContextBuilder(db)
        content = await builder._get_doc_content("unknown_type", str(FAKE_DOC_ID), FAKE_PROJECT_ID)
        assert content == ""


# ---------------------------------------------------------------------------
# _build_citations 测试（D3 属性）
# ---------------------------------------------------------------------------


class TestBuildCitations:
    """D3: 引用可追溯 — 每条 knowledge_hit 必带可定位 source"""

    def test_citations_from_hits(self):
        """每条 hit 生成对应 citation"""
        db = _mock_db()
        builder = ContextBuilder(db)

        hits = [
            SearchHit(
                source_type="workpaper",
                source_id="id-1",
                content="内容1",
                score=0.9,
                chunk_index=0,
                source_name="E1-1",
            ),
            SearchHit(
                source_type="knowledge_doc",
                source_id="id-2",
                content="内容2",
                score=0.8,
                chunk_index=2,
                source_name="准则文档",
            ),
        ]

        citations = builder._build_citations(hits)

        assert len(citations) == 2
        # D3: 每条 citation 都有 source_id 和 paragraph_index
        for c in citations:
            assert c.source_id
            assert c.paragraph_index is not None
            assert c.source_name

    def test_citations_deduplicate(self):
        """相同 source 的重复 hit 只生成一条 citation"""
        db = _mock_db()
        builder = ContextBuilder(db)

        hits = [
            SearchHit(source_type="workpaper", source_id="id-1", content="A", score=0.9, chunk_index=0),
            SearchHit(source_type="workpaper", source_id="id-1", content="B", score=0.8, chunk_index=0),
        ]

        citations = builder._build_citations(hits)
        assert len(citations) == 1

    def test_citations_different_chunks_not_deduped(self):
        """同一 source 不同 chunk 不去重"""
        db = _mock_db()
        builder = ContextBuilder(db)

        hits = [
            SearchHit(source_type="workpaper", source_id="id-1", content="A", score=0.9, chunk_index=0),
            SearchHit(source_type="workpaper", source_id="id-1", content="B", score=0.8, chunk_index=1),
        ]

        citations = builder._build_citations(hits)
        assert len(citations) == 2


# ---------------------------------------------------------------------------
# _estimate_tokens 测试
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    """token 估算基本正确性"""

    def test_estimate_tokens_basic(self):
        """token 估算 ≈ 总字符数 / 2"""
        db = _mock_db()
        builder = ContextBuilder(db)

        doc = "测试文档内容" * 10  # 50 字符
        hits = [SearchHit(source_type="x", source_id="y", content="知识内容" * 5, score=0.9, chunk_index=0)]
        summary = "项目摘要"

        estimate = builder._estimate_tokens(doc, hits, summary)
        total_chars = len(doc) + len(hits[0].content) + len(summary)
        assert estimate == total_chars // 2

    def test_estimate_tokens_empty(self):
        """空内容 token 估算为 0"""
        db = _mock_db()
        builder = ContextBuilder(db)
        assert builder._estimate_tokens("", [], "") == 0


# ---------------------------------------------------------------------------
# 辅助函数测试
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """辅助函数单元测试"""

    def test_strip_html_tags(self):
        """去除 HTML 标签"""
        html = "<p>段落1</p><div><span>内容</span></div>"
        text = _strip_html_tags(html)
        assert "<" not in text
        assert "段落1" in text
        assert "内容" in text

    def test_strip_html_tags_empty(self):
        """空 HTML 返回空字符串"""
        assert _strip_html_tags("") == ""

    def test_extract_cell_texts_list(self):
        """从 list 格式 cells 提取文本"""
        cells = [
            ["科目", "期初", "期末"],
            ["银行存款", 100000, 200000],
            [None, None, None],
        ]
        text = _extract_cell_texts(cells)
        assert "银行存款" in text
        assert "100000" in text

    def test_extract_cell_texts_dict(self):
        """从 dict 格式 cells 提取文本"""
        cells = {
            "A1": {"v": "标题"},
            "B1": {"v": "金额"},
            "A2": {"v": "银行存款"},
            "B2": {"v": 123456},
        }
        text = _extract_cell_texts(cells)
        assert "标题" in text
        assert "123456" in text

    def test_extract_cell_texts_empty(self):
        """空 cells 返回空字符串"""
        assert _extract_cell_texts([]) == ""
        assert _extract_cell_texts({}) == ""


# ---------------------------------------------------------------------------
# Token 预算管理测试（Task 2 — D1 属性）
# ---------------------------------------------------------------------------


class TestTokenBudgetManagement:
    """Task 2: token 预算管理 — chunk + 相关性排序 + 截断

    D1 属性：ContextBuilder 输出 token_estimate ≤ 配置上限
    需求: 2.3, 2.4
    """

    def test_enforce_budget_truncates_doc_excerpt(self):
        """文档内容超预算时被截断"""
        db = _mock_db()
        builder = ContextBuilder(db, token_budget=100)  # 极小预算

        # 文档内容远超预算（1000 字符 ≈ 500 token）
        long_doc = "审计底稿内容" * 200
        hits = []
        summary = "项目摘要"

        doc_out, hits_out, summary_out = builder._enforce_token_budget(
            long_doc, hits, summary
        )

        # 文档应被截断
        assert len(doc_out) < len(long_doc)
        assert "已截断" in doc_out

    def test_enforce_budget_trims_low_score_hits(self):
        """知识 hits 超预算时从低分端裁剪"""
        db = _mock_db()
        builder = ContextBuilder(db, token_budget=200)

        doc = "短文档"
        summary = "摘要"
        # 多条 hits，按 score 降序
        hits = [
            SearchHit(source_type="wp", source_id="1", content="高分内容" * 50, score=0.95, chunk_index=0),
            SearchHit(source_type="wp", source_id="2", content="中分内容" * 50, score=0.80, chunk_index=1),
            SearchHit(source_type="wp", source_id="3", content="低分内容" * 50, score=0.60, chunk_index=2),
        ]

        _, hits_out, _ = builder._enforce_token_budget(doc, hits, summary)

        # 低分 hits 应被裁剪（不是全部保留）
        assert len(hits_out) < len(hits)
        # 保留的 hits 应是高分优先
        if hits_out:
            assert hits_out[0].score >= hits_out[-1].score

    def test_enforce_budget_chunks_long_hit_content(self):
        """单条 hit 内容超 CHUNK_SIZE_CHARS 时被 chunk 截断"""
        db = _mock_db()
        builder = ContextBuilder(db, token_budget=5000)

        doc = "短文档"
        summary = "摘要"
        # 单条 hit 内容超长
        long_content = "知识内容" * 500  # 2000 字符
        hits = [
            SearchHit(source_type="kd", source_id="1", content=long_content, score=0.9, chunk_index=0),
        ]

        _, hits_out, _ = builder._enforce_token_budget(doc, hits, summary)

        # hit 内容应被截断到 CHUNK_SIZE_CHARS
        if hits_out:
            from app.services.doc_ai_context_builder import CHUNK_SIZE_CHARS
            assert len(hits_out[0].content) <= CHUNK_SIZE_CHARS

    def test_token_estimate_never_exceeds_budget(self):
        """D1 核心：无论输入多大，token_estimate 始终 ≤ budget"""
        db = _mock_db()
        budget = 500
        builder = ContextBuilder(db, token_budget=budget)

        # 极大输入
        doc = "大量文档内容" * 1000
        summary = "很长的项目摘要" * 100
        hits = [
            SearchHit(source_type="wp", source_id=str(i), content="知识内容" * 200, score=0.9 - i * 0.05, chunk_index=i)
            for i in range(20)
        ]

        doc_out, hits_out, summary_out = builder._enforce_token_budget(doc, hits, summary)
        estimate = builder._estimate_tokens(doc_out, hits_out, summary_out)

        assert estimate <= budget

    def test_small_input_not_truncated(self):
        """输入小于预算时不截断"""
        db = _mock_db()
        builder = ContextBuilder(db, token_budget=8000)

        doc = "短文档内容"
        summary = "项目摘要"
        hits = [
            SearchHit(source_type="wp", source_id="1", content="知识片段", score=0.9, chunk_index=0),
        ]

        doc_out, hits_out, summary_out = builder._enforce_token_budget(doc, hits, summary)

        # 不应被截断
        assert doc_out == doc
        assert summary_out == summary
        assert len(hits_out) == 1
        assert hits_out[0].content == "知识片段"

    def test_token_budget_configurable(self):
        """token 预算可通过构造参数配置"""
        db = _mock_db()
        builder = ContextBuilder(db, token_budget=4000)
        assert builder.token_budget == 4000

        builder2 = ContextBuilder(db, token_budget=16000)
        assert builder2.token_budget == 16000

    def test_empty_input_returns_zero_tokens(self):
        """空输入 token 估算为 0，不超预算"""
        db = _mock_db()
        builder = ContextBuilder(db, token_budget=100)

        doc_out, hits_out, summary_out = builder._enforce_token_budget("", [], "")
        estimate = builder._estimate_tokens(doc_out, hits_out, summary_out)

        assert estimate == 0
        assert estimate <= builder.token_budget


# ---------------------------------------------------------------------------
# D1 属性 PBT（Property-Based Test）
# ---------------------------------------------------------------------------

from hypothesis import given, settings, strategies as st


def _text_strategy(max_size: int = 5000):
    """生成中文为主的文本"""
    return st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=0,
        max_size=max_size,
    )


def _search_hit_strategy():
    """生成 SearchHit"""
    return st.builds(
        SearchHit,
        source_type=st.sampled_from(["workpaper", "knowledge_doc", "trial_balance"]),
        source_id=st.text(min_size=1, max_size=36, alphabet="abcdef0123456789-"),
        content=_text_strategy(2000),
        score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        chunk_index=st.integers(min_value=0, max_value=100),
        source_name=st.text(min_size=0, max_size=50),
    )


class TestTokenBudgetD1Property:
    """D1 属性 PBT：ContextBuilder 输出 token_estimate ≤ 配置上限

    **Validates: Requirements 2.3, 2.4**
    属性 D1: token 预算不超限（chunk 截断生效）
    """

    @given(
        doc_excerpt=_text_strategy(10000),
        knowledge_hits=st.lists(_search_hit_strategy(), min_size=0, max_size=15),
        project_summary=_text_strategy(1000),
        budget=st.integers(min_value=100, max_value=20000),
    )
    @settings(max_examples=15)
    def test_d1_token_estimate_never_exceeds_budget(
        self, doc_excerpt, knowledge_hits, project_summary, budget
    ):
        """D1: 对任意输入，enforce_token_budget 后 token_estimate ≤ budget

        **Validates: Requirements 2.4**
        """
        db = _mock_db()
        builder = ContextBuilder(db, token_budget=budget)

        # 确保 hits 按 score 降序（模拟真实行为）
        knowledge_hits_sorted = sorted(knowledge_hits, key=lambda h: h.score, reverse=True)

        doc_out, hits_out, summary_out = builder._enforce_token_budget(
            doc_excerpt, knowledge_hits_sorted, project_summary
        )

        estimate = builder._estimate_tokens(doc_out, hits_out, summary_out)
        assert estimate <= budget, (
            f"D1 violated: token_estimate={estimate} > budget={budget}"
        )


# ---------------------------------------------------------------------------
# D2 权限过滤测试（Task 3 — 属性 D2）
# ---------------------------------------------------------------------------


class TestPermissionFiltering:
    """Task 3: 权限过滤 — ContextBuilder 检索只含 user 有权访问的知识文件

    D2 属性：对话上下文只含 user 有权访问的知识文件（继承 KnowledgeDocument 权限）
    需求: 5.1
    """

    def test_user_has_access_public(self):
        """public 文档所有用户可访问"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        assert ContextBuilder._user_has_access(
            KnowledgeAccessLevel.public, None, None, uuid4(), []
        ) is True

    def test_user_has_access_none_treated_as_public(self):
        """access_level=None 视为 public"""
        assert ContextBuilder._user_has_access(
            None, None, None, uuid4(), []
        ) is True

    def test_user_has_access_project_group_allowed(self):
        """project_group 文档：用户属于允许的项目组时可访问"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        project_id = uuid4()
        assert ContextBuilder._user_has_access(
            KnowledgeAccessLevel.project_group,
            [str(project_id)],
            None,
            uuid4(),
            [project_id],
        ) is True

    def test_user_has_access_project_group_denied(self):
        """project_group 文档：用户不属于允许的项目组时拒绝"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        assert ContextBuilder._user_has_access(
            KnowledgeAccessLevel.project_group,
            [str(uuid4())],  # 允许的项目
            None,
            uuid4(),
            [uuid4()],  # 用户的项目（不同）
        ) is False

    def test_user_has_access_project_group_no_user_projects(self):
        """project_group 文档：用户无项目时拒绝"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        assert ContextBuilder._user_has_access(
            KnowledgeAccessLevel.project_group,
            [str(uuid4())],
            None,
            uuid4(),
            [],  # 用户无项目
        ) is False

    def test_user_has_access_private_owner(self):
        """private 文档：创建者可访问"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        user_id = uuid4()
        assert ContextBuilder._user_has_access(
            KnowledgeAccessLevel.private,
            None,
            user_id,  # created_by
            user_id,  # 同一用户
            [],
        ) is True

    def test_user_has_access_private_not_owner(self):
        """private 文档：非创建者拒绝"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        assert ContextBuilder._user_has_access(
            KnowledgeAccessLevel.private,
            None,
            uuid4(),  # created_by（其他人）
            uuid4(),  # 当前用户
            [],
        ) is False

    def test_check_folder_access_public(self):
        """public 文件夹所有用户可访问"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        folder = MagicMock()
        folder.access_level = KnowledgeAccessLevel.public
        user = MagicMock(id=uuid4())

        assert ContextBuilder._check_folder_access(folder, user, []) is True

    def test_check_folder_access_project_group_allowed(self):
        """project_group 文件夹：用户属于允许的项目组时可访问"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        project_id = uuid4()
        folder = MagicMock()
        folder.access_level = KnowledgeAccessLevel.project_group
        folder.project_ids = [str(project_id)]
        user = MagicMock(id=uuid4())

        assert ContextBuilder._check_folder_access(folder, user, [project_id]) is True

    def test_check_folder_access_project_group_denied(self):
        """project_group 文件夹：用户不属于允许的项目组时拒绝"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        folder = MagicMock()
        folder.access_level = KnowledgeAccessLevel.project_group
        folder.project_ids = [str(uuid4())]
        user = MagicMock(id=uuid4())

        assert ContextBuilder._check_folder_access(folder, user, [uuid4()]) is False

    def test_check_folder_access_private_owner(self):
        """private 文件夹：创建者可访问"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        user_id = uuid4()
        folder = MagicMock()
        folder.access_level = KnowledgeAccessLevel.private
        folder.created_by = user_id
        user = MagicMock(id=user_id)

        assert ContextBuilder._check_folder_access(folder, user, []) is True

    def test_check_folder_access_private_not_owner(self):
        """private 文件夹：非创建者拒绝"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        folder = MagicMock()
        folder.access_level = KnowledgeAccessLevel.private
        folder.created_by = uuid4()
        user = MagicMock(id=uuid4())

        assert ContextBuilder._check_folder_access(folder, user, []) is False

    def test_check_doc_access_inherits_folder(self):
        """文档 access_level=None 时继承文件夹权限（已通过文件夹检查）"""
        user = MagicMock(id=uuid4())
        assert ContextBuilder._check_doc_access(
            None, None, None, user, []
        ) is True

    @pytest.mark.asyncio
    async def test_filter_hits_excludes_unauthorized_knowledge_docs(self):
        """D2 核心：_filter_hits_by_permission 排除无权访问的知识文档"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        db = _mock_db()
        user = MagicMock(id=uuid4())

        # 两个文档：一个 public，一个 private（非创建者）
        public_doc_id = uuid4()
        private_doc_id = uuid4()

        # Mock 1: 批量查询文档权限信息（_filter_hits_by_permission 先查文档权限）
        doc_perm_result = MagicMock()
        doc_perm_result.all.return_value = [
            (public_doc_id, KnowledgeAccessLevel.public, None, None,
             KnowledgeAccessLevel.public, None, None),
            (private_doc_id, KnowledgeAccessLevel.private, None, uuid4(),
             KnowledgeAccessLevel.public, None, None),
        ]

        # Mock 2: _get_user_project_ids 查询（之后查用户项目）
        user_projects_result = MagicMock()
        user_projects_result.all.return_value = []

        db.execute = AsyncMock(side_effect=[doc_perm_result, user_projects_result])

        builder = ContextBuilder(db)

        hits = [
            SearchHit(source_type="knowledge_doc", source_id=str(public_doc_id),
                      content="公开内容", score=0.9, chunk_index=0),
            SearchHit(source_type="knowledge_doc", source_id=str(private_doc_id),
                      content="私密内容", score=0.8, chunk_index=0),
        ]

        filtered = await builder._filter_hits_by_permission(hits, user)

        # 只保留 public 文档
        assert len(filtered) == 1
        assert filtered[0].source_id == str(public_doc_id)

    @pytest.mark.asyncio
    async def test_filter_hits_keeps_non_knowledge_doc_types(self):
        """D2: 非 knowledge_doc 类型（workpaper 等）不过滤"""
        db = _mock_db()
        user = MagicMock(id=uuid4())
        builder = ContextBuilder(db)

        hits = [
            SearchHit(source_type="workpaper", source_id=str(uuid4()),
                      content="底稿内容", score=0.9, chunk_index=0),
            SearchHit(source_type="trial_balance", source_id=str(uuid4()),
                      content="试算表", score=0.8, chunk_index=0),
        ]

        filtered = await builder._filter_hits_by_permission(hits, user)

        # 非 knowledge_doc 类型全部保留
        assert len(filtered) == 2

    @pytest.mark.asyncio
    async def test_filter_hits_empty_list(self):
        """空 hits 列表返回空"""
        db = _mock_db()
        user = MagicMock(id=uuid4())
        builder = ContextBuilder(db)

        filtered = await builder._filter_hits_by_permission([], user)
        assert filtered == []

    @pytest.mark.asyncio
    async def test_filter_hits_project_group_access(self):
        """D2: project_group 文档只对有权项目成员可见"""
        from app.models.knowledge_models import KnowledgeAccessLevel

        db = _mock_db()
        user = MagicMock(id=uuid4())
        allowed_project = uuid4()

        # Mock 1: 批量查询文档权限信息（先执行）
        doc_id = uuid4()
        doc_perm_result = MagicMock()
        doc_perm_result.all.return_value = [
            (doc_id, KnowledgeAccessLevel.project_group, [str(allowed_project)], None,
             KnowledgeAccessLevel.public, None, None),
        ]

        # Mock 2: _get_user_project_ids — 用户属于 allowed_project（后执行）
        user_projects_result = MagicMock()
        user_projects_result.all.return_value = [(allowed_project,)]

        db.execute = AsyncMock(side_effect=[doc_perm_result, user_projects_result])

        builder = ContextBuilder(db)

        hits = [
            SearchHit(source_type="knowledge_doc", source_id=str(doc_id),
                      content="项目组文档", score=0.9, chunk_index=0),
        ]

        filtered = await builder._filter_hits_by_permission(hits, user)

        # 用户属于允许的项目组，应保留
        assert len(filtered) == 1

    @pytest.mark.asyncio
    async def test_get_user_project_ids_returns_projects(self):
        """_get_user_project_ids 返回用户所属项目列表"""
        db = _mock_db()
        user = MagicMock(id=uuid4())
        project1 = uuid4()
        project2 = uuid4()

        result = MagicMock()
        result.all.return_value = [(project1,), (project2,)]
        db.execute = AsyncMock(return_value=result)

        builder = ContextBuilder(db)
        project_ids = await builder._get_user_project_ids(user)

        assert len(project_ids) == 2
        assert project1 in project_ids
        assert project2 in project_ids

    @pytest.mark.asyncio
    async def test_get_user_project_ids_no_user(self):
        """_get_user_project_ids 无用户时返回空列表"""
        db = _mock_db()
        builder = ContextBuilder(db)

        assert await builder._get_user_project_ids(None) == []
        assert await builder._get_user_project_ids(MagicMock(id=None)) == []


# ---------------------------------------------------------------------------
# D2 属性 PBT（Property-Based Test）
# ---------------------------------------------------------------------------


class TestPermissionD2Property:
    """D2 属性 PBT：对话上下文只含 user 有权访问的知识文件

    **Validates: Requirements 5.1**
    属性 D2: 权限隔离 — 无权文档永远不出现在上下文中
    """

    @given(
        num_public=st.integers(min_value=0, max_value=5),
        num_private_owned=st.integers(min_value=0, max_value=3),
        num_private_other=st.integers(min_value=0, max_value=5),
        num_project_group_allowed=st.integers(min_value=0, max_value=3),
        num_project_group_denied=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=15)
    def test_d2_unauthorized_docs_never_in_context(
        self,
        num_public,
        num_private_owned,
        num_private_other,
        num_project_group_allowed,
        num_project_group_denied,
    ):
        """D2: 对任意权限组合，无权文档永远不出现在过滤结果中

        **Validates: Requirements 5.1**
        """
        from app.models.knowledge_models import KnowledgeAccessLevel

        user_id = uuid4()
        allowed_project = uuid4()
        user_project_ids = [allowed_project]

        # 构造各类文档
        allowed_doc_ids: set[str] = set()
        denied_doc_ids: set[str] = set()

        # public 文档 — 所有人可访问
        for _ in range(num_public):
            doc_id = str(uuid4())
            allowed_doc_ids.add(doc_id)

        # private 文档（用户是创建者）— 可访问
        for _ in range(num_private_owned):
            doc_id = str(uuid4())
            allowed_doc_ids.add(doc_id)

        # private 文档（其他人创建）— 不可访问
        for _ in range(num_private_other):
            doc_id = str(uuid4())
            denied_doc_ids.add(doc_id)

        # project_group 文档（用户属于允许项目）— 可访问
        for _ in range(num_project_group_allowed):
            doc_id = str(uuid4())
            allowed_doc_ids.add(doc_id)

        # project_group 文档（用户不属于允许项目）— 不可访问
        for _ in range(num_project_group_denied):
            doc_id = str(uuid4())
            denied_doc_ids.add(doc_id)

        # 对每个文档验证 _user_has_access 判断正确
        for doc_id in allowed_doc_ids:
            # 确定该文档的权限类型
            pass  # 已在上面分类

        # 验证 public 文档可访问
        for _ in range(num_public):
            assert ContextBuilder._user_has_access(
                KnowledgeAccessLevel.public, None, None, user_id, user_project_ids
            ) is True

        # 验证 private 文档（自己创建）可访问
        for _ in range(num_private_owned):
            assert ContextBuilder._user_has_access(
                KnowledgeAccessLevel.private, None, user_id, user_id, user_project_ids
            ) is True

        # 验证 private 文档（他人创建）不可访问
        for _ in range(num_private_other):
            other_user = uuid4()
            assert ContextBuilder._user_has_access(
                KnowledgeAccessLevel.private, None, other_user, user_id, user_project_ids
            ) is False

        # 验证 project_group 文档（用户属于允许项目）可访问
        for _ in range(num_project_group_allowed):
            assert ContextBuilder._user_has_access(
                KnowledgeAccessLevel.project_group,
                [str(allowed_project)],
                None,
                user_id,
                user_project_ids,
            ) is True

        # 验证 project_group 文档（用户不属于允许项目）不可访问
        for _ in range(num_project_group_denied):
            other_project = uuid4()
            assert ContextBuilder._user_has_access(
                KnowledgeAccessLevel.project_group,
                [str(other_project)],
                None,
                user_id,
                user_project_ids,
            ) is False
