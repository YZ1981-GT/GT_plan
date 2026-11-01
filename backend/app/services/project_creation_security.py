"""项目创建入口的 actor 级 Redis 固定窗口限流。

限流只减少枚举请求；Redis 故障时 fail-open，但后续精确公司授权仍 fail-closed。
spec: batch-project-authorization-and-lock-hardening R2
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)
_DEFAULT_LIMIT = 30
_DEFAULT_WINDOW_SECONDS = 60


def _config() -> tuple[int, int]:
    limit = max(1, int(getattr(settings, "PROJECT_CREATION_RATE_LIMIT_PER_MINUTE", _DEFAULT_LIMIT)))
    window = max(1, int(getattr(settings, "PROJECT_CREATION_RATE_LIMIT_WINDOW_SECONDS", _DEFAULT_WINDOW_SECONDS)))
    return limit, window


async def enforce_creation_rate_limit(actor: Any, *, entrypoint: str) -> None:
    """累计一个创建类请求；超限抛 429，并返回稳定错误码与 Retry-After。"""
    actor_id = getattr(actor, "id", None)
    if actor_id is None:
        return
    limit, window = _config()
    bucket = int(time.time()) // window
    key = f"rate_limit:project_creation:{actor_id}:{bucket}"
    try:
        from app.core.redis import redis_client

        count = int(await redis_client.incr(key))
        if count == 1:
            await redis_client.expire(key, window + 1)
        if count <= limit:
            return
        ttl = int(await redis_client.ttl(key))
        retry_after = max(1, ttl if ttl > 0 else window)
    except Exception:  # noqa: BLE001 — 限流依赖不可用时按设计放行
        logger.warning("项目创建限流 Redis 不可用，已降级放行：entrypoint=%s", entrypoint)
        return
    raise HTTPException(
        status_code=429,
        detail={
            "error_code": "PROJECT_CREATION_RATE_LIMITED",
            "message": f"项目创建请求过于频繁，请 {retry_after} 秒后重试",
        },
        headers={"Retry-After": str(retry_after)},
    )


__all__ = ["enforce_creation_rate_limit"]
