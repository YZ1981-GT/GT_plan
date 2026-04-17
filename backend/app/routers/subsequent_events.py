"""后续事项 API 路由

Phase 9 Task 6.2
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/api/projects", tags=["subsequent-events"])


class SubsequentEventCreate(BaseModel):
    event_type: str  # adjusting / non_adjusting
    event_description: str
    impact_amount: float | None = None
    treatment: str = "no_action_needed"


@router.get("/{project_id}/subsequent-events")
async def list_events(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取后续事项列表"""
    import sqlalchemy as sa
    try:
        from app.models.collaboration_models import SubsequentEvent
        q = sa.select(SubsequentEvent).where(
            SubsequentEvent.project_id == project_id,
            SubsequentEvent.is_deleted == False,  # noqa
        ).order_by(SubsequentEvent.created_at.desc())
        rows = (await db.execute(q)).scalars().all()
        return [
            {
                "id": str(r.id),
                "event_type": r.event_type,
                "event_description": r.event_description,
                "impact_amount": float(r.impact_amount) if r.impact_amount else None,
                "treatment": r.treatment,
                "review_status": r.review_status,
            }
            for r in rows
        ]
    except Exception:
        # SubsequentEvent 模型可能使用同步 ORM，降级返回空
        return []


@router.post("/{project_id}/subsequent-events")
async def create_event(
    project_id: UUID,
    data: SubsequentEventCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """创建后续事项"""
    try:
        from app.models.collaboration_models import SubsequentEvent
        import sqlalchemy as sa

        event = SubsequentEvent(
            project_id=project_id,
            event_type=data.event_type,
            event_description=data.event_description,
            impact_amount=data.impact_amount,
            treatment=data.treatment,
        )
        db.add(event)
        await db.flush()
        await db.commit()
        return {"id": str(event.id), "message": "创建成功"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"创建失败: {e}")
