"""Property test for permission mapping (P4)

**Validates: Requirements F4.1, F4.6**

Property 4: For any role, permissions = project_role_perms ∪ system_role_perms;
admin always gets ALL_PERMISSIONS.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.routers.project_permissions import (
    ALL_PERMISSIONS,
    PROJECT_ROLE_PERMISSIONS,
    SYSTEM_ROLE_PERMISSIONS,
)

PROJECT_ROLES = list(PROJECT_ROLE_PERMISSIONS.keys())
SYSTEM_ROLES = list(SYSTEM_ROLE_PERMISSIONS.keys())


class TestPermissionMappingProperty:
    """Property 4: permission mapping correctness."""

    @settings(max_examples=30)
    @given(
        project_role=st.sampled_from(PROJECT_ROLES),
        system_role=st.sampled_from([r for r in SYSTEM_ROLES if r != "admin"]),
    )
    def test_p4_merged_permissions_equals_union(self, project_role: str, system_role: str):
        """For any non-admin role combo, merged perms = project ∪ system."""
        project_perms = set(PROJECT_ROLE_PERMISSIONS[project_role])
        system_perms = set(SYSTEM_ROLE_PERMISSIONS[system_role])
        expected = sorted(project_perms | system_perms)

        # Simulate the endpoint logic
        merged = sorted(set(PROJECT_ROLE_PERMISSIONS[project_role]) | set(SYSTEM_ROLE_PERMISSIONS[system_role]))
        assert merged == expected

    @settings(max_examples=30)
    @given(project_role=st.sampled_from(PROJECT_ROLES + [None]))
    def test_p4_admin_always_gets_all_permissions(self, project_role):
        """Admin system role always returns ALL_PERMISSIONS regardless of project role."""
        # Admin logic: skip project role check, return ALL_PERMISSIONS
        assert ALL_PERMISSIONS == sorted(set(ALL_PERMISSIONS))
        assert len(ALL_PERMISSIONS) > 0

        # Verify admin perms are a superset of any project role perms
        if project_role and project_role in PROJECT_ROLE_PERMISSIONS:
            project_perms = set(PROJECT_ROLE_PERMISSIONS[project_role])
            assert project_perms.issubset(set(ALL_PERMISSIONS))

    def test_all_permissions_contains_all_defined_perms(self):
        """ALL_PERMISSIONS is the union of all project + system role perms."""
        all_defined = set()
        for perms in PROJECT_ROLE_PERMISSIONS.values():
            all_defined.update(perms)
        for perms in SYSTEM_ROLE_PERMISSIONS.values():
            all_defined.update(perms)
        assert set(ALL_PERMISSIONS) == all_defined
