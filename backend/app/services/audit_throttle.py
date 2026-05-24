"""审计日志洪泛节流器 — Redis SET NX EX 5s 分布式节流

对相同 (user_id, source, filters_hash) 三元组在 5 秒窗口内只记录 1 条审计日志。
敏感操作（cell_writeback / cross_sheet_trace）绕过节流，每次必记。
Redis 不可用时降级为"不节流，全部记录" + logger.warning。
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger("audit_platform.audit_throttle")

# 敏感操作白名单：这些 action 不参与节流，每次必记
SENSITIVE_ACTIONS: frozenset[str] = frozenset({
    "cell_writeback",
    "cross_sheet_trace",
})

# 节流窗口 TTL（秒）
THROTTLE_WINDOW_SECONDS: int = 5


def _build_throttle_key(user_id: str, source: str, filters: dict[str, Any]) -> str:
    """构建 Redis 节流键：audit:throttle:{user_id}:{sha1(source+filters)}"""
    payload = source + json.dumps(filters, sort_keys=True, default=str)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"audit:throttle:{user_id}:{digest}"


async def should_record(
    redis: Redis | None,
    user_id: str,
    source: str,
    filters: dict[str, Any],
    action: str | None = None,
) -> bool:
    """判断是否应该记录本次审计日志。

    Parameters
    ----------
    redis : Redis | None
        Redis 客户端实例，None 表示不可用。
    user_id : str
        当前用户 ID。
    source : str
        查询数据源标识。
    filters : dict
        查询过滤条件。
    action : str | None
        操作类型，若为敏感操作则绕过节流。

    Returns
    -------
    bool
        True = 应该记录，False = 应该跳过（节流窗口内重复）。
    """
    # 敏感操作白名单：永远记录，不节流
    if action and action in SENSITIVE_ACTIONS:
        return True

    # Redis 不可用：降级为全部记录
    if redis is None:
        logger.warning("Redis unavailable for audit throttle, fallback to always-record")
        return True

    key = _build_throttle_key(user_id, source, filters)

    try:
        # SET NX EX 5：仅当 key 不存在时设置，TTL=5s
        result = await redis.set(key, "1", nx=True, ex=THROTTLE_WINDOW_SECONDS)
        return result is not None  # True = 首次（key 不存在），应记录
    except RedisError as e:
        logger.warning("Redis unavailable for audit throttle, fallback to always-record: %s", e)
        return True
