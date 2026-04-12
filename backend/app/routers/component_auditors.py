"""组成部分审计师路由

提供组成部分审计师、审计指令和审计结果的 RESTful API。
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.core import User
from app.models.consolidation_models import (
    ComponentAuditor,
    ComponentInstruction,
    ComponentResult,
)
from app.models.consolidation_schemas import (
    ComponentAuditorCreate,
    ComponentAuditorUpdate,
    ComponentAuditorResponse,
    ComponentInstructionResponse,
    ComponentResultCreate,
    ComponentResultResponse,
    InstructionCreate,
    InstructionSend,
    InstructionUpdate,
    InstructionStatus,
)
from app.services.component_auditor_service import ComponentAuditorService

router = APIRouter(
    prefix="/api/projects/{project_id}/component-auditors",
    tags=["组成部分审计师"],
)


def get_service(db: Session = Depends(get_db)) -> ComponentAuditorService:
    """获取服务实例"""
    return ComponentAuditorService(db)


# =============================================================================
# 组成部分审计师端点
# =============================================================================

@router.get("", response_model=list[ComponentAuditorResponse])
def list_auditors(
    project_id: UUID,
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> list[ComponentAuditor]:
    """列出项目下所有组成部分审计师"""
    return service.get_auditors_by_project(project_id)


@router.post(
    "",
    response_model=ComponentAuditorResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_auditor(
    project_id: UUID,
    data: ComponentAuditorCreate,
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> ComponentAuditor:
    """创建组成部分审计师

    competence_rating 和 rating_basis 为必填字段。
    """
    try:
        return service.create_auditor(project_id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{auditor_id}", response_model=ComponentAuditorResponse)
def get_auditor(
    project_id: UUID,
    auditor_id: UUID,
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> ComponentAuditor:
    """获取单个组成部分审计师详情"""
    auditor = service.get_auditor(auditor_id)
    if not auditor or str(auditor.project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="组成部分审计师不存在",
        )
    return auditor


@router.put("/{auditor_id}", response_model=ComponentAuditorResponse)
def update_auditor(
    project_id: UUID,
    auditor_id: UUID,
    data: ComponentAuditorUpdate,
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> ComponentAuditor:
    """更新组成部分审计师信息

    如果评分发生变化，系统会记录变更日志。
    """
    # 验证审计师存在
    existing = service.get_auditor(auditor_id)
    if not existing or str(existing.project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="组成部分审计师不存在",
        )

    try:
        return service.update_auditor(auditor_id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/dashboard")
def get_dashboard(
    project_id: UUID,
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """获取仪表盘统计数据

    返回:
    - total_auditors: 审计师总数
    - instructions_by_status: 各状态指令数量
    - results_by_status: 各状态结果数量
    - pending_review: 待复核数量
    """
    return service.get_dashboard(project_id)


# =============================================================================
# 审计指令端点
# =============================================================================

instruction_router = APIRouter(
    prefix="/api/projects/{project_id}/instructions",
    tags=["审计指令"],
)


@instruction_router.get("", response_model=list[ComponentInstructionResponse])
def list_instructions(
    project_id: UUID,
    auditor_id: UUID | None = Query(None, description="按审计师ID过滤"),
    status: InstructionStatus | None = Query(None, description="按状态过滤"),
    year: int | None = Query(None, description="按年份过滤"),
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> list[ComponentInstruction]:
    """列出审计指令（支持过滤）"""
    filters: dict[str, Any] = {}
    if auditor_id:
        filters["auditor_id"] = auditor_id
    if status:
        filters["status"] = status
    if year:
        filters["year"] = year
    return service.get_instructions(project_id, filters)


@instruction_router.post(
    "",
    response_model=ComponentInstructionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_instruction(
    project_id: UUID,
    data: InstructionCreate,
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> ComponentInstruction:
    """创建审计指令

    指令创建后状态为 draft，可修改。
    """
    try:
        return service.create_instruction(project_id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@instruction_router.put(
    "/{instruction_id}",
    response_model=ComponentInstructionResponse,
)
def update_instruction(
    project_id: UUID,
    instruction_id: UUID,
    data: InstructionUpdate,
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> ComponentInstruction:
    """更新审计指令

    仅在指令状态为 draft 时允许更新。
    """
    instruction = service.get_instruction(instruction_id)
    if not instruction or str(instruction.project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计指令不存在",
        )

    try:
        return service.update_instruction(instruction_id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@instruction_router.post("/{instruction_id}/send", response_model=ComponentInstructionResponse)
def send_instruction(
    project_id: UUID,
    instruction_id: UUID,
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> ComponentInstruction:
    """发送审计指令

    发送后指令内容被锁定，状态变为 sent。
    """
    instruction = service.get_instruction(instruction_id)
    if not instruction or str(instruction.project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计指令不存在",
        )

    try:
        return service.send_instruction(instruction_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# 审计结果端点
# =============================================================================

result_router = APIRouter(
    prefix="/api/projects/{project_id}/results",
    tags=["审计结果"],
)


@result_router.get("", response_model=list[ComponentResultResponse])
def list_results(
    project_id: UUID,
    auditor_id: UUID | None = Query(None, description="按审计师ID过滤"),
    status: str | None = Query(None, description="按状态过滤"),
    year: int | None = Query(None, description="按年份过滤"),
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> list[ComponentResult]:
    """列出审计结果（支持过滤）"""
    filters: dict[str, Any] = {}
    if auditor_id:
        filters["auditor_id"] = auditor_id
    if status:
        filters["status"] = status
    if year:
        filters["year"] = year
    return service.get_results(project_id, filters)


@result_router.post(
    "",
    response_model=ComponentResultResponse,
    status_code=status.HTTP_201_CREATED,
)
def receive_result(
    project_id: UUID,
    data: ComponentResultCreate,
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> ComponentResult:
    """接收组成部分审计结果

    非标准意见（qualified/adverse/disclaimer）必须提供评价说明。
    """
    try:
        return service.receive_result(project_id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@result_router.put("/{result_id}/accept", response_model=ComponentResultResponse)
def accept_result(
    project_id: UUID,
    result_id: UUID,
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> ComponentResult:
    """接受审计结果

    接受后，该组成部分的调整金额可用于合并。
    仅在结果状态为 pending 时允许接受。
    """
    result = service.get_result(result_id)
    if not result or str(result.project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计结果不存在",
        )

    try:
        return service.accept_result(result_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@result_router.put("/{result_id}/reject", response_model=ComponentResultResponse)
def reject_result(
    project_id: UUID,
    result_id: UUID,
    reason: str = Query(..., description="拒绝原因"),
    service: ComponentAuditorService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> ComponentResult:
    """拒绝审计结果

    拒绝原因将被记录到审计结果中。
    """
    result = service.get_result(result_id)
    if not result or str(result.project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计结果不存在",
        )

    try:
        return service.reject_result(result_id, reason)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
