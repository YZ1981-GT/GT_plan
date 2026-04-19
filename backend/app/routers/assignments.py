"""团队委派 API 路由

Phase 9 Task 1.4
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.staff_schemas import AssignmentBatchRequest, AssignmentResponse
from app.services.assignment_service import AssignmentService

router = APIRouter(prefix="/api/projects", tags=["assignments"])


# ⚠ /my/assignments 必须在 /{project_id}/assignments 之前，
# 否则 FastAPI 会把 "my" 当成 UUID 类型的 project_id 导致 422
@router.get("/my/assignments")
async def my_assignments(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取当前用户被委派的项目列表"""
    svc = AssignmentService(db)
    return await svc.get_my_assignments(user.id)


@router.get("/{project_id}/assignments")
async def list_assignments(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = AssignmentService(db)
    return await svc.list_assignments(project_id)


@router.post("/{project_id}/assignments")
async def save_assignments(
    project_id: UUID,
    data: AssignmentBatchRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = AssignmentService(db)
    assignments = [a.model_dump() for a in data.assignments]
    created = await svc.save_assignments(
        project_id, assignments, assigned_by=user.id if user else None
    )
    await db.commit()
    return {
        "message": f"已委派 {len(created)} 名成员",
        "count": len(created),
    }
