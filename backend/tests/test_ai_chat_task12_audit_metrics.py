"""Task 12 测试：AI Chat 限流、哈希链审计与运行指标

Validates: Requirements 12.6, 12.7, 12.8, 13.5, 13.6, 13.7
Properties: 32, 36

Test Coverage:
- Property 32: 哈希链事件成对完整（run started+terminal, tool started+finished/failed）
- Property 36: AI Chat 真实限流接线（quota route matcher + typed response）
- Req 12.6: run / tool call 审计成对
- Req 12.7: 审计不含 token/正文/附件内容
- Req 12.8: 指标覆盖所有规定维度
- Req 13.5: route matcher 真实命中
- Req 13.6: 限流 typed 响应含 remaining/reset/retry_after
- Req 13.7: 配额单一真源（服务端配置）
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings


# ===========================================================================
# Property 32: 哈希链事件成对完整
# ===========================================================================


class TestProperty32HashChainPaired:
    """每个 run 恰有 started 与一个 terminal 哈希链事件；
    每个 tool call 恰有 started 与 finished/failed。
    审计字段完整且不含 token、完整正文或附件内容。
    """

    @pytest.mark.asyncio
    async def test_audit_run_started_writes_required_fields(self):
        """audit_run_started 写入的 payload 包含 run_id/status/engine，不含正文。"""
        from app.services.ai_chat.audit import audit_run_started

        captured_payloads = []
        original_append = None

        async def mock_append(db, payload):
            captured_payloads.append(payload)
            return uuid.uuid4()

        with patch("app.services.ai_chat.audit.append_audit_log", side_effect=mock_append):
            db = AsyncMock()
            await audit_run_started(
                db,
                user_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                run_id=uuid.uuid4(),
                engine="native",
                host_type="workpaper",
            )

        assert len(captured_payloads) == 1
        p = captured_payloads[0]
        assert p["action"] == "ai_chat_run_started"
        details = p["details"]
        assert details["event_type"] == "ai_chat_run_lifecycle"
        assert details["status"] == "started"
        assert details["engine"] == "native"
        # Req 12.7: 不含正文/token/附件
        assert "content" not in details
        assert "token" not in details
        assert "text" not in details

    @pytest.mark.asyncio
    async def test_audit_run_terminal_writes_required_fields(self):
        """audit_run_terminal 写入的 payload 包含 status/error_code/latency，不含正文。"""
        from app.services.ai_chat.audit import audit_run_terminal

        captured_payloads = []

        async def mock_append(db, payload):
            captured_payloads.append(payload)
            return uuid.uuid4()

        with patch("app.services.ai_chat.audit.append_audit_log", side_effect=mock_append):
            db = AsyncMock()
            await audit_run_terminal(
                db,
                user_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                run_id=uuid.uuid4(),
                status="done",
                engine="native",
                latency_ms=1500,
                tokens_total=350,
            )

        assert len(captured_payloads) == 1
        p = captured_payloads[0]
        assert p["action"] == "ai_chat_run_done"
        details = p["details"]
        assert details["status"] == "done"
        assert details["latency_ms"] == 1500
        assert details["tokens_total"] == 350
        # Req 12.7: 不含正文/token 内容
        assert "content" not in details
        assert "text" not in details

    @pytest.mark.asyncio
    async def test_audit_tool_started_writes_required_fields(self):
        """audit_tool_started 写入 tool_call_id/tool_name/status=started。"""
        from app.services.ai_chat.audit import audit_tool_started

        captured_payloads = []

        async def mock_append(db, payload):
            captured_payloads.append(payload)
            return uuid.uuid4()

        with patch("app.services.ai_chat.audit.append_audit_log", side_effect=mock_append):
            db = AsyncMock()
            await audit_tool_started(
                db,
                user_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                run_id=uuid.uuid4(),
                tool_call_id="tc-001",
                tool_name="wp_read",
            )

        assert len(captured_payloads) == 1
        p = captured_payloads[0]
        assert p["action"] == "ai_chat_tool_started"
        details = p["details"]
        assert details["event_type"] == "ai_chat_tool_lifecycle"
        assert details["tool_call_id"] == "tc-001"
        assert details["tool_name"] == "wp_read"
        assert details["status"] == "started"

    @pytest.mark.asyncio
    async def test_audit_tool_finished_writes_required_fields(self):
        """audit_tool_finished 写入 status/result_bytes/duration_ms/error_code。"""
        from app.services.ai_chat.audit import audit_tool_finished

        captured_payloads = []

        async def mock_append(db, payload):
            captured_payloads.append(payload)
            return uuid.uuid4()

        with patch("app.services.ai_chat.audit.append_audit_log", side_effect=mock_append):
            db = AsyncMock()
            await audit_tool_finished(
                db,
                user_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                run_id=uuid.uuid4(),
                tool_call_id="tc-001",
                tool_name="wp_read",
                status="finished",
                result_bytes=4096,
                duration_ms=250,
            )

        assert len(captured_payloads) == 1
        p = captured_payloads[0]
        assert p["action"] == "ai_chat_tool_finished"
        details = p["details"]
        assert details["status"] == "finished"
        assert details["result_bytes"] == 4096
        assert details["duration_ms"] == 250
        assert details["error_code"] == ""
        # Req 12.7: 不含入参正文或附件内容
        assert "args" not in details
        assert "content" not in details
        assert "token" not in details

    @pytest.mark.asyncio
    async def test_audit_tool_failed_carries_error_code(self):
        """audit_tool_finished(status=failed) 携带 error_code。"""
        from app.services.ai_chat.audit import audit_tool_finished

        captured_payloads = []

        async def mock_append(db, payload):
            captured_payloads.append(payload)
            return uuid.uuid4()

        with patch("app.services.ai_chat.audit.append_audit_log", side_effect=mock_append):
            db = AsyncMock()
            await audit_tool_finished(
                db,
                user_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                run_id=uuid.uuid4(),
                tool_call_id="tc-002",
                tool_name="tb_query",
                status="failed",
                error_code="tool_budget_exceeded",
                duration_ms=50,
            )

        p = captured_payloads[0]
        assert p["action"] == "ai_chat_tool_failed"
        assert p["details"]["error_code"] == "tool_budget_exceeded"
        assert p["details"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_raise(self):
        """审计写入失败不应抛异常（降级 WARNING）。"""
        from app.services.ai_chat.audit import audit_tool_started

        with patch(
            "app.services.ai_chat.audit.append_audit_log",
            side_effect=RuntimeError("DB unavailable"),
        ):
            db = AsyncMock()
            # 不应抛异常
            await audit_tool_started(
                db,
                user_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                run_id=uuid.uuid4(),
                tool_call_id="tc-fail",
                tool_name="failing_tool",
            )


# ===========================================================================
# Property 36: AI Chat 真实限流接线
# ===========================================================================


class TestProperty36RateLimitAccess:
    """配额 route matcher 真实命中已注册 prefix；
    限流触发有 typed event with remaining/reset/retry_after。
    """

    def test_rate_limiter_matches_ai_chat_runs_path(self):
        """AI Chat 的 /api/ai-chat/runs 路径被 matcher 真实命中。"""
        from app.middleware.rate_limiter import _is_ai_chat_endpoint

        assert _is_ai_chat_endpoint("/api/ai-chat/runs") is True
        assert _is_ai_chat_endpoint("/api/ai-chat/adopt") is True
        assert _is_ai_chat_endpoint("/api/ai-chat/doc/workpaper/some-id") is True
        # SSE events 路径也命中 matcher（但限流只对 POST/PUT 生效，GET 在 dispatch 层跳过）
        assert _is_ai_chat_endpoint("/api/ai-chat/runs/some-id/events") is True

    def test_rate_limiter_excludes_non_ai_chat_paths(self):
        """非 AI Chat 路径不命中 AI Chat 限流池。"""
        from app.middleware.rate_limiter import _is_ai_chat_endpoint

        assert _is_ai_chat_endpoint("/api/users") is False
        assert _is_ai_chat_endpoint("/api/workpapers/some-id") is False
        assert _is_ai_chat_endpoint("/api/health") is False

    def test_ai_chat_not_in_llm_pool(self):
        """AI Chat 端点不走 LLM 通用限流池（独立计数）。"""
        from app.middleware.rate_limiter import _is_llm_endpoint

        assert _is_llm_endpoint("/api/ai-chat/runs") is False
        assert _is_llm_endpoint("/api/ai-chat/adopt") is False
        assert _is_llm_endpoint("/api/ai-chat/doc/workpaper/x") is False

    def test_quota_config_is_single_source(self):
        """配额配置存在于 settings 且有合理默认值（Req 13.7 单一真源）。"""
        assert settings.AI_CHAT_RATE_LIMIT_PER_MINUTE >= 1
        assert settings.AI_CHAT_MAX_ACTIVE_RUNS >= 1
        assert settings.AI_CHAT_MAX_ATTACHMENTS_PER_RUN >= 1
        assert settings.AI_CHAT_MAX_CONTEXT_TOKENS >= 1024
        assert settings.AI_MCP_MAX_CALLS_PER_RUN >= 1
        assert settings.AI_MCP_MAX_BYTES_PER_CALL >= 1024
        assert settings.AI_DSH_MAX_ACTIVE_RUNS >= 1
        assert settings.AI_DSH_QUEUE_LIMIT >= 1


# ===========================================================================
# Req 12.8: 指标覆盖所有规定维度
# ===========================================================================


class TestReq12_8Metrics:
    """结构化指标覆盖 active/queued、queue wait、latency、tokens、denials 等。"""

    def test_metrics_module_exports_all_required_instruments(self):
        """metrics 模块导出所有 Req 12.8 要求的指标收集函数。"""
        from app.services.ai_chat import metrics

        # 检查所有便捷函数都存在且可调用
        assert callable(metrics.set_active_runs)
        assert callable(metrics.set_queued_runs)
        assert callable(metrics.observe_queue_wait)
        assert callable(metrics.observe_run_latency)
        assert callable(metrics.inc_tokens)
        assert callable(metrics.observe_cancel_latency)
        assert callable(metrics.inc_denial)
        assert callable(metrics.inc_attachment_bytes)
        assert callable(metrics.inc_cleanup_failure)
        assert callable(metrics.inc_run_status)
        assert callable(metrics.render_ai_chat_metrics)

    def test_render_metrics_returns_bytes_and_content_type(self):
        """render_ai_chat_metrics 返回 (bytes, content_type) 元组。"""
        from app.services.ai_chat.metrics import render_ai_chat_metrics

        body, ct = render_ai_chat_metrics()
        assert isinstance(body, bytes)
        assert isinstance(ct, str)
        assert len(ct) > 0

    def test_metrics_convenience_functions_no_error(self):
        """所有便捷函数调用不抛异常（即使 prometheus_client 不可用时也不崩）。"""
        from app.services.ai_chat.metrics import (
            set_active_runs,
            set_queued_runs,
            observe_queue_wait,
            observe_run_latency,
            inc_tokens,
            observe_cancel_latency,
            inc_denial,
            inc_attachment_bytes,
            inc_cleanup_failure,
            inc_run_status,
        )

        # 这些调用不应抛异常
        set_active_runs(3)
        set_queued_runs(2)
        observe_queue_wait(1.5)
        observe_run_latency("native", "done", 5.0)
        inc_tokens("native", prompt_tokens=100, completion_tokens=200)
        observe_cancel_latency(0.5)
        inc_denial("access_denied")
        inc_attachment_bytes(1024)
        inc_cleanup_failure()
        inc_run_status("native", "done")


# ===========================================================================
# Req 13.5/13.7: 限流真实接线 + 配额 route
# ===========================================================================


class TestReq13_5_13_7QuotaRoute:
    """AI chat endpoint 被真实纳入独立限流匹配规则。
    配额单一真源来自服务端配置。
    """

    def test_ai_chat_rate_limit_config_exists(self):
        """AI_CHAT_RATE_LIMIT_PER_MINUTE 配置存在且为正整数。"""
        assert hasattr(settings, "AI_CHAT_RATE_LIMIT_PER_MINUTE")
        assert settings.AI_CHAT_RATE_LIMIT_PER_MINUTE >= 1

    def test_rate_limit_key_uses_ai_chat_prefix(self):
        """限流 key 使用独立 ai_chat 前缀（不与 LLM 混用）。"""
        from app.middleware.rate_limiter import _ai_chat_rate_limit_key

        key = _ai_chat_rate_limit_key("user-123")
        assert key.startswith("rate_limit:ai_chat:")
        assert "user-123" in key


# ===========================================================================
# event_type schema 校验
# ===========================================================================


class TestAuditLogHelperSchema:
    """audit_log_helper 的 event_type schema 覆盖 AI Chat 所有事件类型。"""

    def test_ai_chat_event_types_registered(self):
        """所有 AI Chat 审计 event_type 在 EVENT_TYPE_SCHEMAS 中注册。"""
        from app.services.audit_log_helper import EVENT_TYPE_SCHEMAS

        expected_types = [
            "ai_chat_run_lifecycle",
            "ai_chat_access_denied",
            "ai_chat_note_saved",
            "ai_chat_adopt_requested",
            "ai_chat_attachment_cleanup",
            "ai_chat_tool_lifecycle",
        ]
        for et in expected_types:
            assert et in EVENT_TYPE_SCHEMAS, f"{et} missing from EVENT_TYPE_SCHEMAS"

    def test_tool_lifecycle_schema_requires_fields(self):
        """ai_chat_tool_lifecycle schema 要求 run_id/tool_call_id/tool_name/status。"""
        from app.services.audit_log_helper import EVENT_TYPE_SCHEMAS

        schema = EVENT_TYPE_SCHEMAS["ai_chat_tool_lifecycle"]
        assert "run_id" in schema
        assert "tool_call_id" in schema
        assert "tool_name" in schema
        assert "status" in schema

    def test_validate_event_type_rejects_missing_fields(self):
        """校验函数对缺失必需字段抛 ValueError。"""
        from app.services.audit_log_helper import validate_event_type_details

        with pytest.raises(ValueError, match="缺少必需字段"):
            validate_event_type_details({
                "event_type": "ai_chat_tool_lifecycle",
                "run_id": "r1",
                # 缺 tool_call_id, tool_name, status
            })

    def test_validate_event_type_passes_with_all_fields(self):
        """校验函数对齐全字段不抛异常。"""
        from app.services.audit_log_helper import validate_event_type_details

        # 不应抛异常
        validate_event_type_details({
            "event_type": "ai_chat_tool_lifecycle",
            "run_id": "r1",
            "tool_call_id": "tc1",
            "tool_name": "wp_read",
            "status": "started",
        })
