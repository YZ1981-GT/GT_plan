"""审计程序裁剪与委派 API 路由

Phase 9 Task 9.12
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.procedure_service import ProcedureService

router = APIRouter(prefix="/api/projects", tags=["procedures"])


class TrimItem(BaseModel):
    id: str
    status: str  # execute / skip / not_applicable
    skip_reason: str | None = None


class TrimRequest(BaseModel):
    items: list[TrimItem]


class CustomProcedureRequest(BaseModel):
    procedure_name: str
    procedure_code: str | None = None
    sort_order: int | None = None


class AssignRequest(BaseModel):
    assignments: list[dict]  # [{procedure_id, staff_id}]


class BatchApplyRequest(BaseModel):
    target_project_ids: list[str]


@router.get("/{project_id}/procedures/{cycle}")
async def get_procedures(
    project_id: UUID, cycle: str,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    svc = ProcedureService(db)
    return await svc.get_procedures(project_id, cycle)


@router.post("/{project_id}/procedures/{cycle}/init")
async def init_procedures(
    project_id: UUID, cycle: str,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    svc = ProcedureService(db)
    result = await svc.init_from_templates(project_id, cycle)
    await db.commit()
    return {"count": len(result), "procedures": result}


@router.put("/{project_id}/procedures/{cycle}/trim")
async def save_trim(
    project_id: UUID, cycle: str, data: TrimRequest,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    svc = ProcedureService(db)
    count = await svc.save_trim(project_id, cycle, [i.model_dump() for i in data.items])
    await db.commit()
    return {"updated": count}


@router.post("/{project_id}/procedures/{cycle}/custom")
async def add_custom(
    project_id: UUID, cycle: str, data: CustomProcedureRequest,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    svc = ProcedureService(db)
    result = await svc.add_custom(project_id, cycle, data.model_dump())
    await db.commit()
    return result


@router.put("/{project_id}/procedures/assign")
async def assign_procedures(
    project_id: UUID, data: AssignRequest,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    svc = ProcedureService(db)
    count = await svc.assign_procedures(project_id, data.assignments)
    await db.commit()
    return {"assigned": count}


@router.get("/{project_id}/procedures/{cycle}/trim-scheme")
async def get_trim_scheme(
    project_id: UUID, cycle: str,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    svc = ProcedureService(db)
    return await svc.get_trim_scheme(project_id, cycle) or {}


@router.post("/{project_id}/procedures/{cycle}/apply-scheme")
async def apply_scheme(
    project_id: UUID, cycle: str,
    source_project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    svc = ProcedureService(db)
    count = await svc.apply_scheme(project_id, cycle, source_project_id)
    await db.commit()
    return {"applied": count}


@router.post("/{project_id}/procedures/{cycle}/batch-apply")
async def batch_apply(
    project_id: UUID, cycle: str, data: BatchApplyRequest,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    svc = ProcedureService(db)
    result = await svc.batch_apply(project_id, cycle, [UUID(t) for t in data.target_project_ids])
    await db.commit()
    return result


class ExecutionStatusUpdate(BaseModel):
    execution_status: str  # not_started / in_progress / completed


@router.put("/{project_id}/procedures/instance/{procedure_id}/execution")
async def update_execution_status(
    project_id: UUID,
    procedure_id: UUID,
    data: ExecutionStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """更新程序执行状态（审计助理标记进度）"""
    from app.models.procedure_models import ProcedureInstance
    import sqlalchemy as sa

    result = await db.execute(
        sa.select(ProcedureInstance).where(
            ProcedureInstance.id == procedure_id,
            ProcedureInstance.project_id == project_id,
        )
    )
    proc = result.scalar_one_or_none()
    if not proc:
        from fastapi import HTTPException
        raise HTTPException(404, "程序不存在")

    proc.execution_status = data.execution_status
    await db.flush()
    await db.commit()
    return {"id": str(proc.id), "execution_status": proc.execution_status}
