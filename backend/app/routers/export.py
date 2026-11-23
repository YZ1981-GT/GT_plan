"""PDF导出 API 路由

覆盖：
- POST /api/export/create — 创建导出任务
- GET  /api/export/{task_id}/status — 查询任务状态
- GET  /api/export/{task_id}/download — 下载导出文件
- GET  /api/export/{project_id}/history — 导出历史记录

Validates: Requirements 7.1-7.10
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.report_models import ExportTaskStatus
from app.models.report_schemas import (
    ExportTaskCreate,
    ExportTaskStatusResponse,
    ExportHistoryResponse,
)
from app.services.export_policy_snapshot import resolve_policy_snapshot_for_project
from app.services.pdf_export_engine import (
    PDFConversionUnavailable,
    PDFExportEngine,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/export",
    tags=["export"],
)


@router.post("/create")
async def create_export_task(
    data: ExportTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建导出任务并同步执行（MVP 无 Celery）"""
    engine = PDFExportEngine(db)
    try:
        # spec platform-global-display-settings-closure 任务 10 / AC-21：
        # 落单位策略快照证据（`export_tasks.unit_policy_snapshot`，V265）。
        # 🔴 失败**不得静默放行**：没有 policy 快照的正式导出无法审计
        # 「这份交付件按哪个单位出的」。AC-20 明文要求「逐调用方删除参数均失败」
        # ⇒ 构造失败返回 422（策略不完整属请求前置条件问题），不是 warning。
        try:
            unit_policy_snapshot = await resolve_policy_snapshot_for_project(
                db, project_id=data.project_id
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("导出单位策略快照构造失败: %s", exc)
            raise HTTPException(
                status_code=422,
                detail=f"项目单位策略不完整，无法正式导出：{exc}",
            ) from exc
        task = await engine.create_export_task(
            project_id=data.project_id,
            task_type=data.task_type,
            document_type=data.document_type,
            unit_policy_snapshot=unit_policy_snapshot,
        )
        # MVP: execute synchronously
        task = await engine.execute_export(task.id)
        await db.commit()
        return ExportTaskStatusResponse.model_validate(task)
    except HTTPException:
        await db.rollback()
        raise
    except PDFConversionUnavailable as exc:
        # 转换链缺失是环境问题：503 + 可重试语义（任务已标 failed 留痕）。
        await db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"导出任务创建失败: {str(e)}")


@router.get("/{task_id}/status")
async def get_task_status(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
):
    """获取项目导出历史"""
    engine = PDFExportEngine(db)
    tasks = await engine.get_history(project_id)
    return ExportHistoryResponse(
        tasks=[ExportTaskStatusResponse.model_validate(t) for t in tasks]
    )
