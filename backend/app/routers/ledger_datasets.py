"""数据集版本管理 API — 导入历史中心 + 一键回滚

提供：
- 数据集历史列表
- 当前 active 版本查询
- 一键回滚到上一版本
- 激活记录查询
- 导入作业历史
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.dataset_models import JobStatus
from app.services.dataset_service import DatasetService
from app.services.import_job_service import ImportJobService
from app.services.import_job_runner import ImportJobRunner
from app.services.import_queue_service import ImportQueueService
from app.services.import_artifact_service import ImportArtifactService

router = APIRouter(prefix="/api/projects/{project_id}/ledger-import", tags=["数据集版本"])


@router.get("/datasets")
async def list_datasets(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询数据集版本历史"""
    datasets = await DatasetService.list_datasets(db, project_id, year)
    return [
        {
            "id": str(d.id),
            "status": d.status.value,
            "source_type": d.source_type,
            "source_summary": d.source_summary,
            "record_summary": d.record_summary,
            "validation_summary": d.validation_summary,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "activated_at": d.activated_at.isoformat() if d.activated_at else None,
            "previous_dataset_id": str(d.previous_dataset_id) if d.previous_dataset_id else None,
        }
        for d in datasets
    ]


@router.get("/datasets/active")
async def get_active_dataset(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询当前 active 数据集"""
    dataset_id = await DatasetService.get_active_dataset_id(db, project_id, year)
    if not dataset_id:
        return {"active_dataset_id": None, "message": "当前无有效数据集"}
    return {"active_dataset_id": str(dataset_id)}


@router.post("/datasets/{dataset_id}/rollback")
async def rollback_dataset(
    project_id: UUID,
    dataset_id: UUID,
    year: int = 2025,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """回滚到上一版本数据集"""
    result = await DatasetService.rollback(
        db, project_id, year,
        performed_by=current_user.id,
        reason=reason,
    )
    if not result:
        raise HTTPException(status_code=400, detail="无法回滚：没有上一版本或当前无 active 数据集")
    await db.commit()
    await DatasetService.publish_dataset_rolled_back_from_record(result)
    return {
        "message": "回滚成功",
        "restored_dataset_id": str(result.id),
        "status": result.status.value,
    }


@router.get("/activation-records")
async def list_activation_records(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询激活/回滚操作历史"""
    records = await DatasetService.list_activation_records(db, project_id, year)
    return [
        {
            "id": str(r.id),
            "dataset_id": str(r.dataset_id),
            "action": r.action.value,
            "previous_dataset_id": str(r.previous_dataset_id) if r.previous_dataset_id else None,
            "performed_at": r.performed_at.isoformat() if r.performed_at else None,
            "reason": r.reason,
        }
        for r in records
    ]


@router.get("/jobs")
async def list_import_jobs(
    project_id: UUID,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询导入作业历史"""
    jobs = await ImportJobService.list_jobs(db, project_id, year)
    return [
        {
            "id": str(j.id),
            "year": j.year,
            "status": j.status.value,
            "progress_pct": j.progress_pct,
            "progress_message": j.progress_message,
            "error_message": j.error_message,
            "retry_count": j.retry_count,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]


@router.get("/artifacts")
async def list_import_artifacts(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询上传产物历史"""
    artifacts = await ImportArtifactService.list_artifacts(db, project_id=project_id)
    return [
        {
            "id": str(a.id),
            "upload_token": a.upload_token,
            "status": a.status.value,
            "storage_uri": a.storage_uri,
            "checksum": a.checksum,
            "total_size_bytes": a.total_size_bytes,
            "file_manifest": a.file_manifest,
            "file_count": a.file_count,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in artifacts
    ]


@router.get("/jobs/{job_id}")
async def get_import_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询单个导入作业状态"""
    job = await ImportJobService.get_job(db, job_id)
    if not job or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="作业不存在")
    return {
        "id": str(job.id),
        "year": job.year,
        "status": job.status.value,
        "current_phase": job.current_phase,
        "progress_pct": job.progress_pct,
        "progress": -1 if job.status.value in ("failed", "timed_out", "canceled") else (100 if job.status.value == "completed" else job.progress_pct),
        "progress_message": job.progress_message,
        "message": job.progress_message or job.error_message,
        "error_message": job.error_message,
        "result_summary": job.result_summary,
        "result": job.result_summary,
        "retry_count": job.retry_count,
        "max_retries": job.max_retries,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/jobs/{job_id}/retry")
async def retry_import_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """重试失败的导入作业"""
    try:
        existing = await ImportJobService.get_job(db, job_id)
        if not existing or existing.project_id != project_id:
            raise HTTPException(status_code=404, detail="作业不存在")
        job = await ImportJobService.retry(db, job_id)
        await ImportJobService.transition(db, job.id, JobStatus.queued, progress_pct=0, progress_message="重试作业已排队")
        await db.commit()
        from app.core.config import settings
        if settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED:
            ImportJobRunner.enqueue(job.id)
        return {"message": f"作业已重新排队（第 {job.retry_count} 次重试）", "job_id": str(job.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{job_id}/cancel")
async def cancel_import_job(
    project_id: UUID,
    job_id: UUID,
    expected_version: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """取消导入作业。

    P1-Q1: 可选 `expected_version` 参数做乐观锁——前端传入期望版本号，
    与 DB 当前 version 不一致时返回 409（说明另一个请求已修改 job 状态）。
    不传则保持向后兼容，但可能并发 cancel 冲突。
    """
    try:
        existing = await ImportJobService.get_job(db, job_id)
        if not existing or existing.project_id != project_id:
            raise HTTPException(status_code=404, detail="作业不存在")
        # P1-Q1: 乐观锁守卫
        if expected_version is not None and existing.version != expected_version:
            raise HTTPException(
                status_code=409,
                detail=f"作业已被修改（期望版本 {expected_version}，当前版本 {existing.version}），请刷新后重试",
            )
        existing_status = existing.status
        job = await ImportJobService.cancel(db, job_id)
        # P1-Q1: 每次状态变更自增 version
        job.version = (existing.version or 0) + 1
        await db.commit()
        ImportJobRunner.request_cancel(job.id)
        if existing_status in (JobStatus.pending, JobStatus.queued):
            ImportQueueService.release_lock(project_id)
            batch_id_raw = (job.options or {}).get("queue_batch_id")
            if batch_id_raw:
                await ImportQueueService.fail_job(
                    project_id,
                    UUID(batch_id_raw),
                    db,
                    message="导入已取消",
                    year=job.year,
                )
        # P2-4.2: 同步清理对应的 ImportArtifact，避免重复提交累加存储
        try:
            from app.services.import_artifact_service import ImportArtifactService
            if job.artifact_id:
                await ImportArtifactService.mark_consumed(db, job.artifact_id)
                await db.commit()
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "cancel: artifact cleanup failed for %s", job_id, exc_info=True,
            )
        return {"message": "作业已取消", "job_id": str(job.id), "status": "canceled"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
