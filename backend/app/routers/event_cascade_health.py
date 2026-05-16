"""Spec C R10 Sprint 1.2.2 — 事件级联健康度端点

GET /api/projects/{project_id}/event-cascade/health
- admin/partner：完整 schema（lag_seconds + stuck_handlers + dlq_depth + worker_status + redis_available + status）
- 普通用户：只看 status / lag_seconds（design D3 隔离）
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.event_cascade_health_service import EventCascadeHealthService

router = APIRouter(
    prefix="/api/projects/{project_id}/event-cascade",
    tags=["event-cascade"],
)


@router.get("/health")
async def get_event_cascade_health(
    project_id: UUID,
    current_user: User = Depends(require_project_access("readonly")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """聚合事件级联健康度。

    全量 schema（admin/partner）：
        {
          "lag_seconds": int,
          "stuck_handlers": [{"outbox_id", "event_type", "stuck_for_minutes"}],
          "dlq_depth": int,
          "worker_status": {worker_name: {"alive", "last_heartbeat", "stale_seconds"}},
          "redis_available": bool,
          "status": "healthy" | "degraded" | "critical"
        }

    普通用户响应（design D3 隔离）：
        {"status": "...", "lag_seconds": int}
    """
    svc = EventCascadeHealthService(db)
    full = await svc.get_health_summary(project_id)

    # 普通用户只看 status + lag_seconds
    role = getattr(current_user.role, "value", current_user.role)
    if role not in ("admin", "partner"):
        return {
            "status": full["status"],
            "lag_seconds": full["lag_seconds"],
        }

    return full


__all__ = ["router"]
