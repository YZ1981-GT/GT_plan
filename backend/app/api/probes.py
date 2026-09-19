"""探针端点 /livez 与 /readyz（无需认证）。

/livez：存活探针，只要事件循环能响应即 200，不查 DB/依赖。
/readyz：就绪探针，反映实例是否可接收流量。

# Feature: zero-downtime-deployment, Component 2
"""
import time

from fastapi import APIRouter
from starlette.responses import JSONResponse

from app.core.build_version import get_build_version
from app.core.runtime_state import migration_state, shutdown_state

router = APIRouter(tags=["探针"])

# Health snapshot cache (short TTL to avoid hammering DB with high-frequency probes)
_health_cache: dict = {"data": None, "ts": 0.0}
_READYZ_HEALTH_CACHE_TTL: float = 2.0  # seconds


async def _get_health_snapshot_cached() -> dict:
    """Get health status with short TTL cache to avoid high-frequency probes overloading DB.

    Reuses the same logic as /api/health but only returns the status string.
    """
    now = time.time()
    if _health_cache["data"] is not None and (now - _health_cache["ts"]) < _READYZ_HEALTH_CACHE_TTL:
        return _health_cache["data"]

    try:
        from app.core.database import engine
        from sqlalchemy import text

        all_healthy = True

        # PostgreSQL check (same as /api/health)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            all_healthy = False

        # Redis check (same as /api/health)
        try:
            from app.core.redis import get_redis
            redis_client = await get_redis()
            if redis_client is None:
                all_healthy = False
            else:
                await redis_client.ping()
        except Exception:
            all_healthy = False

        if not all_healthy:
            result = {"status": "unhealthy"}
        else:
            result = {"status": "healthy"}

        _health_cache["data"] = result
        _health_cache["ts"] = now
        return result
    except Exception:
        # Health check failed → conservative: treat as unhealthy
        return {"status": "unhealthy"}


@router.get("/livez")
async def livez():
    """存活探针：只要事件循环能响应即 200。不查 DB/依赖。"""
    return JSONResponse(status_code=200, content={"status": "alive"})


@router.get("/readyz")
async def readyz():
    """就绪探针：draining→503 / unhealthy 或迁移未完成→503 / 否则 200。"""
    # 1. 零成本判进程内标志
    if shutdown_state.is_draining():
        return JSONResponse(status_code=503, content={"status": "draining"})

    if not migration_state.is_complete():
        return JSONResponse(status_code=503, content={
            "status": "not_ready",
            "migration_complete": False,
        })

    # 2. 短 TTL 缓存的 health 数据
    health = await _get_health_snapshot_cached()
    health_status = health.get("status", "unhealthy")

    if health_status == "unhealthy":
        return JSONResponse(status_code=503, content={
            "status": "not_ready",
            "migration_complete": True,
            "health": "unhealthy",
        })

    return JSONResponse(status_code=200, content={
        "status": "ready",
        "degraded": health_status == "degraded",
        "build_version": get_build_version()["git_commit"],
    })
