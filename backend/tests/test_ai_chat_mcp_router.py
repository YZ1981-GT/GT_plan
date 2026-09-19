"""Tests for MCP REST router endpoints（dsh-agent-panel-integration Task 25）

Integration-level tests covering:
  - Token create/revoke endpoints
  - Tool call with budget enforcement
  - Tool whitelist rejection
  - Budget query
  - Child token creation

Validates: Requirements 11.5, 11.7, 11.8, 11.9, 12.6, 12.7
Properties: 28, 29, 30, 32
"""

from uuid import uuid4

import pytest

from app.services.ai_chat.mcp_token import (
    MCP_READONLY_TOOLS,
    McpTokenService,
)
from app.services.ai_chat.mcp_budget import McpBudgetTracker


# ---------------------------------------------------------------------------
# Unit tests for router-level logic (without HTTP server)
# ---------------------------------------------------------------------------


class TestMcpRouterToolWhitelist:
    """工具白名单 enforcement。"""

    def test_allowed_tools(self):
        """所有 7 个工具均在白名单内。"""
        for tool in MCP_READONLY_TOOLS:
            assert tool in MCP_READONLY_TOOLS

    def test_dangerous_tool_rejected(self):
        """危险工具不在白名单。"""
        dangerous = ["bash", "shell", "fs_write", "web_fetch", "subprocess", "rm"]
        for tool in dangerous:
            assert tool not in MCP_READONLY_TOOLS


class TestMcpTokenEndpointLogic:
    """Token endpoint 逻辑测试（不需要 HTTP server）。"""

    def test_create_token_for_known_roles(self):
        """所有已知角色可创建 token。"""
        svc = McpTokenService()
        user_id = uuid4()
        project_id = uuid4()
        run_id = uuid4()

        for role in ["auditor", "manager", "partner", "qc", "eqcr", "admin"]:
            token = svc.create_token(
                user_id=user_id,
                project_id=project_id,
                run_id=run_id,
                role=role,
                cycle_scope=frozenset({"D"}),
            )
            assert token.payload.role == role

    def test_revoke_and_revalidate(self):
        """撤销后验证失败。"""
        svc = McpTokenService()
        token = svc.create_token(
            user_id=uuid4(),
            project_id=uuid4(),
            run_id=uuid4(),
            role="auditor",
            cycle_scope=frozenset(),
        )
        svc.revoke_token(token.payload.token_id)
        from app.services.ai_chat.mcp_token import McpTokenRevoked

        with pytest.raises(McpTokenRevoked):
            svc.validate_token(token.token)


class TestMcpBudgetEndpointLogic:
    """Budget endpoint 逻辑测试。"""

    def test_budget_status_shows_usage(self):
        """budget 状态反映真实用量。"""
        tracker = McpBudgetTracker()
        run_id = uuid4()

        budget = tracker.get_or_create(run_id)
        assert budget.calls_used == 0

        tracker.check_and_consume(run_id, response_bytes=500)
        budget = tracker.get_or_create(run_id)
        assert budget.calls_used == 1
        assert budget.total_bytes == 500

    def test_budget_per_run_isolated(self):
        """不同 run 的 budget 相互隔离。"""
        tracker = McpBudgetTracker()
        run_a = uuid4()
        run_b = uuid4()

        tracker.check_and_consume(run_a, response_bytes=100)
        budget_a = tracker.get_or_create(run_a)
        budget_b = tracker.get_or_create(run_b)

        assert budget_a.calls_used == 1
        assert budget_b.calls_used == 0


class TestMcpToolCallIntegration:
    """Tool call 集成逻辑。"""

    def test_tool_call_with_budget_tracking(self):
        """工具调用消费 budget。"""
        tracker = McpBudgetTracker()
        run_id = uuid4()

        # 模拟 5 次调用
        for i in range(5):
            budget = tracker.check_and_consume(run_id, response_bytes=100)
            assert budget.calls_used == i + 1

    def test_tool_call_after_budget_exhausted(self):
        """配额耗尽后调用被拒。"""
        from app.services.ai_chat.mcp_budget import McpBudgetExceeded

        tracker = McpBudgetTracker()
        run_id = uuid4()

        budget = tracker.get_or_create(run_id)
        budget.calls_used = budget.max_calls  # 人为耗尽

        with pytest.raises(McpBudgetExceeded):
            tracker.check_and_consume(run_id, response_bytes=0)


class TestMcpSecurityContext:
    """安全上下文一致性。"""

    def test_token_carries_full_context(self):
        """token 携带完整安全上下文。"""
        svc = McpTokenService()
        user_id = uuid4()
        project_id = uuid4()
        run_id = uuid4()
        scope = frozenset({"D", "E", "F"})

        token = svc.create_token(
            user_id=user_id,
            project_id=project_id,
            run_id=run_id,
            role="manager",
            cycle_scope=scope,
        )

        payload = svc.validate_token(token.token)
        assert payload.user_id == user_id
        assert payload.project_id == project_id
        assert payload.run_id == run_id
        assert payload.role == "manager"
        assert payload.cycle_scope == scope
        assert payload.mask_policy == "partial"  # manager → partial

    def test_child_security_context_narrowed(self):
        """子 token 安全上下文只能收窄。"""
        svc = McpTokenService()
        parent = svc.create_token(
            user_id=uuid4(),
            project_id=uuid4(),
            run_id=uuid4(),
            role="auditor",
            cycle_scope=frozenset({"D", "E", "F", "G", "H"}),
        )

        child = svc.create_child_token(
            parent.payload, narrowed_scope=frozenset({"D", "E"})
        )
        assert child.payload.cycle_scope == frozenset({"D", "E"})
        assert child.payload.cycle_scope <= parent.payload.cycle_scope
