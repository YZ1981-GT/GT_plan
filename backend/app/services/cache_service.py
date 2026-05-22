"""性能优化缓存服务 — TB 查询缓存 + Prefill 结果缓存

Phase 3 F3.4 瓶颈优化：
- TB 查询缓存：Redis 60s TTL，减少大科目表重复查询
- Prefill 结果缓存：Redis，key=wp_id+tb_version，避免重复计算

缓存失效策略：
- TB 数据变更（TRIAL_BALANCE_UPDATED 事件）→ 失效对应 project 的 TB 缓存
- Prefill 重新执行 → 覆盖旧缓存
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# 缓存命名空间
NS_TB_QUERY = "tb_query"          # 试算表查询缓存
NS_PREFILL = "prefill_result"     # Prefill 结果缓存

# TTL 配置（秒）
TB_QUERY_TTL = 60       # 试算表查询 60s TTL
PREFILL_RESULT_TTL = 300  # Prefill 结果 5 分钟 TTL


class CacheService:
    """性能优化缓存服务

    提供 TB 查询缓存和 Prefill 结果缓存，
    用于减少高并发场景下的数据库压力。
    """

    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    # ------------------------------------------------------------------
    # TB 查询缓存
    # ------------------------------------------------------------------

    def _tb_cache_key(self, project_id: UUID, year: int, company_code: str = "001") -> str:
        """生成 TB 查询缓存 key"""
        return f"{NS_TB_QUERY}:{project_id}:{year}:{company_code}"

    async def get_tb_cache(
        self, project_id: UUID, year: int, company_code: str = "001"
    ) -> list[dict] | None:
        """获取 TB 查询缓存，命中返回 list[dict]，未命中返回 None"""
        key = self._tb_cache_key(project_id, year, company_code)
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning("TB cache get failed: %s", e)
            return None

    async def set_tb_cache(
        self,
        project_id: UUID,
        year: int,
        company_code: str,
        data: list[dict],
    ) -> None:
        """设置 TB 查询缓存（60s TTL）"""
        key = self._tb_cache_key(project_id, year, company_code)
        try:
            serialized = json.dumps(data, ensure_ascii=False, default=str)
            await self._redis.set(key, serialized, ex=TB_QUERY_TTL)
        except Exception as e:
            logger.warning("TB cache set failed: %s", e)

    async def invalidate_tb_cache(self, project_id: UUID, year: int | None = None) -> int:
        """失效 TB 缓存

        Args:
            project_id: 项目 ID
            year: 可选年份，不指定则失效该项目所有年份缓存
        """
        if year is not None:
            pattern = f"{NS_TB_QUERY}:{project_id}:{year}:*"
        else:
            pattern = f"{NS_TB_QUERY}:{project_id}:*"

        deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    deleted += await self._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("TB cache invalidate failed: %s", e)
        return deleted

    # ------------------------------------------------------------------
    # Prefill 结果缓存
    # ------------------------------------------------------------------

    def _prefill_cache_key(self, wp_id: UUID, tb_version: str) -> str:
        """生成 Prefill 结果缓存 key

        Args:
            wp_id: 底稿 ID
            tb_version: TB 数据版本标识（通常为 TB 最后更新时间的 hash）
        """
        return f"{NS_PREFILL}:{wp_id}:{tb_version}"

    @staticmethod
    def compute_tb_version(project_id: UUID, year: int, last_updated: str | None = None) -> str:
        """计算 TB 数据版本标识

        基于 project_id + year + 最后更新时间生成 hash，
        TB 数据变更后 version 自动变化，旧缓存自然失效。
        """
        raw = f"{project_id}:{year}:{last_updated or 'none'}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    async def get_prefill_cache(self, wp_id: UUID, tb_version: str) -> dict | None:
        """获取 Prefill 结果缓存"""
        key = self._prefill_cache_key(wp_id, tb_version)
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning("Prefill cache get failed: %s", e)
            return None

    async def set_prefill_cache(
        self, wp_id: UUID, tb_version: str, result: dict
    ) -> None:
        """设置 Prefill 结果缓存（5 分钟 TTL）"""
        key = self._prefill_cache_key(wp_id, tb_version)
        try:
            serialized = json.dumps(result, ensure_ascii=False, default=str)
            await self._redis.set(key, serialized, ex=PREFILL_RESULT_TTL)
        except Exception as e:
            logger.warning("Prefill cache set failed: %s", e)

    async def invalidate_prefill_cache(self, wp_id: UUID) -> int:
        """失效指定底稿的所有 Prefill 缓存"""
        pattern = f"{NS_PREFILL}:{wp_id}:*"
        deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    deleted += await self._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("Prefill cache invalidate failed: %s", e)
        return deleted

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    async def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        stats: dict[str, Any] = {}
        for ns in [NS_TB_QUERY, NS_PREFILL]:
            count = 0
            try:
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(
                        cursor=cursor, match=f"{ns}:*", count=200
                    )
                    count += len(keys)
                    if cursor == 0:
                        break
            except Exception:
                pass
            stats[ns] = {"key_count": count}
        return stats
