"""合并范围路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import require_project_access
from app.core.database import get_db
from app.models.core import User
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
async def list_scope(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    return await get_scope_list(db, project_id, year)


@router.post("", response_model=ConsolScopeResponse, status_code=201)
async def create_scope(
    project_id: UUID,
    data: ConsolScopeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    try:
        result = await create_scope_item(db, project_id, data)
        from app.services.consol_audit_helper import log_consol_action
        await log_consol_action(
            db,
            user_id=user.id,
            project_id=project_id,
            action="consol.scope.change",
            resource_type="consol_scope",
            resource_id=str(result.id) if hasattr(result, 'id') else None,
            before=None,
            after={"action": "create", "company_code": data.company_code if hasattr(data, 'company_code') else None},
        )
        await db.flush()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{scope_id}", response_model=ConsolScopeResponse)
async def update_scope(
    scope_id: UUID,
    project_id: UUID,
    data: ConsolScopeUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    scope = await update_scope_item(db, scope_id, project_id, data)
    if not scope:
        raise HTTPException(status_code=404, detail="合并范围项不存在")
    from app.services.consol_audit_helper import log_consol_action
    await log_consol_action(
        db,
        user_id=user.id,
        project_id=project_id,
        action="consol.scope.change",
        resource_type="consol_scope",
        resource_id=str(scope_id),
        before=None,
        after={"action": "update", "scope_id": str(scope_id)},
    )
    await db.flush()
    return scope


@router.delete("/{scope_id}", status_code=204)
async def delete_scope(
    scope_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    if not await delete_scope_item(db, scope_id, project_id):
        raise HTTPException(status_code=404, detail="合并范围项不存在")
    from app.services.consol_audit_helper import log_consol_action
    await log_consol_action(
        db,
        user_id=user.id,
        project_id=project_id,
        action="consol.scope.change",
        resource_type="consol_scope",
        resource_id=str(scope_id),
        before={"scope_id": str(scope_id)},
        after={"action": "delete"},
    )
    await db.flush()


@router.post("/batch", response_model=list[ConsolScopeResponse])
async def batch_update(
    project_id: UUID,
    data: ConsolScopeBatchUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    result = await batch_update_scope(db, project_id, data)
    from app.services.consol_audit_helper import log_consol_action
    await log_consol_action(
        db,
        user_id=user.id,
        project_id=project_id,
        action="consol.scope.change",
        resource_type="consol_scope",
        resource_id=str(project_id),
        before=None,
        after={"action": "batch_update", "count": len(result)},
    )
    await db.flush()
    return result


@router.get("/summary", response_model=ConsolScopeSummary)
async def scope_summary(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    return await get_scope_summary(db, project_id, year)
