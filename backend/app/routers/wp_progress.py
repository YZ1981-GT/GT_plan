"""底稿完成度与交叉索引 API

Phase 9 Task 9.7
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.wp_progress_service import WpProgressService

router = APIRouter(prefix="/api/projects", tags=["wp-progress"])


@router.get("/{project_id}/workpapers/progress")
async def get_progress(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WpProgressService(db)
    return await svc.get_progress(project_id)


@router.get("/{project_id}/workpapers/overdue")
async def get_overdue(
    project_id: UUID,
    days: int = Query(7, ge=1),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WpProgressService(db)
    return await svc.get_overdue(project_id, days)


@router.get("/{project_id}/workpapers/cross-refs")
async def get_cross_refs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WpProgressService(db)
    return await svc.get_cross_refs(project_id)
