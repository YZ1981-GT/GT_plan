"""统一缓存管理器 — 命名空间化的Redis缓存操作

提供：
- 命名空间隔离：{namespace}:{key}
- 预定义命名空间与默认TTL
- 按命名空间批量失效
- 缓存统计监控
"""

from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class CacheManager:
    """统一缓存管理器"""

    # Predefined namespaces with default TTLs (seconds)
    NAMESPACES: dict[str, int] = {
        "formula": 300,       # 5 min — 取数公式缓存
        "metabase": 300,      # 5 min — Metabase查询缓存
        "ledger": 300,        # 5 min — 穿透查询缓存
        "auth": 7200,         # 2 hours — 认证/会话缓存
        "notification": 60,   # 1 min — 通知缓存
    }

    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def _make_key(self, namespace: str, key: str) -> str:
        return f"{namespace}:{key}"

    async def get(self, namespace: str, key: str) -> Any:
        """Get a cached value. Returns None on miss."""
        raw = await self._redis.get(self._make_key(namespace, key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        """Set a cached value. Uses namespace default TTL if not specified."""
        if ttl is None:
            ttl = self.NAMESPACES.get(namespace, 300)
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        await self._redis.set(self._make_key(namespace, key), serialized, ex=ttl)

    async def delete(self, namespace: str, key: str) -> bool:
        """Delete a single key. Returns True if key existed."""
        result = await self._redis.delete(self._make_key(namespace, key))
        return result > 0

    async def invalidate_namespace(self, namespace: str) -> int:
        """Delete ALL keys in a namespace. Returns count of deleted keys."""
        pattern = f"{namespace}:*"
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor, match=pattern, count=200
            )
            if keys:
                deleted += await self._redis.delete(*keys)
            if cursor == 0:
                break
        return deleted

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict:
        """Cache statistics per namespace."""
        stats: dict[str, Any] = {}
        for ns in self.NAMESPACES:
            pattern = f"{ns}:*"
            count = 0
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor, match=pattern, count=200
                )
                count += len(keys)
                if cursor == 0:
                    break
            stats[ns] = {
                "key_count": count,
                "default_ttl": self.NAMESPACES[ns],
            }
        stats["_total"] = sum(s["key_count"] for s in stats.values() if isinstance(s, dict) and "key_count" in s)
        return stats
