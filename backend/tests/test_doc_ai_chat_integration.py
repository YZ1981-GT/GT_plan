"""文档级 AI 对话 — 全链路集成测试

测试完整链路：ContextBuilder → 对话端点 → 采纳回写（D4 确认流门禁）

验证 D4 属性端到端：
- AI 内容经 wrap_ai_output_with_log → pending 状态
- 从未直接写入底稿/附注

需求: 4.1  属性: D4
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.doc_ai_context_builder import (
    ContextBuilder,
    ChatContext,
    SearchHit,
    Citation,
)
from app.routers.doc_ai_chat import (
    doc_ai_chat,
    adopt_ai_content,
    get_chat_history,
    DocChatRequest,
    AdoptHostRef,
    AdoptRequest,
    _build_messages,
)

# Task 1 起端点先过 ResourceAccessResolver；宿主放行替身的唯一真源见该模块 docstring。
from ._ai_chat_host_stub import allow_ai_host  # noqa: F401


def _adopt_request(**overrides) -> AdoptRequest:
    """Task 7 契约的最小合法 adopt 请求（**没有** content / confidence 可传）。"""
    payload = {
        "message_id": uuid.uuid4(),
        "host": AdoptHostRef(type="workpaper", id=str(uuid.uuid4())),
        "idempotency_key": uuid.uuid4(),
    }
    payload.update(overrides)
    return AdoptRequest(**payload)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user():
    """模拟当前用户"""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "integration_test_user"
    user.role = MagicMock()
    user.role.value = "auditor"
    return user


@pytest.fixture
def mock_db():
    """模拟 AsyncSession"""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def clear_chat_history():
    """每个测试前清空对话历史（已迁移到 DB 持久化，此 fixture 为空操作）"""
    yield


# ---------------------------------------------------------------------------
# 集成测试：ContextBuilder → 对话端点 → 采纳回写 全链路
# ---------------------------------------------------------------------------


class TestFullChainIntegration:
    """全链路集成测试：build context → chat → adopt → pending confirmation

    验证 D4 属性端到端：AI 内容经 wrap_ai_output_with_log → pending 状态
    """

    @pytest.mark.asyncio
    async def test_full_chain_context_to_chat_to_adopt(self, mock_db, mock_user, allow_ai_host):
        """全链路：ContextBuilder 构建上下文 → 对话端点 streaming → 采纳走确认流

        D4: AI 生成内容回写前必经 AIContentMustBeConfirmedRule（pending 状态）
        """
        project_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        # ── Step 1: ContextBuilder 构建上下文 ──
        context = ChatContext(
            doc_excerpt="底稿 E1-1 银行存款：期末余额 1,234,567.89",
            knowledge_hits=[
                SearchHit(
                    source_type="workpaper",
                    source_id=str(uuid.uuid4()),
                    content="审计程序：检查银行对账单与账面余额的一致性",
                    score=0.92,
                    chunk_index=0,
                    source_name="E1-1 银行存款",
                ),
            ],
            project_summary="项目：首汽租车_2025，客户：首汽租车",
            citations=[
                Citation(
                    source_type="workpaper",
                    source_id=str(uuid.uuid4()),
                    source_name="E1-1 银行存款",
                    paragraph_index=0,
                    excerpt="检查银行对账单",
                ),
            ],
            token_estimate=200,
        )

        # ── Step 2: 对话端点返回 streaming 响应 ──
        chat_req = DocChatRequest(
            query="银行存款期末余额变动是否合理？",
            year=2025,
            project_id=str(project_id),
        )

        with patch("app.routers.doc_ai_chat.ContextBuilder") as MockBuilder:
            mock_instance = AsyncMock()
            mock_instance.build = AsyncMock(return_value=context)
            MockBuilder.return_value = mock_instance

            from fastapi.responses import StreamingResponse

            response = await doc_ai_chat(
                "workpaper", str(doc_id), chat_req,
                db=mock_db, current_user=mock_user,
            )

            assert isinstance(response, StreamingResponse)
            assert response.media_type == "text/event-stream"

        # ── Step 3: 采纳 AI 内容 → 走确认流（D4 核心验证）──
        # Task 7：端点只提交服务端 message ID + 宿主 + 幂等键，正文由服务层读库。
        from app.services.ai_chat.adopt import ADOPT_CONFIRM_FLOW_MESSAGE, AdoptOutcome

        message_id = uuid.uuid4()
        log_id = uuid.uuid4()
        adopt_req = _adopt_request(
            message_id=message_id,
            host=AdoptHostRef(
                type="workpaper", id=str(doc_id), project_id=str(project_id)
            ),
            target_cell="E5",
        )
        outcome = AdoptOutcome(
            ai_content_log_id=log_id,
            content_hash="abc123" * 10 + "abcd",
            message_id=message_id,
            receipt_id=uuid.uuid4(),
            idempotent_replay=False,
        )

        with patch(
            "app.routers.doc_ai_chat.adopt_message",
            new_callable=AsyncMock,
            return_value=outcome,
        ) as adopt_service:
            result = await adopt_ai_content(adopt_req, db=mock_db, current_user=mock_user)

            # D4 断言：采纳只走 server-authoritative 服务层
            adopt_service.assert_called_once()

            # D4 断言：返回 pending 状态（未直接写入文档）
            assert result["success"] is True
            assert result["confirm_action"] == "pending"
            assert result["ai_content_log_id"] == str(log_id)
            assert result["message"] == ADOPT_CONFIRM_FLOW_MESSAGE

            # D4 断言：服务层收到的是服务端 ID 与已授权宿主，没有任何客户端正文
            call_kwargs = adopt_service.call_args.kwargs
            assert call_kwargs["message_id"] == message_id
            assert call_kwargs["actor_id"] == mock_user.id
            assert call_kwargs["host"].project_id == project_id
            assert call_kwargs["host"].resource_id == str(doc_id)
            assert call_kwargs["target_cell"] == "E5"
            assert "content" not in call_kwargs and "confidence" not in call_kwargs

    @pytest.mark.asyncio
    async def test_context_builder_feeds_chat_endpoint(self, mock_db, mock_user):
        """ContextBuilder 输出正确传递给对话端点的 _build_messages"""
        context = ChatContext(
            doc_excerpt="附注第三章：固定资产折旧政策",
            knowledge_hits=[
                SearchHit(
                    source_type="knowledge_doc",
                    source_id=str(uuid.uuid4()),
                    content="CAS 4 号准则：固定资产折旧方法",
                    score=0.88,
                    chunk_index=2,
                    source_name="CAS4-固定资产",
                ),
            ],
            project_summary="项目：测试项目_2025",
            citations=[],
            token_estimate=150,
        )

        messages = _build_messages("note", "note-id", "折旧政策是否合规？", context, [])

        # 验证消息结构完整
        assert messages[0]["role"] == "system"
        # 上下文注入
        context_msg = messages[1]["content"]
        assert "固定资产折旧政策" in context_msg or "测试项目" in context_msg
        # 用户消息在最后
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "折旧政策是否合规？"

    @pytest.mark.asyncio
    async def test_adopt_never_writes_directly_to_document(self, mock_db, mock_user, allow_ai_host):
        """D4 核心：adopt 端点永远不直接写入文档，只经确认流服务层（pending）

        Task 7：端点自己不再持有任何写入语句 —— 唯一出口是
        ``adopt_message``（内部写 ``ai_content_log`` pending + 收据 + 哈希链审计）。
        本判据断言"端点在服务层被替身掉之后对数据库零写入"，即不存在第二条旁路。
        """
        from app.services.ai_chat.adopt import AdoptOutcome

        message_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        adopt_req = _adopt_request(
            message_id=message_id,
            host=AdoptHostRef(type="note", id=str(doc_id)),
            target_field="depreciation_adjustment",
        )
        outcome = AdoptOutcome(
            ai_content_log_id=uuid.uuid4(),
            content_hash="x" * 64,
            message_id=message_id,
            receipt_id=uuid.uuid4(),
            idempotent_replay=False,
        )

        mock_db.add = MagicMock()
        with patch(
            "app.routers.doc_ai_chat.adopt_message",
            new_callable=AsyncMock,
            return_value=outcome,
        ) as adopt_service:
            result = await adopt_ai_content(adopt_req, db=mock_db, current_user=mock_user)

        adopt_service.assert_called_once()
        assert result["confirm_action"] == "pending"
        # 端点自身零写入：既不 add ORM 对象，也不 execute 任何语句、也不 commit
        mock_db.add.assert_not_called()
        mock_db.execute.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_streaming_produces_sse_events(self, mock_db, mock_user):
        """对话端点 streaming 产出 SSE 事件（citations + content + done）"""
        from app.routers.doc_ai_chat import _stream_chat

        context = ChatContext(
            doc_excerpt="测试文档",
            knowledge_hits=[],
            project_summary="项目摘要",
            citations=[
                Citation(
                    source_type="workpaper",
                    source_id="cite-id-1",
                    source_name="E1-1",
                    paragraph_index=0,
                    excerpt="引用片段",
                ),
            ],
            token_estimate=50,
        )

        # Mock AIService streaming
        async def mock_stream():
            yield "审计"
            yield "结论"

        mock_session_obj = AsyncMock()
        mock_session_obj.commit = AsyncMock()

        # async_session 是在函数体内 local import，patch app.core.database.async_session
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session_obj)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.routers.doc_ai_chat.AIService") as MockAI, \
             patch("app.routers.doc_ai_chat.doc_chat_persistence") as mock_persist, \
             patch("app.core.database.async_session", return_value=mock_ctx):
            mock_ai_instance = MagicMock()
            mock_ai_instance.chat_completion = AsyncMock(return_value=mock_stream())
            MockAI.return_value = mock_ai_instance

            # Mock persistence layer
            mock_persist.get_or_create_session = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
            mock_persist.get_history = AsyncMock(return_value=[])
            mock_persist.append_message = AsyncMock()

            events = []
            async for event in _stream_chat(
                "workpaper", "doc-1", "问题", context, mock_user, uuid.uuid4()
            ):
                events.append(event)

        # 验证 SSE 事件结构
        assert len(events) >= 3  # citations + content chunks + done

        # 第一个事件是 citations
        first_data = json.loads(events[0].replace("data: ", "").strip())
        assert first_data["type"] == "citations"

        # 最后一个事件是 done
        last_data = json.loads(events[-1].replace("data: ", "").strip())
        assert last_data["type"] == "done"

    @pytest.mark.asyncio
    async def test_chat_history_persists_after_streaming(self, mock_db, mock_user, allow_ai_host):
        """对话后历史记录持久化（可通过 history 端点查询）"""
        from app.routers.doc_ai_chat import _stream_chat

        doc_id = "test-doc-persist"
        context = ChatContext(
            doc_excerpt="",
            knowledge_hits=[],
            project_summary="",
            citations=[],
            token_estimate=0,
        )

        async def mock_stream():
            yield "回答内容"

        with patch("app.routers.doc_ai_chat.AIService") as MockAI, \
             patch("app.routers.doc_ai_chat.doc_chat_persistence") as mock_persist, \
             patch("app.core.database.async_session") as mock_async_session:
            mock_ai_instance = MagicMock()
            mock_ai_instance.chat_completion = AsyncMock(return_value=mock_stream())
            MockAI.return_value = mock_ai_instance

            # Mock DB session context manager
            mock_session_obj = AsyncMock()
            mock_session_obj.commit = AsyncMock()
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session_obj)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_async_session.return_value = mock_ctx

            # Mock persistence layer
            mock_persist.get_or_create_session = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
            mock_persist.get_history = AsyncMock(return_value=[])
            mock_persist.append_message = AsyncMock()

            # 消费 streaming（_stream_chat 自建 session，不接受外部 db）
            async for _ in _stream_chat(
                "workpaper", doc_id, "用户问题", context, mock_user, uuid.uuid4()
            ):
                pass

        # 验证历史记录（DB 持久化后需传 db 参数）
        with patch("app.routers.doc_ai_chat.doc_chat_persistence") as mock_persist:
            mock_persist.get_history = AsyncMock(return_value=[
                {"role": "user", "content": "用户问题"},
                {"role": "assistant", "content": "回答内容"},
            ])
            result = await get_chat_history("workpaper", doc_id, db=mock_db, current_user=mock_user)
            assert result["total"] == 2
            assert result["messages"][0]["role"] == "user"
            assert result["messages"][0]["content"] == "用户问题"
            assert result["messages"][1]["role"] == "assistant"
            assert result["messages"][1]["content"] == "回答内容"


# ---------------------------------------------------------------------------
# D4 属性端到端验证
# ---------------------------------------------------------------------------


class TestD4EndToEnd:
    """D4 属性端到端：AI 内容必经确认流，永远不直接写入文档

    Task 7 后 D4 的成立依据从"端点把客户端 content 送进 wrap"改成"端点把**服务端
    message ID** 交给 server-authoritative 服务层"。写入侧行为（真实 ``ai_content_log``
    行、pending 状态、失败回滚）在
    ``backend/tests/dsh_agent_panel/test_task7_adopt_fail_closed.py`` 的真实 PostgreSQL
    上守卫；本类只验证**端点这一层**在各宿主类型下都不存在绕过确认流的旁路。
    """

    @pytest.mark.asyncio
    async def test_d4_all_host_types_go_through_server_authoritative_service(
        self, mock_db, mock_user, allow_ai_host
    ):
        """D4: 四类宿主的采纳都必须经 ``adopt_message``，且端点不接受任何正文。"""
        from app.services.ai_chat.adopt import AdoptOutcome

        for doc_type in ("workpaper", "note", "report", "knowledge_doc"):
            message_id = uuid.uuid4()
            doc_id = uuid.uuid4()
            req = _adopt_request(
                message_id=message_id,
                host=AdoptHostRef(type=doc_type, id=str(doc_id)),
            )
            outcome = AdoptOutcome(
                ai_content_log_id=uuid.uuid4(),
                content_hash="h" * 64,
                message_id=message_id,
                receipt_id=uuid.uuid4(),
                idempotent_replay=False,
            )
            with patch(
                "app.routers.doc_ai_chat.adopt_message",
                new_callable=AsyncMock,
                return_value=outcome,
            ) as adopt_service:
                result = await adopt_ai_content(
                    req, db=mock_db, current_user=mock_user
                )

            # D4: 每个宿主都以 pending 进入确认流，且没有第二条写入路径
            assert result["confirm_action"] == "pending"
            assert result["success"] is True
            adopt_service.assert_called_once()
            kwargs = adopt_service.call_args.kwargs
            assert kwargs["message_id"] == message_id
            assert kwargs["host"].resource_type.value == doc_type
            assert "content" not in kwargs, "端点仍在向服务层传正文"

    @pytest.mark.asyncio
    async def test_d4_typed_failure_never_reports_success(
        self, mock_db, mock_user, allow_ai_host
    ):
        """D4 + Property 33: 确认流写入失败时端点不得返回成功。"""
        from fastapi import HTTPException
        from app.services.ai_chat.adopt import ADOPT_LOG_FAILED, AdoptFailed

        with patch(
            "app.routers.doc_ai_chat.adopt_message",
            new_callable=AsyncMock,
            side_effect=AdoptFailed(ADOPT_LOG_FAILED, "注入：确认流记录未写入"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await adopt_ai_content(
                    _adopt_request(), db=mock_db, current_user=mock_user
                )
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["code"] == ADOPT_LOG_FAILED
