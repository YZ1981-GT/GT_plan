"""Tests for Phase 3 F3.4 CacheService — TB 查询缓存 + Prefill 结果缓存"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.cache_service import (
    CacheService,
    NS_PREFILL,
    NS_TB_QUERY,
    PREFILL_RESULT_TTL,
    TB_QUERY_TTL,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Create a mock Redis client with async methods."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.scan = AsyncMock(return_value=(0, []))
    return redis


@pytest.fixture
def cache_svc(mock_redis):
    """Create CacheService with mock Redis."""
    return CacheService(mock_redis)


@pytest.fixture
def sample_project_id():
    return UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def sample_wp_id():
    return UUID("abcdefab-cdef-abcd-efab-cdefabcdefab")


@pytest.fixture
def sample_tb_data():
    return [
        {
            "standard_account_code": "1001",
            "account_name": "库存现金",
            "account_category": "asset",
            "unadjusted_amount": "50000.00",
            "rje_adjustment": "0",
            "aje_adjustment": "0",
            "audited_amount": "50000.00",
            "opening_balance": "45000.00",
            "exceeds_materiality": False,
            "below_trivial": True,
            "updated_at": "2026-05-27T10:00:00",
        },
        {
            "standard_account_code": "1002",
            "account_name": "银行存款",
            "account_category": "asset",
            "unadjusted_amount": "4950000.00",
            "rje_adjustment": "0",
            "aje_adjustment": "0",
            "audited_amount": "4950000.00",
            "opening_balance": "4800000.00",
            "exceeds_materiality": True,
            "below_trivial": False,
            "updated_at": "2026-05-27T10:00:00",
        },
    ]


# ---------------------------------------------------------------------------
# TB Query Cache Tests
# ---------------------------------------------------------------------------


class TestTBQueryCache:
    """TB 查询缓存测试"""

    @pytest.mark.asyncio
    async def test_tb_cache_key_format(self, cache_svc, sample_project_id):
        """验证 TB 缓存 key 格式正确"""
        key = cache_svc._tb_cache_key(sample_project_id, 2025, "001")
        assert key == f"{NS_TB_QUERY}:{sample_project_id}:2025:001"

    @pytest.mark.asyncio
    async def test_get_tb_cache_miss(self, cache_svc, mock_redis, sample_project_id):
        """缓存未命中返回 None"""
        mock_redis.get.return_value = None
        result = await cache_svc.get_tb_cache(sample_project_id, 2025)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_tb_cache_hit(self, cache_svc, mock_redis, sample_project_id, sample_tb_data):
        """缓存命中返回数据"""
        mock_redis.get.return_value = json.dumps(sample_tb_data)
        result = await cache_svc.get_tb_cache(sample_project_id, 2025)
        assert result == sample_tb_data
        assert len(result) == 2
        assert result[0]["standard_account_code"] == "1001"

    @pytest.mark.asyncio
    async def test_set_tb_cache(self, cache_svc, mock_redis, sample_project_id, sample_tb_data):
        """设置 TB 缓存使用正确的 TTL"""
        await cache_svc.set_tb_cache(sample_project_id, 2025, "001", sample_tb_data)
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get("ex") == TB_QUERY_TTL or call_args[1].get("ex") == TB_QUERY_TTL

    @pytest.mark.asyncio
    async def test_invalidate_tb_cache_with_year(self, cache_svc, mock_redis, sample_project_id):
        """失效指定年份的 TB 缓存"""
        mock_redis.scan.return_value = (0, [b"tb_query:xxx:2025:001"])
        await cache_svc.invalidate_tb_cache(sample_project_id, 2025)
        mock_redis.scan.assert_called()

    @pytest.mark.asyncio
    async def test_invalidate_tb_cache_all_years(self, cache_svc, mock_redis, sample_project_id):
        """失效所有年份的 TB 缓存"""
        mock_redis.scan.return_value = (0, [])
        await cache_svc.invalidate_tb_cache(sample_project_id)
        call_args = mock_redis.scan.call_args
        # pattern 应不含年份
        pattern = call_args.kwargs.get("match") or call_args[1].get("match")
        assert f"{sample_project_id}:*" in pattern

    @pytest.mark.asyncio
    async def test_get_tb_cache_redis_error(self, cache_svc, mock_redis, sample_project_id):
        """Redis 异常时降级返回 None（不阻断请求）"""
        mock_redis.get.side_effect = Exception("Redis connection refused")
        result = await cache_svc.get_tb_cache(sample_project_id, 2025)
        assert result is None

    @pytest.mark.asyncio
    async def test_set_tb_cache_redis_error(self, cache_svc, mock_redis, sample_project_id, sample_tb_data):
        """Redis 写入异常时静默失败（不阻断请求）"""
        mock_redis.set.side_effect = Exception("Redis connection refused")
        # 不应抛出异常
        await cache_svc.set_tb_cache(sample_project_id, 2025, "001", sample_tb_data)


# ---------------------------------------------------------------------------
# Prefill Result Cache Tests
# ---------------------------------------------------------------------------


class TestPrefillCache:
    """Prefill 结果缓存测试"""

    @pytest.mark.asyncio
    async def test_prefill_cache_key_format(self, cache_svc, sample_wp_id):
        """验证 Prefill 缓存 key 格式正确"""
        tb_version = "abc123def456"
        key = cache_svc._prefill_cache_key(sample_wp_id, tb_version)
        assert key == f"{NS_PREFILL}:{sample_wp_id}:{tb_version}"

    @pytest.mark.asyncio
    async def test_compute_tb_version(self, sample_project_id):
        """TB 版本计算确定性"""
        v1 = CacheService.compute_tb_version(sample_project_id, 2025, "2026-05-27T10:00:00")
        v2 = CacheService.compute_tb_version(sample_project_id, 2025, "2026-05-27T10:00:00")
        assert v1 == v2
        assert len(v1) == 12  # md5[:12]

    @pytest.mark.asyncio
    async def test_compute_tb_version_changes_with_update(self, sample_project_id):
        """TB 数据更新后版本标识变化"""
        v1 = CacheService.compute_tb_version(sample_project_id, 2025, "2026-05-27T10:00:00")
        v2 = CacheService.compute_tb_version(sample_project_id, 2025, "2026-05-27T11:00:00")
        assert v1 != v2

    @pytest.mark.asyncio
    async def test_get_prefill_cache_miss(self, cache_svc, mock_redis, sample_wp_id):
        """Prefill 缓存未命中返回 None"""
        mock_redis.get.return_value = None
        result = await cache_svc.get_prefill_cache(sample_wp_id, "version123")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_prefill_cache_hit(self, cache_svc, mock_redis, sample_wp_id):
        """Prefill 缓存命中返回结果"""
        prefill_result = {
            "wp_id": str(sample_wp_id),
            "status": "ok",
            "formulas_found": 10,
            "formulas_filled": 8,
            "errors": [],
            "message": "预填充完成：8/10 个公式已计算",
        }
        mock_redis.get.return_value = json.dumps(prefill_result)
        result = await cache_svc.get_prefill_cache(sample_wp_id, "version123")
        assert result["status"] == "ok"
        assert result["formulas_filled"] == 8

    @pytest.mark.asyncio
    async def test_set_prefill_cache(self, cache_svc, mock_redis, sample_wp_id):
        """设置 Prefill 缓存使用正确的 TTL"""
        prefill_result = {"wp_id": str(sample_wp_id), "status": "ok", "formulas_filled": 5}
        await cache_svc.set_prefill_cache(sample_wp_id, "version123", prefill_result)
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get("ex") == PREFILL_RESULT_TTL or call_args[1].get("ex") == PREFILL_RESULT_TTL

    @pytest.mark.asyncio
    async def test_invalidate_prefill_cache(self, cache_svc, mock_redis, sample_wp_id):
        """失效指定底稿的 Prefill 缓存"""
        mock_redis.scan.return_value = (0, [b"prefill_result:xxx:v1"])
        deleted = await cache_svc.invalidate_prefill_cache(sample_wp_id)
        mock_redis.scan.assert_called()

    @pytest.mark.asyncio
    async def test_prefill_cache_redis_error(self, cache_svc, mock_redis, sample_wp_id):
        """Redis 异常时降级返回 None"""
        mock_redis.get.side_effect = Exception("Redis timeout")
        result = await cache_svc.get_prefill_cache(sample_wp_id, "version123")
        assert result is None


# ---------------------------------------------------------------------------
# Cache Stats Tests
# ---------------------------------------------------------------------------


class TestCacheStats:
    """缓存统计测试"""

    @pytest.mark.asyncio
    async def test_get_cache_stats(self, cache_svc, mock_redis):
        """获取缓存统计信息"""
        mock_redis.scan.return_value = (0, [])
        stats = await cache_svc.get_cache_stats()
        assert NS_TB_QUERY in stats
        assert NS_PREFILL in stats
        assert stats[NS_TB_QUERY]["key_count"] == 0
        assert stats[NS_PREFILL]["key_count"] == 0


# ---------------------------------------------------------------------------
# DB Pool Configuration Tests
# ---------------------------------------------------------------------------


class TestDBPoolConfig:
    """DB 连接池配置验证"""

    def test_pool_size_optimized(self):
        """验证连接池配置已优化为 6000 并发目标"""
        from app.core.config import settings
        assert settings.DB_POOL_SIZE >= 50, "pool_size 应 >= 50（6000 并发优化）"
        assert settings.DB_MAX_OVERFLOW >= 100, "max_overflow 应 >= 100（6000 并发优化）"

    def test_pool_total_capacity(self):
        """验证连接池总容量 >= 150"""
        from app.core.config import settings
        total = settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW
        assert total >= 150, f"连接池总容量 {total} 应 >= 150"
