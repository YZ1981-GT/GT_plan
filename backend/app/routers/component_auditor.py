"""组成部分审计师路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user
from app.core.database import get_db
from app.models.consolidation_schemas import (
    ComponentAuditorCreate,
    ComponentAuditorUpdate,
    ComponentAuditorResponse,
    InstructionCreate,
    InstructionUpdate,
    InstructionResponse,
    ResultCreate,
    ResultUpdate,
    ResultResponse,
    ComponentDashboard,
)
from app.services.component_auditor_service import (
    create_auditor,
    create_instruction,
    create_result,
    delete_auditor,
    delete_instruction,
    delete_result,
    get_auditor,
    get_auditors,
    get_dashboard,
    get_instruction,
    get_instructions,
    get_result,
    get_results,
    update_auditor,
    update_instruction,
    update_result,
)

router = APIRouter(prefix="/api/consolidation/component-auditor", tags=["组成部分审计师"])


# --- 组成部分审计师 ---
@router.get("/auditors", response_model=list[ComponentAuditorResponse])
async def list_auditors(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_auditors(db, project_id)


@router.post("/auditors", response_model=ComponentAuditorResponse, status_code=201)
async def create_auditor_route(
    project_id: UUID,
    data: ComponentAuditorCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await create_auditor(db, project_id, data)


@router.put("/auditors/{auditor_id}", response_model=ComponentAuditorResponse)
async def update_auditor_route(
    auditor_id: UUID,
    project_id: UUID,
    data: ComponentAuditorUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    auditor = await update_auditor(db, auditor_id, project_id, data)
    if not auditor:
        raise HTTPException(status_code=404, detail="组成部分审计师不存在")
    return auditor


@router.delete("/auditors/{auditor_id}", status_code=204)
async def delete_auditor_route(
    auditor_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not await delete_auditor(db, auditor_id, project_id):
        raise HTTPException(status_code=404, detail="组成部分审计师不存在")


# --- 组成部分指令 ---
@router.get("/instructions", response_model=list[InstructionResponse])
async def list_instructions(
    project_id: UUID,
    auditor_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_instructions(db, project_id, auditor_id)


@router.post("/instructions", response_model=InstructionResponse, status_code=201)
async def create_instruction_route(
    project_id: UUID,
    data: InstructionCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await create_instruction(db, project_id, data)


@router.put("/instructions/{instruction_id}", response_model=InstructionResponse)
async def update_instruction_route(
    instruction_id: UUID,
    project_id: UUID,
    data: InstructionUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    instruction = await update_instruction(db, instruction_id, project_id, data)
    if not instruction:
        raise HTTPException(status_code=404, detail="组成部分指令不存在")
    return instruction


@router.delete("/instructions/{instruction_id}", status_code=204)
async def delete_instruction_route(
    instruction_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not await delete_instruction(db, instruction_id, project_id):
        raise HTTPException(status_code=404, detail="组成部分指令不存在")


# --- 组成部分结果 ---
@router.get("/results", response_model=list[ResultResponse])
async def list_results(
    project_id: UUID,
    auditor_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_results(db, project_id, auditor_id)


@router.post("/results", response_model=ResultResponse, status_code=201)
async def create_result_route(
    project_id: UUID,
    data: ResultCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await create_result(db, project_id, data)


@router.put("/results/{result_id}", response_model=ResultResponse)
async def update_result_route(
    result_id: UUID,
    project_id: UUID,
    data: ResultUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    result = await update_result(db, result_id, project_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="组成部分结果不存在")
    return result


@router.delete("/results/{result_id}", status_code=204)
async def delete_result_route(
    result_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not await delete_result(db, result_id, project_id):
        raise HTTPException(status_code=404, detail="组成部分结果不存在")


# --- 看板 ---
@router.get("/dashboard", response_model=ComponentDashboard)
async def get_dashboard_route(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_dashboard(db, project_id)
