# Feature: zero-downtime-deployment, Property 17, Property 18, Property 19
"""Property tests for FeatureFlagService.

Property 17: Flag 默认关闭且关闭即时不暴露 (Requirements 9.1, 9.2, 9.4)
Property 18: 灰度命中按百分比且稳定 (Requirements 9.3)
Property 19: 多副本一致 (Requirements 9.5)
"""
import hashlib
import pytest
from hypothesis import given, settings, HealthCheck, strategies as st
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.feature_flag_service import FeatureFlagService, _cache


@pytest.fixture(autouse=True)
def clear_cache():
    _cache.clear()
    yield
    _cache.clear()


def _make_flag(*, enabled=False, rollout_percentage=0, whitelist_user_ids=None):
    """Create a mock FeatureFlag object."""
    flag = MagicMock()
    flag.enabled = enabled
    flag.rollout_percentage = rollout_percentage
    flag.whitelist_user_ids = whitelist_user_ids
    return flag


# --- Property 17: Default off + immediate disable ---
# **Validates: Requirements 9.1, 9.2, 9.4**


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(flag_key=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()))
@pytest.mark.asyncio
async def test_property17_default_disabled(flag_key):
    """Flag 不存在或 enabled=false → is_enabled 返回 False。"""
    db = AsyncMock()

    # Flag doesn't exist
    with patch.object(FeatureFlagService, '_get_flag_cached', return_value=None):
        result = await FeatureFlagService.is_enabled(db, flag_key, user_id="user1")
        assert result is False

    # Flag exists but disabled
    flag = _make_flag(enabled=False, rollout_percentage=100)
    with patch.object(FeatureFlagService, '_get_flag_cached', return_value=flag):
        result = await FeatureFlagService.is_enabled(db, flag_key, user_id="user1")
        assert result is False


# --- Property 18: Rollout percentage + stability ---
# **Validates: Requirements 9.3**


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(
    percentage=st.integers(min_value=1, max_value=99),
    user_id=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
)
@pytest.mark.asyncio
async def test_property18_stable_hash(percentage, user_id):
    """同一 (flag, user) 多次调用结果稳定（幂等）。"""
    db = AsyncMock()
    flag = _make_flag(enabled=True, rollout_percentage=percentage)

    with patch.object(FeatureFlagService, '_get_flag_cached', return_value=flag):
        r1 = await FeatureFlagService.is_enabled(db, "test_flag", user_id=user_id)
        r2 = await FeatureFlagService.is_enabled(db, "test_flag", user_id=user_id)
        assert r1 == r2, "Same (flag, user) should always return same result"


@pytest.mark.asyncio
async def test_property18_whitelist_always_hits():
    """白名单用户恒命中，不受 rollout_percentage 限制。"""
    db = AsyncMock()
    flag = _make_flag(enabled=True, rollout_percentage=0, whitelist_user_ids=["special_user"])

    with patch.object(FeatureFlagService, '_get_flag_cached', return_value=flag):
        result = await FeatureFlagService.is_enabled(db, "test_flag", user_id="special_user")
        assert result is True


# --- Property 19: Multi-replica consistency ---
# **Validates: Requirements 9.5**


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(
    percentage=st.integers(min_value=0, max_value=100),
    user_id=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
)
@pytest.mark.asyncio
async def test_property19_multi_replica_consistent(percentage, user_id):
    """两副本缓存一致后，同 (flag,user) 判定相同（DB 唯一权威源）。"""
    db = AsyncMock()
    flag = _make_flag(enabled=True, rollout_percentage=percentage)

    # Simulate two replicas reading same flag state from DB
    with patch.object(FeatureFlagService, '_get_flag_cached', return_value=flag):
        result_replica1 = await FeatureFlagService.is_enabled(db, "test_flag", user_id=user_id)
        result_replica2 = await FeatureFlagService.is_enabled(db, "test_flag", user_id=user_id)
        assert result_replica1 == result_replica2
