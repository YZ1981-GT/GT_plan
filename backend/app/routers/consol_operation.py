"""持久合并 operation 创建、状态、列表与取消 API。"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import check_consol_lock, require_project_access
from app.models.core import User
from app.schemas.consol_operation import ConsolOperationCreate
from app.services.consol_operation_service import (
    OperationBoundaryError,
    OperationConflict,
    cancel_operation,
    get_operation,
    list_operations,
    operation_payload,
    request_operation,
    validate_project_boundary,
)

router = APIRouter(prefix="/api/consolidation", tags=["合并运行"])


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, OperationBoundaryError):
        return HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        )
    if isinstance(error, OperationConflict):
        return HTTPException(
            status_code=409,
            detail={"code": "OPERATION_CONFLICT", "message": str(error)},
        )
    return HTTPException(
        status_code=400,
        detail={"code": "INVALID_OPERATION_REQUEST", "message": str(error)},
    )


@router.post("/{project_id}/{year}/operations")
async def create_operation(
    project_id: UUID,
    year: int,
    body: ConsolOperationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
    idempotency_header: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if body.idempotency_key and idempotency_header and body.idempotency_key != idempotency_header:
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEMPOTENCY_KEY_MISMATCH", "message": "请求体与请求头的幂等键不一致"},
        )
    try:
        result = await request_operation(
            db,
            project_id=project_id,
            year=year,
            operation_type=body.operation_type,
            idempotency_key=body.idempotency_key or idempotency_header,
            trigger_source=body.trigger_source,
            triggered_by=getattr(user, "id", None),
            requested_actions=body.requested_actions,
        )
        await db.commit()
    except (OperationBoundaryError, OperationConflict, ValueError) as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    from app.workers.consol_operation_worker import wake

    wake()
    return {**operation_payload(result.operation), "disposition": result.disposition}


@router.get("/{project_id}/{year}/operations")
async def get_operations(
    project_id: UUID,
    year: int,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    try:
        await validate_project_boundary(db, project_id, year, writable=False)
    except OperationBoundaryError as exc:
        raise _http_error(exc) from exc
    rows = await list_operations(db, project_id, year, limit=limit)
    return {"operations": [operation_payload(row) for row in rows]}


@router.get("/{project_id}/{year}/operations/{operation_id}")
async def get_operation_status(
    project_id: UUID,
    year: int,
    operation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    try:
        await validate_project_boundary(db, project_id, year, writable=False)
    except OperationBoundaryError as exc:
        raise _http_error(exc) from exc
    operation = await get_operation(db, project_id, year, operation_id)
    if operation is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "OPERATION_NOT_FOUND", "message": "合并运行不存在"},
        )
    return operation_payload(operation)


@router.post("/{project_id}/{year}/operations/{operation_id}/cancel")
async def cancel_operation_route(
    project_id: UUID,
    year: int,
    operation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    try:
        await validate_project_boundary(db, project_id, year, writable=True)
        operation = await cancel_operation(db, project_id, year, operation_id)
        if operation is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "OPERATION_NOT_FOUND", "message": "合并运行不存在"},
            )
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except (OperationBoundaryError, OperationConflict, ValueError) as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    return operation_payload(operation)


__all__ = ["router"]
