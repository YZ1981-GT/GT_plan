"""程序行任务显式物化 API（Task 4）

Feature: procedure-delegation-notification / 需求 2.1-2.8, 12.2 / Design C2、D3、API section

端点：
- ``POST /api/projects/{project_id}/procedure-row-tasks/materialize``：同步显式物化。
- ``POST /api/projects/{project_id}/procedure-row-tasks/materialize-jobs``：提交可追踪 job
  （delegation preview 前置 job；job 失败不产生 preview）。
- ``GET  /api/projects/{project_id}/procedure-row-tasks/materialize-jobs/{job_id}``：查询 job 状态。

约定：service 只 flush；router 显式 commit。这些是**显式 POST 写命令**，非 GET/render 读路径。
项目级 Delegator 权限守卫（Req 11.4）在 Task 7 统一挂载；本任务先用认证用户 + 项目锚点校验，
service 已校验 wp_index 属于本项目（拒绝跨项目物化）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.procedure_models import ProcedureRowTask
from app.services.procedure_authorization import (
    assert_sod_distinct,
    assert_task_in_project,
    ensure_project_delegator,
    normalize_staff_to_user,
    require_staff_active_user,
)
from app.services.procedure_review_service import ProcedureReviewService
from app.services.procedure_task_materialization_service import (
    ProcedureTaskMaterializationService,
)
from app.services.procedure_task_transition_service import (
    ACTOR_ASSIGNEE,
    ACTOR_DELEGATOR,
    ACTOR_REVIEWER,
    ProcedureTaskTransitionService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["procedure-row-tasks"])


class MaterializeRequest(BaseModel):
    wp_index_ids: list[UUID] = Field(default_factory=list)
    definition_revision: str | None = None
    request_id: str | None = None


@router.post("/{project_id}/procedure-row-tasks/materialize")
async def materialize_row_tasks(
    project_id: UUID,
    body: MaterializeRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """显式物化 ProcedureRowTask（批量 active partial unique upsert）。"""
    svc = ProcedureTaskMaterializationService(db)
    result = await svc.materialize(
        project_id,
        body.wp_index_ids,
        definition_revision=body.definition_revision,
        actor_user_id=user.id,
        request_id=body.request_id,
    )
    await db.commit()
    return result


@router.post("/{project_id}/procedure-row-tasks/materialize-jobs")
async def create_materialize_job(
    project_id: UUID,
    body: MaterializeRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """同步物化（兼容旧 materialize-jobs POST 签名，直接返回 succeeded）。

    procedure-mainline-convergence Task 4.2: 不再经进程内 job store 注册/追踪；
    同步执行完毕后返回 ``{status: "succeeded", ...result}``。
    """
    svc = ProcedureTaskMaterializationService(db)
    try:
        result = await svc.materialize(
            project_id,
            body.wp_index_ids,
            definition_revision=body.definition_revision,
            actor_user_id=user.id,
            request_id=body.request_id,
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("materialize 失败 project=%s: %s", project_id, exc)
        return {"status": "failed", "error": str(exc)}
    return {"status": "succeeded", **(result if isinstance(result, dict) else {})}


@router.get("/{project_id}/procedure-row-tasks/materialize-jobs/{job_id}")
async def get_materialize_job(
    project_id: UUID,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """已下线（410）：进程内 job store 不再作为可追踪生产真源。

    procedure-mainline-convergence Task 4.2: materialize 改为同步命令（POST 直接返回 succeeded），
    job 查询端点不再有追踪意义。
    """
    raise HTTPException(
        status_code=410,
        detail={
            "error": "materialize_job_query_removed",
            "message": "物化改为同步命令，不再支持 job 查询",
            "replacement": "POST /api/projects/{pid}/procedure-row-tasks/materialize-jobs（直接返回 succeeded）",
        },
    )


# ---------------------------------------------------------------------------
# 状态转换端点（Task 9，Design C7 / API section）
# POST /api/projects/{project_id}/procedure-row-tasks/{task_id}/transitions
#
# 单一状态写入口：所有动作转调 ProcedureTaskTransitionService；task+history+outbox+
# 精确 projection 同事务。actor 授权：delegator 动作走 require_project_delegator；
# assignee/reviewer 动作按 staff→user 归一比较；非法 actor/边/版本 → 403/409 零副作用。
# ---------------------------------------------------------------------------

_DELEGATOR_ACTIONS = {"assign", "reassign", "cancel", "reopen"}
_ASSIGNEE_ACTIONS = {"acknowledge", "start", "submit"}
_REVIEWER_ACTIONS = {"request_changes", "review"}
_ALL_ACTIONS = _DELEGATOR_ACTIONS | _ASSIGNEE_ACTIONS | _REVIEWER_ACTIONS


class TransitionRequest(BaseModel):
    action: str = Field(..., description="assign/reassign/acknowledge/start/submit/request_changes/review/cancel/reopen")
    request_id: str | None = None
    expected_lock_version: int | None = None
    expected_assignment_version: int | None = None
    new_assignee_staff_id: UUID | None = None
    new_reviewer_staff_id: UUID | None = None
    reason: str | None = None
    execution_summary: str | None = None
    evidence_snapshot: list | None = None
    due_at: datetime | None = None
    open_issue_count: int = 0


@router.post("/{project_id}/procedure-row-tasks/{task_id}/transitions")
async def transition_row_task(
    project_id: UUID,
    task_id: UUID,
    body: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """程序行任务状态转换（单一状态机入口）。"""
    action = (body.action or "").strip()
    if action not in _ALL_ACTIONS:
        raise HTTPException(status_code=422, detail=f"未知动作: {action}")

    # 反查 task→project 绑定（跨项目 404，不泄露程序文本）
    await assert_task_in_project(db, task_id, project_id)
    task = (
        await db.execute(
            sa.select(ProcedureRowTask)
            .where(
                ProcedureRowTask.id == task_id,
                ProcedureRowTask.project_id == project_id,
                ProcedureRowTask.is_deleted == sa.false(),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    # actor 授权 + 角色解析
    if action in _DELEGATOR_ACTIONS:
        await ensure_project_delegator(db, user, project_id)  # 403 fail-closed
        actor_role = ACTOR_DELEGATOR
    elif action in _ASSIGNEE_ACTIONS:
        assignee_user = await normalize_staff_to_user(db, task.assignee_staff_id)
        if assignee_user is None or assignee_user != user.id:
            raise HTTPException(status_code=403, detail="仅当前执行人可执行该动作")
        actor_role = ACTOR_ASSIGNEE
    else:  # reviewer actions
        # Task 13：reviewer 未显式设置时按 C9 决定性 fallback 解析并持久化，
        # 使 request_changes/review 能识别有效操作复核人（reviewer_staff_id 写入不触碰
        # workflow/applicability，故不属状态机 bypass）。
        if task.reviewer_staff_id is None:
            resolved, _src = await ProcedureReviewService(db).resolve_reviewer(task)
            if resolved is not None:
                task.reviewer_staff_id = resolved
        reviewer_user = await normalize_staff_to_user(db, task.reviewer_staff_id)
        if reviewer_user is None or reviewer_user != user.id:
            raise HTTPException(status_code=403, detail="仅当前操作复核人可执行该动作")
        actor_role = ACTOR_REVIEWER

    svc = ProcedureTaskTransitionService(db)

    if action == "assign":
        if body.new_assignee_staff_id is None:
            raise HTTPException(status_code=422, detail="assign 需要 new_assignee_staff_id")
        await require_staff_active_user(db, body.new_assignee_staff_id)
        await assert_sod_distinct(
            db, body.new_assignee_staff_id, body.new_reviewer_staff_id or task.reviewer_staff_id
        )
        result = await svc.assign(
            task,
            new_assignee_staff_id=body.new_assignee_staff_id,
            actor_user_id=user.id,
            actor_role=actor_role,
            request_id=body.request_id,
            new_reviewer_staff_id=body.new_reviewer_staff_id,
            due_at=body.due_at,
            expected_lock_version=body.expected_lock_version,
            reason=body.reason,
        )
    elif action == "reassign":
        if body.new_assignee_staff_id is None:
            raise HTTPException(status_code=422, detail="reassign 需要 new_assignee_staff_id")
        await require_staff_active_user(db, body.new_assignee_staff_id)
        await assert_sod_distinct(db, body.new_assignee_staff_id, task.reviewer_staff_id)
        result = await svc.reassign(
            task,
            new_assignee_staff_id=body.new_assignee_staff_id,
            actor_user_id=user.id,
            reason=body.reason or "",
            actor_role=actor_role,
            request_id=body.request_id,
            expected_lock_version=body.expected_lock_version,
        )
    elif action == "acknowledge":
        result = await svc.acknowledge(
            task,
            actor_user_id=user.id,
            actor_role=actor_role,
            request_id=body.request_id,
            expected_assignment_version=body.expected_assignment_version,
            expected_lock_version=body.expected_lock_version,
        )
    elif action == "start":
        result = await svc.start(
            task,
            actor_user_id=user.id,
            actor_role=actor_role,
            request_id=body.request_id,
            expected_lock_version=body.expected_lock_version,
        )
    elif action == "submit":
        result = await svc.submit(
            task,
            actor_user_id=user.id,
            execution_summary=body.execution_summary or "",
            evidence_snapshot=body.evidence_snapshot or [],
            actor_role=actor_role,
            request_id=body.request_id,
            expected_lock_version=body.expected_lock_version,
        )
        # Task 11 / Req 5.6：提交后若复核人不可解析，向有权限的 Delegator 产生
        # reviewer_missing 通知意图（同事务；非阻断）。
        try:
            await ProcedureReviewService(db).notify_reviewer_missing(
                task, actor_user_id=user.id
            )
        except Exception:  # 通知意图失败不影响提交领域写
            logger.warning("reviewer_missing 通知生成失败 task=%s", task.id, exc_info=True)
    elif action == "request_changes":
        result = await svc.request_changes(
            task,
            actor_user_id=user.id,
            reason=body.reason or "",
            actor_role=actor_role,
            request_id=body.request_id,
            expected_lock_version=body.expected_lock_version,
        )
        # Task 13：退回同事务创建/复用正式未解决项 IssueTicket + 关联 ReviewConversation。
        review_svc = ProcedureReviewService(db)
        conv = await review_svc.ensure_conversation(task, actor_user_id=user.id)
        await review_svc.create_or_reuse_issue_ticket(
            task,
            actor_user_id=user.id,
            reason=body.reason or "",
            conversation_id=conv.id,
            request_id=body.request_id,
        )
    elif action == "review":
        # Task 13：review 门槛由服务端从 DB 计算未关闭 IssueTicket 数（不信任客户端 open_issue_count）。
        open_issue_count = await ProcedureReviewService(
            db
        ).open_changes_requested_issue_count(task.id)
        result = await svc.review(
            task,
            actor_user_id=user.id,
            actor_role=actor_role,
            request_id=body.request_id,
            expected_lock_version=body.expected_lock_version,
            open_issue_count=open_issue_count,
        )
    elif action == "cancel":
        changed = await svc.cancel(
            task,
            actor_user_id=user.id,
            reason=body.reason or "",
            request_id=body.request_id,
        )
        result = {
            "task_id": str(task.id),
            "changed": changed,
            "workflow_status": task.workflow_status,
            "applicability_status": task.applicability_status,
            "assignment_version": task.assignment_version,
            "lock_version": task.lock_version,
        }
    else:  # reopen
        changed = await svc.reopen(
            task,
            actor_user_id=user.id,
            request_id=body.request_id,
            reason=body.reason,
        )
        result = {
            "task_id": str(task.id),
            "changed": changed,
            "workflow_status": task.workflow_status,
            "applicability_status": task.applicability_status,
            "assignment_version": task.assignment_version,
            "lock_version": task.lock_version,
        }

    await db.commit()
    return result
