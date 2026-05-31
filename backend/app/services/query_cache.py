"""高级查询结果 Redis 缓存服务

高频相同查询（dashboard 卡片）结果加 Redis 短 TTL 缓存（query hash 为 key）。
不动白名单安全模型——缓存发生在安全校验之后。

设计要点：
- cache key = query_cache:{hash(user_id + project_id + query_params)}
  包含 user_id 防止跨租户数据泄漏
- 短 TTL（30~60 秒）适配 dashboard 刷新模式
- Redis 不可用时优雅降级（直接执行查询，不报错）
- 仅缓存成功结果（含 rows 的响应），错误结果不缓存

Validates: Requirements 4.1, 4.3
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 默认 TTL 30 秒（dashboard 刷新周期）
DEFAULT_TTL_SECONDS = 30

# Redis key 前缀
_KEY_PREFIX = "query_cache:"


def compute_cache_key(
    user_id: str,
    project_id: str,
    query_params: dict[str, Any],
) -> str:
    """计算查询缓存 key（含 user_id 防跨租户泄漏）。

    Parameters
    ----------
    user_id : str
        当前用户 ID（隔离租户）
    project_id : str
        项目 ID
    query_params : dict
        查询参数（source/filters/limit 等或 QueryDSL 字段）

    Returns
    -------
    str
        Redis key: query_cache:{sha256_hex[:16]}
    """
    # 构建稳定的 hash 输入（排序 key 保证相同参数产生相同 hash）
    payload = {
        "user_id": user_id,
        "project_id": project_id,
        "params": query_params,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{_KEY_PREFIX}{digest}"


async def get_cached_result(cache_key: str) -> dict[str, Any] | None:
    """从 Redis 读取缓存的查询结果。

    Returns None if:
    - Redis 不可用（降级）
    - key 不存在（未命中）
    - 反序列化失败
    """
    from app.core.redis import get_redis

    redis = await get_redis()
    if redis is None:
        return None

    try:
        raw = await redis.get(cache_key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("query_cache get failed (key=%s): %s", cache_key, e)
        return None


async def set_cached_result(
    cache_key: str,
    result: dict[str, Any],
    ttl: int = DEFAULT_TTL_SECONDS,
) -> None:
    """将查询结果写入 Redis 缓存。

    仅缓存成功结果（无 error 字段）。
    Redis 不可用时静默跳过（降级）。
    """
    from app.core.redis import get_redis

    # 不缓存错误结果
    if "error" in result:
        return

    redis = await get_redis()
    if redis is None:
        return

    try:
        serialized = json.dumps(result, default=str, ensure_ascii=False)
        await redis.set(cache_key, serialized, ex=ttl)
    except Exception as e:
        logger.warning("query_cache set failed (key=%s): %s", cache_key, e)
