"""Tests for audit throttle service (Req 7)

Property 13: 审计节流窗口 — 相同三元组 5s 内只有首次返回 True
Property 14: 敏感操作绕过节流 — cell_writeback / cross_sheet_trace 永远返回 True
Redis 降级单测 — Redis 不可用时全部记录 + logger.warning
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import fakeredis.aioredis
import pytest
import pytest_asyncio
from hypothesis import given, settings, strategies as st
from redis.exceptions import RedisError

from app.services.audit_throttle import (
    SENSITIVE_ACTIONS,
    THROTTLE_WINDOW_SECONDS,
    _build_throttle_key,
    should_record,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def fake_redis():
    """Provide a fresh fakeredis instance for each test."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ---------------------------------------------------------------------------
# Property 13: 审计节流窗口
# Feature: advanced-query-enhancements-p1p2, Property 13: Audit throttle window
# ---------------------------------------------------------------------------


class TestProperty13AuditThrottleWindow:
    """For same (user_id, source, filters) within 5s window, only first call returns True."""

    @pytest.mark.asyncio
    @settings(max_examples=20)
    @given(
        user_id=st.text(min_size=1, max_size=36, alphabet=st.characters(whitelist_categories=("L", "N", "Pd"))),
        source=st.sampled_from(["workpaper:D2|审定表D2-1", "consol_unit:S01:tb_detail", "disclosure_note:五-1-1"]),
        filter_key=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",))),
        filter_val=st.text(min_size=0, max_size=50),
    )
    async def test_first_call_returns_true_subsequent_false(
        self, user_id, source, filter_key, filter_val
    ):
        """First call within window → True, second call → False.

        **Validates: Requirements 7.1, 7.2**
        """
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        try:
            filters = {filter_key: filter_val}

            # First call: should record
            result1 = await should_record(redis, user_id, source, filters)
            assert result1 is True

            # Second call with same params: should skip (within 5s window)
            result2 = await should_record(redis, user_id, source, filters)
            assert result2 is False
        finally:
            await redis.aclose()

    @pytest.mark.asyncio
    async def test_different_user_not_throttled(self, fake_redis):
        """Different user_id should not be throttled by another user's window."""
        source = "workpaper:D2|审定表D2-1"
        filters = {"year": "2025"}

        r1 = await should_record(fake_redis, "user-A", source, filters)
        r2 = await should_record(fake_redis, "user-B", source, filters)

        assert r1 is True
        assert r2 is True

    @pytest.mark.asyncio
    async def test_different_source_not_throttled(self, fake_redis):
        """Different source should not be throttled."""
        user_id = "user-1"
        filters = {"year": "2025"}

        r1 = await should_record(fake_redis, user_id, "workpaper:D2|审定表D2-1", filters)
        r2 = await should_record(fake_redis, user_id, "workpaper:D3|审定表D3-1", filters)

        assert r1 is True
        assert r2 is True

    @pytest.mark.asyncio
    async def test_different_filters_not_throttled(self, fake_redis):
        """Different filters should not be throttled."""
        user_id = "user-1"
        source = "workpaper:D2|审定表D2-1"

        r1 = await should_record(fake_redis, user_id, source, {"year": "2025"})
        r2 = await should_record(fake_redis, user_id, source, {"year": "2024"})

        assert r1 is True
        assert r2 is True

    @pytest.mark.asyncio
    async def test_key_format(self):
        """Verify the throttle key format matches design spec."""
        key = _build_throttle_key("user-123", "workpaper:D2", {"year": 2025})
        assert key.startswith("audit:throttle:user-123:")
        # SHA1 hex digest is 40 chars
        suffix = key.split(":")[-1]
        assert len(suffix) == 40


# ---------------------------------------------------------------------------
# Property 14: 敏感操作绕过节流
# Feature: advanced-query-enhancements-p1p2, Property 14: Sensitive operations bypass throttle
# ---------------------------------------------------------------------------


class TestProperty14SensitiveOperationsBypass:
    """Sensitive operations (cell_writeback / cross_sheet_trace) always return True."""

    @pytest.mark.asyncio
    @settings(max_examples=20)
    @given(
        user_id=st.text(min_size=1, max_size=36, alphabet=st.characters(whitelist_categories=("L", "N", "Pd"))),
        source=st.sampled_from(["workpaper:D2|审定表D2-1", "consol_unit:S01:tb_detail"]),
        action=st.sampled_from(sorted(SENSITIVE_ACTIONS)),
        num_calls=st.integers(min_value=2, max_value=10),
    )
    async def test_sensitive_actions_always_record(
        self, user_id, source, action, num_calls
    ):
        """Sensitive actions bypass throttle regardless of window state.

        **Validates: Requirements 7.4**
        """
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        try:
            filters = {"year": "2025"}

            # All calls should return True for sensitive actions
            for _ in range(num_calls):
                result = await should_record(redis, user_id, source, filters, action=action)
                assert result is True
        finally:
            await redis.aclose()

    @pytest.mark.asyncio
    async def test_cell_writeback_bypasses_throttle(self, fake_redis):
        """cell_writeback action always records."""
        user_id = "user-1"
        source = "workpaper:D2|审定表D2-1"
        filters = {"year": "2025"}

        # First normal call sets the throttle key
        r1 = await should_record(fake_redis, user_id, source, filters)
        assert r1 is True

        # Second normal call is throttled
        r2 = await should_record(fake_redis, user_id, source, filters)
        assert r2 is False

        # But cell_writeback bypasses
        r3 = await should_record(fake_redis, user_id, source, filters, action="cell_writeback")
        assert r3 is True

    @pytest.mark.asyncio
    async def test_cross_sheet_trace_bypasses_throttle(self, fake_redis):
        """cross_sheet_trace action always records."""
        user_id = "user-1"
        source = "workpaper:D2|审定表D2-1"
        filters = {"year": "2025"}

        # Set throttle
        await should_record(fake_redis, user_id, source, filters)

        # cross_sheet_trace bypasses
        result = await should_record(fake_redis, user_id, source, filters, action="cross_sheet_trace")
        assert result is True


# ---------------------------------------------------------------------------
# Redis 降级单测
# ---------------------------------------------------------------------------


class TestRedisDegradation:
    """Redis 不可用时降级为全部记录 + logger.warning。"""

    @pytest.mark.asyncio
    async def test_redis_none_always_records(self):
        """When redis is None, should_record always returns True."""
        with patch("app.services.audit_throttle.logger") as mock_logger:
            result = await should_record(
                redis=None,
                user_id="user-1",
                source="workpaper:D2",
                filters={"year": "2025"},
            )
            assert result is True
            mock_logger.warning.assert_called_once()
            assert "Redis unavailable" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_redis_error_always_records(self, fake_redis):
        """When Redis raises RedisError, should_record returns True + warning."""
        # Patch the redis.set to raise RedisError
        fake_redis.set = AsyncMock(side_effect=RedisError("Connection refused"))

        with patch("app.services.audit_throttle.logger") as mock_logger:
            result = await should_record(
                redis=fake_redis,
                user_id="user-1",
                source="workpaper:D2",
                filters={"year": "2025"},
            )
            assert result is True
            mock_logger.warning.assert_called_once()
            assert "Redis unavailable" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_redis_error_does_not_block_request(self, fake_redis):
        """Redis errors should never raise exceptions to the caller."""
        fake_redis.set = AsyncMock(side_effect=RedisError("Timeout"))

        # Should not raise, just return True
        result = await should_record(
            redis=fake_redis,
            user_id="user-1",
            source="workpaper:D2",
            filters={},
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_redis_none_repeated_calls_all_record(self):
        """Multiple calls with redis=None all return True (no throttle)."""
        results = []
        for _ in range(5):
            r = await should_record(
                redis=None,
                user_id="user-1",
                source="workpaper:D2",
                filters={"year": "2025"},
            )
            results.append(r)

        assert all(results)
