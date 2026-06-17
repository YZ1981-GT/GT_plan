"""OnlyOffice 并发编辑会话限制器。

用 Redis 原子计数控制同时编辑文档的最大人数，超限时拒绝新会话。
前端收到 429 后弹窗提示"当前编辑人数已满，请稍后再试"。

配置：环境变量 ONLYOFFICE_MAX_SESSIONS（默认 10）。
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)

# 最大并发编辑会话数
MAX_SESSIONS: int = int(getattr(settings, "ONLYOFFICE_MAX_SESSIONS", 10))
# Redis key
_REDIS_KEY = "onlyoffice:active_sessions"
# 会话过期时间（秒）—— 兜底清理僵尸会话（正常由 callback status=4 释放）
_SESSION_TTL = 3600  # 1 小时


async def acquire_session(user_id: UUID, document_key: str) -> bool:
    """尝试获取一个编辑席位。返回 True=成功，False=已满。"""
    from app.core.redis import get_redis

    redis = await get_redis()
    if redis is None:
        # Redis 不可用时不阻塞，降级放行
        logger.warning("Redis unavailable, skipping session limit check")
        return True

    session_key = f"{_REDIS_KEY}:{user_id}:{document_key}"

    # 先检查该用户+文档是否已有会话（幂等：刷新页面不重复计数）
    exists = await redis.exists(session_key)
    if exists:
        # 续期
        await redis.expire(session_key, _SESSION_TTL)
        return True

    # 统计当前活跃会话数
    count = 0
    async for _ in redis.scan_iter(match=f"{_REDIS_KEY}:*"):
        count += 1

    if count >= MAX_SESSIONS:
        return False

    # 占位
    await redis.set(session_key, "1", ex=_SESSION_TTL)
    return True


async def release_session(user_id: UUID, document_key: str) -> None:
    """释放一个编辑席位（文档关闭/callback status=4 时调用）。"""
    from app.core.redis import get_redis

    redis = await get_redis()
    if redis is None:
        return

    session_key = f"{_REDIS_KEY}:{user_id}:{document_key}"
    await redis.delete(session_key)


async def get_active_count() -> int:
    """获取当前活跃编辑会话数。"""
    from app.core.redis import get_redis

    redis = await get_redis()
    if redis is None:
        return 0

    count = 0
    async for _ in redis.scan_iter(match=f"{_REDIS_KEY}:*"):
        count += 1
    return count
