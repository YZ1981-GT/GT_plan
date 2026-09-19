"""模板 reconcile preview/apply API（Task 5）

Feature: procedure-delegation-notification
需求：1.6、3.1-3.2、3.8、4.2-4.6 / Design C3、D4、API section

端点：
- ``POST /api/projects/{pid}/procedure-row-tasks/reconcile/preview``：跑分类 + 创建一次性 preview。
- ``POST /api/projects/{pid}/procedure-row-tasks/reconcile/apply``：消费 preview，显式迁移 matched
  与 Delegator resolution 项；ambiguous/orphaned/conflict 零继承。

两端点均挂 **项目级 Delegator 守卫**（Task 7 `require_project_delegator_pid`，fail-closed 403）。
约定：service 只 flush；router 显式 commit。这些是显式 POST 写命令，非 GET/render 读路径。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.procedure_authorization import (
    DelegatorContext,
    require_project_delegator_pid,
)
from app.services.procedure_reconcile_service import ProcedureReconcileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["procedure-row-tasks"])


class ReconcileResolution(BaseModel):
    source_key: str
    target_key: str


class ReconcilePreviewRequest(BaseModel):
    template_code: str
    target_revision: str
    wp_index_ids: list[UUID] = Field(default_factory=list)
    resolutions: list[ReconcileResolution] = Field(default_factory=list)


class ReconcileApplyRequest(ReconcilePreviewRequest):
    preview_id: UUID
    request_id: str


@router.post("/{pid}/procedure-row-tasks/reconcile/preview")
async def reconcile_preview(
    pid: UUID,
    body: ReconcilePreviewRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """reconcile 预览：分类 + 一次性 preview 凭证。"""
    svc = ProcedureReconcileService(db)
    result = await svc.preview(
        pid,
        actor_user_id=user.id,
        template_code=body.template_code,
        target_revision=body.target_revision,
        wp_index_ids=body.wp_index_ids,
        resolutions=[r.model_dump() for r in body.resolutions],
    )
    await db.commit()
    return result


@router.post("/{pid}/procedure-row-tasks/reconcile/apply")
async def reconcile_apply(
    pid: UUID,
    body: ReconcileApplyRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """reconcile 应用：消费 preview，显式迁移 matched + resolution 项。"""
    svc = ProcedureReconcileService(db)
    try:
        result = await svc.apply(
            pid,
            actor_user_id=user.id,
            preview_id=body.preview_id,
            request_id=body.request_id,
            template_code=body.template_code,
            target_revision=body.target_revision,
            wp_index_ids=body.wp_index_ids,
            resolutions=[r.model_dump() for r in body.resolutions],
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result
