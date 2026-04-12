"""合并范围管理路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.consolidation_schemas import (
    ConsolScopeCreate,
    ConsolScopeResponse,
)
from app.services.group_structure_service import GroupStructureService

router = APIRouter(prefix="/api/projects/{project_id}/consol-scope", tags=["合并范围"])


def get_service(db: Session = Depends(get_db)) -> GroupStructureService:
    return GroupStructureService(db)


@router.get("/{year}", response_model=list[ConsolScopeResponse])
def get_consol_scope(
    project_id: UUID,
    year: int,
    service: GroupStructureService = Depends(get_service),
) -> list:
    """获取指定年度合并范围"""
    return service.get_consol_scope(project_id, year)


@router.put("/{year}", response_model=list[ConsolScopeResponse])
def update_consol_scope(
    project_id: UUID,
    year: int,
    scope_items: list[ConsolScopeCreate],
    service: GroupStructureService = Depends(get_service),
) -> list:
    """批量更新合并范围"""
    try:
        results = service.manage_consol_scope(project_id, year, scope_items)
        return [ConsolScopeResponse.model_validate(r) for r in results]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
