"""
Tests for permission_matrix_service.py

验证 7 个 operation code × 6 个系统角色的权限映射正确性。
"""
import pytest

from app.services.permission_matrix_service import (
    OPERATION_CODES,
    ROLE_OPERATIONS,
    get_allowed_operations,
    can,
)


# ─── 基础常量验证 ────────────────────────────────────────────────────────────

class TestOperationCodes:
    """验证 operation code 定义完整"""

    def test_has_7_operation_codes(self):
        assert len(OPERATION_CODES) == 7

    def test_expected_codes_present(self):
        expected = [
            "project:view",
            "wp:edit",
            "wp:review",
            "report:edit",
            "report:sign",
            "note:edit",
            "archive:manage",
        ]
        for code in expected:
            assert code in OPERATION_CODES, f"Missing operation code: {code}"


class TestRoleOperations:
    """验证角色映射定义完整"""

    def test_has_6_roles(self):
        expected_roles = {"admin", "partner", "manager", "auditor", "qc", "eqcr"}
        assert set(ROLE_OPERATIONS.keys()) == expected_roles

    def test_admin_has_all_operations(self):
        assert ROLE_OPERATIONS["admin"] == set(OPERATION_CODES)


# ─── get_allowed_operations 测试 ─────────────────────────────────────────────

class TestGetAllowedOperations:
    """验证 get_allowed_operations 行为"""

    def test_admin_gets_all(self):
        ops = get_allowed_operations("admin")
        assert ops == set(OPERATION_CODES)

    def test_partner_gets_all_7(self):
        ops = get_allowed_operations("partner")
        assert ops == set(OPERATION_CODES)

    def test_manager_no_sign_no_archive(self):
        ops = get_allowed_operations("manager")
        assert "report:sign" not in ops
        assert "archive:manage" not in ops
        assert "project:view" in ops
        assert "wp:edit" in ops
        assert "wp:review" in ops
        assert "report:edit" in ops
        assert "note:edit" in ops

    def test_auditor_minimal(self):
        ops = get_allowed_operations("auditor")
        assert ops == {"project:view", "wp:edit", "note:edit"}

    def test_qc_specific(self):
        ops = get_allowed_operations("qc")
        assert ops == {"project:view", "wp:review", "report:edit"}

    def test_eqcr_read_only_plus_review(self):
        ops = get_allowed_operations("eqcr")
        assert ops == {"project:view", "wp:review"}

    def test_unknown_role_returns_empty(self):
        ops = get_allowed_operations("unknown_role")
        assert ops == set()

    def test_case_insensitive(self):
        ops = get_allowed_operations("Admin")
        assert ops == set(OPERATION_CODES)

    def test_whitespace_trimmed(self):
        ops = get_allowed_operations("  partner  ")
        assert ops == set(OPERATION_CODES)

    def test_project_role_union(self):
        """project_role 提供时，权限为系统角色 + 项目角色的并集"""
        ops = get_allowed_operations("auditor", project_role="manager")
        # auditor: project:view, wp:edit, note:edit
        # manager: project:view, wp:edit, wp:review, report:edit, note:edit
        assert "wp:review" in ops
        assert "report:edit" in ops


# ─── can() 测试 ──────────────────────────────────────────────────────────────

class TestCan:
    """验证 can() 判断逻辑"""

    @pytest.mark.parametrize("operation", OPERATION_CODES)
    def test_admin_can_do_everything(self, operation):
        assert can("admin", None, operation) is True

    @pytest.mark.parametrize("operation", OPERATION_CODES)
    def test_partner_can_do_everything(self, operation):
        assert can("partner", None, operation) is True

    def test_auditor_cannot_review(self):
        assert can("auditor", None, "wp:review") is False

    def test_auditor_cannot_sign(self):
        assert can("auditor", None, "report:sign") is False

    def test_auditor_can_edit_wp(self):
        assert can("auditor", None, "wp:edit") is True

    def test_qc_cannot_edit_wp(self):
        assert can("qc", None, "wp:edit") is False

    def test_qc_can_review_wp(self):
        assert can("qc", None, "wp:review") is True

    def test_eqcr_cannot_edit_anything(self):
        assert can("eqcr", None, "wp:edit") is False
        assert can("eqcr", None, "report:edit") is False
        assert can("eqcr", None, "note:edit") is False

    def test_unknown_role_cannot_do_anything(self):
        assert can("stranger", None, "project:view") is False

    def test_invalid_operation_code(self):
        assert can("admin", None, "nonexistent:op") is False
        # admin 实际上只对 OPERATION_CODES 内的才返回 True
        # 但 admin 检查是 role == admin 且 operation in allowed_set
        # admin 的 allowed_set 是 set(OPERATION_CODES)，所以非法 op 应返回 False


# ─── 继承关系验证 ─────────────────────────────────────────────────────────────

class TestRoleHierarchy:
    """验证角色继承关系：高级角色权限 ⊇ 低级角色权限"""

    def test_partner_superset_of_manager(self):
        partner_ops = get_allowed_operations("partner")
        manager_ops = get_allowed_operations("manager")
        assert manager_ops.issubset(partner_ops)

    def test_manager_superset_of_auditor(self):
        manager_ops = get_allowed_operations("manager")
        auditor_ops = get_allowed_operations("auditor")
        assert auditor_ops.issubset(manager_ops)

    def test_admin_superset_of_partner(self):
        admin_ops = get_allowed_operations("admin")
        partner_ops = get_allowed_operations("partner")
        assert partner_ops.issubset(admin_ops)

    def test_all_roles_have_project_view(self):
        """所有角色至少可查看项目"""
        for role in ROLE_OPERATIONS:
            assert can(role, None, "project:view") is True
