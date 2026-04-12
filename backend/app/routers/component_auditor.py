"""组成部分审计师路由"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from app.deps import get_current_user
from app.core.database import get_db
from app.models.consolidation_schemas import (
    ComponentAuditorCreate,
    ComponentAuditorUpdate,
    ComponentAuditorResponse,
    InstructionCreate,
    InstructionUpdate,
    ComponentInstructionResponse,
    ComponentResultCreate,
    ComponentResultUpdate,
    ComponentResultResponse,
    ComponentDashboard,
)
from app.services.component_auditor_service import ComponentAuditorService as Svc

router = APIRouter(prefix="/api/consolidation/component-auditor", tags=["组成部分审计师"])

# 异步 service 调用包装器
async def _svc(): return Svc()

async def create_auditor(db, project_id, data): return await Svc.create_auditor(await _svc(), db, project_id, data)
async def create_instruction(db, project_id, data): return await Svc.create_instruction(await _svc(), db, project_id, data)
async def create_result(db, project_id, data): return await Svc.create_result(await _svc(), db, project_id, data)
async def delete_auditor(db, auditor_id, project_id): return await Svc.delete_auditor(await _svc(), db, auditor_id, project_id)
async def delete_instruction(db, instruction_id, project_id): return await Svc.delete_instruction(await _svc(), db, instruction_id, project_id)
async def delete_result(db, result_id, project_id): return await Svc.delete_result(await _svc(), db, result_id, project_id)
async def get_auditor(db, auditor_id): return await Svc.get_auditor(await _svc(), db, auditor_id)
async def get_auditors(db, project_id): return await Svc.get_auditors_by_project(await _svc(), db, project_id)
async def get_dashboard(db, project_id): return await Svc.get_dashboard(await _svc(), db, project_id)
async def get_instruction(db, instruction_id): return await Svc.get_instruction(await _svc(), db, instruction_id)
async def get_instructions(db, project_id, auditor_id=None): return await Svc.get_instructions(await _svc(), db, project_id, auditor_id)
async def get_result(db, result_id): return await Svc.get_result(await _svc(), db, result_id)
async def get_results(db, project_id, auditor_id=None): return await Svc.get_results(await _svc(), db, project_id, auditor_id)
async def update_auditor(db, auditor_id, project_id, data): return await Svc.update_auditor(await _svc(), db, auditor_id, project_id, data)
async def update_instruction(db, instruction_id, project_id, data): return await Svc.update_instruction(await _svc(), db, instruction_id, project_id, data)
async def update_result(db, result_id, project_id, data): return await Svc.update_result(await _svc(), db, result_id, project_id, data)


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


@router.get("/auditors/{auditor_id}", response_model=ComponentAuditorResponse)
async def get_auditor_route(
    auditor_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    auditor = await get_auditor(db, auditor_id)
    if not auditor:
        raise HTTPException(status_code=404, detail="组成部分审计师不存在")
    return auditor


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
    return None


# --- 组成部分指令 ---
@router.get("/instructions", response_model=list[ComponentInstructionResponse])
async def list_instructions(
    project_id: UUID,
    auditor_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_instructions(db, project_id, auditor_id)


@router.post("/instructions", response_model=ComponentInstructionResponse, status_code=201)
async def create_instruction_route(
    project_id: UUID,
    data: InstructionCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await create_instruction(db, project_id, data)


@router.get("/instructions/{instruction_id}", response_model=ComponentInstructionResponse)
async def get_instruction_route(
    instruction_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    instruction = await get_instruction(db, instruction_id)
    if not instruction:
        raise HTTPException(status_code=404, detail="组成部分指令不存在")
    return instruction


@router.put("/instructions/{instruction_id}", response_model=ComponentInstructionResponse)
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
    return None


# --- 组成部分结果 ---
@router.get("/results", response_model=list[ComponentResultResponse])
async def list_results(
    project_id: UUID,
    auditor_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_results(db, project_id, auditor_id)


@router.post("/results", response_model=ComponentResultResponse, status_code=201)
async def create_result_route(
    project_id: UUID,
    data: ComponentResultCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await create_result(db, project_id, data)


@router.get("/results/{result_id}", response_model=ComponentResultResponse)
async def get_result_route(
    result_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    result = await get_result(db, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="组成部分结果不存在")
    return result


@router.put("/results/{result_id}", response_model=ComponentResultResponse)
async def update_result_route(
    result_id: UUID,
    project_id: UUID,
    data: ComponentResultUpdate,
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
    return None


# --- 看板 ---
@router.get("/dashboard", response_model=ComponentDashboard)
async def get_dashboard_route(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_dashboard(db, project_id)
