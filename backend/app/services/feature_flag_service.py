"""FeatureFlagService: DB 权威源 + 5s TTL 缓存 + 稳定哈希灰度。

# Feature: zero-downtime-deployment, Component 8
"""
import hashlib
import logging
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import FeatureFlag

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 5.0
_cache: dict[str, tuple[float, Optional[FeatureFlag]]] = {}


class FeatureFlagService:
    """Feature flag 服务。DB 为唯一权威源，短 TTL 内存缓存平衡性能与一致性。"""

    @staticmethod
    async def is_enabled(db: AsyncSession, flag_key: str, *, user_id: str | None = None) -> bool:
        """判断 flag 是否对指定用户启用。

        逻辑：
        - 全局关 → False
        - 白名单命中 → True
        - rollout_percentage >= 100 → True
        - rollout_percentage <= 0 → False
        - 否则稳定哈希 md5(f"{flag_key}:{user_id}") % 100 < rollout_percentage

        DB 不可达→返回上次缓存值，无则保守关闭。
        """
        flag = await FeatureFlagService._get_flag_cached(db, flag_key)
        if flag is None or not flag.enabled:
            return False

        # 白名单命中
        if user_id and flag.whitelist_user_ids:
            if user_id in flag.whitelist_user_ids:
                return True

        # 百分比
        if flag.rollout_percentage >= 100:
            return True
        if flag.rollout_percentage <= 0:
            return False

        # 稳定哈希灰度
        if not user_id:
            return False
        bucket = int(hashlib.md5(f"{flag_key}:{user_id}".encode()).hexdigest(), 16) % 100
        return bucket < flag.rollout_percentage

    @staticmethod
    async def _get_flag_cached(db: AsyncSession, flag_key: str) -> Optional[FeatureFlag]:
        """TTL 缓存读取 flag。DB 不可达时返回上次缓存值。"""
        now = time.time()
        cached = _cache.get(flag_key)
        if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

        try:
            result = await db.execute(
                select(FeatureFlag).where(FeatureFlag.flag_key == flag_key)
            )
            flag = result.scalar_one_or_none()
            _cache[flag_key] = (now, flag)
            return flag
        except Exception as e:
            logger.warning("[FeatureFlag] DB read failed for %s: %s", flag_key, e)
            # Return stale cache if available, else None (conservative: disabled)
            if cached:
                return cached[1]
            return None

    @staticmethod
    async def list_all(db: AsyncSession) -> list[FeatureFlag]:
        """List all feature flags."""
        result = await db.execute(select(FeatureFlag).order_by(FeatureFlag.flag_key))
        return list(result.scalars().all())

    @staticmethod
    async def get_by_key(db: AsyncSession, flag_key: str) -> Optional[FeatureFlag]:
        """Get a single flag by key."""
        result = await db.execute(
            select(FeatureFlag).where(FeatureFlag.flag_key == flag_key)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert(db: AsyncSession, flag_key: str, *, enabled: bool | None = None,
                     rollout_percentage: int | None = None,
                     whitelist_user_ids: list[str] | None = None,
                     description: str | None = None) -> FeatureFlag:
        """Create or update a flag. Invalidates cache."""
        flag = await FeatureFlagService.get_by_key(db, flag_key)
        if flag is None:
            flag = FeatureFlag(flag_key=flag_key)
            db.add(flag)

        if enabled is not None:
            flag.enabled = enabled
        if rollout_percentage is not None:
            flag.rollout_percentage = rollout_percentage
        if whitelist_user_ids is not None:
            flag.whitelist_user_ids = whitelist_user_ids
        if description is not None:
            flag.description = description

        await db.flush()
        # Invalidate cache
        _cache.pop(flag_key, None)
        return flag
