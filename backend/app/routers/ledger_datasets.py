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
from app.deps import get_current_user
from app.models.core import User
from app.services.dataset_service import DatasetService
from app.services.import_job_service import ImportJobService

router = APIRouter(prefix="/api/projects/{project_id}/ledger-import", tags=["数据集版本"])


@router.get("/datasets")
async def list_datasets(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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


@router.get("/jobs/{job_id}")
async def get_import_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
        "progress_message": job.progress_message,
        "error_message": job.error_message,
        "result_summary": job.result_summary,
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
    current_user: User = Depends(get_current_user),
):
    """重试失败的导入作业"""
    try:
        job = await ImportJobService.retry(db, job_id)
        await db.commit()
        return {"message": f"作业已重新排队（第 {job.retry_count} 次重试）", "job_id": str(job.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{job_id}/cancel")
async def cancel_import_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取消导入作业"""
    try:
        job = await ImportJobService.cancel(db, job_id)
        await db.commit()
        return {"message": "作业已取消", "job_id": str(job.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
