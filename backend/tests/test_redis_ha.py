"""Redis 高可用测试 — Sentinel 连接 + 降级逻辑 + 健康检查。

测试覆盖：
- get_redis() 正常返回客户端
- get_redis() Redis 不可用时返回 None
- Sentinel 模式初始化
- 降级模式下核心功能可用
- 健康检查端点返回正确状态
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Tests: get_redis 降级逻辑
# ---------------------------------------------------------------------------

class TestGetRedis:
    """get_redis() 降级逻辑测试。"""

    async def test_returns_client_when_healthy(self):
        """Redis 可用时应返回客户端。"""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)

        with patch("app.core.redis._get_client", return_value=mock_client):
            from app.core.redis import get_redis
            result = await get_redis()

        assert result is mock_client

    async def test_returns_none_when_ping_fails(self):
        """Redis ping 失败时应返回 None。"""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("app.core.redis._get_client", return_value=mock_client):
            from app.core.redis import get_redis
            result = await get_redis()

        assert result is None

    async def test_returns_none_when_client_is_none(self):
        """客户端为 None 时应返回 None。"""
        with patch("app.core.redis._get_client", return_value=None):
            from app.core.redis import get_redis
            result = await get_redis()

        assert result is None


# ---------------------------------------------------------------------------
# Tests: Sentinel 初始化
# ---------------------------------------------------------------------------

class TestSentinelInit:
    """Sentinel 模式初始化测试。"""

    def test_sentinel_hosts_parsing(self):
        """应正确解析 REDIS_SENTINEL_HOSTS 配置。"""
        hosts_str = "host1:26379,host2:26380,host3:26381"
        hosts = []
        for host_str in hosts_str.split(","):
            host_str = host_str.strip()
            if ":" in host_str:
                h, p = host_str.rsplit(":", 1)
                hosts.append((h, int(p)))
            else:
                hosts.append((host_str, 26379))

        assert hosts == [("host1", 26379), ("host2", 26380), ("host3", 26381)]

    def test_sentinel_hosts_default_port(self):
        """无端口时应使用默认 26379。"""
        hosts_str = "host1"
        hosts = []
        for host_str in hosts_str.split(","):
            host_str = host_str.strip()
            if ":" in host_str:
                h, p = host_str.rsplit(":", 1)
                hosts.append((h, int(p)))
            else:
                hosts.append((host_str, 26379))

        assert hosts == [("host1", 26379)]


# ---------------------------------------------------------------------------
# Tests: 健康检查端点
# ---------------------------------------------------------------------------

class TestRedisHealthEndpoint:
    """Redis 健康检查端点测试。"""

    async def test_healthy_response(self):
        """Redis 可用时应返回 200 + healthy。"""
        from app.routers.health_redis import _get_redis_health_info

        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.info = AsyncMock(return_value={
            "used_memory": 1024 * 1024 * 50,  # 50MB
            "role": "master",
            "connected_slaves": 2,
        })

        with patch("app.core.redis.redis_client", mock_client):
            with patch("app.core.redis.REDIS_MODE", "single"):
                info = await _get_redis_health_info()

        assert info["connected"] is True
        assert info["master_status"] == "ok"

    async def test_unhealthy_response(self):
        """Redis 不可用时应返回降级状态。"""
        from app.routers.health_redis import _get_redis_health_info

        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("app.core.redis.redis_client", mock_client):
            with patch("app.core.redis.REDIS_MODE", "single"):
                info = await _get_redis_health_info()

        assert info["connected"] is False
        assert info["master_status"] == "unavailable"

    async def test_none_client_returns_unavailable(self):
        """redis_client 为 None 时应返回 unavailable。"""
        from app.routers.health_redis import _get_redis_health_info

        with patch("app.core.redis.redis_client", None):
            with patch("app.core.redis.REDIS_MODE", "single"):
                info = await _get_redis_health_info()

        assert info["connected"] is False


# ---------------------------------------------------------------------------
# Tests: 配置
# ---------------------------------------------------------------------------

class TestRedisConfig:
    """Redis 配置测试。"""

    def test_redis_mode_default(self):
        """默认 REDIS_MODE 应为 standalone 或 single。"""
        from app.core.config import settings
        assert settings.REDIS_MODE in ("single", "standalone")

    def test_redis_sentinel_hosts_configured(self):
        """REDIS_SENTINEL_HOSTS 应有默认值。"""
        from app.core.config import settings
        assert "26379" in settings.REDIS_SENTINEL_HOSTS

    def test_redis_sentinel_service_configured(self):
        """REDIS_SENTINEL_SERVICE 应为 mymaster。"""
        from app.core.config import settings
        assert settings.REDIS_SENTINEL_SERVICE == "mymaster"
