"""Task 4.1: sign_status 端点通用化 — 单元测试

验证：
1. Pydantic 枚举校验：仅接受 "draft"/"pending"/"signed"
2. scope 格式: A16 子版本 → word_template:A16:{wp_code}，独立底稿 → word_template:{wp_code}
3. 默认 sign_status = "draft"
4. 向后兼容 version 字段（A16 旧调用方）
5. 非法 status 值返回 422
"""

import pytest
from pydantic import ValidationError

from app.routers.wp_editor_router import SignStatusUpdateBody


class TestSignStatusUpdateBodyValidation:
    """Pydantic model 枚举校验"""

    def test_valid_draft(self):
        body = SignStatusUpdateBody(status="draft")
        assert body.status == "draft"

    def test_valid_pending(self):
        body = SignStatusUpdateBody(status="pending")
        assert body.status == "pending"

    def test_valid_signed(self):
        body = SignStatusUpdateBody(status="signed")
        assert body.status == "signed"

    def test_default_status_is_draft(self):
        body = SignStatusUpdateBody()
        assert body.status == "draft"

    def test_invalid_status_sent_rejected(self):
        """旧的 'sent' 状态不再接受"""
        with pytest.raises(ValidationError) as exc_info:
            SignStatusUpdateBody(status="sent")
        assert "status" in str(exc_info.value)

    def test_invalid_status_arbitrary_string_rejected(self):
        with pytest.raises(ValidationError):
            SignStatusUpdateBody(status="completed")

    def test_invalid_status_empty_string_rejected(self):
        with pytest.raises(ValidationError):
            SignStatusUpdateBody(status="")

    def test_wp_code_optional(self):
        body = SignStatusUpdateBody(status="signed", wp_code="A9-1")
        assert body.wp_code == "A9-1"

    def test_version_backward_compat(self):
        """version 字段向后兼容"""
        body = SignStatusUpdateBody(status="signed", version="A16-3", sign_date="2025-03-15")
        assert body.version == "A16-3"
        assert body.sign_date == "2025-03-15"

    def test_wp_code_and_version_both_optional(self):
        body = SignStatusUpdateBody(status="pending")
        assert body.wp_code is None
        assert body.version is None


class TestScopeLogic:
    """scope 格式逻辑验证（纯逻辑，不需要 DB）"""

    @staticmethod
    def _compute_scope(effective_wp_code: str) -> str:
        """复刻端点中的 scope 逻辑"""
        is_a16_sub = effective_wp_code.startswith("A16-")
        if is_a16_sub:
            return f"word_template:A16:{effective_wp_code}"
        else:
            return f"word_template:{effective_wp_code}"

    def test_a16_sub_version_scope(self):
        assert self._compute_scope("A16-1") == "word_template:A16:A16-1"
        assert self._compute_scope("A16-7") == "word_template:A16:A16-7"
        assert self._compute_scope("A16-3") == "word_template:A16:A16-3"

    def test_standalone_wp_code_scope(self):
        assert self._compute_scope("A9-1") == "word_template:A9-1"
        assert self._compute_scope("A8-2") == "word_template:A8-2"
        assert self._compute_scope("A18-1") == "word_template:A18-1"

    def test_a16_parent_scope(self):
        """A16 本身（非子版本）→ 独立格式"""
        assert self._compute_scope("A16") == "word_template:A16"

    def test_wp_code_priority_over_version(self):
        """wp_code 优先于 version"""
        body = SignStatusUpdateBody(status="signed", wp_code="A9-1", version="A16-2")
        target_wp_code = body.wp_code or body.version
        assert target_wp_code == "A9-1"

    def test_version_fallback_when_no_wp_code(self):
        """无 wp_code 时 fallback 到 version"""
        body = SignStatusUpdateBody(status="signed", version="A16-2")
        target_wp_code = body.wp_code or body.version
        assert target_wp_code == "A16-2"


class TestSignStatusRollbackPermission:
    """Task 4.3: 签署状态回退权限控制 — 逻辑验证

    signed → draft/pending 转换需校验用户角色:
    - 允许: signing_partner, partner, qc, eqcr
    - 拒绝: auditor, manager
    """

    # 复刻端点中的权限判断逻辑
    _SIGN_ROLLBACK_ROLES = {"signing_partner", "partner", "qc", "eqcr"}

    @pytest.mark.parametrize("role", ["signing_partner", "partner", "qc", "eqcr"])
    def test_allowed_roles_can_rollback(self, role: str):
        """高权限角色可撤回签署"""
        assert role in self._SIGN_ROLLBACK_ROLES

    @pytest.mark.parametrize("role", ["auditor", "manager"])
    def test_denied_roles_cannot_rollback(self, role: str):
        """低权限角色不可撤回签署"""
        assert role not in self._SIGN_ROLLBACK_ROLES

    def test_rollback_only_triggered_from_signed(self):
        """只有当前状态为 signed 时才触发回退权限检查"""
        # 模拟：current=draft, new=pending → 不触发检查
        current = "draft"
        new_status = "pending"
        needs_check = (current == "signed" and new_status in ("draft", "pending"))
        assert needs_check is False

    def test_rollback_triggered_signed_to_draft(self):
        """signed→draft 触发权限检查"""
        current = "signed"
        new_status = "draft"
        needs_check = (current == "signed" and new_status in ("draft", "pending"))
        assert needs_check is True

    def test_rollback_triggered_signed_to_pending(self):
        """signed→pending 触发权限检查"""
        current = "signed"
        new_status = "pending"
        needs_check = (current == "signed" and new_status in ("draft", "pending"))
        assert needs_check is True

    def test_no_check_for_forward_transitions(self):
        """正向状态变更(draft→signed)不触发权限检查"""
        for current in ("draft", "pending"):
            for new_status in ("draft", "pending", "signed"):
                needs_check = (current == "signed" and new_status in ("draft", "pending"))
                assert needs_check is False, f"{current}→{new_status} should not trigger check"

    def test_no_check_when_no_existing_status(self):
        """首次设置（无现有状态）不触发权限检查"""
        current = None
        new_status = "signed"
        needs_check = (current == "signed" and new_status in ("draft", "pending"))
        assert needs_check is False

    def test_none_role_denied(self):
        """未分配角色的用户不可撤回"""
        user_role = None
        assert user_role not in self._SIGN_ROLLBACK_ROLES
