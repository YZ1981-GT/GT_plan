"""三粒度程序行委派 preview/apply API（Task 8）

Feature: procedure-delegation-notification
需求：4.1-4.10、6.4、10.7 / Design C6、D4、D8、API section

端点（均挂 **项目级 Delegator 守卫** `require_project_delegator_pid`，fail-closed 403）：
- ``POST /api/projects/{pid}/procedure-delegations/preview``：materialize 前置 + 解析目标 + 分类 +
  一次性 preview 凭证（返回 status=ready/materialization_pending）。
- ``POST /api/projects/{pid}/procedure-delegations/apply``：消费 preview，经 TransitionService 真实
  assign/reassign；默认整批原子（冲突 → 409），显式 best_effort 才逐任务结果。

约定：service 只 flush；router 显式 commit。均为显式 POST 写命令，非 GET/render 读路径。
selector 三粒度：cycle / workpaper(wp_index_ids) / row(task_ids)。
"""

from __future__ import annotations

import logging
from datetime import datetime
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
from app.services.procedure_delegation_service import (
    CONFLICT_REJECT,
    ProcedureDelegationService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["procedure-row-tasks"])


class DelegationSelector(BaseModel):
    kind: str  # "cycle" | "workpaper" | "row"
    cycle: str | None = None
    wp_index_ids: list[UUID] = Field(default_factory=list)
    task_ids: list[UUID] = Field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "kind": self.kind,
            "cycle": self.cycle,
            "wp_index_ids": [str(i) for i in self.wp_index_ids],
            "task_ids": [str(i) for i in self.task_ids],
        }


class DelegationPreviewRequest(BaseModel):
    selector: DelegationSelector
    assignee_staff_id: UUID
    reviewer_staff_id: UUID | None = None
    unassigned_only: bool = False
    conflict_policy: str = CONFLICT_REJECT
    reason: str | None = None
    best_effort: bool = False
    due_at: datetime | None = None


class DelegationApplyRequest(DelegationPreviewRequest):
    preview_id: UUID
    request_id: str


@router.post("/{pid}/procedure-delegations/preview")
async def delegation_preview(
    pid: UUID,
    body: DelegationPreviewRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """委派预览：materialize 前置 + 目标分类 + 一次性 preview 凭证。"""
    svc = ProcedureDelegationService(db)
    try:
        result = await svc.preview(
            pid,
            actor_user_id=user.id,
            selector=body.selector.to_payload(),
            assignee_staff_id=body.assignee_staff_id,
            reviewer_staff_id=body.reviewer_staff_id,
            unassigned_only=body.unassigned_only,
            conflict_policy=body.conflict_policy,
            reason=body.reason,
            best_effort=body.best_effort,
            due_at=body.due_at,
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result


@router.post("/{pid}/procedure-delegations/apply")
async def delegation_apply(
    pid: UUID,
    body: DelegationApplyRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """委派应用：消费 preview，真实 assign/reassign；默认原子，best_effort 逐任务结果。"""
    svc = ProcedureDelegationService(db)
    try:
        result = await svc.apply(
            pid,
            actor_user_id=user.id,
            preview_id=body.preview_id,
            request_id=body.request_id,
            selector=body.selector.to_payload(),
            assignee_staff_id=body.assignee_staff_id,
            reviewer_staff_id=body.reviewer_staff_id,
            unassigned_only=body.unassigned_only,
            conflict_policy=body.conflict_policy,
            reason=body.reason,
            best_effort=body.best_effort,
            due_at=body.due_at,
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result
