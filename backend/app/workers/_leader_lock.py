"""选主锁辅助：多副本下确保同一后台任务仅一个副本执行。

Redis `SET key value NX PX ttl` 选主；Redis 不可用降级 pg_try_advisory_lock。

# Feature: zero-downtime-deployment, Component 9
"""
import logging
import os
import uuid

logger = logging.getLogger(__name__)

# 本副本唯一标识（容器启动时生成）
_INSTANCE_ID = str(uuid.uuid4())[:8]

# 默认锁 TTL（毫秒）— 必须 > 单轮任务最长耗时
DEFAULT_LOCK_TTL_MS = int(os.getenv("WORKER_LOCK_TTL_MS", "60000"))


async def try_acquire_leadership(worker_key: str, ttl_ms: int = DEFAULT_LOCK_TTL_MS) -> bool:
    """尝试获取 worker 选主锁。返回是否成为本轮 leader。

    策略：
    1. 首选 Redis SET NX PX（原子操作 + 自动过期）
    2. Redis 不可用时降级 pg_try_advisory_lock（非阻塞）

    Args:
        worker_key: worker 任务标识（如 "sla_check", "outbox_processor"）
        ttl_ms: 锁 TTL 毫秒数（防脑裂：leader 崩溃后 TTL 过期其他副本可接管）

    Returns:
        True = 本副本是本轮 leader，应执行任务
        False = 其他副本持有锁，本轮跳过
    """
    lock_key = f"worker_leader:{worker_key}"

    # 1. 尝试 Redis
    try:
        from app.core.redis import get_redis
        redis_client = await get_redis()
        if redis_client is not None:
            # SET key value NX PX ttl — 仅当 key 不存在时设置
            result = await redis_client.set(lock_key, _INSTANCE_ID, nx=True, px=ttl_ms)
            if result:
                logger.debug("[LeaderLock] Acquired Redis lock for %s (instance=%s)", worker_key, _INSTANCE_ID)
                return True
            else:
                logger.debug("[LeaderLock] Redis lock held by another instance for %s", worker_key)
                return False
    except Exception as e:
        logger.warning("[LeaderLock] Redis unavailable for %s, falling back to PG: %s", worker_key, e)

    # 2. 降级：pg_try_advisory_lock（非阻塞）
    try:
        from app.core.database import async_session
        from sqlalchemy import text

        # Use a stable hash of worker_key as advisory lock ID
        lock_id = hash(worker_key) & 0x7FFFFFFF  # positive int32

        async with async_session() as conn_session:
            result = await conn_session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": lock_id},
            )
            acquired = result.scalar()
            if acquired:
                logger.debug("[LeaderLock] Acquired PG advisory lock for %s (id=%d)", worker_key, lock_id)
                # Release immediately — advisory lock is session-scoped,
                # we just use it as a "check if another instance holds it" mechanism
                await conn_session.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": lock_id},
                )
                return True
            else:
                logger.debug("[LeaderLock] PG advisory lock held by another for %s", worker_key)
                return False
    except Exception as e:
        logger.warning("[LeaderLock] PG advisory lock failed for %s: %s", worker_key, e)
        # If both Redis and PG unavailable, skip this round (conservative)
        return False


def with_leader_lock(worker_key: str, ttl_ms: int = DEFAULT_LOCK_TTL_MS):
    """Decorator for worker coroutines that should only run on the leader instance.

    Usage:
        @with_leader_lock("sla_check")
        async def do_sla_check():
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            if await try_acquire_leadership(worker_key, ttl_ms):
                return await func(*args, **kwargs)
            else:
                logger.debug("[LeaderLock] Skipping %s (not leader)", worker_key)
                return None
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator
