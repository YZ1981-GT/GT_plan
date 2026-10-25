"""D5 用户确认合并范围端点。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.consol_scope_confirmation_service import (
    ScopeConfirmationError,
    confirm_scope,
    preview_scope_confirmation,
)

router = APIRouter(prefix="/api/consolidation", tags=["合并范围确认"])


class ConfirmScopeRequest(BaseModel):
    expected_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_revision: int = Field(ge=0)


@router.get("/{project_id}/scope-confirmation/preview")
async def get_scope_confirmation_preview(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
):
    try:
        return await preview_scope_confirmation(db, project_id)
    except ScopeConfirmationError as exc:
        raise HTTPException(status_code=exc.status_code, detail={
            "error_code": exc.error_code,
            "message": exc.message,
        }) from exc


@router.post("/{project_id}/scope-confirmation/confirm")
async def post_scope_confirmation(
    project_id: UUID,
    body: ConfirmScopeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    try:
        result = await confirm_scope(
            db,
            project_id,
            confirmed_by=user.id,
            expected_fingerprint=body.expected_fingerprint,
            expected_revision=body.expected_revision,
        )
        await db.commit()
        return result
    except ScopeConfirmationError as exc:
        await db.rollback()
        detail = {"error_code": exc.error_code, "message": exc.message}
        if exc.latest_preview is not None:
            detail["latest_preview"] = exc.latest_preview
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc
