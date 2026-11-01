"""项目创建入口的 actor 级 Redis 安全限流。"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)
RATE_LIMIT_ERROR_CODE = "PROJECT_CREATION_RATE_LIMITED"
RATE_LIMIT_WINDOW_SECONDS = 60


def rate_limit_per_minute() -> int:
    try:
        return max(1, min(300, int(os.getenv("GT_PROJECT_CREATION_RATE_PER_MINUTE", "30"))))
    except ValueError:
        return 30


async def _get_redis():
    from app.core.redis import get_redis

    return await get_redis()


async def _audit_limit(actor: Any, entrypoint: str, retry_after: int) -> None:
    try:
        from app.services.audit_logger_enhanced import audit_logger

        await audit_logger.log_action(
            user_id=actor.id,
            action="project.creation.rate_limited",
            object_type="project_creation",
            details={
                "entrypoint": entrypoint,
                "retry_after": retry_after,
                "actor_role": getattr(getattr(actor, "role", None), "value", None),
            },
        )
    except Exception:
        return


async def enforce_creation_rate_limit(actor: Any, *, entrypoint: str) -> None:
    """超 actor 固定窗口预算时 429；Redis 故障只跳过限流，不影响授权门。"""
    try:
        redis = await _get_redis()
        if redis is None:
            return
        key = f"security:project_creation:{actor.id}"
        script = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
return {n, ttl}
"""
        count, ttl = await redis.eval(script, 1, key, RATE_LIMIT_WINDOW_SECONDS)
        limit = rate_limit_per_minute()
        if int(count) <= limit:
            return
        retry_after = max(1, int(ttl))
        await _audit_limit(actor, entrypoint, retry_after)
        raise HTTPException(
            status_code=429,
            detail={
                "error_code": RATE_LIMIT_ERROR_CODE,
                "message": f"项目创建请求过于频繁，请 {retry_after} 秒后重试",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("项目创建安全限流暂不可用，授权门继续生效：%s", exc)


__all__ = [
    "RATE_LIMIT_ERROR_CODE",
    "RATE_LIMIT_WINDOW_SECONDS",
    "enforce_creation_rate_limit",
    "rate_limit_per_minute",
]
