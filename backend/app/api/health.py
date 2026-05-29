"""健康检查路由 — GET /api/health（无需认证）

使用 ServiceContainer 简化依赖注入（示范用法）。

migration-runner-resilience spec / Sprint 2 / Task 2.4：
增强 health endpoint 暴露：
- ``migration``: { applied_count, failures }
- ``schema_drift``: { count, items }
任一字段非空 → status="degraded" → 前端 DegradedBanner 提示运维。

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
    """检查 PostgreSQL / Redis / 迁移状态 / schema 漂移。

    返回结构::

        {
          "status": "healthy" | "unhealthy" | "degraded",
          "services": { "postgres": "ok|unavailable", "redis": "ok|unavailable" },
          "redis": {...},
          "migration": { "applied_count": 26, "failures": [...] },
          "schema_drift": { "count": 0, "items": [...] }
        }

    状态码：
    - 200：healthy 或 degraded（应用可用，但有迁移失败 / schema 漂移需关注）
    - 503：unhealthy（PG 或 Redis 不可达，应用不可用）
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

    # Redis 详细信息（非阻塞）
    redis_details = {}
    try:
        from app.routers.health_redis import _get_redis_health_info
        redis_details = await _get_redis_health_info()
    except Exception:
        pass

    # 迁移失败 + schema 漂移（migration-runner-resilience spec）
    migration_info = await _query_migration_status()
    drift_info = await _query_schema_drift()

    # 状态判定
    if not all_healthy:
        status = "unhealthy"
        status_code = 503
    elif migration_info["failures"] or drift_info["count"] > 0:
        status = "degraded"
        status_code = 200
    else:
        status = "healthy"
        status_code = 200

    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "services": services,
            "redis": redis_details,
            "migration": migration_info,
            "schema_drift": drift_info,
        },
    )


async def _query_migration_status() -> dict:
    """查询 schema_version + schema_migration_failures。"""
    from app.core.database import engine
    if engine.dialect.name != "postgresql":
        return {"applied_count": 0, "failures": []}
    try:
        async with engine.begin() as conn:
            applied_row = await conn.execute(text(
                "SELECT COUNT(*) FROM schema_version"
            ))
            applied_count = applied_row.scalar() or 0

            failures: list[dict] = []
            try:
                rows = await conn.execute(text(
                    "SELECT version, filename, error_type, error_message, attempt_count "
                    "FROM schema_migration_failures ORDER BY attempted_at DESC"
                ))
                for r in rows.fetchall():
                    failures.append({
                        "version": r[0],
                        "filename": r[1],
                        "error_type": r[2],
                        "error_message": (r[3] or "")[:500],
                        "attempt_count": r[4],
                    })
            except Exception:
                # 表不存在（V025 未跑），视为无失败
                pass

            return {"applied_count": applied_count, "failures": failures}
    except Exception:
        return {"applied_count": 0, "failures": []}


async def _query_schema_drift() -> dict:
    """查询 schema_drift_log。"""
    from app.core.database import engine
    from app.core.schema_drift_detector import SchemaDriftDetector
    items = await SchemaDriftDetector.query_drift(engine)
    return {
        "count": len(items),
        "items": [
            {
                "table": it.table,
                "column": it.column,
                "drift_type": it.drift_type,
                "detail": it.detail,
            }
            for it in items
        ],
    }
