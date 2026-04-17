"""底稿存储管理 API

Phase 9 Task 9.9
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.wp_storage_service import WpStorageService

router = APIRouter(prefix="/api/workpapers", tags=["wp-storage"])


@router.get("/{wp_id}/versions")
async def list_versions(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WpStorageService(db)
    return await svc.list_versions(wp_id)


@router.post("/{wp_id}/save-version")
async def save_version(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WpStorageService(db)
    result = await svc.save_version(wp_id)
    await db.commit()
    return result


@router.post("/projects/{project_id}/archive")
async def archive_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WpStorageService(db)
    return await svc.archive_project(project_id)
