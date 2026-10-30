"""健康检查路由 — GET /api/health（无需认证）

使用 ServiceContainer 简化依赖注入（示范用法）。

migration-runner-resilience spec / Sprint 2 / Task 2.4：
增强 health endpoint 暴露：
- ``migration``: { applied_count, failures }
- ``schema_drift``: { count, items }
任一字段非空 → status="degraded" → 前端 DegradedBanner 提示运维。

platform-architecture-convergence Task 12：
- ``startup``: 启动任务逐项报告（``startup_registry.startup_report_as_dict``，已脱敏），
  只作可观测暴露，**不参与** status 判定。

Validates: Requirements 4.8, 4.9
"""

import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.container import ServiceContainer, get_container
from app.core.reload_handoff import status_snapshot as reload_status_snapshot
from app.core.startup_registry import startup_report_as_dict
from app.core.gc_tuning import get_last_freeze_report
from app.middleware.audit_log import audit_log_failure_state

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
          "schema_drift": { "count": 0, "items": [...] },
          "startup": { "status": "complete|not_run", "tasks": [...], "failed": [...], ... },
          "reload": { "mode": "standalone|overlap|never", "primary": true, "last": {...} | null }
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
    audit_state = audit_log_failure_state()
    events_info = _events_replay_info()
    reload_info = reload_status_snapshot()
    reload_last = reload_info.get("last") or {}
    reload_degraded = (
        reload_info.get("primary_state") == "failed"
        or reload_last.get("result") == "degraded"
        or reload_last.get("phase") in {"primary_failed", "primary_timeout", "recovery_primary_failed"}
    )

    # 审计链健康（ADR-ALC-10）
    audit_chain_info = await _query_audit_chain_health(ctx.db)

    # 状态判定
    #
    # degraded 只看「critical 漂移」（schema_drift_detector.CRITICAL_DRIFT_TYPES —— 会导致
    # 业务接口运行时 500 / 插入失败，或已应用迁移的编辑静默丢失）+ 迁移失败 + 审计链分叉。
    # INFO 级 db_extra（DB 历史残留表/列，如 deleted_at 软删列、raw SQL 建的表）和
    # WARN 级 type_mismatch 仅作可观测暴露，不翻 degraded banner。
    if not all_healthy:
        status = "unhealthy"
        status_code = 503
    elif (
        migration_info["failures"]
        or drift_info["critical_count"] > 0
        or audit_chain_info["unacknowledged_forks"] > 0
        or reload_degraded
        or int(audit_state.get("failed_count") or 0) > 0
    ):
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
            "audit_chain": audit_chain_info,
            # 启动报告只读进程内快照，不做 I/O；best_effort 失败不翻 status（Req 6.x）
            "startup": startup_report_as_dict(),
            # HTTP 审计日志写入失败累计（fail-open，但必须可观测；follow-up R4.2）
            "audit_log": audit_state,
            # 事件重放可用性与积压（Redis 不可用时 live 仍降级可用，但补拉不可用；R3.4）
            "events": events_info,
            # GC 只在连续空闲窗口执行；这里暴露等待 / 重排 / 实际停顿，不额外做 I/O。
            "gc": get_last_freeze_report(),
            # 热重载交接：本进程模式 + 最近一次重载结果（读父进程写的小文件；不参与 status 判定）
            "reload": reload_info,
        },
    )


# ── 审计链健康缓存（进程级，300 秒） ──────────────────────────────
_audit_chain_cache: dict[str, object] = {"data": None, "ts": 0.0}
_AUDIT_CHAIN_CACHE_TTL = 300  # 秒


async def _query_audit_chain_health(db) -> dict:
    """查询未确认分叉数（带进程级 300s 缓存）。"""
    now = time.monotonic()
    if (
        _audit_chain_cache["data"] is not None
        and now - _audit_chain_cache["ts"] < _AUDIT_CHAIN_CACHE_TTL
    ):
        return _audit_chain_cache["data"]

    from datetime import datetime, timezone

    try:
        from app.services.audit_chain.forks import scan_forks

        forks = await scan_forks(db)
        unack = sum(1 for f in forks if len(f.get("survivors", [])) > 1)
    except Exception:
        unack = 0

    result = {
        "unacknowledged_forks": unack,
        "quarantined_entries": 0,  # batch A 硬编码，batch B 加真实隔离区
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _audit_chain_cache["data"] = result
    _audit_chain_cache["ts"] = now
    return result


def _events_replay_info() -> dict:
    """事件补拉可用性（R3.4）。

    Redis 不可用时 live SSE 仍按内存降级工作，但「断线后按 id 补拉」这条路**不可用** ——
    必须显式说出来，不能让调用方以为事件无损。只读进程内最近一次重放报告，不做 I/O。
    """
    try:
        from app.services.event_bus import event_bus

        report = event_bus.get_replay_report()
    except Exception:  # noqa: BLE001 — 可观测字段不得影响 health 本身
        return {"replay_available": None, "pending_remaining": None, "last_checked_at": None}
    return {
        "replay_available": bool(report.get("redis_available")),
        "pending_remaining": report.get("pending_remaining"),
        "last_checked_at": report.get("checked_at"),
        "last_error": report.get("last_error"),
    }


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
    """查询 schema_drift_log。

    ``critical_count`` 只统计 ``CRITICAL_DRIFT_TYPES``（单一真源：orm_extra / enum_mismatch /
    checksum_drift —— 会导致运行时 500 / 插入失败、或已应用迁移的编辑静默丢失），用于 health
    degraded 判定；``count`` 是总数（含 INFO 级 db_extra），仅作可观测展示。
    """
    from app.core.database import engine
    from app.core.schema_drift_detector import SchemaDriftDetector, count_critical
    items = await SchemaDriftDetector.query_drift(engine)
    critical_count = count_critical(items)
    return {
        "count": len(items),
        "critical_count": critical_count,
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
