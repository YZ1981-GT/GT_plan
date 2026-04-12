"""科目映射 API 路由

Validates: Requirements 3.1-3.8
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import (
    MappingCompletionRate,
    MappingInput,
    MappingResponse,
    MappingResult,
    MappingSuggestion,
)
from app.models.core import User
from app.services import mapping_service

router = APIRouter(prefix="/api/projects", tags=["mapping"])


@router.post(
    "/{project_id}/mapping/auto-suggest",
    response_model=list[MappingSuggestion],
)
async def auto_suggest(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MappingSuggestion]:
    """自动匹配建议：编码前缀→名称精确→名称模糊。

    Validates: Requirements 3.1
    """
    return await mapping_service.auto_suggest(project_id, db)


@router.get(
    "/{project_id}/mapping",
    response_model=list[MappingResponse],
)
async def get_mappings(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MappingResponse]:
    """获取映射列表。

    Validates: Requirements 3.8
    """
    return await mapping_service.get_mappings(project_id, db)


@router.post(
    "/{project_id}/mapping",
    response_model=MappingResponse,
)
async def save_mapping(
    project_id: UUID,
    mapping: MappingInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MappingResponse:
    """保存单条映射。

    Validates: Requirements 3.3
    """
    record = await mapping_service.save_mapping(project_id, mapping, db)
    return MappingResponse.model_validate(record)


@router.put(
    "/{project_id}/mapping/{mapping_id}",
    response_model=MappingResponse,
)
async def update_mapping(
    project_id: UUID,
    mapping_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MappingResponse:
    """修改映射。

    Validates: Requirements 3.7
    """
    new_standard_code = body.get("standard_account_code")
    if not new_standard_code:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="缺少 standard_account_code")
    record = await mapping_service.update_mapping(
        project_id, mapping_id, new_standard_code, db
    )
    return MappingResponse.model_validate(record)


@router.post(
    "/{project_id}/mapping/batch-confirm",
    response_model=MappingResult,
)
async def batch_confirm(
    project_id: UUID,
    mappings: list[MappingInput],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MappingResult:
    """批量确认映射。

    Validates: Requirements 3.5
    """
    return await mapping_service.batch_confirm(project_id, mappings, db)


@router.get(
    "/{project_id}/mapping/completion-rate",
    response_model=MappingCompletionRate,
)
async def get_completion_rate(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MappingCompletionRate:
    """获取映射完成率。

    Validates: Requirements 3.5, 3.6
    """
    return await mapping_service.get_completion_rate(project_id, db)
