"""项目当前审计阶段与预审截止日的读写（spec voucher-identity-writeback-and-audit-phase 任务 8，需求 6.1 / 6.5）。

- ``GET /api/projects/{project_id}/audit-phase``：项目成员可读；``can_edit`` 告诉前端当前用户能不能改。
- ``PUT /api/projects/{project_id}/audit-phase``：项目 edit 级（含归档只读守卫）+ 项目经理 / 合伙人（含签字
  合伙人）/ admin（与程序行委派人同一判定 ensure_project_delegator）；只收 preliminary / final（其他 422）；
  预审截止日须在审计期间内且早于期末；改动写 app_audit_log。

平台没有通用的「项目更新」接口（项目字段由向导分步保存或专用端点改），阶段单独一条，权限比 edit 更严。
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, require_project_access
from app.models.core import User
from app.services.procedure_authorization import ensure_project_delegator
from app.services.project_audit_phase import load_project_audit_phase, update_project_audit_phase

router = APIRouter(prefix="/api/projects", tags=["projects"])


class AuditPhaseUpdate(BaseModel):
    current_audit_phase: Literal["preliminary", "final"]
    interim_cutoff_date: date | None = None


async def _can_edit(db: AsyncSession, user: User, project_id: UUID) -> bool:
    try:
        await assert_project_permission(db, user, project_id, "edit")
        await ensure_project_delegator(db, user, project_id)
    except HTTPException:
        return False
    return True


@router.get("/{project_id}/audit-phase")
async def get_audit_phase(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> dict:
    state = await load_project_audit_phase(db, project_id)
    return {**state.to_dict(), "can_edit": await _can_edit(db, current_user, project_id)}


@router.put("/{project_id}/audit-phase")
async def put_audit_phase(
    project_id: UUID,
    body: AuditPhaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
) -> dict:
    await ensure_project_delegator(db, current_user, project_id)
    changed = await update_project_audit_phase(
        db, project_id, phase=body.current_audit_phase, interim_cutoff_date=body.interim_cutoff_date,
        actor_id=current_user.id,
    )
    await db.commit()
    state = await load_project_audit_phase(db, project_id)
    return {**state.to_dict(), "can_edit": True, "changed": changed}
