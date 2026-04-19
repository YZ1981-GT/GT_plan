# -*- coding: utf-8 -*-
"""数据生命周期管理 API"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.data_lifecycle_service import DataLifecycleService
from app.services.import_queue_service import ImportQueueService

router = APIRouter(prefix="/api/data-lifecycle", tags=["data-lifecycle"])


@router.get("/capacity")
async def get_capacity(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全局容量统计（各表行数、大小、按项目分布）"""
    svc = DataLifecycleService(db)
    return await svc.get_capacity_stats()


@router.get("/projects/{project_id}/stats")
async def get_project_stats(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """单个项目数据统计"""
    svc = DataLifecycleService(db)
    return await svc.get_project_data_stats(project_id)


@router.post("/projects/{project_id}/archive")
async def archive_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """归档项目数据（软删除，可恢复）"""
    svc = DataLifecycleService(db)
    return await svc.archive_project_data(project_id)


@router.post("/projects/{project_id}/restore")
async def restore_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """恢复已归档的项目数据"""
    svc = DataLifecycleService(db)
    return await svc.restore_project_data(project_id)


@router.delete("/projects/{project_id}/purge")
async def purge_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """物理删除已归档数据（不可恢复）"""
    svc = DataLifecycleService(db)
    return await svc.purge_project_data(project_id)


@router.get("/import-queue")
async def get_import_queue(
    current_user: User = Depends(get_current_user),
):
    """查看当前导入队列"""
    return {"active": ImportQueueService.get_all_active()}


@router.get("/import-queue/{project_id}")
async def get_import_status(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """查看项目导入状态"""
    status = ImportQueueService.get_status(project_id)
    return {"status": status or "idle"}
