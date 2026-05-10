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
    # F42 / Sprint 7.10 + 10.43：用户明确覆盖规模警告后重发的标记
    # detect 返回 scale_warnings 非空时，submit 必须传 force_submit=True，
    # 否则端点返回 400 SCALE_WARNING_BLOCKED。
    force_submit: bool = Field(
        False,
        description="规模警告强制继续（detect 返回 scale_warnings 时必填 true）",
    )
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
    """Multipart file upload → 持久化到 bundle → 识别 → 返回 LedgerDetectionResult.

    持久化策略（S7+ 企业级链路）：
    - 文件通过 `LedgerImportUploadService.create_bundle` 保存到共享存储
      （本地或 S3），同时建 ImportArtifact 记录；后续 /submit 阶段 worker 用
      upload_token 恢复文件、走完整 pipeline。
    - 识别阶段走 `detect_from_paths`，大文件不全量读入内存。
    - upload_token 以 bundle manifest 为准（覆盖 orchestrator 随机生成的 token）。

    Limits: max 20 files, total 500 MB（沿用 MAX_FILES/MAX_TOTAL_SIZE_BYTES）。
    """
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"最多上传 {MAX_FILES} 个文件，当前 {len(files)} 个",
        )

    # Step 0: 上传安全校验（F40 / Sprint 7 批次 A）——MIME/magic/大小/zip bomb/宏
    from app.services.ledger_import.upload_security import validate_upload_safety

    client_ip = None
    try:
        # 尝试从 FastAPI Request 获取 client ip（需依赖注入 Request 才完美，
        # 此处用轻量方式：从 files 上下文拿不到，先传 None，后续补依赖注入）
        pass
    except Exception:  # pragma: no cover
        pass

    for _upload in files:
        if _upload is None:
            continue
        await validate_upload_safety(
            _upload,
            user_id=current_user.id,
            project_id=project_id,
            ip_address=client_ip,
        )

    # Step 1: 持久化文件到 bundle + 写 ImportArtifact（复用老链路）
    from app.services.ledger_import.orchestrator import ImportOrchestrator
    from app.services.ledger_import_upload_service import LedgerImportUploadService

    try:
        manifest = await LedgerImportUploadService.create_bundle(
            project_id, str(current_user.id), files,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("detect bundle 持久化失败")
        raise HTTPException(status_code=500, detail=f"文件保存失败: {exc}") from exc

    upload_token = manifest["upload_token"]
    file_entries = LedgerImportUploadService.get_bundle_files(project_id, upload_token)

    # Step 2: 识别（从 bundle 文件路径读，不全量加载内存）
    file_paths = [str(path) for _name, path in file_entries]
    result = ImportOrchestrator.detect_from_paths(
        file_paths,
        year_override=year_override,
        adapter_hint=adapter_hint,
    )
    # orchestrator.detect_from_paths 内部生成的 token 覆盖为 bundle token
    # （保证 /submit 走 bundle 路径能找到文件）
    result.upload_token = upload_token

    # 用原始 filename 覆盖（bundle 存储时可能做了 safe_filename 前缀处理）
    name_by_path = {str(path): name for name, path in file_entries}
    for fd in result.files:
        # FileDetection.file_name 应是用户原始名
        for orig_name in name_by_path.values():
            if fd.file_name.endswith(orig_name) or orig_name.endswith(fd.file_name):
                fd.file_name = orig_name
                break

    # F17 / Sprint 4.13：附上总行数估算 + 预计耗时 + 规模档位，
    # 供前端 DetectionPreview 展示"预计 X 分钟"。
    from app.services.ledger_import.duration_estimator import (
        estimate_duration_bucket,
        estimate_duration_seconds,
    )

    total_rows_estimate = sum(
        s.row_count_estimate
        for fd in result.files
        for s in fd.sheets
        if s.table_type != "unknown"
    )

    response = result.model_dump(mode="json")
    response["total_rows_estimate"] = total_rows_estimate
    response["estimated_duration_seconds"] = estimate_duration_seconds(total_rows_estimate)
    response["size_bucket"] = estimate_duration_bucket(total_rows_estimate)

    # F42 / design D30 / Sprint 7.9 + 10.42：规模异常警告（零行 / 异常规模）
    # 前端收到 warnings 后必须引导用户点"强制继续"才能调 /submit 时传
    # force_submit=True；否则 submit 会被 SCALE_WARNING_BLOCKED 拦截。
    from app.services.ledger_import.scale_warnings import check_scale_warnings

    response["scale_warnings"] = await check_scale_warnings(
        response, project_id, db
    )
    return response


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

    F42 / design D30：detect 阶段产生 ``scale_warnings`` 时必须在前端点"强制
    继续"后以 ``force_submit=True`` 重发；否则此端点返回 400 + 错误码
    ``SCALE_WARNING_BLOCKED`` 并附带 warnings 数组，供前端再次展示。
    """
    # F42 门控：从 bundle 再次计算 scale_warnings（不依赖前端传递，防止客户端
    # 伪造 force_submit 绕过）。重跑 detect_from_paths 只读表头/行数，不
    # 做完整 parse，< 2s。
    from app.services.ledger_import.duration_estimator import (
        estimate_duration_seconds,
    )
    from app.services.ledger_import.orchestrator import ImportOrchestrator
    from app.services.ledger_import.scale_warnings import check_scale_warnings
    from app.services.ledger_import_upload_service import LedgerImportUploadService

    try:
        file_entries = LedgerImportUploadService.get_bundle_files(
            project_id, body.upload_token
        )
    except Exception:  # pragma: no cover - 上传产物不存在/过期在别处拦截
        file_entries = []

    if file_entries:
        detection = ImportOrchestrator.detect_from_paths(
            [str(path) for _name, path in file_entries]
        )
        total_rows_estimate = sum(
            s.row_count_estimate
            for fd in detection.files
            for s in fd.sheets
            if s.table_type != "unknown"
        )
        scale_warnings = await check_scale_warnings(
            {"total_rows_estimate": total_rows_estimate}, project_id, db
        )
        if scale_warnings and not body.force_submit:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "SCALE_WARNING_BLOCKED",
                    "message": "检测到规模异常，需用户确认后强制继续",
                    "warnings": scale_warnings,
                    "total_rows_estimate": total_rows_estimate,
                    "estimated_duration_seconds": estimate_duration_seconds(
                        total_rows_estimate
                    ),
                },
            )

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

    # F42 / Sprint 7.10：把 force_submit 持久化到 ImportJob（审计轨迹）
    if body.force_submit:
        job_id = result["job_id"]
        if not isinstance(job_id, UUID):
            job_id = UUID(str(job_id))
        await db.execute(
            ImportJob.__table__.update()
            .where(ImportJob.id == job_id)
            .values(force_submit=True)
        )

    await db.commit()

    # 立即 enqueue 触发 worker，不等 recover_jobs 30s 轮询
    try:
        from app.services.import_job_runner import ImportJobRunner
        from uuid import UUID as _UUID
        jid = result["job_id"]
        if not isinstance(jid, _UUID):
            jid = _UUID(str(jid))
        ImportJobRunner.enqueue(jid)
    except Exception:
        # enqueue 失败不阻断 submit 返回，recover_jobs 会兜底
        logger.exception("ImportJob enqueue 失败，等待 recover 兜底")

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

    # F32 / Sprint 6.12: enrich findings with human-readable hints
    from app.services.ledger_import.error_hints import enrich_finding_with_hint

    result_summary = dict(job.result_summary) if job.result_summary else {}
    findings = result_summary.get("findings")
    if isinstance(findings, list):
        result_summary["findings"] = [
            enrich_finding_with_hint(f) if isinstance(f, dict) else f
            for f in findings
        ]
    blocking = result_summary.get("blocking_findings")
    if isinstance(blocking, list):
        result_summary["blocking_findings"] = [
            enrich_finding_with_hint(f) if isinstance(f, dict) else f
            for f in blocking
        ]

    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "current_phase": job.current_phase,
        "progress_pct": job.progress_pct,
        "error_message": job.error_message,
        "result_summary": result_summary,
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
# 注：cancel 端点由 `ledger_datasets.cancel_import_job` 提供。本模块无定义——
# 两个 router 注册到同一 prefix，ledger_datasets 先注册会拦截本模块的路由。
# 历史上 v2 也曾定义此端点（现已删除，见 Sprint 8 UX v3 复盘 M2）。
# ---------------------------------------------------------------------------


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
# POST /jobs/{job_id}/resume (F14 / Sprint 4.3 — checkpoint 恢复)
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/resume")
async def resume_from_checkpoint(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """从最后一个 checkpoint 恢复失败/超时的导入作业（F14）。

    - 查 job.current_phase → 按路由表决定从哪个阶段继续
    - activate_dataset / rebuild_aux_summary 都是幂等操作，全量重跑安全
    - staged dataset 已清理时降级为 full_restart_required
    """
    # Verify job belongs to this project
    stmt = select(ImportJob).where(
        ImportJob.id == job_id,
        ImportJob.project_id == project_id,
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="作业不存在")

    from app.services.import_job_runner import ImportJobRunner

    return await ImportJobRunner.resume_from_checkpoint(job_id)


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

    F21 / Sprint 5.7 扩展：当有活跃锁时额外返回 `lock_info` 对象，
    包含 holder_name / action / progress / 预估剩余等信息供前端 tooltip 展示。

    Returns:
        - 有活跃 job: {status, progress, message, job_id, year, lock_info?}
        - 无活跃 job: {status: "idle"}
    """
    from datetime import datetime, timedelta, timezone

    from app.services.import_queue_service import ImportQueueService

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
        # P3-5.5: 剩余耗时估算（基于已用时间和进度线性外推）
        estimated_remaining = None
        if job.started_at and job.progress_pct and 5 <= job.progress_pct < 100:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            started = job.started_at if job.started_at.tzinfo is None else (
                job.started_at.replace(tzinfo=None)
            )
            elapsed_sec = max(1, int((now - started).total_seconds()))
            total_est_sec = elapsed_sec * 100 / job.progress_pct
            estimated_remaining = max(0, int(total_est_sec - elapsed_sec))
        response = {
            "status": "processing",
            "phase": job.current_phase or "writing",
            "progress": job.progress_pct or 0,
            "message": job.progress_message or "导入中...",
            "job_id": str(job.id),
            "year": job.year,
            "estimated_remaining_seconds": estimated_remaining,
        }
        # F51 / Sprint 8.30: queued 作业展示全局队列位置
        # 1-indexed：1 = 下一个将被执行；N = 前面还有 N-1 个排队
        if job.status in (JobStatus.queued, JobStatus.pending):
            from app.services.ledger_import.global_concurrency import (
                GLOBAL_CONCURRENCY,
            )
            try:
                position = await GLOBAL_CONCURRENCY.queue_position(db, job.id)
                if position > 0:
                    response["queue_position"] = position
                    response["global_max_concurrent"] = GLOBAL_CONCURRENCY.max_concurrent
            except Exception:  # noqa: BLE001
                # queue_position 查询失败不应阻断整个端点
                pass
        # F21: 合并锁透明信息
        lock_info = await ImportQueueService.get_lock_info(project_id, db)
        if lock_info:
            response["lock_info"] = lock_info
        return response

    # 没有活跃 job，查最近 5 分钟内完成/失败的（给前端 toast 用）
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
        response = {
            "status": recent_job.status.value,
            "phase": recent_job.current_phase or (
                "completed" if recent_job.status == JobStatus.completed else "failed"
            ),
            "progress": 100 if recent_job.status == JobStatus.completed else 0,
            "message": recent_job.progress_message or (
                "导入完成" if recent_job.status == JobStatus.completed else "导入失败"
            ),
            "job_id": str(recent_job.id),
            "year": recent_job.year,
        }
        # F21: 若有未释放的 action_lock（例如进行中 rollback），也带出
        lock_info = await ImportQueueService.get_lock_info(project_id, db)
        if lock_info:
            response["lock_info"] = lock_info
        return response

    # 无活跃 job 也无最近 job，但可能有 rollback 在跑
    lock_info = await ImportQueueService.get_lock_info(project_id, db)
    if lock_info:
        return {
            "status": "processing",
            "phase": lock_info.get("current_phase") or "processing",
            "progress": lock_info.get("progress_pct") or 0,
            "message": lock_info.get("progress_message") or f"{lock_info.get('action', '操作')}进行中",
            "job_id": lock_info.get("job_id"),
            "year": None,
            "lock_info": lock_info,
        }

    return {"status": "idle"}
