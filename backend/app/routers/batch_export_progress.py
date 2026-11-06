"""底稿文件批量打包导出：耐久任务提交、状态查询与下载。

公共 API 兼容旧版：

* ``POST /api/projects/{project_id}/working-papers/batch-export-async`` → task_id
* ``GET /api/exports/{task_id}/status`` → pending/running/complete/failed
* ``GET /api/exports/{task_id}`` → ZIP

B3 起新任务统一落 ``platform_jobs`` 并由 ``workpaper_pack_export`` executor 执行。
旧 ``ExportProgressService`` 仅在 ``LEGACY_EXPORT_PROGRESS_READ_UNTIL`` 前提供已存在内存任务的
兼容读取，公共路由再也不会创建内存任务。
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import (
    assert_project_permission,
    get_current_user,
    get_current_user_stream,
    require_project_access,
)
from app.models.core import User
from app.models.platform_job_models import PlatformJob
from app.services import platform_job_service as jobs
from app.services.export_pack_executor import OPERATION
from app.services.export_progress_service import (
    EXPORT_DIR,
    export_progress_service,
    legacy_export_task_readable,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/working-papers",
    tags=["batch-export-progress"],
)
download_router = APIRouter(prefix="/api/exports", tags=["batch-export-progress"])

_DURABLE_TO_LEGACY_STATUS = {
    "queued": "pending",
    "running": "running",
    "retry_wait": "pending",
    "succeeded": "complete",
    "failed": "failed",
    "cancelled": "failed",
}


class BatchExportAsyncRequest(BaseModel):
    """请求体。

    ``operation_id`` 是可选客户端幂等键：同一次用户点击重试必须复用它，才会复用同一个
    durable job。缺失时服务端生成新 id，避免「同一组选项在数天后再次导出」意外复用旧 ZIP。
    """

    wp_ids: list[str] = Field(min_length=1, max_length=1000)
    operation_id: str | None = Field(default=None, max_length=100)


class BatchExportAsyncResponse(BaseModel):
    task_id: str
    total: int
    status: str


class ExportTaskStatus(BaseModel):
    task_id: str
    status: str
    done: int
    total: int
    percent: int
    error: str | None = None
    download_url: str | None = None


def _idempotency_key(operation_id: str | None) -> str:
    """返回小于 PlatformJob.idempotency_key 128 字符限制的稳定键。"""
    raw = (operation_id or "").strip()
    if not raw:
        raw = uuid.uuid4().hex
    # operation_id 已有 max_length=100，仍做 sha256 防未来 schema 放宽后撞 DB 长度限制。
    return f"pack:{jobs.canonical_hash({'operation_id': raw})}"


def _durable_export_path(snapshot: dict[str, Any]) -> Path | None:
    """只接受 executor 写入 EXPORT_DIR 的 artifact，禁止 result_ref 被篡改后读任意本地文件。"""
    raw = (snapshot.get("result_ref") or {}).get("zip_path")
    if not raw:
        return None
    try:
        path = Path(str(raw)).resolve()
        path.relative_to(EXPORT_DIR.resolve())
    except (OSError, ValueError):
        return None
    return path


async def _owned_durable_snapshot(task_id: str, current_user: User) -> dict[str, Any] | None:
    """读取当前用户自己的导出 job，并在下载/状态查询时重新校验项目权限。

    ``task_id`` 可能恰好也是其他 durable operation 的 UUID；必须加 ``operation==OPERATION``，
    否则同一用户能借导出端点探测/下载无关任务的 result_ref。任务在排队后被移出项目时也
    不能继续下载，所以这里不只查 actor_id，还调用平台唯一项目权限守卫。
    """
    try:
        job_id = UUID(task_id)
    except ValueError:
        return None

    try:
        from app.core.database import async_session

        async with async_session() as db:
            job = (
                await db.execute(
                    sa.select(PlatformJob).where(
                        PlatformJob.id == job_id,
                        PlatformJob.actor_id == current_user.id,
                        PlatformJob.operation == OPERATION,
                    )
                )
            ).scalar_one_or_none()
            if job is None:
                return None
            await assert_project_permission(db, current_user, job.project_id, "readonly")
            return jobs.job_snapshot(job)
    except HTTPException:
        raise
    except sa.SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="导出任务状态暂不可用，请稍后重试") from exc


def _owned_legacy_task(task_id: str, current_user: User):
    """退役窗口内的旧进程内任务兼容读取。"""
    if not legacy_export_task_readable():
        raise HTTPException(status_code=404, detail="导出任务不存在或已过期")
    task = export_progress_service.get_task(task_id)
    if task is None or task.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="导出任务不存在或已过期")
    return task


def _status_from_durable(task_id: str, snapshot: dict[str, Any]) -> ExportTaskStatus:
    durable_status = str(snapshot.get("status") or "failed")
    done = int(snapshot.get("progress_current") or 0)
    total = int(snapshot.get("progress_total") or 0)
    status = _DURABLE_TO_LEGACY_STATUS.get(durable_status, "failed")
    error = snapshot.get("error_message")
    if durable_status == "cancelled" and not error:
        error = "导出已取消"
    return ExportTaskStatus(
        task_id=task_id,
        status=status,
        done=done,
        total=total,
        percent=int(done * 100 / max(total, 1)),
        error=error,
        download_url=(
            (snapshot.get("result_ref") or {}).get("download_url")
            if durable_status == "succeeded" and _durable_export_path(snapshot) is not None
            else None
        ),
    )


@router.post("/batch-export-async", response_model=BatchExportAsyncResponse)
async def batch_export_async(
    project_id: UUID,
    body: BatchExportAsyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> BatchExportAsyncResponse:
    """提交耐久导出 job；请求路径只做权限/预算/INSERT，不在 Web 事件循环压缩 ZIP。"""
    from app.services.wp_visibility.entry_integration import make_bulk_visible_filter

    visible = make_bulk_visible_filter(
        db,
        current_user,
        entrypoint="workpaper.detail",
        action="read_detail",
        method="GET",
        entry_family="export",
    )
    # 去重但保留用户的选择顺序；ZIP 的条目顺序是可见行为，不能 sort 后让同一 operation 得到不同产物。
    visible_wp_ids: list[str] = []
    seen: set[str] = set()
    for raw in body.wp_ids:
        wp_id = str(raw)
        if wp_id in seen:
            continue
        seen.add(wp_id)
        if await visible(wp_id, None):
            visible_wp_ids.append(wp_id)
    if not visible_wp_ids:
        # 同 legacy route 一样不点名哪一项不可见，避免资源枚举。
        raise HTTPException(status_code=404, detail="没有可导出的底稿")

    try:
        job, _created = await jobs.create_or_get_job(
            db,
            operation=OPERATION,
            project_id=project_id,
            actor_id=current_user.id,
            idempotency_key=_idempotency_key(body.operation_id),
            payload_ref={"wp_ids": visible_wp_ids},
            progress_total=len(visible_wp_ids),
        )
        await db.commit()
    except jobs.PlatformJobConflict as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return BatchExportAsyncResponse(
        task_id=str(job.id),
        total=int(job.progress_total or len(visible_wp_ids)),
        status=_DURABLE_TO_LEGACY_STATUS.get(job.status, "pending"),
    )


@download_router.get("/{task_id}/status", response_model=ExportTaskStatus)
async def get_export_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> ExportTaskStatus:
    """状态恢复端点：优先 durability DB，退役窗口内再读旧内存任务。"""
    snapshot = await _owned_durable_snapshot(task_id, current_user)
    if snapshot is not None:
        return _status_from_durable(task_id, snapshot)

    task = _owned_legacy_task(task_id, current_user)
    return ExportTaskStatus(
        task_id=task.task_id,
        status=task.status,
        done=task.done,
        total=task.total,
        percent=int(task.done * 100 / max(task.total, 1)),
        error=task.error,
        download_url=(
            f"/api/exports/{task.task_id}"
            if task.status == "complete" and task.file_path
            else None
        ),
    )


@download_router.get("/{task_id}")
async def download_export(
    task_id: str,
    current_user: User = Depends(get_current_user_stream),
):
    """下载 artifact；查询和项目权限校验的 session 在返回 FileResponse 前已关闭。"""
    snapshot = await _owned_durable_snapshot(task_id, current_user)
    if snapshot is not None:
        if snapshot.get("status") != "succeeded":
            raise HTTPException(status_code=409, detail=f"任务尚未完成（状态：{snapshot.get('status')}）")
        zip_path = _durable_export_path(snapshot)
        if zip_path is None or not zip_path.is_file():
            raise HTTPException(status_code=404, detail="导出文件已被清理")
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=f"workpapers_export_{task_id[:8]}.zip",
        )

    task = _owned_legacy_task(task_id, current_user)
    if task.status != "complete":
        raise HTTPException(status_code=409, detail=f"任务尚未完成（状态：{task.status}）")
    if not task.file_path or not Path(task.file_path).is_file():
        raise HTTPException(status_code=404, detail="导出文件已被清理")
    return FileResponse(
        path=str(task.file_path),
        media_type="application/zip",
        filename=f"workpapers_export_{task_id[:8]}.zip",
    )
