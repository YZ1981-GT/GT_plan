"""管理后台事件健康页面 — 企业级联动 Sprint 4

GET /api/admin/event-health 返回最近 100 条级联记录（含状态/耗时/失败原因）

Validates: Requirements 7.3
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.event_cascade_monitor import EventCascadeMonitor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/event-health", tags=["admin-event-health"])


@router.get("")
async def get_event_health(
    db: AsyncSession = Depends(get_db),
):
    """返回最近 100 条级联记录 + 健康统计。"""
    # Get health stats
    monitor = EventCascadeMonitor(db)
    stats = await monitor.get_health_stats(hours=24)
    alert_needed = await monitor.check_alert_threshold()

    # Get recent cascade records
    query = text("""
        SELECT id, project_id, year, trigger_event, trigger_payload,
               steps, status, started_at, completed_at, total_duration_ms
        FROM event_cascade_log
        ORDER BY started_at DESC
        LIMIT 100
    """)
    result = await db.execute(query)
    rows = result.fetchall()

    records = []
    for r in rows:
        records.append({
            "id": str(r[0]),
            "project_id": str(r[1]) if r[1] else None,
            "year": r[2],
            "trigger_event": r[3],
            "trigger_payload": r[4],
            "steps": r[5],
            "status": r[6],
            "started_at": r[7].isoformat() if r[7] else None,
            "completed_at": r[8].isoformat() if r[8] else None,
            "total_duration_ms": r[9],
        })

    return {
        "stats": stats,
        "alert_needed": alert_needed,
        "records": records,
    }
