"""程序行任务投递 dead-letter 列表 + replay API（Task 10）。

Feature: procedure-delegation-notification
需求：10.2, 10.9 / Design C10（ProcedureDeliveryDispatcher）、API section

端点（均挂 **项目级 Delegator 守卫** `require_project_delegator_pid`，fail-closed 403）：
- ``GET  /api/projects/{pid}/procedure-delivery/dead-letters``：列出本项目 dead-letter 事件（纯读）。
- ``GET  /api/projects/{pid}/procedure-delivery/metrics``：backlog/oldest age/lease/失败/延迟指标（纯读）。
- ``POST /api/projects/{pid}/procedure-delivery/{event_id}/replay``：把 dead-letter 事件重置为可领取。

约定：GET 严格只读（仅 SELECT task_events，不写领域/投递状态）；replay 是显式 POST 写命令，
router 显式 commit。dispatcher 全部 task_events 访问收敛在 ``ProcedureDeliveryDispatcher`` service。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.procedure_authorization import (
    DelegatorContext,
    require_project_delegator_pid,
)
from app.services.procedure_delivery_dispatcher import ProcedureDeliveryDispatcher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["procedure-row-tasks"])


@router.get("/{pid}/procedure-delivery/dead-letters")
async def list_dead_letters(
    pid: UUID,
    db: AsyncSession = Depends(get_db),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """列出本项目投递失败进入 dead-letter 的事件（纯读）。"""
    dispatcher = ProcedureDeliveryDispatcher()
    items = await dispatcher.list_dead_letters(db, pid)
    return {"items": items, "count": len(items)}


@router.get("/{pid}/procedure-delivery/metrics")
async def delivery_metrics(
    pid: UUID,
    db: AsyncSession = Depends(get_db),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """投递指标：backlog/oldest age/lease/失败/延迟/dead-letter（纯读）。"""
    dispatcher = ProcedureDeliveryDispatcher()
    return await dispatcher.metrics(db)


@router.post("/{pid}/procedure-delivery/{event_id}/replay")
async def replay_dead_letter(
    pid: UUID,
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """把 dead-letter 事件重置为可领取（保留事件，清 dead_letter/lease/backoff）。"""
    dispatcher = ProcedureDeliveryDispatcher()
    try:
        result = await dispatcher.replay(db, pid, event_id)
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result
