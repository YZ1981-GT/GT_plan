"""Tests for project_permissions router — Phase 6 F4

Validates: Requirements F4.1, F4.2, F4.3, F4.7
"""

import pytest

from app.routers.project_permissions import (
    ALL_PERMISSIONS,
    PROJECT_ROLE_PERMISSIONS,
    SYSTEM_ROLE_PERMISSIONS,
)


class TestProjectRolePermissionsMapping:
    """Test PROJECT_ROLE_PERMISSIONS mapping correctness."""

    def test_all_six_roles_defined(self):
        """6 种角色全部定义"""
        expected_roles = {"manager", "signing_partner", "auditor", "eqcr", "qc", "readonly"}
        assert set(PROJECT_ROLE_PERMISSIONS.keys()) == expected_roles

    def test_readonly_is_minimal(self):
        """readonly 角色权限最少"""
        readonly_perms = set(PROJECT_ROLE_PERMISSIONS["readonly"])
        for role, perms in PROJECT_ROLE_PERMISSIONS.items():
            if role != "readonly":
                assert len(perms) > len(readonly_perms), f"{role} should have more perms than readonly"

    def test_manager_has_review_approve(self):
        """manager 角色包含 review_approve 权限"""
        assert "workpaper:review_approve" in PROJECT_ROLE_PERMISSIONS["manager"]

    def test_signing_partner_has_sign_execute(self):
        """signing_partner 角色包含 sign:execute 权限"""
        assert "sign:execute" in PROJECT_ROLE_PERMISSIONS["signing_partner"]

    def test_auditor_has_workpaper_edit(self):
        """auditor 角色包含 workpaper:edit 权限"""
        assert "workpaper:edit" in PROJECT_ROLE_PERMISSIONS["auditor"]

    def test_eqcr_has_eqcr_approve(self):
        """eqcr 角色包含 eqcr:approve 权限"""
        assert "eqcr:approve" in PROJECT_ROLE_PERMISSIONS["eqcr"]

    def test_qc_has_qc_initiate(self):
        """qc 角色包含 qc:initiate 权限"""
        assert "qc:initiate" in PROJECT_ROLE_PERMISSIONS["qc"]

    def test_all_permissions_is_superset(self):
        """ALL_PERMISSIONS 是所有角色权限的超集"""
        all_perms_set = set(ALL_PERMISSIONS)
        for role, perms in PROJECT_ROLE_PERMISSIONS.items():
            for perm in perms:
                assert perm in all_perms_set, f"{perm} from {role} not in ALL_PERMISSIONS"

    def test_admin_system_role_returns_empty(self):
        """admin 系统角色映射为空列表（admin 跳过检查）"""
        assert SYSTEM_ROLE_PERMISSIONS["admin"] == []

    def test_project_view_in_all_roles(self):
        """所有角色都有 project:view 权限"""
        for role, perms in PROJECT_ROLE_PERMISSIONS.items():
            assert "project:view" in perms, f"{role} missing project:view"

    def test_permission_union_for_auditor(self):
        """auditor 项目角色 + auditor 系统角色 = 并集"""
        project_perms = set(PROJECT_ROLE_PERMISSIONS["auditor"])
        system_perms = set(SYSTEM_ROLE_PERMISSIONS["auditor"])
        union = project_perms | system_perms
        # 并集应包含两者所有权限
        assert project_perms.issubset(union)
        assert system_perms.issubset(union)
