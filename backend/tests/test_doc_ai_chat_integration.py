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
    AdoptRequest,
    _chat_history,
    _history_key,
    _build_messages,
)


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
    """每个测试前清空对话历史"""
    _chat_history.clear()
    yield
    _chat_history.clear()


# ---------------------------------------------------------------------------
# 集成测试：ContextBuilder → 对话端点 → 采纳回写 全链路
# ---------------------------------------------------------------------------


class TestFullChainIntegration:
    """全链路集成测试：build context → chat → adopt → pending confirmation

    验证 D4 属性端到端：AI 内容经 wrap_ai_output_with_log → pending 状态
    """

    @pytest.mark.asyncio
    async def test_full_chain_context_to_chat_to_adopt(self, mock_db, mock_user):
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
        ai_generated_content = "经核查，银行存款期末余额变动合理，与银行对账单一致。"

        adopt_req = AdoptRequest(
            content=ai_generated_content,
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
            "content_hash": "abc123" * 10 + "abcd",
            "content": ai_generated_content,
        }

        with patch(
            "app.services.wp_ai_service.wrap_ai_output_with_log",
            new_callable=AsyncMock,
            return_value=mock_wrap_result,
        ) as mock_wrap:
            result = await adopt_ai_content(adopt_req, db=mock_db, current_user=mock_user)

            # D4 断言：wrap_ai_output_with_log 被调用
            mock_wrap.assert_called_once()

            # D4 断言：返回 pending 状态（未直接写入文档）
            assert result["success"] is True
            assert result["confirm_action"] == "pending"
            assert result["ai_content_log_id"] is not None

            # D4 断言：传递了正确的参数
            call_kwargs = mock_wrap.call_args.kwargs
            assert call_kwargs["content"] == ai_generated_content
            assert call_kwargs["project_id"] == project_id
            assert call_kwargs["user_id"] == mock_user.id
            assert call_kwargs["instance_type"] == "workpaper"
            assert call_kwargs["instance_id"] == doc_id
            assert call_kwargs["target_cell"] == "E5"
            assert call_kwargs["confidence"] == 0.9

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

        messages = _build_messages("note", "note-id", "折旧政策是否合规？", context, mock_user)

        # 验证消息结构完整
        assert messages[0]["role"] == "system"
        # 上下文注入
        context_msg = messages[1]["content"]
        assert "固定资产折旧政策" in context_msg or "测试项目" in context_msg
        # 用户消息在最后
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "折旧政策是否合规？"

    @pytest.mark.asyncio
    async def test_adopt_never_writes_directly_to_document(self, mock_db, mock_user):
        """D4 核心：adopt 端点永远不直接写入文档，只写 ai_content_log（pending）

        验证：wrap_ai_output_with_log 被调用时传入 db + 5 参齐全 → 写 ai_content_log
        而非直接修改底稿/附注表。
        """
        project_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        adopt_req = AdoptRequest(
            content="AI 建议：应补提折旧 50,000 元",
            project_id=str(project_id),
            doc_type="note",
            doc_id=str(doc_id),
            target_field="depreciation_adjustment",
            confidence=0.85,
        )

        mock_wrap_result = {
            "ai_content_log_id": str(uuid.uuid4()),
            "confirm_action": "pending",
            "content_hash": "x" * 64,
        }

        with patch(
            "app.services.wp_ai_service.wrap_ai_output_with_log",
            new_callable=AsyncMock,
            return_value=mock_wrap_result,
        ) as mock_wrap:
            result = await adopt_ai_content(adopt_req, db=mock_db, current_user=mock_user)

            # D4: 确认走了 wrap_ai_output_with_log（写 ai_content_log 表）
            mock_wrap.assert_called_once()
            call_kwargs = mock_wrap.call_args.kwargs

            # 5 参齐全 → 触发写 ai_content_log
            assert call_kwargs["db"] is mock_db
            assert call_kwargs["project_id"] == project_id
            assert call_kwargs["user_id"] == mock_user.id
            assert call_kwargs["instance_type"] == "note"
            assert call_kwargs["instance_id"] == doc_id

            # 返回 pending（未确认，不直接写文档）
            assert result["confirm_action"] == "pending"

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

        with patch("app.routers.doc_ai_chat.AIService") as MockAI:
            mock_ai_instance = MagicMock()
            mock_ai_instance.chat_completion = AsyncMock(return_value=mock_stream())
            MockAI.return_value = mock_ai_instance

            events = []
            async for event in _stream_chat(
                mock_db, "workpaper", "doc-1", "问题", context, mock_user
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
    async def test_chat_history_persists_after_streaming(self, mock_db, mock_user):
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

        with patch("app.routers.doc_ai_chat.AIService") as MockAI:
            mock_ai_instance = MagicMock()
            mock_ai_instance.chat_completion = AsyncMock(return_value=mock_stream())
            MockAI.return_value = mock_ai_instance

            # 消费 streaming
            async for _ in _stream_chat(
                mock_db, "workpaper", doc_id, "用户问题", context, mock_user
            ):
                pass

        # 验证历史记录
        result = await get_chat_history("workpaper", doc_id, current_user=mock_user)
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

    验证完整流程中 D4 门禁不可绕过。
    """

    @pytest.mark.asyncio
    async def test_d4_multiple_adopt_all_pending(self, mock_db, mock_user):
        """D4: 多次采纳操作全部返回 pending（确认流不可绕过）"""
        project_id = uuid.uuid4()

        contents = [
            "AI 结论 1：余额合理",
            "AI 结论 2：需补提减值",
            "AI 结论 3：关联交易已披露",
        ]

        for content in contents:
            doc_id = uuid.uuid4()
            req = AdoptRequest(
                content=content,
                project_id=str(project_id),
                doc_type="workpaper",
                doc_id=str(doc_id),
                confidence=0.85,
            )

            mock_wrap_result = {
                "ai_content_log_id": str(uuid.uuid4()),
                "confirm_action": "pending",
                "content_hash": "h" * 64,
            }

            with patch(
                "app.services.wp_ai_service.wrap_ai_output_with_log",
                new_callable=AsyncMock,
                return_value=mock_wrap_result,
            ):
                result = await adopt_ai_content(req, db=mock_db, current_user=mock_user)

                # D4: 每次都是 pending
                assert result["confirm_action"] == "pending"
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_d4_adopt_with_different_doc_types(self, mock_db, mock_user):
        """D4: 不同文档类型的采纳都走确认流"""
        project_id = uuid.uuid4()
        doc_types = ["workpaper", "note", "report", "knowledge_doc"]

        for doc_type in doc_types:
            doc_id = uuid.uuid4()
            req = AdoptRequest(
                content=f"AI 内容 for {doc_type}",
                project_id=str(project_id),
                doc_type=doc_type,
                doc_id=str(doc_id),
                confidence=0.8,
            )

            mock_wrap_result = {
                "ai_content_log_id": str(uuid.uuid4()),
                "confirm_action": "pending",
                "content_hash": "z" * 64,
            }

            with patch(
                "app.services.wp_ai_service.wrap_ai_output_with_log",
                new_callable=AsyncMock,
                return_value=mock_wrap_result,
            ) as mock_wrap:
                result = await adopt_ai_content(req, db=mock_db, current_user=mock_user)

                # D4: 所有文档类型都走确认流
                assert result["confirm_action"] == "pending"
                mock_wrap.assert_called_once()

                # 验证 instance_type 正确传递
                assert mock_wrap.call_args.kwargs["instance_type"] == doc_type

    @pytest.mark.asyncio
    async def test_d4_wrap_receives_all_five_mandatory_params(self, mock_db, mock_user):
        """D4: wrap_ai_output_with_log 必须收到 5 个强制参数（触发写 ai_content_log）"""
        project_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        req = AdoptRequest(
            content="AI 生成内容",
            project_id=str(project_id),
            doc_type="workpaper",
            doc_id=str(doc_id),
            target_cell="F10",
            target_field="amount",
            confidence=0.92,
        )

        mock_wrap_result = {
            "ai_content_log_id": str(uuid.uuid4()),
            "confirm_action": "pending",
            "content_hash": "m" * 64,
        }

        with patch(
            "app.services.wp_ai_service.wrap_ai_output_with_log",
            new_callable=AsyncMock,
            return_value=mock_wrap_result,
        ) as mock_wrap:
            await adopt_ai_content(req, db=mock_db, current_user=mock_user)

            call_kwargs = mock_wrap.call_args.kwargs

            # 5 个强制参数（齐全时写 ai_content_log 表）
            assert call_kwargs["db"] is not None, "D4: db 参数缺失"
            assert call_kwargs["project_id"] is not None, "D4: project_id 参数缺失"
            assert call_kwargs["user_id"] is not None, "D4: user_id 参数缺失"
            assert call_kwargs["instance_type"] is not None, "D4: instance_type 参数缺失"
            assert call_kwargs["instance_id"] is not None, "D4: instance_id 参数缺失"

            # 额外参数也正确传递
            assert call_kwargs["content"] == "AI 生成内容"
            assert call_kwargs["target_cell"] == "F10"
            assert call_kwargs["target_field"] == "amount"
            assert call_kwargs["confidence"] == 0.92
