"""项目初始化向导 API 路由

Validates: Requirements 1.1-1.8
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import (
    BasicInfoSchema,
    ProjectCreateResponse,
    ValidationResult,
    WizardState,
    WizardStep,
)
from app.models.core import User
from app.services import project_wizard_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectCreateResponse)
async def create_project(
    data: BasicInfoSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectCreateResponse:
    """创建审计项目（向导步骤1-基本信息）。

    Validates: Requirements 1.2, 1.3
    """
    project = await project_wizard_service.create_project(data, db)
    return ProjectCreateResponse(
        id=project.id,
        client_name=project.client_name,
        audit_year=data.audit_year,
        project_type=project.project_type.value if project.project_type else None,
        status=project.status.value,
        created_at=project.created_at,
    )


@router.get("/{project_id}/wizard", response_model=WizardState)
async def get_wizard_state(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WizardState:
    """获取向导当前状态（支持断点续做）。

    Validates: Requirements 1.4, 1.5
    """
    return await project_wizard_service.get_wizard_state(project_id, db)


@router.put("/{project_id}/wizard/{step}", response_model=WizardState)
async def update_step(
    project_id: UUID,
    step: WizardStep,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WizardState:
    """更新指定步骤数据并持久化。

    Validates: Requirements 1.3, 1.4, 1.5
    """
    return await project_wizard_service.update_step(project_id, step, data, db)


@router.post(
    "/{project_id}/wizard/validate/{step}",
    response_model=ValidationResult,
)
async def validate_step(
    project_id: UUID,
    step: WizardStep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidationResult:
    """校验指定步骤是否满足前进条件。

    Validates: Requirements 1.8
    """
    return await project_wizard_service.validate_step(project_id, step, db)


@router.post("/{project_id}/wizard/confirm", response_model=ProjectCreateResponse)
async def confirm_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectCreateResponse:
    """确认创建项目，状态 created → planning。

    Validates: Requirements 1.7
    """
    project = await project_wizard_service.confirm_project(project_id, db)
    # 从 wizard_state 提取 audit_year
    state = await project_wizard_service.get_wizard_state(project_id, db)
    audit_year = None
    basic_info = state.steps.get(WizardStep.basic_info.value)
    if basic_info and basic_info.data:
        audit_year = basic_info.data.get("audit_year")
    return ProjectCreateResponse(
        id=project.id,
        client_name=project.client_name,
        audit_year=audit_year,
        project_type=project.project_type.value if project.project_type else None,
        status=project.status.value,
        created_at=project.created_at,
    )
