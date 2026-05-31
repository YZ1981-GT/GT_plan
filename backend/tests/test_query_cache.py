"""Tests for query_cache service — Redis 短 TTL 缓存

Validates: Requirements 4.1, 4.3
- 高频相同查询结果加 Redis 短 TTL 缓存（query hash 为 key）
- 不动白名单安全模型（缓存在安全校验之后）
- Redis 不可用时优雅降级
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.query_cache import (
    DEFAULT_TTL_SECONDS,
    compute_cache_key,
    get_cached_result,
    set_cached_result,
)

# patch target: lazy import inside query_cache functions
_REDIS_PATCH = "app.core.redis.get_redis"


# ─── compute_cache_key 测试 ──────────────────────────────────────────────────


class TestComputeCacheKey:
    """cache key 计算逻辑"""

    def test_same_params_produce_same_key(self):
        """相同参数产生相同 key"""
        key1 = compute_cache_key("user1", "proj1", {"source": "report", "year": 2025})
        key2 = compute_cache_key("user1", "proj1", {"source": "report", "year": 2025})
        assert key1 == key2

    def test_different_user_produces_different_key(self):
        """不同用户产生不同 key（防跨租户泄漏）"""
        key1 = compute_cache_key("user1", "proj1", {"source": "report"})
        key2 = compute_cache_key("user2", "proj1", {"source": "report"})
        assert key1 != key2

    def test_different_project_produces_different_key(self):
        """不同项目产生不同 key"""
        key1 = compute_cache_key("user1", "proj1", {"source": "report"})
        key2 = compute_cache_key("user1", "proj2", {"source": "report"})
        assert key1 != key2

    def test_different_params_produce_different_key(self):
        """不同查询参数产生不同 key"""
        key1 = compute_cache_key("user1", "proj1", {"source": "report", "year": 2025})
        key2 = compute_cache_key("user1", "proj1", {"source": "report", "year": 2024})
        assert key1 != key2

    def test_key_has_correct_prefix(self):
        """key 有正确前缀"""
        key = compute_cache_key("user1", "proj1", {"source": "report"})
        assert key.startswith("query_cache:")

    def test_param_order_does_not_matter(self):
        """参数顺序不影响 key（sort_keys=True）"""
        key1 = compute_cache_key("u", "p", {"a": 1, "b": 2})
        key2 = compute_cache_key("u", "p", {"b": 2, "a": 1})
        assert key1 == key2


# ─── get_cached_result 测试 ──────────────────────────────────────────────────


class TestGetCachedResult:
    """Redis 读取缓存"""

    @pytest.mark.asyncio
    async def test_returns_none_when_redis_unavailable(self):
        """Redis 不可用时返回 None（降级）"""
        mock_get_redis = AsyncMock(return_value=None)
        with patch(_REDIS_PATCH, mock_get_redis):
            result = await get_cached_result("query_cache:abc123")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self):
        """缓存未命中返回 None"""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_get_redis = AsyncMock(return_value=mock_redis)
        with patch(_REDIS_PATCH, mock_get_redis):
            result = await get_cached_result("query_cache:abc123")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_cached_data_on_hit(self):
        """缓存命中返回反序列化数据"""
        cached_data = {"rows": [{"id": 1}], "columns": ["id"], "total": 1}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))
        mock_get_redis = AsyncMock(return_value=mock_redis)
        with patch(_REDIS_PATCH, mock_get_redis):
            result = await get_cached_result("query_cache:abc123")
            assert result == cached_data

    @pytest.mark.asyncio
    async def test_returns_none_on_deserialization_error(self):
        """反序列化失败返回 None（降级）"""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="not valid json{{{")
        mock_get_redis = AsyncMock(return_value=mock_redis)
        with patch(_REDIS_PATCH, mock_get_redis):
            result = await get_cached_result("query_cache:abc123")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_exception(self):
        """Redis 异常时返回 None（降级）"""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("connection lost"))
        mock_get_redis = AsyncMock(return_value=mock_redis)
        with patch(_REDIS_PATCH, mock_get_redis):
            result = await get_cached_result("query_cache:abc123")
            assert result is None


# ─── set_cached_result 测试 ──────────────────────────────────────────────────


class TestSetCachedResult:
    """Redis 写入缓存"""

    @pytest.mark.asyncio
    async def test_writes_to_redis_with_ttl(self):
        """成功结果写入 Redis 并设置 TTL"""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        result_data = {"rows": [{"id": 1}], "columns": ["id"], "total": 1}
        mock_get_redis = AsyncMock(return_value=mock_redis)

        with patch(_REDIS_PATCH, mock_get_redis):
            await set_cached_result("query_cache:abc123", result_data)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "query_cache:abc123"
        assert json.loads(call_args[0][1]) == result_data
        assert call_args[1]["ex"] == DEFAULT_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_does_not_cache_error_results(self):
        """错误结果不缓存"""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        error_result = {"rows": [], "columns": [], "total": 0, "error": "查询失败"}
        mock_get_redis = AsyncMock(return_value=mock_redis)

        with patch(_REDIS_PATCH, mock_get_redis):
            await set_cached_result("query_cache:abc123", error_result)

        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_graceful_when_redis_unavailable(self):
        """Redis 不可用时静默跳过"""
        mock_get_redis = AsyncMock(return_value=None)
        with patch(_REDIS_PATCH, mock_get_redis):
            # 不应抛异常
            await set_cached_result("query_cache:abc123", {"rows": [], "total": 0})

    @pytest.mark.asyncio
    async def test_graceful_on_redis_exception(self):
        """Redis 写入异常时静默跳过"""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=Exception("write failed"))
        mock_get_redis = AsyncMock(return_value=mock_redis)

        with patch(_REDIS_PATCH, mock_get_redis):
            # 不应抛异常
            await set_cached_result("query_cache:abc123", {"rows": [{"x": 1}], "total": 1})

    @pytest.mark.asyncio
    async def test_custom_ttl(self):
        """支持自定义 TTL"""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        result_data = {"rows": [], "columns": [], "total": 0}
        mock_get_redis = AsyncMock(return_value=mock_redis)

        with patch(_REDIS_PATCH, mock_get_redis):
            await set_cached_result("query_cache:abc123", result_data, ttl=60)

        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 60
