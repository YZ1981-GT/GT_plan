"""合并推送兼容路由；V240 起请求进入持久 operation。"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import check_consol_lock, require_project_access
from app.models.core import Project, User
from app.services.consol_operation_service import (
    OperationBoundaryError,
    OperationConflict,
    request_operation,
)
from app.services.consol_push_service import (
    TRIGGER_FORMULA,
    TRIGGER_MANUAL,
    list_runs,
    push_status,
)

router = APIRouter(prefix="/api/consolidation", tags=["合并推送"])


class PushRequest(BaseModel):
    trigger: str = TRIGGER_MANUAL
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


async def _require_consolidated(db: AsyncSession, project_id: UUID) -> None:
    scope = (await db.execute(
        sa.select(Project.report_scope).where(Project.id == project_id, Project.is_deleted == sa.false())
    )).first()
    if scope is None:
        raise HTTPException(status_code=404, detail="项目不存在或已删除")
    if (scope[0] or "").strip().lower() != "consolidated":
        raise HTTPException(status_code=400, detail="只有合并报表项目可以推送合并数据")


def _operation_error(exc: Exception) -> HTTPException:
    if isinstance(exc, OperationBoundaryError):
        return HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(
        status_code=409 if isinstance(exc, OperationConflict) else 400,
        detail={"code": "OPERATION_CONFLICT", "message": str(exc)},
    )


@router.post("/{project_id}/{year}/push")
async def trigger_push(
    project_id: UUID,
    year: int,
    body: PushRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    trigger = (body.trigger if body else TRIGGER_MANUAL) or TRIGGER_MANUAL
    if trigger not in (TRIGGER_MANUAL, TRIGGER_FORMULA):
        raise HTTPException(status_code=400, detail="手动推送的触发来源只能是 manual 或 formula_changed")
    try:
        requested = await request_operation(
            db,
            project_id=project_id,
            year=year,
            operation_type="push",
            idempotency_key=body.idempotency_key if body else None,
            trigger_source=trigger,
            triggered_by=getattr(user, "id", None),
        )
        await db.commit()
    except (OperationBoundaryError, OperationConflict, ValueError) as exc:
        await db.rollback()
        raise _operation_error(exc) from exc
    from app.workers.consol_operation_worker import wake

    wake()
    operation = requested.operation
    newly_queued = requested.disposition == "created"
    return {
        "queued": newly_queued,
        "message": "已开始推送，完成后自动刷新" if newly_queued else "已有推送在排队，本次请求已并入",
        "project_id": str(project_id),
        "year": year,
        "operation_id": str(operation.id),
        "status": operation.status,
        "revision": operation.revision,
    }


@router.get("/{project_id}/{year}/push-runs")
async def get_push_runs(
    project_id: UUID,
    year: int,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    return {"runs": await list_runs(db, project_id, year, limit=limit)}


@router.get("/{project_id}/{year}/push-status")
async def get_push_status(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    return await push_status(db, project_id, year)
