"""统一AI+OCR+缓存健康检查 & 缓存统计 API

- GET /api/ai/health   — 统一AI+OCR+缓存健康检查
- GET /api/cache/stats  — 缓存统计
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.services.cache_manager import CacheManager
from app.services.unified_ai_service import UnifiedAIService

router = APIRouter(tags=["ai-unified"])


@router.get("/api/ai/health")
async def unified_health_check(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """统一AI+OCR+缓存健康检查"""
    ai_svc = UnifiedAIService(db)
    ai_health = await ai_svc.health_check()

    cache_mgr = CacheManager(redis)
    try:
        cache_stats = await cache_mgr.get_stats()
        cache_status = "healthy"
    except Exception:
        cache_stats = {}
        cache_status = "unhealthy"

    ai_health["cache"] = {"status": cache_status, "stats": cache_stats}
    return ai_health


@router.get("/api/cache/stats")
async def cache_stats(
    redis: Redis = Depends(get_redis),
):
    """缓存统计"""
    cache_mgr = CacheManager(redis)
    return await cache_mgr.get_stats()
