"""人员库 API 路由

Phase 9 Task 1.2
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.staff_schemas import (
    StaffCreate,
    StaffListResponse,
    StaffResponse,
    StaffResumeResponse,
    StaffUpdate,
)
from app.services.staff_service import StaffService

router = APIRouter(prefix="/api/staff", tags=["staff"])


@router.get("", response_model=StaffListResponse)
async def list_staff(
    search: str | None = Query(None),
    department: str | None = Query(None),
    partner_name: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = StaffService(db)
    items, total = await svc.list_staff(search, department, partner_name, offset, limit)
    return StaffListResponse(
        items=[StaffResponse.model_validate(s) for s in items],
        total=total,
    )


@router.post("", response_model=StaffResponse)
async def create_staff(
    data: StaffCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = StaffService(db)
    staff = await svc.create_staff(data.model_dump(exclude_none=True))
    await db.commit()
    return StaffResponse.model_validate(staff)


@router.put("/{staff_id}", response_model=StaffResponse)
async def update_staff(
    staff_id: UUID,
    data: StaffUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = StaffService(db)
    staff = await svc.update_staff(staff_id, data.model_dump(exclude_none=True))
    if not staff:
        raise HTTPException(404, "人员不存在")
    await db.commit()
    return StaffResponse.model_validate(staff)


@router.get("/{staff_id}/resume")
async def get_resume(
    staff_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = StaffService(db)
    staff = await svc.get_staff(staff_id)
    if not staff:
        raise HTTPException(404, "人员不存在")
    resume = await svc.get_resume(staff_id)
    return {
        "staff_id": str(staff_id),
        "name": staff.name,
        "title": staff.title,
        "department": staff.department,
        **resume,
    }


@router.get("/{staff_id}/projects")
async def get_projects(
    staff_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = StaffService(db)
    return await svc.get_projects(staff_id)
