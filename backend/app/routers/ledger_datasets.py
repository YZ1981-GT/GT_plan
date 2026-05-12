"""数据集版本管理 API — 导入历史中心 + 一键回滚

提供：
- 数据集历史列表
- 当前 active 版本查询
- 一键回滚到上一版本
- 激活记录查询
- 导入作业历史
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.dataset_models import JobStatus
from app.services.dataset_service import DatasetService
from app.services.import_job_service import ImportJobService
from app.services.import_job_runner import ImportJobRunner
from app.services.import_queue_service import ImportLockError, ImportQueueService
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
    # 返回 source_summary 供前端读取金额单位等元信息
    from sqlalchemy import select
    from app.models.dataset_models import LedgerDataset
    result = await db.execute(
        select(LedgerDataset.source_summary).where(LedgerDataset.id == dataset_id)
    )
    source_summary = result.scalar_one_or_none()
    return {
        "active_dataset_id": str(dataset_id),
        "source_summary": source_summary or {},
    }


@router.get("/datasets/history")
async def get_datasets_history(
    project_id: UUID,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """F25 / Sprint 5.19: 账套导入历史时间轴。

    返回 `[{dataset, activation_records: [...]}]`，按 dataset.created_at DESC
    排序。每个 dataset 附带其相关的 activate/rollback 审计记录（含 ip/duration/
    before/after row counts）。

    Query 参数：
    - year（可选）：只返回该年度；不传则返回全部年度的完整时间轴
    """
    import sqlalchemy as sa

    from app.models.dataset_models import ActivationRecord, LedgerDataset

    dataset_filters = [LedgerDataset.project_id == project_id]
    if year is not None:
        dataset_filters.append(LedgerDataset.year == year)
    datasets = (
        await db.execute(
            sa.select(LedgerDataset)
            .where(*dataset_filters)
            .order_by(LedgerDataset.created_at.desc())
        )
    ).scalars().all()

    record_filters = [ActivationRecord.project_id == project_id]
    if year is not None:
        record_filters.append(ActivationRecord.year == year)
    records = (
        await db.execute(
            sa.select(ActivationRecord)
            .where(*record_filters)
            .order_by(ActivationRecord.performed_at.desc())
        )
    ).scalars().all()

    records_by_dataset: dict = {}
    for r in records:
        records_by_dataset.setdefault(r.dataset_id, []).append(
            {
                "id": str(r.id),
                "action": r.action.value,
                "previous_dataset_id": str(r.previous_dataset_id) if r.previous_dataset_id else None,
                "performed_by": str(r.performed_by) if r.performed_by else None,
                "performed_at": r.performed_at.isoformat() if r.performed_at else None,
                "reason": r.reason,
                "ip_address": r.ip_address,
                "duration_ms": r.duration_ms,
                "before_row_counts": r.before_row_counts,
                "after_row_counts": r.after_row_counts,
            }
        )

    return [
        {
            "dataset_id": str(d.id),
            "year": d.year,
            "status": d.status.value,
            "source_type": d.source_type,
            "source_summary": d.source_summary,
            "record_summary": d.record_summary,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "activated_at": d.activated_at.isoformat() if d.activated_at else None,
            "activated_by": str(d.activated_by) if d.activated_by else None,
            "created_by": str(d.created_by) if d.created_by else None,
            "previous_dataset_id": str(d.previous_dataset_id) if d.previous_dataset_id else None,
            "activation_records": records_by_dataset.get(d.id, []),
        }
        for d in datasets
    ]


@router.post("/datasets/{dataset_id}/rollback")
async def rollback_dataset(
    project_id: UUID,
    dataset_id: UUID,
    request: Request,
    year: int = 2025,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """回滚到上一版本数据集。

    F23: activate 与 rollback 共享同一项目锁；锁被占用时返回 409。
    F25: 写入 ActivationRecord.reason / ip_address / duration_ms / before_/after_row_counts。
    """
    # F25: 从请求里拿客户端 IP（X-Forwarded-For 优先，兼容反向代理）
    ip_address: str | None = None
    if request is not None:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            ip_address = xff.split(",")[0].strip()
        elif request.client is not None:
            ip_address = request.client.host
    try:
        result = await DatasetService.rollback(
            db, project_id, year,
            performed_by=current_user.id,
            reason=reason,
            ip_address=ip_address,
        )
    except ImportLockError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
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
    from app.models.core import User as UserModel
    jobs = await ImportJobService.list_jobs(db, project_id, year)
    # 批量查询用户名
    user_ids = {j.created_by for j in jobs if j.created_by}
    user_map: dict = {}
    if user_ids:
        import sqlalchemy as sa
        result = await db.execute(
            sa.select(UserModel.id, UserModel.username)
            .where(UserModel.id.in_(user_ids))
        )
        for row in result.fetchall():
            user_map[str(row[0])] = row[1] or str(row[0])[:8]
    return [
        {
            "id": str(j.id),
            "year": j.year,
            "status": j.status.value,
            "progress_pct": j.progress_pct,
            "progress_message": j.progress_message,
            "error_message": j.error_message,
            "retry_count": j.retry_count,
            "created_by_name": user_map.get(str(j.created_by), '—') if j.created_by else '—',
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
