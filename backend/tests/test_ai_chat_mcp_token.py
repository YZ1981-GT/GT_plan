"""Tests for MCP scoped token service（dsh-agent-panel-integration Task 25）

Coverage:
  - Token create / validate / revoke lifecycle
  - Child token inheritance (Property 29: 只收窄)
  - Cross-user isolation (Property 28: 双用户交换拒绝)
  - Role masking (Property 30: 五角色一致)
  - Budget enforcement (Req 11.8)
  - Unknown role fail-closed (Req 11.9)

Validates: Requirements 11.5, 11.7, 11.8, 11.9, 12.6, 12.7
Properties: 28, 29, 30, 32
"""

import time
from uuid import UUID, uuid4

import pytest

from app.services.ai_chat.mcp_token import (
    MCP_READONLY_TOOLS,
    MCP_ROLE_MASK_POLICY,
    McpMaskLevel,
    McpScopedToken,
    McpTokenExpired,
    McpTokenInvalid,
    McpTokenPayload,
    McpTokenRevoked,
    McpTokenScopeMismatch,
    McpTokenService,
    resolve_mask_policy,
)
from app.services.ai_chat.mcp_budget import (
    McpBudget,
    McpBudgetExceeded,
    McpBudgetTracker,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def token_service() -> McpTokenService:
    return McpTokenService()


@pytest.fixture
def budget_tracker() -> McpBudgetTracker:
    return McpBudgetTracker()


@pytest.fixture
def user_a_id() -> UUID:
    return uuid4()


@pytest.fixture
def user_b_id() -> UUID:
    return uuid4()


@pytest.fixture
def project_id() -> UUID:
    return uuid4()


@pytest.fixture
def run_id() -> UUID:
    return uuid4()


# ---------------------------------------------------------------------------
# Token Create & Validate
# ---------------------------------------------------------------------------


class TestTokenLifecycle:
    """Token 创建/验证/过期/撤销生命周期。"""

    def test_create_and_validate(
        self, token_service: McpTokenService, user_a_id: UUID, project_id: UUID, run_id: UUID
    ):
        """正常创建并验证 token。"""
        scoped = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset({"D", "E", "F"}),
        )
        assert isinstance(scoped, McpScopedToken)
        assert scoped.payload.user_id == user_a_id
        assert scoped.payload.project_id == project_id
        assert scoped.payload.run_id == run_id
        assert scoped.payload.role == "auditor"
        assert scoped.payload.cycle_scope == frozenset({"D", "E", "F"})
        assert scoped.payload.mask_policy == McpMaskLevel.STRICT

        # validate
        payload = token_service.validate_token(scoped.token)
        assert payload.user_id == user_a_id
        assert payload.run_id == run_id

    def test_validate_with_expected_binding(
        self, token_service: McpTokenService, user_a_id: UUID, project_id: UUID, run_id: UUID
    ):
        """验证时可指定期望的 binding。"""
        scoped = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="manager",
            cycle_scope=frozenset(),
        )
        payload = token_service.validate_token(
            scoped.token,
            expected_run_id=run_id,
            expected_project_id=project_id,
            expected_user_id=user_a_id,
        )
        assert payload.run_id == run_id

    def test_token_expired(self, token_service: McpTokenService, user_a_id: UUID, project_id: UUID, run_id: UUID):
        """已过期 token 验证失败。"""
        scoped = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset(),
            ttl_seconds=1,
        )
        # 手动让 token 过期
        import json, base64
        parts = scoped.token.split(".")
        data_b64 = parts[0]
        padding = 4 - len(data_b64) % 4
        if padding != 4:
            data_b64_padded = data_b64 + "=" * padding
        else:
            data_b64_padded = data_b64
        data = json.loads(base64.urlsafe_b64decode(data_b64_padded))
        data["exp"] = time.time() - 10  # 已过期
        # 重编码（绕过签名只为测试 validate 的过期逻辑）
        # 直接用 time.sleep 太慢，改为创建 ttl=0 的测试
        # 改用 monkey patch approach
        scoped2 = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset(),
            ttl_seconds=1,
        )
        # 猴补 _decode 的结果让 expires_at 过期
        original_decode = token_service._decode

        def patched_decode(token_str):
            p = original_decode(token_str)
            # 构造已过期 payload
            return McpTokenPayload(
                token_id=p.token_id,
                user_id=p.user_id,
                project_id=p.project_id,
                run_id=p.run_id,
                role=p.role,
                cycle_scope=p.cycle_scope,
                mask_policy=p.mask_policy,
                issued_at=p.issued_at,
                expires_at=time.time() - 100,  # 过期
                parent_token_id=p.parent_token_id,
            )

        token_service._decode = patched_decode
        try:
            with pytest.raises(McpTokenExpired):
                token_service.validate_token(scoped2.token)
        finally:
            token_service._decode = original_decode

    def test_token_revoked(
        self, token_service: McpTokenService, user_a_id: UUID, project_id: UUID, run_id: UUID
    ):
        """已撤销 token 验证失败。"""
        scoped = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset(),
        )
        # 验证正常
        token_service.validate_token(scoped.token)

        # 撤销
        token_service.revoke_token(scoped.payload.token_id)

        # 验证失败
        with pytest.raises(McpTokenRevoked):
            token_service.validate_token(scoped.token)

    def test_invalid_token_format(self, token_service: McpTokenService):
        """格式错误的 token 被拒绝。"""
        with pytest.raises(McpTokenInvalid):
            token_service.validate_token("not-a-valid-token")

    def test_tampered_token(
        self, token_service: McpTokenService, user_a_id: UUID, project_id: UUID, run_id: UUID
    ):
        """篡改 token payload 后签名校验失败。"""
        scoped = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset(),
        )
        parts = scoped.token.split(".")
        # 篡改 payload
        tampered = parts[0] + "X" + "." + parts[1]
        with pytest.raises(McpTokenInvalid):
            token_service.validate_token(tampered)


# ---------------------------------------------------------------------------
# Property 28: 双用户交换拒绝
# ---------------------------------------------------------------------------


class TestCrossUserIsolation:
    """Property 28：双用户交换 token/run/project 均返回拒绝。"""

    def test_wrong_user_rejected(
        self,
        token_service: McpTokenService,
        user_a_id: UUID,
        user_b_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ):
        """用户 A 的 token 不能用于用户 B 的请求。"""
        scoped = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset(),
        )
        with pytest.raises(McpTokenScopeMismatch, match="user_id"):
            token_service.validate_token(
                scoped.token, expected_user_id=user_b_id
            )

    def test_wrong_run_rejected(
        self,
        token_service: McpTokenService,
        user_a_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ):
        """token 不能用于其他 run。"""
        scoped = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset(),
        )
        other_run = uuid4()
        with pytest.raises(McpTokenScopeMismatch, match="run_id"):
            token_service.validate_token(
                scoped.token, expected_run_id=other_run
            )

    def test_wrong_project_rejected(
        self,
        token_service: McpTokenService,
        user_a_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ):
        """token 不能用于其他 project。"""
        scoped = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset(),
        )
        other_project = uuid4()
        with pytest.raises(McpTokenScopeMismatch, match="project_id"):
            token_service.validate_token(
                scoped.token, expected_project_id=other_project
            )


# ---------------------------------------------------------------------------
# Property 29: 子 Agent 权限只收窄
# ---------------------------------------------------------------------------


class TestChildTokenInheritance:
    """Property 29：子 Agent 继承只能收窄。"""

    def test_child_inherits_parent_scope(
        self,
        token_service: McpTokenService,
        user_a_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ):
        """child token 继承父 token 的 scope（不指定收窄时相等）。"""
        parent = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="manager",
            cycle_scope=frozenset({"D", "E", "F", "G"}),
        )
        child = token_service.create_child_token(parent.payload)
        assert child.payload.cycle_scope == frozenset({"D", "E", "F", "G"})
        assert child.payload.parent_token_id == parent.payload.token_id
        assert child.payload.user_id == parent.payload.user_id
        assert child.payload.project_id == parent.payload.project_id
        assert child.payload.run_id == parent.payload.run_id

    def test_child_narrowed_scope(
        self,
        token_service: McpTokenService,
        user_a_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ):
        """child token 可收窄到 parent scope 的子集。"""
        parent = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="manager",
            cycle_scope=frozenset({"D", "E", "F", "G"}),
        )
        child = token_service.create_child_token(
            parent.payload, narrowed_scope=frozenset({"D", "E"})
        )
        assert child.payload.cycle_scope == frozenset({"D", "E"})

    def test_child_cannot_widen_scope(
        self,
        token_service: McpTokenService,
        user_a_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ):
        """child token 不能扩大 scope（超出部分被交集剪掉）。"""
        parent = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset({"D", "E"}),
        )
        child = token_service.create_child_token(
            parent.payload, narrowed_scope=frozenset({"D", "E", "F", "G"})
        )
        # 交集：只有 D, E
        assert child.payload.cycle_scope == frozenset({"D", "E"})

    def test_child_expiry_bounded_by_parent(
        self,
        token_service: McpTokenService,
        user_a_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ):
        """child token expiry 不超过 parent。"""
        parent = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset(),
            ttl_seconds=30,
        )
        child = token_service.create_child_token(
            parent.payload, ttl_seconds=9999
        )
        assert child.payload.expires_at <= parent.payload.expires_at

    def test_parent_revoke_invalidates_child(
        self,
        token_service: McpTokenService,
        user_a_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ):
        """撤销父 token 后，子 token 也失效。"""
        parent = token_service.create_token(
            user_id=user_a_id,
            project_id=project_id,
            run_id=run_id,
            role="auditor",
            cycle_scope=frozenset(),
        )
        child = token_service.create_child_token(parent.payload)

        # 验证子 token 正常
        token_service.validate_token(child.token)

        # 撤销父 token
        token_service.revoke_token(parent.payload.token_id)

        # 子 token 失效
        with pytest.raises(McpTokenRevoked):
            token_service.validate_token(child.token)


# ---------------------------------------------------------------------------
# Property 30: 五角色脱敏一致
# ---------------------------------------------------------------------------


class TestRoleMasking:
    """Property 30：五角色脱敏映射。"""

    @pytest.mark.parametrize(
        "role,expected_policy",
        [
            ("auditor", McpMaskLevel.STRICT),
            ("manager", McpMaskLevel.PARTIAL),
            ("partner", McpMaskLevel.NONE),
            ("qc", McpMaskLevel.STRICT),
            ("eqcr", McpMaskLevel.STRICT),
            ("admin", McpMaskLevel.NONE),
        ],
    )
    def test_known_roles_mapped(self, role: str, expected_policy: str):
        """五个已知角色有明确脱敏策略。"""
        assert resolve_mask_policy(role) == expected_policy

    def test_unknown_role_rejected(self):
        """未知角色 fail-closed。"""
        assert resolve_mask_policy("unknown_role") == McpMaskLevel.REJECTED
        assert resolve_mask_policy("") == McpMaskLevel.REJECTED
        assert resolve_mask_policy(None) == McpMaskLevel.REJECTED

    def test_unknown_role_cannot_create_token(
        self,
        token_service: McpTokenService,
        user_a_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ):
        """未知角色不能创建 MCP token。"""
        with pytest.raises(McpTokenInvalid, match="未知角色"):
            token_service.create_token(
                user_id=user_a_id,
                project_id=project_id,
                run_id=run_id,
                role="unknown_hacker",
                cycle_scope=frozenset(),
            )

    def test_token_carries_mask_policy(
        self,
        token_service: McpTokenService,
        user_a_id: UUID,
        project_id: UUID,
        run_id: UUID,
    ):
        """token 创建时记录脱敏策略。"""
        for role, expected in MCP_ROLE_MASK_POLICY.items():
            scoped = token_service.create_token(
                user_id=user_a_id,
                project_id=project_id,
                run_id=run_id,
                role=role,
                cycle_scope=frozenset(),
            )
            assert scoped.payload.mask_policy == expected


# ---------------------------------------------------------------------------
# Budget Enforcement (Req 11.8)
# ---------------------------------------------------------------------------


class TestBudgetTracker:
    """MCP 配额追踪。"""

    def test_budget_creation(self, budget_tracker: McpBudgetTracker, run_id: UUID):
        """首次获取时按配置创建 budget。"""
        budget = budget_tracker.get_or_create(run_id)
        assert budget.run_id == run_id
        assert budget.calls_used == 0
        assert budget.calls_remaining > 0

    def test_consume_decrements(self, budget_tracker: McpBudgetTracker, run_id: UUID):
        """消费减少剩余额度。"""
        budget = budget_tracker.check_and_consume(run_id, response_bytes=100)
        assert budget.calls_used == 1
        assert budget.total_bytes == 100

    def test_calls_exceeded(self, budget_tracker: McpBudgetTracker, run_id: UUID):
        """调用次数超限时抛异常。"""
        budget = budget_tracker.get_or_create(run_id)
        # 人为耗尽
        budget.calls_used = budget.max_calls

        with pytest.raises(McpBudgetExceeded, match="calls"):
            budget_tracker.check_and_consume(run_id, response_bytes=0)

    def test_bytes_exceeded(self, budget_tracker: McpBudgetTracker, run_id: UUID):
        """单次字节超限时抛异常。"""
        with pytest.raises(McpBudgetExceeded, match="bytes_per_call"):
            budget_tracker.check_and_consume(run_id, response_bytes=999_999_999)

    def test_pre_check(self, budget_tracker: McpBudgetTracker, run_id: UUID):
        """预检在配额耗尽时失败。"""
        budget = budget_tracker.get_or_create(run_id)
        budget.calls_used = budget.max_calls

        with pytest.raises(McpBudgetExceeded):
            budget_tracker.pre_check(run_id)

    def test_release(self, budget_tracker: McpBudgetTracker, run_id: UUID):
        """释放后 budget 清理。"""
        budget_tracker.get_or_create(run_id)
        budget_tracker.release(run_id)
        assert budget_tracker.get_status(run_id) is None


# ---------------------------------------------------------------------------
# MCP_READONLY_TOOLS (Design §13)
# ---------------------------------------------------------------------------


class TestMcpReadonlyTools:
    """MCP 工具白名单。"""

    def test_all_seven_tools_present(self):
        """白名单包含设计文档定义的 7 个工具。"""
        expected = {
            "wp_list", "wp_read", "tb_query", "addr_lookup",
            "kb_search", "note_read", "review_prompt",
        }
        assert MCP_READONLY_TOOLS == expected

    def test_no_dangerous_tools(self):
        """白名单不含危险工具。"""
        dangerous = {"bash", "shell", "fs_write", "web_fetch", "subprocess"}
        assert MCP_READONLY_TOOLS & dangerous == set()


# ---------------------------------------------------------------------------
# Token cleanup
# ---------------------------------------------------------------------------


class TestTokenCleanup:
    """撤销记录清理。"""

    def test_cleanup_expired_revocations(self, token_service: McpTokenService):
        """过期撤销记录被清理。"""
        # 模拟旧撤销
        token_service._revoked["old_token_1"] = time.time() - 700
        token_service._revoked["old_token_2"] = time.time() - 800
        token_service._revoked["recent_token"] = time.time() - 100

        cleaned = token_service.cleanup_expired()
        assert cleaned == 2
        assert "recent_token" in token_service._revoked
        assert "old_token_1" not in token_service._revoked
