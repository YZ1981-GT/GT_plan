"""工时管理 API 路由

Phase 9 Task 1.6
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.staff_schemas import WorkHourCreate, WorkHourUpdate
from app.services.workhour_service import WorkHourService

router = APIRouter(prefix="/api", tags=["workhours"])


@router.get("/staff/{staff_id}/work-hours")
async def list_hours(
    staff_id: UUID,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WorkHourService(db)
    return await svc.list_hours(staff_id, start_date, end_date)


@router.post("/staff/{staff_id}/work-hours")
async def create_hour(
    staff_id: UUID,
    data: WorkHourCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WorkHourService(db)
    wh, warnings = await svc.create_hour(staff_id, data.model_dump())
    await db.commit()
    return {
        "id": str(wh.id),
        "work_date": str(wh.work_date),
        "hours": float(wh.hours),
        "warnings": warnings,
    }


@router.put("/work-hours/{hour_id}")
async def update_hour(
    hour_id: UUID,
    data: WorkHourUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WorkHourService(db)
    wh = await svc.update_hour(hour_id, data.model_dump(exclude_none=True))
    if not wh:
        raise HTTPException(404, "工时记录不存在")
    await db.commit()
    return {"id": str(wh.id), "status": wh.status}


@router.post("/work-hours/ai-suggest")
async def ai_suggest(
    staff_id: UUID = Query(...),
    target_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WorkHourService(db)
    suggestions = await svc.ai_suggest(staff_id, target_date)
    return {"suggestions": suggestions}


@router.get("/projects/{project_id}/work-hours")
async def project_hours(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WorkHourService(db)
    return await svc.project_summary(project_id)
