"""健康检查路由 — GET /health（无需认证）

示范 ServiceContainer 用法：将 db + redis 打包为一个依赖注入。

Validates: Requirements 4.8, 4.9
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.container import ServiceContainer, get_container

router = APIRouter(tags=["健康检查"])


@router.get("/health")
async def health_check(
    ctx: ServiceContainer = Depends(get_container),
) -> JSONResponse:
    """检查 PostgreSQL 和 Redis 连接状态。

    全部可用 → 200，任一不可用 → 503 + 详情。

    使用 ServiceContainer 简化依赖注入（示范用法）。
    """
    services: dict[str, str] = {}
    all_healthy = True

    # PostgreSQL 检查
    try:
        await ctx.db.execute(text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception:
        services["postgres"] = "unavailable"
        all_healthy = False

    # Redis 检查
    try:
        await ctx.redis.ping()
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
