"""底稿主编（Workpaper Lead）语义 API

Feature: procedure-mainline-convergence / 需求 5、设计 §2

粗裁层的"底稿主编"= ``WorkingPaper.assigned_to``（user_id，权威），
``ProcedureInstance.assigned_to``（staff_id）只是投影。旧
``PUT /api/projects/{pid}/procedures/assign`` 名字与语义都指向"委派程序"，
容易与程序行执行人（``ProcedureRowTask.assignee_staff_id``）混淆，故本路由提供
语义明确的入口：

- ``PUT /api/projects/{pid}/workpaper-leads``：批量设置/清除底稿主编。

原子性与副作用完全复用 ``ProcedureService.assign_procedures``
→ ``DelegationTransactionService.delegate_lead``（同事务写权威 + 投影 +
统一委派历史 + policy epoch + invalidation outbox）。任一 assignment 校验失败
抛 ``DelegationError`` → 本路由回滚整批（不 commit），返回 400。

授权：项目级 Delegator 守卫（fail-closed 403）。
约定：service 只 flush；router 显式 commit。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.procedure_authorization import (
    DelegatorContext,
    require_project_delegator_pid,
)
from app.services.procedure_service import ProcedureService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["workpaper-leads"])


class WorkpaperLeadAssignment(BaseModel):
    """单条底稿主编设置。``staff_id=None`` 表示清除主编。"""

    procedure_id: UUID
    staff_id: UUID | None = None
    request_id: str | None = Field(default=None, max_length=64)


class WorkpaperLeadRequest(BaseModel):
    assignments: list[WorkpaperLeadAssignment] = Field(min_length=1)


@router.put("/{pid}/workpaper-leads")
async def set_workpaper_leads(
    pid: UUID,
    body: WorkpaperLeadRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """批量设置底稿主编（``WorkingPaper.assigned_to`` 权威 + 投影 + 历史 + epoch + outbox）。"""
    from app.services.wp_visibility.delegation_transaction import DelegationError

    svc = ProcedureService(db)
    try:
        updated = await svc.assign_procedures(
            pid,
            [a.model_dump() for a in body.assignments],
            actor_user_id=getattr(user, "id", None),
        )
    except DelegationError as exc:
        # fail-closed：整批回滚，不留半成品委派
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail={"error": "lead_delegation_rejected", "reason": exc.reason.value},
        ) from exc
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return {"updated": updated}
