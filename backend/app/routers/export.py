"""PDF导出 API 路由

覆盖：
- POST /api/export/create — 创建导出任务
- GET  /api/export/{task_id}/status — 查询任务状态
- GET  /api/export/{task_id}/download — 下载导出文件
- GET  /api/export/{project_id}/history — 导出历史记录

Validates: Requirements 7.1-7.10
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.report_models import ExportTaskStatus
from app.models.report_schemas import (
    ExportTaskCreate,
    ExportTaskStatusResponse,
    ExportHistoryResponse,
)
from app.services.pdf_export_engine import PDFExportEngine

router = APIRouter(
    prefix="/api/export",
    tags=["export"],
)


@router.post("/create")
async def create_export_task(
    data: ExportTaskCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建导出任务并同步执行（MVP 无 Celery）"""
    engine = PDFExportEngine(db)
    try:
        task = await engine.create_export_task(
            project_id=data.project_id,
            task_type=data.task_type,
            document_type=data.document_type,
        )
        # MVP: execute synchronously
        task = await engine.execute_export(task.id)
        await db.commit()
        return ExportTaskStatusResponse.model_validate(task)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"导出任务创建失败: {str(e)}")


@router.get("/{task_id}/status")
async def get_task_status(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """查询导出任务状态"""
    engine = PDFExportEngine(db)
    task = await engine.get_task_status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="导出任务不存在")
    return ExportTaskStatusResponse.model_validate(task)


@router.get("/{task_id}/download")
async def download_export(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """下载导出文件"""
    engine = PDFExportEngine(db)
    task = await engine.get_task_status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="导出任务不存在")
    if task.status != ExportTaskStatus.completed:
        raise HTTPException(status_code=400, detail=f"任务状态为 {task.status.value}，无法下载")
    if not task.file_path:
        raise HTTPException(status_code=404, detail="导出文件不存在")

    file_path = Path(task.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="导出文件已过期或不存在")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@router.get("/{project_id}/history")
async def get_export_history(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取项目导出历史"""
    engine = PDFExportEngine(db)
    tasks = await engine.get_history(project_id)
    return ExportHistoryResponse(
        tasks=[ExportTaskStatusResponse.model_validate(t) for t in tasks]
    )
