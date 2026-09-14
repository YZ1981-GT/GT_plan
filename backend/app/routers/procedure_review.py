"""程序行一级复核 API（Task 13）

Feature: procedure-delegation-notification / 需求 8.1-8.8 / Design C9、F5、API section

端点：
- ``GET  /api/projects/{pid}/procedure-row-tasks/{task_id}/conversation``：只读复核视图
  （对话 + 消息稳定排序 + 未解决 IssueTicket 数 + 问题单列表）。
- ``POST /api/projects/{pid}/procedure-row-tasks/{task_id}/messages``：追加对话消息。
- ``POST /api/projects/{pid}/procedure-row-tasks/{task_id}/issues/{issue_id}/close``：关闭问题单。

授权（需求 8.5-8.6 / P26）：全部端点先反查 task→project 绑定（跨项目 404，不泄露程序文本），
再按 `resolve_conversation_access` 的并集（当前参与者 + 历史参与者 + IssueTicket 参与者 +
ReviewConversation 参与者 + 项目 Delegator）判定：
- GET：只要非 none 即可读（含历史只读参与者）。
- POST messages/close：仅当前参与者（delegator/assignee/reviewer）可写；历史只读参与者 403。

约定：service 只 flush；router 显式 commit。GET 严格只读（无任何领域写）。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.procedure_models import ProcedureRowTask
from app.services.procedure_authorization import (
    ParticipantAccess,
    assert_task_in_project,
    resolve_conversation_access,
)
from app.services.procedure_review_service import ProcedureReviewService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["procedure-row-tasks"])

# 可执行写动作（发消息 / 关闭问题单）的当前参与者访问级别。
_WRITE_ACCESS = {
    ParticipantAccess.delegator,
    ParticipantAccess.assignee,
    ParticipantAccess.reviewer,
}


async def _load_task(db: AsyncSession, project_id: UUID, task_id: UUID) -> ProcedureRowTask:
    await assert_task_in_project(db, task_id, project_id)  # 跨项目 404
    task = (
        await db.execute(
            sa.select(ProcedureRowTask).where(
                ProcedureRowTask.id == task_id,
                ProcedureRowTask.project_id == project_id,
                ProcedureRowTask.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/{pid}/procedure-row-tasks/{task_id}/conversation")
async def get_procedure_conversation(
    pid: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """只读复核视图（对话 + 消息 + 未解决问题单）。严格只读。"""
    from app.routers._wp_gate import enforce_task_gate

    # Wp_Bound_Gate（task 绑定）：读取程序行复核对话正文之前完成可见性/绑定判定
    # （Req 8.10/8.12 / procedure_task 入口族）。read_task 只读族对全部参与身份可命中，
    # 作为统一门可见性前置；细粒度会话读写授权仍由 resolve_conversation_access 原生强制。
    await enforce_task_gate(
        db, user,
        entrypoint="procedure.task_read", action="read_task", method="GET",
        task_id=task_id, project_id=pid, entry_family="procedure_task",
        route_name="/api/projects/{pid}/procedure-row-tasks/{task_id}/conversation",
    )

    task = await _load_task(db, pid, task_id)
    resolution = await resolve_conversation_access(db, task_id, user)
    if resolution.access == ParticipantAccess.none:
        raise HTTPException(status_code=403, detail="无权查看该程序行复核对话")
    svc = ProcedureReviewService(db)
    view = await svc.get_conversation_view(task)
    view["access"] = resolution.access.value
    view["readonly"] = resolution.access == ParticipantAccess.history_readonly
    return view


class MessageRequest(BaseModel):
    content: str = Field(..., description="消息内容（trim 后 1–5000 字符）")


@router.post("/{pid}/procedure-row-tasks/{task_id}/messages")
async def post_procedure_message(
    pid: UUID,
    task_id: UUID,
    body: MessageRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """追加程序行复核消息（仅当前参与者可写；历史只读参与者 403）。"""
    task = await _load_task(db, pid, task_id)
    resolution = await resolve_conversation_access(db, task_id, user)
    if resolution.access not in _WRITE_ACCESS:
        raise HTTPException(status_code=403, detail="仅当前参与者可发送消息")
    svc = ProcedureReviewService(db)
    msg = await svc.add_message(task, sender_user_id=user.id, content=body.content)
    await db.commit()
    return msg


@router.post("/{pid}/procedure-row-tasks/{task_id}/issues/{issue_id}/close")
async def close_procedure_issue(
    pid: UUID,
    task_id: UUID,
    issue_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """关闭程序行 review_comment IssueTicket（仅当前参与者可写）。"""
    await _load_task(db, pid, task_id)
    resolution = await resolve_conversation_access(db, task_id, user)
    if resolution.access not in _WRITE_ACCESS:
        raise HTTPException(status_code=403, detail="仅当前参与者可关闭问题单")
    svc = ProcedureReviewService(db)
    ticket = await svc.close_issue(task_id, issue_id, actor_user_id=user.id)
    await db.commit()
    return svc._issue_to_dict(ticket)
