"""性能监控 API — Phase 8 Task 8.4"""

from __future__ import annotations

import time
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.import_event_reliability_service import ImportEventReliabilityService
from app.services.import_event_outbox_service import ImportEventOutboxService
from app.services.import_ops_audit_service import ImportOpsAuditService
from app.services.import_slo_service import ImportSLOService
from app.services.performance_monitor import performance_monitor

router = APIRouter(prefix="/api/admin", tags=["performance"])


@router.get("/performance-stats")
async def get_performance_stats(
    current_user: User = Depends(get_current_user),
):
    """获取性能统计摘要。"""
    return performance_monitor.get_performance_stats()


@router.get("/performance-metrics")
async def get_performance_metrics(
    current_user: User = Depends(get_current_user),
):
    """获取详细性能指标。"""
    return performance_monitor.get_metrics()


@router.get("/slow-queries")
async def get_slow_queries(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    """获取慢查询列表。"""
    return {"queries": performance_monitor.get_slow_queries(limit)}


@router.get("/import-slo")
async def get_import_slo(
    hours: int = 24,
    project_id: UUID | None = None,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取导入域 SLO 摘要（JSON，可被外部告警脚本轮询）。"""
    summary = await ImportSLOService.get_summary(db, hours=hours, project_id=project_id, year=year)
    return {**summary, "alerts": ImportSLOService.build_alerts(summary)}


@router.get("/import-alerts")
async def get_import_alerts(
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取导入域告警规则评估结果。"""
    summary = await ImportSLOService.get_summary(db, hours=hours)
    return {"alerts": ImportSLOService.build_alerts(summary), "summary": summary}


@router.get("/import-runner-health")
async def get_import_runner_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取导入 runner/worker 健康状态，识别 queued 堆积与失联作业。"""
    return await ImportSLOService.get_runner_health(db)


@router.get("/import-event-health")
async def get_import_event_health(
    project_id: UUID | None = None,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取导入激活/回滚事件一致性与 replay 证据。"""
    return await ImportEventReliabilityService.get_health(db, project_id=project_id, year=year)


@router.post("/import-event-replay")
async def replay_import_events(
    limit: int = 100,
    project_id: UUID | None = None,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重放导入域 outbox 中 pending/failed 的激活与回滚事件。"""
    started_at = time.perf_counter()
    max_attempts = int(settings.LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS or 0)
    replay_kwargs = {"limit": limit, "project_id": project_id, "year": year}
    if max_attempts > 0:
        replay_kwargs["max_attempts"] = max_attempts

    scope = {
        "project_id": str(project_id) if project_id else None,
        "year": year,
    }
    params = {
        "limit": limit,
        "max_attempts": max_attempts if max_attempts > 0 else None,
    }

    try:
        report = await ImportEventOutboxService.replay_pending(db, **replay_kwargs)
        await db.commit()
        response = {**report, "scope": scope}
        await ImportOpsAuditService.log_operation(
            user_id=current_user.id,
            action_type="import_event_replay",
            project_id=project_id,
            params=params,
            scope=scope,
            outcome="success",
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            result={
                "published_count": report.get("published_count", 0),
                "failed_count": report.get("failed_count", 0),
                "skipped_exhausted_count": report.get("skipped_exhausted_count", 0),
            },
        )
        return response
    except Exception as exc:
        await ImportOpsAuditService.log_operation(
            user_id=current_user.id,
            action_type="import_event_replay",
            project_id=project_id,
            params=params,
            scope=scope,
            outcome="failed",
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            error=str(exc),
        )
        raise
