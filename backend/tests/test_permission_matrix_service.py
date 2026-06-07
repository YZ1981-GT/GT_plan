"""
Tests for permission_matrix_service.py (P0-4.5)

验证 7 个 operation code × 6 个系统角色 × 5 个项目职责的权限映射正确性。
"""
import pytest

from app.services.permission_matrix_service import (
    OPERATION_CODES,
    ROLE_OPERATIONS,
    PROJECT_ROLE_OPERATIONS,
    get_allowed_operations,
    can,
    why_cannot,
    get_permission_matrix,
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

    def test_project_role_operations_has_5_roles(self):
        expected = {"preparer", "reviewer", "manager", "partner", "eqcr"}
        assert set(PROJECT_ROLE_OPERATIONS.keys()) == expected


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
        """P0-4.3: project_role 叠加时，权限为系统角色 + 项目角色的并集"""
        ops = get_allowed_operations("auditor", project_role="reviewer")
        # auditor: project:view, wp:edit, note:edit
        # reviewer: project:view, wp:review, report:edit
        assert "wp:review" in ops
        assert "report:edit" in ops
        assert "wp:edit" in ops  # from system role
        assert "note:edit" in ops  # from system role

    def test_project_role_preparer_adds_edit(self):
        """preparer 项目职责给 eqcr 额外的 wp:edit"""
        ops = get_allowed_operations("eqcr", project_role="preparer")
        assert "wp:edit" in ops
        assert "note:edit" in ops

    def test_project_role_partner_gives_all(self):
        """partner 项目职责给所有权限"""
        ops = get_allowed_operations("auditor", project_role="partner")
        assert ops == set(OPERATION_CODES)


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

    def test_project_role_grants_additional(self):
        """P0-4.5: 项目职责可以叠加额外权限"""
        assert can("auditor", None, "wp:review") is False
        assert can("auditor", "reviewer", "wp:review") is True


# ─── why_cannot() 测试 ───────────────────────────────────────────────────────

class TestWhyCannot:
    """验证 why_cannot() 原因说明"""

    def test_returns_none_when_allowed(self):
        assert why_cannot("admin", None, "wp:edit") is None

    def test_returns_reason_when_denied(self):
        reason = why_cannot("auditor", None, "report:sign")
        assert reason is not None
        assert "auditor" in reason
        assert "report:sign" in reason

    def test_includes_project_role_in_reason(self):
        reason = why_cannot("eqcr", "reviewer", "report:sign")
        assert reason is not None
        assert "reviewer" in reason


# ─── get_permission_matrix() 测试 ────────────────────────────────────────────

class TestGetPermissionMatrix:
    """验证 P0-4.4 API 响应格式"""

    def test_admin_matrix(self):
        matrix = get_permission_matrix("admin")
        assert set(matrix["operations"]) == set(OPERATION_CODES)
        assert matrix["denied_operations"] == []
        assert matrix["system_role"] == "admin"
        assert matrix["all_operation_codes"] == OPERATION_CODES

    def test_auditor_matrix(self):
        matrix = get_permission_matrix("auditor")
        assert "wp:edit" in matrix["operations"]
        assert "report:sign" in matrix["denied_operations"]
        assert matrix["system_role"] == "auditor"
        assert matrix["project_role"] is None

    def test_matrix_with_project_role(self):
        matrix = get_permission_matrix("auditor", "reviewer")
        assert "wp:review" in matrix["operations"]
        assert matrix["project_role"] == "reviewer"

    def test_operations_and_denied_are_complementary(self):
        """operations + denied_operations = all_operation_codes"""
        for role in ROLE_OPERATIONS:
            matrix = get_permission_matrix(role)
            all_ops = set(matrix["operations"]) | set(matrix["denied_operations"])
            assert all_ops == set(OPERATION_CODES)


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
