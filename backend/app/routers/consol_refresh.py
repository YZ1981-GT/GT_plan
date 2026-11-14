"""合并一键刷新兼容路由；V240 起以持久 operation 为真源。"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import check_consol_lock, require_project_access
from app.models.core import User
from app.services.consol_operation_service import (
    OperationBoundaryError,
    OperationConflict,
    get_operation,
    legacy_refresh_payload,
    request_operation,
)
from app.services.consol_refresh_job_service import get_job

router = APIRouter(prefix="/api/consolidation", tags=["合并一键刷新"])


def _raise_request_error(exc: Exception) -> None:
    if isinstance(exc, OperationBoundaryError):
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    raise HTTPException(
        status_code=409 if isinstance(exc, OperationConflict) else 400,
        detail={"code": "OPERATION_CONFLICT", "message": str(exc)},
    ) from exc


@router.post("/{project_id}/{year}/refresh-all")
async def trigger_refresh_all(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """兼容入口：立即持久化 queued operation，后台数据库 worker 认领。"""
    try:
        requested = await request_operation(
            db,
            project_id=project_id,
            year=year,
            operation_type="refresh_all",
            idempotency_key=idempotency_key,
            trigger_source="manual",
            triggered_by=getattr(user, "id", None),
        )
        await db.commit()
    except (OperationBoundaryError, OperationConflict, ValueError) as exc:
        await db.rollback()
        _raise_request_error(exc)
    from app.core.worker_wakeup import wake_worker

    wake_worker("consol_operation_worker")
    operation = requested.operation
    return {
        "job_id": str(operation.id),
        "operation_id": str(operation.id),
        "project_id": str(operation.project_id),
        "year": operation.year,
        "status": operation.status,
        "revision": operation.revision,
        "disposition": requested.disposition,
    }


@router.get("/{project_id}/{year}/refresh-status/{job_id}")
async def get_refresh_status(
    project_id: UUID,
    year: int,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """先查持久 operation；保留旧进程内 job 作为迁移期只读兼容。"""
    try:
        operation_id = UUID(job_id)
    except ValueError:
        operation_id = None
    operation = (
        await get_operation(db, project_id, year, operation_id)
        if operation_id is not None
        else None
    )
    if operation is not None:
        return legacy_refresh_payload(operation)
    legacy = get_job(job_id)
    if legacy is None or legacy.project_id != str(project_id) or legacy.year != year:
        raise HTTPException(status_code=404, detail="刷新任务不存在或已过期")
    return legacy.to_dict()
