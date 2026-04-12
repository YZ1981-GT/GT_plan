"""合并范围路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import db, get_current_user
from app.models.consolidation_schemas import (
    ConsolScopeBatchUpdate,
    ConsolScopeCreate,
    ConsolScopeResponse,
    ConsolScopeUpdate,
    ConsolScopeSummary,
)
from app.services.consol_scope_service import (
    batch_update_scope,
    create_scope_item,
    delete_scope_item,
    get_scope_item,
    get_scope_list,
    get_scope_summary,
    update_scope_item,
)

router = APIRouter(prefix="/api/consolidation/scope", tags=["合并范围"])


@router.get("", response_model=list[ConsolScopeResponse])
def list_scope(
    project_id: UUID,
    year: int,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    return get_scope_list(db, project_id, year)


@router.post("", response_model=ConsolScopeResponse, status_code=201)
def create_scope(
    project_id: UUID,
    data: ConsolScopeCreate,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    try:
        return create_scope_item(db, project_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{scope_id}", response_model=ConsolScopeResponse)
def update_scope(
    scope_id: UUID,
    project_id: UUID,
    data: ConsolScopeUpdate,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    scope = update_scope_item(db, scope_id, project_id, data)
    if not scope:
        raise HTTPException(status_code=404, detail="合并范围项不存在")
    return scope


@router.delete("/{scope_id}", status_code=204)
def delete_scope(
    scope_id: UUID,
    project_id: UUID,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    if not delete_scope_item(db, scope_id, project_id):
        raise HTTPException(status_code=404, detail="合并范围项不存在")


@router.post("/batch", response_model=list[ConsolScopeResponse])
def batch_update(
    project_id: UUID,
    data: ConsolScopeBatchUpdate,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    return batch_update_scope(db, project_id, data)


@router.get("/summary", response_model=ConsolScopeSummary)
def scope_summary(
    project_id: UUID,
    year: int,
    db: Session = Depends(db),
    user=Depends(get_current_user),
):
    return get_scope_summary(db, project_id, year)
