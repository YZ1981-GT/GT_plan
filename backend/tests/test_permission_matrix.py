"""
Tests for backend/app/permissions/ — 后端安全边界权限矩阵

Feature: platform-global-hardening
Validates: Requirements 7.4, 7.5

验证：
- 5 审计角色 × 关键操作 → 正确的 allow/deny
- 锁定底稿限制
- 已复核底稿限制
- 后端为安全边界（前端不一致时后端生效）
"""

import pytest

from app.permissions.permission_matrix import (
    AUDIT_ROLES,
    LOCKED_OVERRIDE_ROLES,
    POST_REVIEW_EDIT_ROLES,
    ROLE_ALIAS_MAP,
    can,
    get_all_operation_codes,
    get_operations_for_role,
    normalize_role,
)


# ─── 角色归一化 ──────────────────────────────────────────────────────────────

class TestNormalizeRole:
    """验证角色名归一化（别名→系统角色）"""

    def test_assistant_maps_to_auditor(self):
        assert normalize_role("assistant") == "auditor"

    def test_qc_partner_maps_to_qc(self):
        assert normalize_role("qc_partner") == "qc"

    def test_signing_partner_maps_to_partner(self):
        assert normalize_role("signing_partner") == "partner"

    def test_eqcr_stays_eqcr(self):
        assert normalize_role("eqcr") == "eqcr"

    def test_case_insensitive(self):
        assert normalize_role("PARTNER") == "partner"
        assert normalize_role("Assistant") == "auditor"

    def test_whitespace_trimmed(self):
        assert normalize_role("  manager  ") == "manager"

    def test_unknown_role_passthrough(self):
        assert normalize_role("unknown") == "unknown"


# ─── 5 审计角色 × 关键操作 ────────────────────────────────────────────────────

class TestFiveRolesPermissions:
    """验证 5 审计角色对关键操作的 allow/deny 判定"""

    # --- 审计助理（assistant → auditor）---

    def test_assistant_can_edit_workpaper(self):
        assert can("assistant", "edit", "workpaper") is True

    def test_assistant_cannot_review_workpaper(self):
        assert can("assistant", "review", "workpaper") is False

    def test_assistant_cannot_sign_report(self):
        assert can("assistant", "sign", "report") is False

    def test_assistant_can_edit_note(self):
        assert can("assistant", "edit", "note") is True

    def test_assistant_can_read_workpaper(self):
        assert can("assistant", "read", "workpaper") is True

    # --- 现场经理（manager）---

    def test_manager_can_edit_workpaper(self):
        assert can("manager", "edit", "workpaper") is True

    def test_manager_can_review_workpaper(self):
        assert can("manager", "review", "workpaper") is True

    def test_manager_can_edit_report(self):
        assert can("manager", "edit", "report") is True

    def test_manager_cannot_sign_report(self):
        assert can("manager", "sign", "report") is False

    def test_manager_cannot_manage_archive(self):
        assert can("manager", "manage", "archive") is False

    # --- 业务合伙人（partner）---

    def test_partner_can_edit_workpaper(self):
        assert can("partner", "edit", "workpaper") is True

    def test_partner_can_review_workpaper(self):
        assert can("partner", "review", "workpaper") is True

    def test_partner_can_sign_report(self):
        assert can("partner", "sign", "report") is True

    def test_partner_can_manage_archive(self):
        assert can("partner", "manage", "archive") is True

    def test_partner_can_edit_note(self):
        assert can("partner", "edit", "note") is True

    # --- 质量控制复核合伙人（qc_partner → qc）---

    def test_qc_partner_cannot_edit_workpaper(self):
        assert can("qc_partner", "edit", "workpaper") is False

    def test_qc_partner_can_review_workpaper(self):
        assert can("qc_partner", "review", "workpaper") is True

    def test_qc_partner_can_edit_report(self):
        assert can("qc_partner", "edit", "report") is True

    def test_qc_partner_cannot_sign_report(self):
        # qc 角色无 report:sign（与 partner 不同）
        assert can("qc_partner", "sign", "report") is False

    # --- EQCR 技术复核人（eqcr）---

    def test_eqcr_cannot_edit_workpaper(self):
        assert can("eqcr", "edit", "workpaper") is False

    def test_eqcr_can_review_workpaper(self):
        assert can("eqcr", "review", "workpaper") is True

    def test_eqcr_cannot_edit_report(self):
        assert can("eqcr", "edit", "report") is False

    def test_eqcr_cannot_edit_note(self):
        assert can("eqcr", "edit", "note") is False

    def test_eqcr_can_view_project(self):
        assert can("eqcr", "view", "project") is True


# ─── 锁定底稿限制 ────────────────────────────────────────────────────────────

class TestLockedWorkpaperRestrictions:
    """验证底稿锁定后的权限约束"""

    def test_assistant_cannot_edit_locked_workpaper(self):
        assert can("assistant", "edit", "workpaper", {"locked": True}) is False

    def test_manager_cannot_edit_locked_workpaper(self):
        assert can("manager", "edit", "workpaper", {"locked": True}) is False

    def test_partner_can_edit_locked_workpaper(self):
        """合伙人可以解锁/编辑锁定底稿"""
        assert can("partner", "edit", "workpaper", {"locked": True}) is True

    def test_qc_cannot_edit_locked_workpaper(self):
        """QC 无编辑权，锁定与否无关"""
        assert can("qc_partner", "edit", "workpaper", {"locked": True}) is False

    def test_eqcr_cannot_edit_locked_workpaper(self):
        assert can("eqcr", "edit", "workpaper", {"locked": True}) is False

    def test_locked_does_not_affect_review(self):
        """锁定不影响复核操作"""
        assert can("manager", "review", "workpaper", {"locked": True}) is True

    def test_locked_does_not_affect_read(self):
        """锁定不影响读取"""
        assert can("assistant", "read", "workpaper", {"locked": True}) is True


# ─── 已复核底稿限制 ───────────────────────────────────────────────────────────

class TestPostReviewRestrictions:
    """验证已复核底稿的编辑权限约束"""

    def test_assistant_cannot_edit_reviewed_workpaper(self):
        assert can("assistant", "edit", "workpaper", {"reviewed": True}) is False

    def test_manager_can_edit_reviewed_workpaper(self):
        """经理可重新打开已复核底稿"""
        assert can("manager", "edit", "workpaper", {"reviewed": True}) is True

    def test_partner_can_edit_reviewed_workpaper(self):
        assert can("partner", "edit", "workpaper", {"reviewed": True}) is True

    def test_eqcr_cannot_edit_reviewed_workpaper(self):
        assert can("eqcr", "edit", "workpaper", {"reviewed": True}) is False

    def test_reviewed_does_not_affect_review(self):
        """复核状态不影响 review 操作本身"""
        assert can("qc_partner", "review", "workpaper", {"reviewed": True}) is True


# ─── 项目职责叠加 ─────────────────────────────────────────────────────────────

class TestProjectRoleContext:
    """验证项目职责可以叠加额外权限"""

    def test_assistant_with_reviewer_role_can_review(self):
        """审计助理 + 项目复核人职责 → 可复核"""
        assert can("assistant", "review", "workpaper", {"project_role": "reviewer"}) is True

    def test_eqcr_with_preparer_role_can_edit(self):
        """EQCR + 项目编制人职责 → 可编辑"""
        assert can("eqcr", "edit", "workpaper", {"project_role": "preparer"}) is True


# ─── 安全边界原则验证 ─────────────────────────────────────────────────────────

class TestSecurityBoundaryPrinciple:
    """
    Req 7.4: 后端 deps 层 SHALL 作为安全边界强制校验权限
    Req 7.5: 不一致时后端判定 SHALL 生效
    """

    def test_unknown_action_resource_denied(self):
        """未映射的 action:resource 组合 → 后端拒绝（安全侧默认拒绝）"""
        assert can("admin", "unknown_action", "unknown_resource") is False

    def test_unknown_role_denied(self):
        """未知角色 → 拒绝"""
        assert can("hacker", "edit", "workpaper") is False

    def test_empty_role_denied(self):
        """空角色 → 拒绝"""
        assert can("", "edit", "workpaper") is False

    def test_admin_bypasses_all(self):
        """admin 跳过所有权限检查"""
        assert can("admin", "edit", "workpaper") is True
        assert can("admin", "sign", "report") is True
        assert can("admin", "manage", "archive") is True

    def test_admin_can_edit_even_locked(self):
        """admin 可编辑锁定底稿"""
        assert can("admin", "edit", "workpaper", {"locked": True}) is True


# ─── 辅助函数 ────────────────────────────────────────────────────────────────

class TestHelperFunctions:
    """验证辅助函数"""

    def test_get_operations_for_assistant(self):
        ops = get_operations_for_role("assistant")
        assert "wp:edit" in ops
        assert "wp:review" not in ops

    def test_get_operations_for_partner(self):
        ops = get_operations_for_role("partner")
        assert "report:sign" in ops
        assert "archive:manage" in ops

    def test_get_all_operation_codes_returns_7(self):
        codes = get_all_operation_codes()
        assert len(codes) == 7
        assert "wp:edit" in codes
        assert "wp:review" in codes

    def test_audit_roles_constant(self):
        assert len(AUDIT_ROLES) == 5
        assert "assistant" in AUDIT_ROLES
        assert "manager" in AUDIT_ROLES
        assert "partner" in AUDIT_ROLES
        assert "qc_partner" in AUDIT_ROLES
        assert "eqcr" in AUDIT_ROLES

    def test_role_alias_map_covers_all_audit_roles(self):
        for role in AUDIT_ROLES:
            assert role in ROLE_ALIAS_MAP

    def test_locked_override_roles_are_privileged(self):
        """只有 admin/partner 能绕过锁定"""
        assert LOCKED_OVERRIDE_ROLES == {"admin", "partner"}

    def test_post_review_edit_roles(self):
        """admin/partner/manager 可重新打开已复核底稿"""
        assert POST_REVIEW_EDIT_ROLES == {"admin", "partner", "manager"}
