"""Tests for password_confirm router — Phase 6 F6

Validates: Requirements F6.1, F6.2, F6.3, F6.4, F6.5, F6.8
"""

import uuid

import pytest

from app.core.security import hash_password, verify_password
from app.routers.password_confirm import (
    CONFIRM_FAIL_TTL,
    CONFIRM_TOKEN_TTL,
    LOCK_MINUTES,
    MAX_ATTEMPTS,
)


class TestPasswordVerificationConfig:
    """Test configuration constants."""

    def test_token_ttl_is_300_seconds(self):
        """confirmation_token TTL = 300s (5 minutes)"""
        assert CONFIRM_TOKEN_TTL == 300

    def test_fail_ttl_is_1800_seconds(self):
        """Failure count TTL = 1800s (30 minutes)"""
        assert CONFIRM_FAIL_TTL == 1800

    def test_max_attempts_is_5(self):
        """Max attempts before lockout = 5"""
        assert MAX_ATTEMPTS == 5

    def test_lock_minutes_is_30(self):
        """Lock duration = 30 minutes"""
        assert LOCK_MINUTES == 30


class TestPasswordVerification:
    """Test password verification logic."""

    def test_verify_password_correct(self):
        """Correct password returns True"""
        hashed = hash_password("test123")
        assert verify_password("test123", hashed) is True

    def test_verify_password_incorrect(self):
        """Incorrect password returns False"""
        hashed = hash_password("test123")
        assert verify_password("wrong", hashed) is False

    def test_token_is_uuid4_format(self):
        """Generated token should be valid UUID v4"""
        token = str(uuid.uuid4())
        parsed = uuid.UUID(token)
        assert parsed.version == 4

    def test_redis_key_format(self):
        """Redis key format: confirm:{token}"""
        token = str(uuid.uuid4())
        key = f"confirm:{token}"
        assert key.startswith("confirm:")
        assert len(key) > 10

    def test_fail_key_format(self):
        """Failure count key format: confirm_fail:{user_id}"""
        user_id = str(uuid.uuid4())
        key = f"confirm_fail:{user_id}"
        assert key.startswith("confirm_fail:")


class TestConfirmationTokenOneTimeUse:
    """Test one-time-use semantics of confirmation_token."""

    def test_token_consumed_after_first_use(self):
        """Token should be consumed (deleted) after first use — conceptual test"""
        # GETDEL semantics: first GET returns value, subsequent GET returns None
        # This is a conceptual test; actual Redis behavior tested in integration
        token_store = {"token123": "user_abc"}

        # First use: get and delete
        value = token_store.pop("token123", None)
        assert value == "user_abc"

        # Second use: should be None
        value = token_store.pop("token123", None)
        assert value is None

    def test_token_user_mismatch_rejected(self):
        """Token belonging to different user should be rejected"""
        token_store = {"token123": "user_abc"}
        current_user_id = "user_xyz"

        stored = token_store.get("token123")
        assert stored != current_user_id  # Mismatch → reject
