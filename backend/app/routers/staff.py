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


@router.delete("/{staff_id}")
async def delete_staff(
    staff_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """删除人员（仅允许删除 source=custom 的自定义人员）"""
    from app.models.staff_models import StaffMember
    import sqlalchemy as sa

    result = await db.execute(
        sa.select(StaffMember).where(StaffMember.id == staff_id, StaffMember.is_deleted == False)
    )
    staff = result.scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=404, detail="人员不存在")

    source = getattr(staff, "source", "custom")
    if source == "seed":
        raise HTTPException(status_code=400, detail="初始导入的人员不允许删除")

    staff.is_deleted = True
    await db.commit()
    return {"message": "已删除", "id": str(staff_id)}


@router.get("/me/staff-id")
async def get_my_staff_id(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取当前登录用户关联的 staff_member ID"""
    from app.models.staff_models import StaffMember
    import sqlalchemy as sa

    result = await db.execute(
        sa.select(StaffMember).where(
            StaffMember.user_id == user.id,
            StaffMember.is_deleted == False,
        )
    )
    staff = result.scalar_one_or_none()
    if staff:
        return {"staff_id": str(staff.id), "name": staff.name}

    # 如果没有关联，尝试按用户名匹配
    result = await db.execute(
        sa.select(StaffMember).where(
            StaffMember.name == user.username,
            StaffMember.is_deleted == False,
        )
    )
    staff = result.scalar_one_or_none()
    if staff:
        # 自动关联
        staff.user_id = user.id
        await db.commit()
        return {"staff_id": str(staff.id), "name": staff.name}

    # 都没找到，自动创建一条 custom 记录
    from app.models.staff_models import StaffMember as SM
    import uuid
    new_staff = SM(
        id=uuid.uuid4(),
        user_id=user.id,
        name=user.username,
        source="custom",
    )
    db.add(new_staff)
    await db.commit()
    return {"staff_id": str(new_staff.id), "name": new_staff.name, "auto_created": True}
