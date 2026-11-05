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
from pydantic import BaseModel, Field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, get_current_user_stream, require_project_access
from app.models.core import User
from app.services.export_progress_service import export_progress_service

# 延迟导入以避免循环（executor 在 worker 启动时注册）
_DURABLE_ENABLED = True  # 灰度开关；设 False 回退旧内存态


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
    """批量异步导出请求体；限制单任务规模，避免无界内存/文件队列。"""
    wp_ids: list[str] = Field(min_length=1, max_length=1000)


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


async def _owned_durable_snapshot(
    task_id: str,
    current_user: User,
) -> dict | None:
    """查 platform_jobs 并校验归属（只校验 actor_id）；找不到返回 None（留给旧路径）。"""
    if not _DURABLE_ENABLED:
        return None
    try:
        job_uuid = UUID(task_id)
    except ValueError:
        return None
    from app.core.database import async_session
    from app.models.platform_job_models import PlatformJob
    from app.services.platform_job_service import job_snapshot

    try:
        async with async_session() as db:
            job = (
                await db.execute(
                    sa.select(PlatformJob).where(
                        PlatformJob.id == job_uuid,
                        PlatformJob.actor_id == current_user.id,
                    )
                )
            ).scalar_one_or_none()
            if job is None:
                return None
            return job_snapshot(job)
    except Exception:  # noqa: BLE001 — 查旧任务失败不阻断
        return None


def _owned_legacy_task(task_id: str, current_user: User):
    """旧内存态兼容读。"""
    task = export_progress_service.get_task(task_id)
    if task is None or task.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="导出任务不存在或已过期")
    return task


@router.post("/batch-export-async", response_model=BatchExportAsyncResponse)
async def batch_export_async(
    project_id: UUID,
    body: BatchExportAsyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> BatchExportAsyncResponse:
    """触发批量导出任务，立即返回 task_id；ZIP 通过后台异步生成。

    迁移后提交端只做权限 + job INSERT，不再 asyncio.create_task。worker 认领后执行。
    """
    if not body.wp_ids:
        raise HTTPException(status_code=400, detail="wp_ids 不能为空")

    from app.services.wp_visibility.entry_integration import make_bulk_visible_filter

    _visible = make_bulk_visible_filter(
        db, current_user, entrypoint="workpaper.detail", action="read_detail",
        method="GET", entry_family="export",
    )
    visible_wp_ids = [wid for wid in body.wp_ids if await _visible(wid, None)]

    if _DURABLE_ENABLED:
        from app.services.export_pack_executor import OPERATION
        from app.services import platform_job_service as jobs

        idempotency_key = f"pack-{project_id}-{'-'.join(sorted(visible_wp_ids))}"
        job, created = await jobs.create_or_get_job(
            db,
            operation=OPERATION,
            project_id=project_id,
            actor_id=current_user.id,
            idempotency_key=idempotency_key,
            payload_ref={"wp_ids": visible_wp_ids},
            progress_total=len(visible_wp_ids),
        )
        await db.commit()
        snapshot = jobs.job_snapshot(job)
        return BatchExportAsyncResponse(
            task_id=str(job.id),
            total=int(snapshot.get("progress_total") or len(visible_wp_ids)),
            status=snapshot.get("status", "queued"),
        )

    # 旧路径（灰度 fallback，_DURABLE_ENABLED=False 时使用）
    task = export_progress_service.create_task(
        project_id=str(project_id),
        user_id=str(current_user.id),
        wp_ids=visible_wp_ids,
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
    """查询导出任务状态——优先查耐久任务（platform_jobs），旧内存态作兼容后备。"""
    durable = await _owned_durable_snapshot(task_id, current_user)
    if durable is not None:
        status = durable["status"]
        done = int(durable.get("progress_current") or 0)
        total = int(durable.get("progress_total") or 0)
        percent = int(done * 100 / max(total, 1))
        download_url = (
            (durable.get("result_ref") or {}).get("download_url")
            if status == "succeeded"
            else None
        )
        # 前端 ExportProgressBar 认 complete/failed/running/pending，映射耐久任务六态
        mapped_status = {
            "queued": "pending",
            "running": "running",
            "retry_wait": "pending",
            "succeeded": "complete",
            "failed": "failed",
            "cancelled": "failed",
        }.get(status, status)
        return ExportTaskStatus(
            task_id=task_id,
            status=mapped_status,
            done=done,
            total=total,
            percent=percent,
            error=durable.get("error_message"),
            download_url=download_url,
        )

    task = _owned_legacy_task(task_id, current_user)
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
    current_user: User = Depends(get_current_user_stream),
):
    """下载已生成的 ZIP 文件——优先查耐久任务，旧内存态作兼容后备。"""
    durable = await _owned_durable_snapshot(task_id, current_user)
    if durable is not None:
        if durable["status"] != "succeeded":
            raise HTTPException(
                status_code=409,
                detail=f"任务尚未完成（状态：{durable['status']}）",
            )
        zip_path = (durable.get("result_ref") or {}).get("zip_path")
        if not zip_path or not Path(zip_path).exists():
            raise HTTPException(status_code=404, detail="导出文件已被清理")
        return FileResponse(
            path=zip_path,
            media_type="application/zip",
            filename=f"workpapers_export_{task_id[:8]}.zip",
        )

    task = _owned_legacy_task(task_id, current_user)
    if task.status != "complete":
        raise HTTPException(status_code=409, detail=f"任务尚未完成（状态：{task.status}）")
    if not task.file_path or not Path(task.file_path).exists():
        raise HTTPException(status_code=404, detail="导出文件已被清理")
    return FileResponse(
        path=str(task.file_path),
        media_type="application/zip",
        filename=f"workpapers_export_{task_id[:8]}.zip",
    )
