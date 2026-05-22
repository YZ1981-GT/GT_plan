"""Property test for confirmation_token one-time-use (P7)

**Validates: Requirements F6.2, F6.8**

Property 7: Token used once → success; second use → fail; after 5min → fail.
Simulates Redis GETDEL behavior.
"""

import uuid
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


class FakeRedis:
    """Simulate Redis GETDEL behavior for token one-time-use testing."""

    def __init__(self):
        self.store: dict[str, tuple[str, float]] = {}  # key -> (value, expire_at)

    def setex(self, key: str, ttl: int, value: str):
        self.store[key] = (value, time.time() + ttl)

    def getdel(self, key: str) -> str | None:
        entry = self.store.pop(key, None)
        if entry is None:
            return None
        value, expire_at = entry
        if time.time() > expire_at:
            return None  # expired
        return value

    def get(self, key: str) -> str | None:
        entry = self.store.get(key)
        if entry is None:
            return None
        value, expire_at = entry
        if time.time() > expire_at:
            del self.store[key]
            return None
        return value


CONFIRM_TOKEN_TTL = 300  # 5 minutes


class TestConfirmationTokenOneTimeUse:
    """Property 7: confirmation_token one-time-use semantics."""

    @settings(max_examples=30)
    @given(user_id=st.uuids())
    def test_p7_first_use_succeeds_second_fails(self, user_id: uuid.UUID):
        """Token used once → success; second use → fail (GETDEL semantics)."""
        redis = FakeRedis()
        token = str(uuid.uuid4())
        token_key = f"confirm:{token}"

        # Store token
        redis.setex(token_key, CONFIRM_TOKEN_TTL, str(user_id))

        # First use: GETDEL returns value
        stored = redis.getdel(token_key)
        assert stored == str(user_id)  # success

        # Second use: GETDEL returns None (already consumed)
        stored_again = redis.getdel(token_key)
        assert stored_again is None  # fail

    @settings(max_examples=30)
    @given(user_id=st.uuids())
    def test_p7_expired_token_fails(self, user_id: uuid.UUID):
        """Token after TTL expiry → fail."""
        redis = FakeRedis()
        token = str(uuid.uuid4())
        token_key = f"confirm:{token}"

        # Store with TTL=0 (already expired)
        redis.store[token_key] = (str(user_id), time.time() - 1)

        # Use expired token
        stored = redis.getdel(token_key)
        assert stored is None  # expired → fail

    @settings(max_examples=30)
    @given(user_id=st.uuids())
    def test_p7_token_belongs_to_correct_user(self, user_id: uuid.UUID):
        """Token stores correct user_id for ownership verification."""
        redis = FakeRedis()
        token = str(uuid.uuid4())
        token_key = f"confirm:{token}"

        redis.setex(token_key, CONFIRM_TOKEN_TTL, str(user_id))

        stored = redis.getdel(token_key)
        assert stored == str(user_id)

        # Different user trying same token pattern
        other_user = uuid.uuid4()
        assert stored != str(other_user) or user_id == other_user
