"""Phase 15: 事件总线路由"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import PaginationParams
from app.deps import get_current_user
from app.models.core import User
from app.services.task_event_bus import task_event_bus

router = APIRouter(prefix="/task-events", tags=["TaskEvents"])


class EventReplayRequest(BaseModel):
    event_id: uuid.UUID
    operator_id: uuid.UUID
    reason_code: str


@router.post("/replay")
async def replay_event(
    req: EventReplayRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_event_bus.replay(db, req.event_id, req.operator_id, req.reason_code)


@router.get("")
async def list_events(
    project_id: uuid.UUID = Query(...),
    status: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import select, func
    from app.models.phase15_models import TaskEvent

    stmt = select(TaskEvent).where(TaskEvent.project_id == project_id)
    if status:
        stmt = stmt.where(TaskEvent.status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(TaskEvent.created_at.desc())
    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    events = result.scalars().all()

    import math
    total_pages = math.ceil(total / pagination.page_size) if total > 0 else 0

    return {
        "items": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "task_node_id": str(e.task_node_id) if e.task_node_id else None,
                "status": e.status,
                "retry_count": e.retry_count,
                "error_message": e.error_message,
                "trace_id": e.trace_id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total_pages": total_pages,
    }
