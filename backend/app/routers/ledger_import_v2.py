"""Ledger Import v2 API endpoints.

Per design.md §7:
- POST /detect — multipart file upload, returns LedgerDetectionResult
- POST /submit — confirmed mappings, creates ImportJob
- GET /jobs/{job_id}/stream — SSE progress
- GET /jobs/{job_id}/diagnostics — diagnostic details (admin/support)
- POST /jobs/{job_id}/cancel — cancel running job
- POST /jobs/{job_id}/retry — retry failed job
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session, get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.dataset_models import ImportJob, JobStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/ledger-import",
    tags=["ledger-import-v2"],
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILES = 20
MAX_TOTAL_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB

TERMINAL_STATUSES = {JobStatus.completed, JobStatus.failed, JobStatus.canceled}
CANCELABLE_STATUSES = {
    JobStatus.pending,
    JobStatus.queued,
    JobStatus.running,
    JobStatus.validating,
    JobStatus.writing,
    JobStatus.activating,
}


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class SubmitRequest(BaseModel):
    """POST /submit request body."""

    upload_token: str
    year: int
    confirmed_mappings: list[dict]
    force_activate: bool = False
    adapter_id: Optional[str] = None
    # S7-9: 增量追加模式
    incremental: bool = Field(
        False,
        description="S7-9 增量追加模式：true 时 submit 前按 overlap_strategy 清理旧数据",
    )
    overlap_strategy: str = Field(
        "skip",
        description="增量追加重叠月份策略（skip=跳过 / overwrite=覆盖），仅 incremental=true 时生效",
    )
    file_periods: Optional[list[int]] = Field(
        None,
        description="文件包含的月份列表（incremental+overwrite 时必填，用于精确清理）",
    )


# ---------------------------------------------------------------------------
# POST /detect (Task 42)
# ---------------------------------------------------------------------------


@router.post("/detect")
async def detect_files(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    year_override: Optional[int] = Form(None),
    adapter_hint: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """Multipart file upload → run detection pipeline → return LedgerDetectionResult.

    Limits: max 20 files, total 500 MB.
    """
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"最多上传 {MAX_FILES} 个文件，当前 {len(files)} 个",
        )

    # Read all file bytes and check total size
    file_data: list[tuple[str, bytes]] = []
    total_size = 0
    for f in files:
        content = await f.read()
        total_size += len(content)
        if total_size > MAX_TOTAL_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"文件总大小超过 {MAX_TOTAL_SIZE_BYTES // (1024 * 1024)} MB 限制",
            )
        file_data.append((f.filename or "unknown", content))

    # Run detection (pure computation, no DB writes)
    from app.services.ledger_import.orchestrator import ImportOrchestrator

    result = ImportOrchestrator.detect(
        file_data,
        year_override=year_override,
        adapter_hint=adapter_hint,
    )

    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# POST /submit (Task 43)
# ---------------------------------------------------------------------------


@router.post("/submit")
async def submit_import(
    project_id: UUID,
    body: SubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """Accept confirmed mappings, create ImportJob, return job info.

    S7-9: 支持 incremental 模式——submit 前自动按 overlap_strategy 清理旧数据，
    用户无需先调 /incremental/apply 再上传（一步到位）。
    """
    # S7-9: 增量追加模式——submit 前清理旧月份
    if body.incremental and body.overlap_strategy == "overwrite":
        if not body.file_periods:
            raise HTTPException(
                status_code=400,
                detail="incremental+overwrite 模式必须提供 file_periods",
            )
        from app.services.ledger_data_service import apply_incremental
        await apply_incremental(
            db,
            project_id=project_id,
            year=body.year,
            file_periods=body.file_periods,
            overlap_strategy="overwrite",
        )
        # apply_incremental 内部已 commit

    from app.services.ledger_import.orchestrator import ImportOrchestrator

    result = await ImportOrchestrator.submit(
        db,
        upload_token=body.upload_token,
        project_id=project_id,
        year=body.year,
        confirmed_mappings=body.confirmed_mappings,
        file_manifest=[],  # Files already stored via upload_token
        storage_uri=f"local:///tmp/uploads/{body.upload_token}",
        force_activate=body.force_activate,
        created_by=current_user.id,
        adapter_id=body.adapter_id,
    )
    await db.commit()

    return {"job_id": str(result["job_id"]), "status": result["status"]}


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/stream (Task 44)
# ---------------------------------------------------------------------------


async def _sse_generator(job_id: UUID):
    """Generate SSE events by polling job status every 2 seconds.

    Uses its own DB session per iteration (request-scoped session
    closes when streaming starts).
    """
    while True:
        async with async_session() as db:
            stmt = select(ImportJob).where(ImportJob.id == job_id)
            result = await db.execute(stmt)
            job = result.scalar_one_or_none()

        if job is None:
            yield f"data: {json.dumps({'error': 'job_not_found'})}\n\n"
            break

        event = {
            "phase": job.current_phase,
            "percent": job.progress_pct,
            "status": job.status.value,
            "message": job.progress_message,
        }
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        if job.status in TERMINAL_STATUSES:
            # Send final event with result summary if available
            if job.result_summary:
                final_event = {
                    "phase": "completed",
                    "result": job.result_summary,
                }
                yield f"data: {json.dumps(final_event, ensure_ascii=False)}\n\n"
            break

        await asyncio.sleep(2)


@router.get("/jobs/{job_id}/stream")
async def stream_job_progress(
    project_id: UUID,
    job_id: UUID,
    current_user: User = Depends(require_project_access("readonly")),
):
    """SSE endpoint for real-time job progress updates.

    Polls ImportJob every 2 seconds and emits progress events.
    Stops when job reaches a terminal status (completed/failed/canceled).
    """
    return StreamingResponse(
        _sse_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/diagnostics (Task 45)
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/diagnostics")
async def get_job_diagnostics(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """Return diagnostic details for a job (admin/support use).

    Includes result_summary, detection_result snapshot, and adapter_used.
    """
    stmt = select(ImportJob).where(
        ImportJob.id == job_id,
        ImportJob.project_id == project_id,
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail="作业不存在")

    # detection_result and adapter_used may be stored in options or as
    # dedicated columns (per design §9.3)
    options = job.options or {}

    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "current_phase": job.current_phase,
        "progress_pct": job.progress_pct,
        "error_message": job.error_message,
        "result_summary": job.result_summary,
        "detection_result": options.get("detection_result"),
        "adapter_used": options.get("adapter_id"),
        "options": options,
        "retry_count": job.retry_count,
        "max_retries": job.max_retries,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/cancel (Task 46)
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """Cancel a running/queued job.

    Sets status to 'canceled'. The worker will detect this and clean up
    any staged data.
    """
    stmt = select(ImportJob).where(
        ImportJob.id == job_id,
        ImportJob.project_id == project_id,
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail="作业不存在")

    if job.status not in CANCELABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"作业当前状态 '{job.status.value}' 不可取消",
        )

    job.status = JobStatus.canceled
    job.progress_message = "用户取消"
    await db.flush()
    await db.commit()

    return {"job_id": str(job.id), "status": "canceled"}


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/retry (Task 47)
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """Retry a failed job using ImportOrchestrator.resume().

    Reuses existing ImportArtifact (files already uploaded).
    Increments retry_count.
    """
    from app.services.ledger_import.orchestrator import ImportOrchestrator

    # Verify job belongs to this project
    stmt = select(ImportJob).where(
        ImportJob.id == job_id,
        ImportJob.project_id == project_id,
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail="作业不存在")

    try:
        resume_result = await ImportOrchestrator.resume(db, job_id=job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()

    return {
        "job_id": str(resume_result["job_id"]),
        "status": resume_result["status"],
        "retry_count": resume_result["retry_count"],
    }


# ---------------------------------------------------------------------------
# GET /jobs/latest (S7 — 进度条轮询改走 import_jobs 表)
# ---------------------------------------------------------------------------


@router.get("/active-job")
async def get_latest_job(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """S7: 获取项目最新的导入作业状态（替代 ImportQueueService 内存态轮询）。

    前端 ThreeColumnLayout 每 10s 轮询此端点显示进度条。
    后端重启后仍能看到正在运行/最近完成的 job。

    Returns:
        - 有活跃 job: {status, progress, message, job_id, year}
        - 无活跃 job: {status: "idle"}
    """
    # 优先找 running/writing/validating/activating 的活跃 job
    active_statuses = (
        JobStatus.running, JobStatus.validating,
        JobStatus.writing, JobStatus.activating,
        JobStatus.queued, JobStatus.pending,
    )
    stmt = (
        select(ImportJob)
        .where(
            ImportJob.project_id == project_id,
            ImportJob.status.in_(active_statuses),
        )
        .order_by(ImportJob.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if job:
        return {
            "status": "processing",
            "progress": job.progress_pct or 0,
            "message": job.progress_message or "导入中...",
            "job_id": str(job.id),
            "year": job.year,
        }

    # 没有活跃 job，查最近 5 分钟内完成/失败的（给前端 toast 用）
    from datetime import datetime, timedelta, timezone
    recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    stmt_recent = (
        select(ImportJob)
        .where(
            ImportJob.project_id == project_id,
            ImportJob.status.in_((JobStatus.completed, JobStatus.failed)),
            ImportJob.completed_at > recent_cutoff,
        )
        .order_by(ImportJob.completed_at.desc())
        .limit(1)
    )
    result_recent = await db.execute(stmt_recent)
    recent_job = result_recent.scalar_one_or_none()

    if recent_job:
        return {
            "status": recent_job.status.value,
            "progress": 100 if recent_job.status == JobStatus.completed else 0,
            "message": recent_job.progress_message or (
                "导入完成" if recent_job.status == JobStatus.completed else "导入失败"
            ),
            "job_id": str(recent_job.id),
            "year": recent_job.year,
        }

    return {"status": "idle"}
