"""Unit tests for authentication and permissions.

Validates: Requirements 1.3, 1.4, 1.6
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from jose import jwt

from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_tokens,
    TokenPair,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from app.services.permission_service import (
    Permission,
    ROLE_PERMISSION_MATRIX,
    check_permission,
)


# ---------------------------------------------------------------------------
# Password hashing tests
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_password_returns_salted_hash(self):
        pw = "MySecret123"
        result = hash_password(pw)
        assert "$" in result
        parts = result.split("$")
        assert len(parts) == 2
        assert len(parts[0]) == 32
        assert len(parts[1]) == 64

    def test_verify_password_correct(self):
        pw = "CorrectPassword"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True

    def test_verify_password_incorrect(self):
        pw = "CorrectPassword"
        hashed = hash_password(pw)
        assert verify_password("WrongPassword", hashed) is False

    def test_verify_password_empty(self):
        pw = "SomePassword"
        hashed = hash_password(pw)
        assert verify_password("", hashed) is False

    def test_different_passwords_different_hashes(self):
        h1 = hash_password("pass1")
        h2 = hash_password("pass2")
        assert h1 != h2


# ---------------------------------------------------------------------------
# JWT Token tests
# ---------------------------------------------------------------------------

class TestJWTTokens:
    @patch("app.services.auth_service.settings")
    def test_create_access_token(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = "test-secret-key"
        mock_settings.JWT_ALGORITHM = "HS256"
        token = create_access_token("user-123", "testuser", "auditor")
        assert isinstance(token, str)
        assert len(token) > 0

    @patch("app.services.auth_service.settings")
    def test_create_refresh_token(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = "test-secret-key"
        mock_settings.JWT_ALGORITHM = "HS256"
        token = create_refresh_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    @patch("app.services.auth_service.settings")
    def test_create_tokens(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = "test-secret-key"
        mock_settings.JWT_ALGORITHM = "HS256"
        tokens = create_tokens("user-123", "testuser", "auditor")
        assert isinstance(tokens, TokenPair)
        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.token_type == "bearer"

    @patch("app.services.auth_service.settings")
    def test_access_token_contains_user_info(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = "test-secret-key"
        mock_settings.JWT_ALGORITHM = "HS256"
        token = create_access_token("user-abc", "alice", "manager")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["sub"] == "user-abc"
        assert payload["username"] == "alice"
        assert payload["role"] == "manager"
        assert payload["type"] == "access"

    @patch("app.services.auth_service.settings")
    def test_access_token_expiration(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = "test-secret-key"
        mock_settings.JWT_ALGORITHM = "HS256"
        token = create_access_token("user-123", "testuser", "auditor")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        exp = payload["exp"]
        now = datetime.now(timezone.utc).timestamp()
        assert ACCESS_TOKEN_EXPIRE_MINUTES - 1 <= (exp - now) / 60 <= ACCESS_TOKEN_EXPIRE_MINUTES + 1

    @patch("app.services.auth_service.settings")
    def test_refresh_token_no_user_info(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = "test-secret-key"
        mock_settings.JWT_ALGORITHM = "HS256"
        token = create_refresh_token("user-123")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["sub"] == "user-123"
        assert payload["type"] == "refresh"
        assert "username" not in payload


# ---------------------------------------------------------------------------
# Permission Matrix tests
# ---------------------------------------------------------------------------

class TestPermissionMatrix:
    def test_admin_has_all_permissions(self):
        admin_perms = ROLE_PERMISSION_MATRIX["admin"]
        all_perms = list(Permission)
        for perm in all_perms:
            assert perm in admin_perms

    def test_partner_missing_user_manage(self):
        partner_perms = ROLE_PERMISSION_MATRIX["partner"]
        assert Permission.USER_MANAGE not in partner_perms

    def test_auditor_has_read_only_permissions(self):
        auditor_perms = ROLE_PERMISSION_MATRIX["auditor"]
        assert Permission.PROJECT_READ in auditor_perms
        assert Permission.WORKPAPER_READ in auditor_perms
        assert Permission.REPORT_READ in auditor_perms
        assert Permission.PROJECT_WRITE not in auditor_perms
        assert Permission.USER_MANAGE not in auditor_perms

    def test_qc_reviewer_can_sign_workpapers(self):
        qc_perms = ROLE_PERMISSION_MATRIX["qc_reviewer"]
        assert Permission.WORKPAPER_SIGN in qc_perms
        assert Permission.REPORT_SIGN in qc_perms
        assert Permission.QC_PERFORM in qc_perms

    def test_readonly_cannot_write(self):
        ro_perms = ROLE_PERMISSION_MATRIX["readonly"]
        assert Permission.PROJECT_WRITE not in ro_perms
        assert Permission.WORKPAPER_WRITE not in ro_perms
        assert Permission.REPORT_WRITE not in ro_perms

    def test_check_permission_valid(self):
        assert check_permission("admin", Permission.USER_MANAGE) is True
        assert check_permission("auditor", Permission.PROJECT_READ) is True

    def test_check_permission_invalid(self):
        assert check_permission("auditor", Permission.USER_MANAGE) is False
        assert check_permission("readonly", Permission.PROJECT_WRITE) is False

    def test_unknown_role_has_no_permissions(self):
        assert check_permission("unknown_role", Permission.PROJECT_READ) is False


# ---------------------------------------------------------------------------
# Project-level permission tests
# ---------------------------------------------------------------------------

class TestProjectPermissions:
    def test_check_project_permission_granted(self):
        result = check_permission("manager", Permission.PROJECT_WRITE)
        assert result is True

    def test_check_project_permission_no_record(self):
        result = check_permission("readonly", Permission.PROJECT_WRITE)
        assert result is False


# ---------------------------------------------------------------------------
# Role segregation of duties tests
# ---------------------------------------------------------------------------

class TestSegregationOfDuties:
    def test_auditor_cannot_approve_own_work(self):
        auditor_perms = ROLE_PERMISSION_MATRIX["auditor"]
        assert Permission.WORKPAPER_WRITE in auditor_perms
        assert Permission.WORKPAPER_SIGN not in auditor_perms

    def test_qc_reviewer_cannot_modify_project_data(self):
        qc_perms = ROLE_PERMISSION_MATRIX["qc_reviewer"]
        assert Permission.WORKPAPER_SIGN in qc_perms
        assert Permission.WORKPAPER_WRITE not in qc_perms

    def test_manager_cannot_manage_users(self):
        manager_perms = ROLE_PERMISSION_MATRIX["manager"]
        assert Permission.USER_MANAGE not in manager_perms
        assert Permission.PROJECT_WRITE in manager_perms

    def test_partner_final_sign_authority(self):
        partner_perms = ROLE_PERMISSION_MATRIX["partner"]
        assert Permission.REPORT_SIGN in partner_perms
        assert Permission.REVIEW_SIGN in partner_perms
        assert Permission.ARCHIVE_MANAGE in partner_perms
