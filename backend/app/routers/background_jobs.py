"""后台任务 API 路由

Phase 12: job_id 状态查询 / SSE事件流 / 失败重试
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(prefix="/api/projects/{project_id}/jobs", tags=["后台任务"])


@router.get("/{job_id}")
async def get_job_status(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取后台任务状态"""
    from app.services.background_job_service import BackgroundJobService
    svc = BackgroundJobService(db)
    result = await svc.get_job_status(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="任务不存在")
    return result


@router.post("/{job_id}/retry")
async def retry_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重试失败项"""
    from app.services.background_job_service import BackgroundJobService
    svc = BackgroundJobService(db)
    return await svc.retry_job(job_id)
