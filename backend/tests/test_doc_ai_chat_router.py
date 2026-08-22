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

# Task 1 起端点先过 ResourceAccessResolver；宿主放行替身的唯一真源见该模块 docstring。
from ._ai_chat_host_stub import allow_ai_host  # noqa: F401

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


def _adopt_request(**overrides):
    """Task 7 契约的最小合法 adopt 请求（无 content 字段可传）。"""
    from app.routers.doc_ai_chat import AdoptHostRef, AdoptRequest

    payload = {
        "message_id": uuid.uuid4(),
        "host": AdoptHostRef(type="workpaper", id=str(uuid.uuid4())),
        "idempotency_key": uuid.uuid4(),
    }
    payload.update(overrides)
    return AdoptRequest(**payload)


class TestAdoptEndpoint:
    """POST /api/ai-chat/adopt — 路由层契约与失败映射（Task 7）

    ⚠️ 采纳的**下游行为**（服务端权威正文、收据幂等、``ai_content_log`` 写入失败回滚、
    哈希链审计）自 Task 7 起是真正 DB 绑定的能力，判据落在
    ``backend/tests/dsh_agent_panel/test_task7_adopt_fail_closed.py`` 的真实 PostgreSQL
    上。本类只保留**不需要数据库**就能真实执行的三件事：请求契约、授权前置、失败映射。
    在 ``AsyncMock`` 数据库上重演确认流写入需要把读消息/收据/存在性核验全部替身掉，
    那样的"通过"只证明替身自己一致，是典型假绿。
    """

    def test_adopt_request_rejects_client_content_and_requires_server_ids(self):
        """请求体不接受客户端正文，且必须带服务端 message ID + 幂等键。

        Feature dsh-agent-panel-integration Req 8.1：采纳引用 message ID，不把客户端
        正文当权威来源。旧契约的 ``content`` / ``confidence`` 字段是本 Task 修掉的缺陷。
        """
        from pydantic import ValidationError
        from app.routers.doc_ai_chat import AdoptRequest

        assert "content" not in AdoptRequest.model_fields
        assert "confidence" not in AdoptRequest.model_fields

        _adopt_request()  # 新契约可构造

        with pytest.raises(ValidationError):
            _adopt_request(content="浏览器伪造的 AI 正文")
        with pytest.raises(ValidationError):
            _adopt_request(confidence=0.99)

    @pytest.mark.asyncio
    async def test_adopt_invalid_project_id_is_non_enumerable_404(self, mock_db, mock_user):
        """无效 project 断言返回不可枚举 404（授权前置，且先于任何写入）

        Feature dsh-agent-panel-integration Req 2.5：无权与不存在对外使用同一响应语义，
        非法标识也不得通过状态码差异被枚举。
        """
        from app.routers.doc_ai_chat import AdoptHostRef, adopt_ai_content
        from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL

        req = _adopt_request(
            host=AdoptHostRef(
                type="workpaper", id=str(uuid.uuid4()), project_id="not-a-uuid"
            )
        )

        with patch(
            "app.routers.doc_ai_chat.adopt_message", new_callable=AsyncMock
        ) as adopt_service:
            with pytest.raises(Exception) as exc_info:
                await adopt_ai_content(req, db=mock_db, current_user=mock_user)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == EXTERNAL_NOT_FOUND_DETAIL
        adopt_service.assert_not_called()

    @pytest.mark.asyncio
    async def test_adopt_success_reports_confirm_flow_and_pending(
        self, mock_db, mock_user, allow_ai_host
    ):
        """服务层给出有效 log ID 时，响应为 pending + "已进入确认流"。"""
        from app.routers.doc_ai_chat import adopt_ai_content
        from app.services.ai_chat.adopt import ADOPT_CONFIRM_FLOW_MESSAGE, AdoptOutcome

        log_id = uuid.uuid4()
        message_id = uuid.uuid4()
        outcome = AdoptOutcome(
            ai_content_log_id=log_id,
            content_hash="a" * 64,
            message_id=message_id,
            receipt_id=uuid.uuid4(),
            idempotent_replay=False,
        )
        req = _adopt_request(message_id=message_id)

        with patch(
            "app.routers.doc_ai_chat.adopt_message",
            new_callable=AsyncMock,
            return_value=outcome,
        ) as adopt_service:
            result = await adopt_ai_content(req, db=mock_db, current_user=mock_user)

        assert result["success"] is True
        assert result["confirm_action"] == "pending"
        assert result["ai_content_log_id"] == str(log_id)
        assert result["message"] == ADOPT_CONFIRM_FLOW_MESSAGE
        # 服务层拿到的是**服务端** message ID 与幂等键，没有任何正文字段
        kwargs = adopt_service.call_args.kwargs
        assert kwargs["message_id"] == message_id
        assert kwargs["idempotency_key"] == req.idempotency_key
        assert "content" not in kwargs

    @pytest.mark.asyncio
    async def test_adopt_log_failure_maps_to_typed_non_success_response(
        self, mock_db, mock_user, allow_ai_host
    ):
        """服务层报 ``adopt_log_failed`` ⇒ 503 + typed code，绝不返回成功文案。

        Property 33：下游故障不产生假成功。
        """
        from fastapi import HTTPException
        from app.routers.doc_ai_chat import adopt_ai_content
        from app.services.ai_chat.adopt import (
            ADOPT_ERROR_MESSAGE,
            ADOPT_LOG_FAILED,
            AdoptFailed,
        )

        with patch(
            "app.routers.doc_ai_chat.adopt_message",
            new_callable=AsyncMock,
            side_effect=AdoptFailed(ADOPT_LOG_FAILED, "注入：日志写入失败"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await adopt_ai_content(req=_adopt_request(), db=mock_db, current_user=mock_user)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["code"] == ADOPT_LOG_FAILED
        assert exc_info.value.detail["message"] == ADOPT_ERROR_MESSAGE[ADOPT_LOG_FAILED]
        assert "已进入确认流" not in exc_info.value.detail["message"]
        # 内部异常细节不外泄（Req 12.5）
        assert "注入" not in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# Unit Tests: history endpoint
# ---------------------------------------------------------------------------


class TestHistoryEndpoint:
    """GET /api/ai-chat/doc/{doc_type}/{doc_id}/history"""

    @pytest.mark.asyncio
    async def test_get_empty_history(self, mock_db, mock_user, allow_ai_host):
        """无历史时返回空列表（历史来自 doc_chat_persistence，非内存字典）"""
        from app.routers.doc_ai_chat import get_chat_history

        with patch(
            "app.services.doc_chat_persistence.get_history",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await get_chat_history(
                "workpaper",
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                db=mock_db,
                current_user=mock_user,
            )
        assert result["messages"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_get_existing_history(self, mock_db, mock_user, allow_ai_host):
        """有历史时按服务端顺序返回消息列表"""
        from app.routers.doc_ai_chat import get_chat_history

        stored = [
            {"role": "user", "content": "什么是审计抽样？"},
            {"role": "assistant", "content": "审计抽样是..."},
        ]
        with patch(
            "app.services.doc_chat_persistence.get_history",
            new_callable=AsyncMock,
            return_value=stored,
        ) as mock_history:
            result = await get_chat_history(
                "workpaper",
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                db=mock_db,
                current_user=mock_user,
            )
        assert result["total"] == 2
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"
        # 服务端按当前用户 scope 取历史，不接受客户端传入的 user 身份
        assert mock_history.call_args.args[3] == mock_user.id

    @pytest.mark.asyncio
    async def test_history_denied_before_reading_messages(self, mock_db, mock_user):
        """无权宿主：拒绝先于任何历史消息读取（Req 2.1/2.4）"""
        from app.routers.doc_ai_chat import get_chat_history
        from app.services.ai_chat.contracts import AccessDecision
        from app.services.wp_visibility.denial import ExternalNotFound

        async def _deny(db, current_user, **kwargs):
            raise ExternalNotFound()

        with patch("app.routers.doc_ai_chat._authorize_doc_host", _deny), patch(
            "app.services.doc_chat_persistence.get_history", new_callable=AsyncMock
        ) as mock_history:
            with pytest.raises(ExternalNotFound):
                await get_chat_history(
                    "workpaper",
                    str(uuid.uuid4()),
                    str(uuid.uuid4()),
                    db=mock_db,
                    current_user=mock_user,
                )
        mock_history.assert_not_called()
        assert AccessDecision is not None  # 契约模块可导入（防止 import 漂移静默失效）


# ---------------------------------------------------------------------------
# Unit Tests: streaming chat endpoint
# ---------------------------------------------------------------------------


class TestDocAiChatEndpoint:
    """POST /api/ai-chat/doc/{doc_type}/{doc_id} — streaming"""

    @pytest.mark.asyncio
    async def test_chat_returns_streaming_response(self, mock_db, mock_user, allow_ai_host):
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
    async def test_chat_invalid_project_id_is_non_enumerable_404(self, mock_db, mock_user):
        """无效 project_id 返回不可枚举 404（Req 2.5）"""
        from app.routers.doc_ai_chat import doc_ai_chat, DocChatRequest
        from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL

        req = DocChatRequest(
            query="测试",
            year=2025,
            project_id="invalid-uuid",
        )

        with pytest.raises(Exception) as exc_info:
            await doc_ai_chat("workpaper", str(uuid.uuid4()), req, db=mock_db, current_user=mock_user)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == EXTERNAL_NOT_FOUND_DETAIL


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
