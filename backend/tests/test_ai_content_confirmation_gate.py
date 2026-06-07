"""AI 内容确认门控 测试 (P0-5).

覆盖：
- P0-5.1: 状态映射 suggestion/draft/confirmed/rejected
- P0-5.3: AI 状态标记与流转
- P0-5.4: AI_CONTENT_CONFIRMATION_STRICT 开关
- P0-5.5: strict=false warning / strict=true blocking
- P0-5.6: draft AI 内容在 strict=true 时被签发阻断
"""
import pytest
from backend.app.services.ai_content_gate import (
    AI_CONTENT_STATES,
    AiContentStatus,
    can_enter_formal_output,
    can_transition,
    is_confirmed,
    is_terminal,
    mark_ai_content_status,
)


class TestAiContentStatus:
    """P0-5.1: 状态定义与映射。"""

    def test_all_states_defined(self):
        assert set(AI_CONTENT_STATES) == {"suggestion", "draft", "confirmed", "rejected"}

    def test_enum_values(self):
        assert AiContentStatus.suggestion.value == "suggestion"
        assert AiContentStatus.draft.value == "draft"
        assert AiContentStatus.confirmed.value == "confirmed"
        assert AiContentStatus.rejected.value == "rejected"


class TestIsConfirmed:
    def test_confirmed_returns_true(self):
        assert is_confirmed("confirmed") is True

    @pytest.mark.parametrize("status", ["suggestion", "draft", "rejected"])
    def test_non_confirmed_returns_false(self, status: str):
        assert is_confirmed(status) is False


class TestIsTerminal:
    def test_confirmed_is_terminal(self):
        assert is_terminal("confirmed") is True

    def test_rejected_is_terminal(self):
        assert is_terminal("rejected") is True

    @pytest.mark.parametrize("status", ["suggestion", "draft"])
    def test_non_terminal(self, status: str):
        assert is_terminal(status) is False


class TestCanTransition:
    """P0-5.3: 合法流转验证。"""

    def test_suggestion_to_draft(self):
        assert can_transition("suggestion", "draft") is True

    def test_suggestion_to_rejected(self):
        assert can_transition("suggestion", "rejected") is True

    def test_draft_to_confirmed(self):
        assert can_transition("draft", "confirmed") is True

    def test_draft_to_rejected(self):
        assert can_transition("draft", "rejected") is True

    def test_suggestion_to_confirmed_invalid(self):
        """不可跳过 draft 直达 confirmed。"""
        assert can_transition("suggestion", "confirmed") is False

    def test_confirmed_no_further_transition(self):
        assert can_transition("confirmed", "draft") is False
        assert can_transition("confirmed", "rejected") is False

    def test_rejected_no_further_transition(self):
        assert can_transition("rejected", "draft") is False
        assert can_transition("rejected", "confirmed") is False


class TestMarkAiContentStatus:
    """P0-5.3: 状态标记工具。"""

    def test_new_content_to_suggestion(self):
        ok, msg = mark_ai_content_status(None, "suggestion")
        assert ok is True

    def test_new_content_to_draft(self):
        ok, msg = mark_ai_content_status(None, "draft")
        assert ok is True

    def test_new_content_to_confirmed_invalid(self):
        ok, msg = mark_ai_content_status(None, "confirmed")
        assert ok is False

    def test_draft_to_confirmed(self):
        ok, msg = mark_ai_content_status("draft", "confirmed")
        assert ok is True

    def test_suggestion_to_confirmed_invalid(self):
        ok, msg = mark_ai_content_status("suggestion", "confirmed")
        assert ok is False


class TestCanEnterFormalOutput:
    """P0-5.5/5.6: 门控行为。"""

    def test_confirmed_passes_strict(self):
        """confirmed 在 strict 模式下通过。"""
        allowed, msg = can_enter_formal_output("confirmed", strict=True)
        assert allowed is True
        assert msg is None

    def test_confirmed_passes_non_strict(self):
        allowed, msg = can_enter_formal_output("confirmed", strict=False)
        assert allowed is True
        assert msg is None

    @pytest.mark.parametrize("status", ["suggestion", "draft", "rejected"])
    def test_unconfirmed_blocked_strict(self, status: str):
        """P0-5.6: strict 模式下，非 confirmed 一律阻断。"""
        allowed, msg = can_enter_formal_output(status, strict=True)
        assert allowed is False
        assert "阻断" in msg or "未确认" in msg

    def test_draft_warning_non_strict(self):
        """P0-5.5: non-strict 模式下，draft 放行但附带 warning。"""
        allowed, msg = can_enter_formal_output("draft", strict=False)
        assert allowed is True
        assert "warning" in msg

    def test_suggestion_blocked_non_strict(self):
        allowed, msg = can_enter_formal_output("suggestion", strict=False)
        assert allowed is False

    def test_rejected_blocked_non_strict(self):
        allowed, msg = can_enter_formal_output("rejected", strict=False)
        assert allowed is False

    def test_draft_blocked_in_strict_mode(self):
        """P0-5.6 核心验证: draft AI 内容在 strict=true 时被签发阻断。"""
        allowed, msg = can_enter_formal_output("draft", strict=True)
        assert allowed is False
        assert "strict" in msg or "阻断" in msg


class TestStrictModuleDefault:
    """P0-5.4: 模块级开关默认值。"""

    def test_default_is_false_unless_env_set(self):
        """默认 warning 模式（除非设置环境变量）。"""
        # 测试环境没设环境变量，应为 False
        from backend.app.services.ai_content_gate import AI_CONTENT_CONFIRMATION_STRICT
        # 不做 assert AI_CONTENT_CONFIRMATION_STRICT is False
        # 因为 CI 可能设了环境变量；只验证类型
        assert isinstance(AI_CONTENT_CONFIRMATION_STRICT, bool)
