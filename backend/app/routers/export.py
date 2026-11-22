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
from app.deps import assert_project_permission, get_current_user
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
from app.services.pdf_export_sources import PDFSourceUnavailable

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
        await assert_project_permission(db, current_user, data.project_id, "readonly")
        # 正式出口必须冻结审计年度：没有年度就无法按 project_id + year 取真实报表，
        # 而 engine 的兼容分支（旧内部调用）会用空 rows 产出「成功」的空白 PDF。
        # 因此在路由层拒绝，不把缺年度降级成兼容路径。
        if data.export_year is None:
            raise HTTPException(
                status_code=422,
                detail="正式 PDF 导出必须携带审计年度（export_year）",
            )
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
            document_types=data.document_types,
            export_year=data.export_year,
            created_by=current_user.id,
            unit_policy_snapshot=unit_policy_snapshot,
        )
        # MVP: execute synchronously；密码只经参数传递（不落库），加密在引擎内完成
        task = await engine.execute_export(task.id, password=data.password)
        await db.commit()
        return ExportTaskStatusResponse.model_validate(task)
    except HTTPException:
        await db.rollback()
        raise
    except PDFSourceUnavailable as exc:
        # 正式数据来源缺失 / 未接入：任务已标 failed 留痕，再按来源自身语义
        # 回 409（数据未就绪）或 422（请求前置条件不足），不用空页面冒充成功。
        await db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
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
    await assert_project_permission(db, current_user, task.project_id, "readonly")
    return ExportTaskStatusResponse.model_validate(task)


@router.get("/{task_id}/download")
async def download_export(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载导出文件"""
    engine = PDFExportEngine(db)
    task = await engine.get_task_status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="导出任务不存在")
    await assert_project_permission(db, current_user, task.project_id, "readonly")
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
    await assert_project_permission(db, current_user, project_id, "readonly")
    engine = PDFExportEngine(db)
    tasks = await engine.get_history(project_id)
    return ExportHistoryResponse(
        tasks=[ExportTaskStatusResponse.model_validate(t) for t in tasks]
    )
