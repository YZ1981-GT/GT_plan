"""AI 内容确认门控 状态映射 + strict/non-strict 行为测试."""
import pytest
from backend.app.services.ai_content_gate import (
    AI_CONTENT_CONFIRMATION_STRICT,
    AI_CONTENT_STATES,
    can_enter_formal_output,
    is_confirmed,
)


class TestIsConfirmed:
    def test_confirmed_returns_true(self):
        assert is_confirmed("confirmed") is True

    @pytest.mark.parametrize("status", ["suggestion", "draft", "rejected"])
    def test_non_confirmed_returns_false(self, status: str):
        assert is_confirmed(status) is False


class TestCanEnterFormalOutput:
    """核心 Property: AI 未确认不可入结论 (strict 模式)."""

    def test_confirmed_passes_strict(self):
        allowed, msg = can_enter_formal_output("confirmed", strict=True)
        assert allowed is True
        assert msg is None

    def test_confirmed_passes_non_strict(self):
        allowed, msg = can_enter_formal_output("confirmed", strict=False)
        assert allowed is True
        assert msg is None

    @pytest.mark.parametrize("status", ["suggestion", "draft", "rejected"])
    def test_unconfirmed_blocked_strict(self, status: str):
        """strict 模式下，非 confirmed 一律阻断。"""
        allowed, msg = can_enter_formal_output(status, strict=True)
        assert allowed is False
        assert msg == "AI 内容未确认"

    def test_draft_warning_non_strict(self):
        """non-strict 模式下，draft 放行但附带 warning。"""
        allowed, msg = can_enter_formal_output("draft", strict=False)
        assert allowed is True
        assert "warning" in msg

    def test_suggestion_blocked_non_strict(self):
        allowed, msg = can_enter_formal_output("suggestion", strict=False)
        assert allowed is False

    def test_rejected_blocked_non_strict(self):
        allowed, msg = can_enter_formal_output("rejected", strict=False)
        assert allowed is False


class TestModuleConstants:
    def test_strict_default_is_false(self):
        """MVP-4: 默认 warning 模式。"""
        assert AI_CONTENT_CONFIRMATION_STRICT is False

    def test_all_states_defined(self):
        assert set(AI_CONTENT_STATES) == {
            "suggestion", "draft", "confirmed", "rejected"
        }
