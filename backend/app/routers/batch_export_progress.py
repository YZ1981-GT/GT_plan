"""批量导出 SSE 进度推送路由 — proposal-remaining-18 C-3

POST /api/projects/{project_id}/working-papers/batch-export-async
  → 立即返回 {task_id}，后台生成 ZIP，进度通过 SSE 推送
GET  /api/exports/{task_id}
  → 下载完成后的 ZIP 文件
GET  /api/exports/{task_id}/status
  → 查询任务状态（done/total/percent/status/error/download_url）

注册到 router_registry 协作域 §116。
ZIP 文件清理策略：完成 24h 后清理（TODO，本任务不实现清理 worker）

Validates: requirements.md §三 C-3
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.export_progress_service import export_progress_service


# 项目级路由（接受 wp_ids 触发任务）
router = APIRouter(
    prefix="/api/projects/{project_id}/working-papers",
    tags=["batch-export-progress"],
)

# 全局下载/状态路由（无 project_id 前缀）
download_router = APIRouter(
    prefix="/api/exports",
    tags=["batch-export-progress"],
)


class BatchExportAsyncRequest(BaseModel):
    """批量异步导出请求体"""
    wp_ids: list[str]


class BatchExportAsyncResponse(BaseModel):
    """批量异步导出响应体（立即返回）"""
    task_id: str
    total: int
    status: str


class ExportTaskStatus(BaseModel):
    """导出任务状态查询响应"""
    task_id: str
    status: str
    done: int
    total: int
    percent: int
    error: str | None = None
    download_url: str | None = None


@router.post("/batch-export-async", response_model=BatchExportAsyncResponse)
async def batch_export_async(
    project_id: UUID,
    body: BatchExportAsyncRequest,
    current_user: User = Depends(require_project_access("readonly")),
) -> BatchExportAsyncResponse:
    """触发批量导出任务，立即返回 task_id；ZIP 通过后台异步生成。

    进度通过 SSE 事件 export.progress 推送，完成时推送 export.complete
    （含 download_url），失败推送 export.failed。
    """
    if not body.wp_ids:
        raise HTTPException(status_code=400, detail="wp_ids 不能为空")

    task = export_progress_service.create_task(
        project_id=str(project_id),
        user_id=str(current_user.id),
        wp_ids=body.wp_ids,
    )
    return BatchExportAsyncResponse(
        task_id=task.task_id,
        total=task.total,
        status=task.status,
    )


@download_router.get("/{task_id}/status", response_model=ExportTaskStatus)
async def get_export_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> ExportTaskStatus:
    """查询导出任务状态"""
    task = export_progress_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="导出任务不存在或已过期")
    download_url = (
        f"/api/exports/{task.task_id}"
        if task.status == "complete" and task.file_path
        else None
    )
    percent = int(task.done * 100 / max(task.total, 1))
    return ExportTaskStatus(
        task_id=task.task_id,
        status=task.status,
        done=task.done,
        total=task.total,
        percent=percent,
        error=task.error,
        download_url=download_url,
    )


@download_router.get("/{task_id}")
async def download_export(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """下载已生成的 ZIP 文件"""
    task = export_progress_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="导出任务不存在或已过期")
    if task.status != "complete":
        raise HTTPException(status_code=409, detail=f"任务尚未完成（状态：{task.status}）")
    if not task.file_path or not Path(task.file_path).exists():
        raise HTTPException(status_code=404, detail="导出文件已被清理")
    return FileResponse(
        path=str(task.file_path),
        media_type="application/zip",
        filename=f"workpapers_export_{task_id[:8]}.zip",
    )
