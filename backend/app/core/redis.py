"""Redis 连接模块 — 支持单实例（开发）和 Sentinel（生产）两种模式。

模式由 REDIS_MODE 环境变量控制：
- "single"（默认）：直接连接单实例 Redis
- "sentinel"：通过 Redis Sentinel 连接，支持自动故障转移

降级策略：连接失败时返回 None，调用方检查后走 fallback 逻辑。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from redis.asyncio import Redis, from_url

from app.core.config import settings

logger = logging.getLogger("audit_platform.redis")

# Redis 模式：single / sentinel
REDIS_MODE = getattr(settings, "REDIS_MODE", "single")

# Sentinel 配置
REDIS_SENTINEL_HOSTS = getattr(settings, "REDIS_SENTINEL_HOSTS", "localhost:26379")
REDIS_SENTINEL_SERVICE = getattr(settings, "REDIS_SENTINEL_SERVICE", "mymaster")

# 全局客户端实例
_redis_client: Redis | None = None
_sentinel_instance = None


def _init_single_client() -> Redis:
    """初始化单实例 Redis 客户端。"""
    return from_url(settings.REDIS_URL, decode_responses=True)


def _init_sentinel_client() -> Redis | None:
    """初始化 Sentinel 模式 Redis 客户端。"""
    try:
        from redis.asyncio.sentinel import Sentinel

        # 解析 sentinel hosts（格式：host1:port1,host2:port2,...）
        hosts = []
        for host_str in REDIS_SENTINEL_HOSTS.split(","):
            host_str = host_str.strip()
            if ":" in host_str:
                h, p = host_str.rsplit(":", 1)
                hosts.append((h, int(p)))
            else:
                hosts.append((host_str, 26379))

        global _sentinel_instance
        _sentinel_instance = Sentinel(
            hosts,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
        )

        # 获取 master 连接
        master = _sentinel_instance.master_for(
            REDIS_SENTINEL_SERVICE,
            decode_responses=True,
        )
        logger.info("[Redis] Sentinel 模式初始化成功，service=%s", REDIS_SENTINEL_SERVICE)
        return master
    except Exception as e:
        logger.warning("[Redis] Sentinel 初始化失败: %s，降级为 None", e)
        return None


def _get_client() -> Redis | None:
    """获取或初始化 Redis 客户端。"""
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    if REDIS_MODE == "sentinel":
        _redis_client = _init_sentinel_client()
    else:
        _redis_client = _init_single_client()

    return _redis_client


# 向后兼容：模块级 redis_client 变量
redis_client: Redis = _init_single_client()


async def get_redis() -> Redis | None:
    """获取 Redis 客户端实例。

    Returns
    -------
    Redis | None
        Redis 客户端，连接不可用时返回 None（降级信号）。
        调用方应检查返回值：
            redis = await get_redis()
            if redis is None:
                # fallback 逻辑
    """
    client = _get_client()
    if client is None:
        return None

    try:
        await client.ping()
        return client
    except Exception as e:
        logger.warning("[Redis] ping 失败: %s，返回 None（降级）", e)
        return None


async def get_redis_or_fail() -> AsyncGenerator[Redis, None]:
    """FastAPI 依赖注入：提供 Redis 客户端实例（向后兼容，不降级）。

    用于不需要降级的场景（如旧代码迁移期间）。
    """
    client = _get_client()
    if client is None:
        client = redis_client  # fallback to module-level single client
    yield client
