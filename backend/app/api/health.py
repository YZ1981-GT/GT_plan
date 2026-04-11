"""健康检查路由 — GET /health（无需认证）

Validates: Requirements 4.8, 4.9
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis

router = APIRouter(tags=["健康检查"])


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> JSONResponse:
    """检查 PostgreSQL 和 Redis 连接状态。

    全部可用 → 200，任一不可用 → 503 + 详情。
    """
    services: dict[str, str] = {}
    all_healthy = True

    # PostgreSQL 检查
    try:
        await db.execute(text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception:
        services["postgres"] = "unavailable"
        all_healthy = False

    # Redis 检查
    try:
        await redis.ping()
        services["redis"] = "ok"
    except Exception:
        services["redis"] = "unavailable"
        all_healthy = False

    status = "healthy" if all_healthy else "unhealthy"
    status_code = 200 if all_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={"status": status, "services": services},
    )
