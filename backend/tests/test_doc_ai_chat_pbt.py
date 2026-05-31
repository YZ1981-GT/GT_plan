"""文档级 AI 对话 — 阶段 1 PBT 综合属性测试

整合 4 个正确性属性的 Property-Based Test：
- D1: token 预算不超限 — ContextBuilder 输出 token_estimate ≤ 配置上限
- D2: 权限隔离 — 对话上下文只含 user 有权访问的知识文件
- D3: 引用可追溯 — 每条 knowledge_hit 必带可定位 source（source_id + chunk_index）
- D4: 确认流门禁 — AI 生成内容回写前必经 AIContentMustBeConfirmedRule（pending 状态）

**Validates: Requirements 2.4, 5.1**
属性: D1, D2, D3, D4

hypothesis max_examples=10~15（遵循项目铁律）
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, strategies as st

from app.services.doc_ai_context_builder import (
    ContextBuilder,
    ChatContext,
    SearchHit,
    Citation,
)


# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------


def _text_strategy(max_size: int = 5000):
    """生成中文为主的文本"""
    return st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=0,
        max_size=max_size,
    )


def _search_hit_strategy():
    """生成 SearchHit（确保 source_id 非空、chunk_index 非负）"""
    return st.builds(
        SearchHit,
        source_type=st.sampled_from(["workpaper", "knowledge_doc", "trial_balance"]),
        source_id=st.text(min_size=1, max_size=36, alphabet="abcdef0123456789-"),
        content=_text_strategy(2000),
        score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        chunk_index=st.integers(min_value=0, max_value=100),
        source_name=st.text(min_size=0, max_size=50),
    )


def _mock_db():
    """创建 mock AsyncSession"""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# D1: token 预算不超限
# ---------------------------------------------------------------------------


class TestD1TokenBudgetProperty:
    """D1 属性 PBT：ContextBuilder 输出 token_estimate ≤ 配置上限

    **Validates: Requirements 2.4**
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
# D2: 权限隔离
# ---------------------------------------------------------------------------


class TestD2PermissionIsolationProperty:
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
    @settings(max_examples=12)
    def test_d2_unauthorized_docs_never_in_context(
        self,
        num_public,
        num_private_owned,
        num_private_other,
        num_project_group_allowed,
        num_project_group_denied,
    ):
        """D2: 对任意权限组合，_user_has_access 正确隔离无权文档

        **Validates: Requirements 5.1**
        """
        from app.models.knowledge_models import KnowledgeAccessLevel

        user_id = uuid4()
        allowed_project = uuid4()
        user_project_ids = [allowed_project]

        # public 文档 — 所有人可访问
        for _ in range(num_public):
            assert ContextBuilder._user_has_access(
                KnowledgeAccessLevel.public, None, None, user_id, user_project_ids
            ) is True

        # private 文档（用户是创建者）— 可访问
        for _ in range(num_private_owned):
            assert ContextBuilder._user_has_access(
                KnowledgeAccessLevel.private, None, user_id, user_id, user_project_ids
            ) is True

        # private 文档（他人创建）— 不可访问
        for _ in range(num_private_other):
            other_user = uuid4()
            assert ContextBuilder._user_has_access(
                KnowledgeAccessLevel.private, None, other_user, user_id, user_project_ids
            ) is False

        # project_group 文档（用户属于允许项目）— 可访问
        for _ in range(num_project_group_allowed):
            assert ContextBuilder._user_has_access(
                KnowledgeAccessLevel.project_group,
                [str(allowed_project)],
                None,
                user_id,
                user_project_ids,
            ) is True

        # project_group 文档（用户不属于允许项目）— 不可访问
        for _ in range(num_project_group_denied):
            other_project = uuid4()
            assert ContextBuilder._user_has_access(
                KnowledgeAccessLevel.project_group,
                [str(other_project)],
                None,
                user_id,
                user_project_ids,
            ) is False


# ---------------------------------------------------------------------------
# D3: 引用可追溯
# ---------------------------------------------------------------------------


class TestD3CitationTraceabilityProperty:
    """D3 属性 PBT：每条 knowledge_hit 必带可定位 source（source_id + chunk_index）

    **Validates: Requirements 2.4, 5.1**
    属性 D3: 引用可追溯 — _build_citations 产出的每条 Citation 都有非空 source_id 和非 None paragraph_index
    """

    @given(
        knowledge_hits=st.lists(_search_hit_strategy(), min_size=1, max_size=15),
    )
    @settings(max_examples=15)
    def test_d3_citations_always_have_locatable_source(self, knowledge_hits):
        """D3: 对任意 SearchHit 列表，_build_citations 产出的每条 citation 都有
        非空 source_id 和非 None paragraph_index

        **Validates: Requirements 2.4, 5.1**
        """
        db = _mock_db()
        builder = ContextBuilder(db)

        citations = builder._build_citations(knowledge_hits)

        # 每条 citation 必须有可定位 source
        for citation in citations:
            assert citation.source_id, (
                f"D3 violated: citation has empty source_id, "
                f"source_type={citation.source_type}"
            )
            assert citation.paragraph_index is not None, (
                f"D3 violated: citation has None paragraph_index, "
                f"source_id={citation.source_id}"
            )


# ---------------------------------------------------------------------------
# D4: 确认流门禁
# ---------------------------------------------------------------------------


class TestD4ConfirmGateProperty:
    """D4 属性 PBT：AI 生成内容回写前必经 AIContentMustBeConfirmedRule（pending 状态）

    **Validates: Requirements 2.4, 5.1**
    属性 D4: 确认流门禁 — adopt 端点对任意有效 AdoptRequest 都调用 wrap_ai_output_with_log 且返回 pending
    """

    @given(
        content=st.text(min_size=1, max_size=200, alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z")
        )),
        doc_type=st.sampled_from(["workpaper", "knowledge_doc", "note", "report"]),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=12)
    def test_d4_adopt_always_calls_wrap_with_pending(
        self, content, doc_type, confidence
    ):
        """D4: 对任意有效 AdoptRequest，adopt 端点必调用 wrap_ai_output_with_log
        且返回 confirm_action='pending'

        **Validates: Requirements 2.4, 5.1**
        """
        import asyncio
        from app.routers.doc_ai_chat import adopt_ai_content, AdoptRequest

        project_id = uuid4()
        doc_id = uuid4()

        req = AdoptRequest(
            content=content,
            project_id=str(project_id),
            doc_type=doc_type,
            doc_id=str(doc_id),
            confidence=confidence,
        )

        mock_db = _mock_db()
        mock_user = MagicMock()
        mock_user.id = uuid4()

        mock_wrap_result = {
            "id": str(uuid4()),
            "ai_content_log_id": str(uuid4()),
            "confirm_action": "pending",
            "content_hash": "a" * 64,
            "content": content,
        }

        with patch(
            "app.services.wp_ai_service.wrap_ai_output_with_log",
            new_callable=AsyncMock,
            return_value=mock_wrap_result,
        ) as mock_wrap:
            result = asyncio.run(
                adopt_ai_content(req, db=mock_db, current_user=mock_user)
            )

            # D4 核心断言：wrap_ai_output_with_log 必须被调用
            mock_wrap.assert_called_once()

            # D4 核心断言：返回 pending 状态
            assert result["confirm_action"] == "pending", (
                f"D4 violated: confirm_action={result['confirm_action']}, expected 'pending'"
            )
            assert result["ai_content_log_id"] is not None, (
                "D4 violated: ai_content_log_id is None"
            )
            assert result["success"] is True
