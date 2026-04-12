"""Redis 连接模块 — 使用 redis.asyncio 创建连接池 + 依赖注入"""

from collections.abc import AsyncGenerator

from redis.asyncio import Redis, from_url

from app.core.config import settings

redis_client: Redis = from_url(
    settings.REDIS_URL,
    decode_responses=True,
)


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI 依赖注入：提供 Redis 客户端实例。"""
    yield redis_client
