"""文档级 AI 对话端点测试

覆盖 Task 4 端点：
- POST /api/ai-chat/doc/{doc_type}/{doc_id} (streaming)
- GET  /api/ai-chat/doc/{doc_type}/{doc_id}/history
- POST /api/ai-chat/adopt (D4 确认流门禁)

属性 D4: AI 生成内容回写前必经 AIContentMustBeConfirmedRule（pending 状态）
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user():
    """模拟当前用户"""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "test_auditor"
    user.role = MagicMock()
    user.role.value = "admin"
    return user


@pytest.fixture
def mock_db():
    """模拟 AsyncSession"""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Unit Tests: adopt endpoint (D4 property)
# ---------------------------------------------------------------------------


class TestAdoptEndpoint:
    """POST /api/ai-chat/adopt — D4 确认流门禁测试"""

    @pytest.mark.asyncio
    async def test_adopt_calls_wrap_ai_output_with_log(self, mock_db, mock_user):
        """D4: adopt 必须调用 wrap_ai_output_with_log 写入 ai_content_log"""
        from app.routers.doc_ai_chat import adopt_ai_content, AdoptRequest

        project_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        req = AdoptRequest(
            content="AI 生成的审计结论：余额变动合理",
            project_id=str(project_id),
            doc_type="workpaper",
            doc_id=str(doc_id),
            target_cell="E5",
            confidence=0.9,
        )

        mock_wrap_result = {
            "id": str(uuid.uuid4()),
            "ai_content_log_id": str(uuid.uuid4()),
            "confirm_action": "pending",
            "content_hash": "a" * 64,
            "content": req.content,
        }

        with patch(
            "app.services.wp_ai_service.wrap_ai_output_with_log",
            new_callable=AsyncMock,
            return_value=mock_wrap_result,
        ):
            result = await adopt_ai_content(req, db=mock_db, current_user=mock_user)

        assert result["success"] is True
        assert result["confirm_action"] == "pending"
        assert result["ai_content_log_id"] is not None

    @pytest.mark.asyncio
    async def test_adopt_returns_pending_status(self, mock_db, mock_user):
        """D4: adopt 返回 confirm_action='pending'（未确认状态）"""
        from app.routers.doc_ai_chat import adopt_ai_content, AdoptRequest

        project_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        req = AdoptRequest(
            content="测试内容",
            project_id=str(project_id),
            doc_type="workpaper",
            doc_id=str(doc_id),
        )

        mock_wrap_result = {
            "id": str(uuid.uuid4()),
            "ai_content_log_id": str(uuid.uuid4()),
            "confirm_action": "pending",
            "content_hash": "b" * 64,
            "content": "测试内容",
        }

        with patch(
            "app.services.wp_ai_service.wrap_ai_output_with_log",
            new_callable=AsyncMock,
            return_value=mock_wrap_result,
        ):
            result = await adopt_ai_content(req, db=mock_db, current_user=mock_user)

        assert result["confirm_action"] == "pending"
        assert "ai_content_log_id" in result

    @pytest.mark.asyncio
    async def test_adopt_passes_all_required_params_to_wrap(self, mock_db, mock_user):
        """D4: adopt 传递 5 个必要参数给 wrap_ai_output_with_log（触发写 ai_content_log）"""
        from app.routers.doc_ai_chat import adopt_ai_content, AdoptRequest

        project_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        req = AdoptRequest(
            content="AI 分析结论",
            project_id=str(project_id),
            doc_type="knowledge_doc",
            doc_id=str(doc_id),
            target_field="conclusion",
            confidence=0.88,
        )

        mock_wrap_result = {
            "id": str(uuid.uuid4()),
            "ai_content_log_id": str(uuid.uuid4()),
            "confirm_action": "pending",
            "content_hash": "c" * 64,
        }

        with patch(
            "app.services.wp_ai_service.wrap_ai_output_with_log",
            new_callable=AsyncMock,
            return_value=mock_wrap_result,
        ) as mock_wrap:
            result = await adopt_ai_content(req, db=mock_db, current_user=mock_user)

            # 验证 wrap_ai_output_with_log 被调用且传递了 5 个必要参数
            mock_wrap.assert_called_once()
            call_kwargs = mock_wrap.call_args.kwargs

            # D4 关键：5 参齐全才会写 ai_content_log
            assert call_kwargs["db"] is mock_db
            assert call_kwargs["project_id"] == project_id
            assert call_kwargs["user_id"] == mock_user.id
            assert call_kwargs["instance_type"] == "knowledge_doc"
            assert call_kwargs["instance_id"] == doc_id
            assert call_kwargs["content"] == "AI 分析结论"
            assert call_kwargs["confidence"] == 0.88
            assert call_kwargs["target_field"] == "conclusion"

    @pytest.mark.asyncio
    async def test_adopt_invalid_project_id_returns_400(self, mock_db, mock_user):
        """无效 project_id 返回 400"""
        from app.routers.doc_ai_chat import adopt_ai_content, AdoptRequest

        req = AdoptRequest(
            content="test",
            project_id="not-a-uuid",
            doc_type="workpaper",
            doc_id=str(uuid.uuid4()),
        )

        with pytest.raises(Exception) as exc_info:
            await adopt_ai_content(req, db=mock_db, current_user=mock_user)
        # HTTPException with 400
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_adopt_commits_db_after_wrap(self, mock_db, mock_user):
        """adopt 在 wrap 成功后 commit DB"""
        from app.routers.doc_ai_chat import adopt_ai_content, AdoptRequest

        project_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        req = AdoptRequest(
            content="内容",
            project_id=str(project_id),
            doc_type="workpaper",
            doc_id=str(doc_id),
        )

        mock_wrap_result = {
            "ai_content_log_id": str(uuid.uuid4()),
            "confirm_action": "pending",
            "content_hash": "d" * 64,
        }

        with patch(
            "app.services.wp_ai_service.wrap_ai_output_with_log",
            new_callable=AsyncMock,
            return_value=mock_wrap_result,
        ):
            await adopt_ai_content(req, db=mock_db, current_user=mock_user)

        mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Unit Tests: history endpoint
# ---------------------------------------------------------------------------


class TestHistoryEndpoint:
    """GET /api/ai-chat/doc/{doc_type}/{doc_id}/history"""

    @pytest.mark.asyncio
    async def test_get_empty_history(self, mock_user):
        """无历史时返回空列表"""
        from app.routers.doc_ai_chat import get_chat_history, _chat_history

        # 清空历史
        _chat_history.clear()

        result = await get_chat_history("workpaper", str(uuid.uuid4()), current_user=mock_user)
        assert result["messages"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_get_existing_history(self, mock_user):
        """有历史时返回消息列表"""
        from app.routers.doc_ai_chat import get_chat_history, _chat_history, _history_key

        doc_id = str(uuid.uuid4())
        key = _history_key("workpaper", doc_id, mock_user.id)

        _chat_history[key] = [
            {"role": "user", "content": "什么是审计抽样？"},
            {"role": "assistant", "content": "审计抽样是..."},
        ]

        result = await get_chat_history("workpaper", doc_id, current_user=mock_user)
        assert result["total"] == 2
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"

        # 清理
        _chat_history.clear()


# ---------------------------------------------------------------------------
# Unit Tests: streaming chat endpoint
# ---------------------------------------------------------------------------


class TestDocAiChatEndpoint:
    """POST /api/ai-chat/doc/{doc_type}/{doc_id} — streaming"""

    @pytest.mark.asyncio
    async def test_chat_returns_streaming_response(self, mock_db, mock_user):
        """对话端点返回 StreamingResponse"""
        from fastapi.responses import StreamingResponse
        from app.routers.doc_ai_chat import doc_ai_chat, DocChatRequest

        req = DocChatRequest(
            query="什么是重要性水平？",
            year=2025,
            project_id=str(uuid.uuid4()),
        )

        with patch(
            "app.routers.doc_ai_chat.ContextBuilder"
        ) as MockBuilder:
            mock_instance = AsyncMock()
            mock_instance.build = AsyncMock(return_value=MagicMock(
                doc_excerpt="测试文档",
                knowledge_hits=[],
                project_summary="项目A",
                citations=[],
                token_estimate=100,
            ))
            MockBuilder.return_value = mock_instance

            result = await doc_ai_chat(
                "workpaper", str(uuid.uuid4()), req,
                db=mock_db, current_user=mock_user,
            )

        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_chat_invalid_project_id_returns_400(self, mock_db, mock_user):
        """无效 project_id 返回 400"""
        from app.routers.doc_ai_chat import doc_ai_chat, DocChatRequest

        req = DocChatRequest(
            query="测试",
            year=2025,
            project_id="invalid-uuid",
        )

        with pytest.raises(Exception) as exc_info:
            await doc_ai_chat("workpaper", str(uuid.uuid4()), req, db=mock_db, current_user=mock_user)
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Unit Tests: _build_messages helper
# ---------------------------------------------------------------------------


class TestBuildMessages:
    """_build_messages 消息构建"""

    def test_build_messages_includes_system_prompt(self, mock_user):
        """消息列表包含 system prompt"""
        from app.routers.doc_ai_chat import _build_messages, ChatContext, SYSTEM_PROMPT

        context = ChatContext(
            doc_excerpt="",
            knowledge_hits=[],
            project_summary="",
            citations=[],
            token_estimate=0,
        )

        messages = _build_messages("workpaper", "test-id", "问题", context, mock_user)
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT

    def test_build_messages_includes_context(self, mock_user):
        """有上下文时注入到消息列表"""
        from app.routers.doc_ai_chat import _build_messages, ChatContext

        context = ChatContext(
            doc_excerpt="底稿内容",
            knowledge_hits=[],
            project_summary="项目：测试项目",
            citations=[],
            token_estimate=100,
        )

        messages = _build_messages("workpaper", "test-id", "问题", context, mock_user)
        # system prompt + context + user message
        assert len(messages) >= 3
        # 第二条是上下文
        assert "项目信息" in messages[1]["content"] or "当前文档内容" in messages[1]["content"]

    def test_build_messages_includes_user_query(self, mock_user):
        """最后一条是用户消息"""
        from app.routers.doc_ai_chat import _build_messages, ChatContext

        context = ChatContext(
            doc_excerpt="",
            knowledge_hits=[],
            project_summary="",
            citations=[],
            token_estimate=0,
        )

        messages = _build_messages("workpaper", "test-id", "我的问题", context, mock_user)
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "我的问题"
