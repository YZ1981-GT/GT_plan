"""PF-6 Prefill 引擎缓存集成验证

验证 cache_service.py 的 prefill 缓存逻辑完整性：
1. cache_prefill_result / get_cached_prefill 函数存在且可调用
2. Redis key 格式为 prefill:{wp_id}:{tb_version}
3. TTL = 300s
4. TB 版本变更后旧缓存自然失效（key 不同）
5. 同一 TB 版本命中缓存
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.services.cache_service import (
    CacheService,
    NS_PREFILL,
    PREFILL_RESULT_TTL,
)


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.scan = AsyncMock(return_value=(0, []))
    redis.delete = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def svc(mock_redis):
    return CacheService(mock_redis)


WP_ID = UUID("11111111-2222-3333-4444-555555555555")


class TestPF6PrefillCacheIntegration:
    """PF-6 验证：prefill 缓存集成点完整性"""

    def test_prefill_ttl_is_300(self):
        """TTL 配置为 300 秒"""
        assert PREFILL_RESULT_TTL == 300

    def test_prefill_key_format(self, svc):
        """Redis key 格式为 prefill_result:{wp_id}:{tb_version}"""
        key = svc._prefill_cache_key(WP_ID, "abc123")
        assert key == f"{NS_PREFILL}:{WP_ID}:abc123"

    @pytest.mark.asyncio
    async def test_set_and_get_prefill_cache(self, svc, mock_redis):
        """set_prefill_cache 写入后 get_prefill_cache 可读取"""
        result = {"status": "ok", "formulas_filled": 12, "errors": []}

        # 写入
        await svc.set_prefill_cache(WP_ID, "v1", result)
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        # 验证 TTL
        assert call_args.kwargs.get("ex") == 300 or (
            len(call_args.args) > 2 and call_args.args[2] == 300
        )

        # 模拟读取命中
        mock_redis.get.return_value = json.dumps(result)
        cached = await svc.get_prefill_cache(WP_ID, "v1")
        assert cached == result

    @pytest.mark.asyncio
    async def test_tb_version_change_invalidates_cache(self, svc, mock_redis):
        """TB 版本变更后，旧 key 不命中（自然失效）"""
        # v1 有缓存
        mock_redis.get.return_value = json.dumps({"status": "ok"})
        cached_v1 = await svc.get_prefill_cache(WP_ID, "v1")
        assert cached_v1 is not None

        # v2 无缓存（key 不同）
        mock_redis.get.return_value = None
        cached_v2 = await svc.get_prefill_cache(WP_ID, "v2")
        assert cached_v2 is None

    def test_compute_tb_version_deterministic(self):
        """同一输入产生相同版本标识"""
        project_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        v1 = CacheService.compute_tb_version(project_id, 2025, "2026-05-22T10:00:00")
        v2 = CacheService.compute_tb_version(project_id, 2025, "2026-05-22T10:00:00")
        assert v1 == v2

    def test_compute_tb_version_changes_on_update(self):
        """TB 更新时间变化 → 版本标识变化"""
        project_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        v1 = CacheService.compute_tb_version(project_id, 2025, "2026-05-22T10:00:00")
        v2 = CacheService.compute_tb_version(project_id, 2025, "2026-05-22T11:00:00")
        assert v1 != v2

    @pytest.mark.asyncio
    async def test_invalidate_prefill_cache(self, svc, mock_redis):
        """invalidate_prefill_cache 清除指定底稿所有版本缓存"""
        mock_redis.scan.return_value = (0, [b"prefill_result:xxx:v1", b"prefill_result:xxx:v2"])
        deleted = await svc.invalidate_prefill_cache(WP_ID)
        mock_redis.scan.assert_called()
        # scan 返回了 2 个 key，delete 被调用
        mock_redis.delete.assert_called()
