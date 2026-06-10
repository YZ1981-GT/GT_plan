# Feature: zero-downtime-deployment, Property 13
"""Property 13: 后台 worker 选主唯一性。

Validates: Requirements 4.5
N 个副本对同一 worker key 并发选主，同一时刻至多一个返回 True。
"""
import asyncio

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st
from unittest.mock import patch, AsyncMock


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(n_replicas=st.integers(min_value=2, max_value=5))
@pytest.mark.asyncio
async def test_property13_at_most_one_leader(n_replicas):
    """同一时刻至多一个 try_acquire_leadership 返回 True。"""
    # Simulate Redis SET NX behavior: only first caller succeeds
    lock_held = {"value": False}

    async def mock_redis_set(key, value, nx=False, px=None):
        if nx and not lock_held["value"]:
            lock_held["value"] = True
            return True
        return None  # Redis returns None when key exists with NX

    mock_redis = AsyncMock()
    mock_redis.set = mock_redis_set

    async def mock_get_redis():
        return mock_redis

    with patch("app.core.redis.get_redis", mock_get_redis):
        from app.workers._leader_lock import try_acquire_leadership

        # All replicas try concurrently
        results = await asyncio.gather(
            *[try_acquire_leadership("test_worker") for _ in range(n_replicas)]
        )

        # At most one should be True
        leaders = sum(1 for r in results if r)
        assert leaders <= 1, f"Expected at most 1 leader, got {leaders}"
        # At least one should get it (first caller)
        assert leaders == 1, f"Expected exactly 1 leader, got {leaders}"
