"""程序行任务状态转换服务（Task 6 建立的 cancel/reopen 种子 + Task 9 扩展入口）

Feature: procedure-delegation-notification
需求：3.3-3.5（细裁 not_applicable→cancelled；恢复须 reopen→assign→ack）、6.1-6.3（独立状态机）
Design：C7（ProcedureTaskTransitionService 转换表）、D7（任务真源与精确投影）
Properties：P9（裁剪与 workflow 正交）、P19-P21（状态机封闭性 / assignment_version / 审计完备）

=== TransitionService 种子（seam）说明 —— 供 Task 9 收编 ===

本 feature 设计要求 **所有** ProcedureRowTask 工作流状态写入与 WorkpaperScopeInstance 粗裁
状态写入 **只有一个入口**：``ProcedureTaskTransitionService``（Design C7 单一状态机 / D7 任务真源）。
架构守卫 ``check_procedure_delegation_architecture.py`` 的 ``_is_transition_service`` 也 **只**
放行本文件本类内的 workflow/applicability/ProcedureInstance.status 写入；任何其它模块直接写
这些状态字段都会被判为 ``procedure-state-transition-bypass`` 债务。

Task 6（裁剪/方案）**仅需要** cancel / reopen 两条转换边（+ 粗裁 scope 状态写），故本文件当前只
实现这两条边及粗裁 scope 写入的最小可用种子（minimal seam）。它们严格遵守 Design C7 的状态表：

    | action | from            | to        | 关键条件                         |
    | cancel | 任意未终态       | cancelled | 原因必填；已 cancelled 且无 applicability 变化时业务 no-op |
    | reopen | cancelled       | unassigned| 不保留 ack/assignee；后续须重新 assign→ack           |

**Task 9 将在本类内追加** assign / acknowledge / start / submit / request_changes / review 等
完整转换边，并接入有序 outbox（Task 10）。Task 9 落地后，本文件仍是唯一状态写入口，
``ProcedureTrimService`` 对 cancel/reopen 的调用点无需改动即可复用 Task 9 的规范实现。

约定：service 只 flush 不 commit；router/dispatcher 显式 commit。history 与领域写同事务；
outbox 由 Task 10 接入（当前仅写 append-only history）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase15_models import TaskEvent
from app.models.procedure_models import (
    ProcedureInstance,
    ProcedureRowTask,
    ProcedureRowTaskHistory,
)
from app.services.procedure_projection_service import (
    ProcedureProjectionService,
    task_projection_value,
)

logger = logging.getLogger(__name__)

# 工作流状态（Design C7 主路径 + changes_requested 返修支路）。
WORKFLOW_UNASSIGNED = "unassigned"
WORKFLOW_ASSIGNED = "assigned"
WORKFLOW_ACKNOWLEDGED = "acknowledged"
WORKFLOW_IN_PROGRESS = "in_progress"
WORKFLOW_SUBMITTED = "submitted"
WORKFLOW_CHANGES_REQUESTED = "changes_requested"
WORKFLOW_REVIEWED = "reviewed"
WORKFLOW_CANCELLED = "cancelled"

# 终态：不可再被 cancel（reviewed 已完成；cancelled 已取消）。
TERMINAL_WORKFLOW_STATES = frozenset({WORKFLOW_REVIEWED, WORKFLOW_CANCELLED})

APPLICABILITY_EXECUTE = "execute"
APPLICABILITY_NOT_APPLICABLE = "not_applicable"

# 归一化 actor 角色（identity 解析由 procedure_authorization 完成；本状态机只校验角色边）。
ACTOR_DELEGATOR = "delegator"
ACTOR_ASSIGNEE = "assignee"
ACTOR_REVIEWER = "reviewer"

# outbox 聚合类型（Delivery_Outbox / Task 10 dispatcher 按 aggregate_version 有序投递）。
AGGREGATE_PROCEDURE_ROW_TASK = "procedure_row_task"

# 每个成功领域动作的 outbox event_type（前后端通知类型同步，Task 11）。
_EVENT_TYPE_PREFIX = "procedure_task."


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProcedureTaskTransitionService:
    """程序行任务状态转换单一入口（Task 6 seam：cancel / reopen / 粗裁 scope 状态写）。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.projection = ProcedureProjectionService(db)

    # -- 内部：追加式 history + 有序 outbox + 精确投影镜像（同事务）------------

    def _append_history(
        self,
        task: ProcedureRowTask,
        *,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        actor_user_id: UUID | None,
        request_id: str | None,
        reason: str | None,
        detail: dict | None = None,
        old_assignee_staff_id: UUID | None = None,
        new_assignee_staff_id: UUID | None = None,
        old_reviewer_staff_id: UUID | None = None,
        new_reviewer_staff_id: UUID | None = None,
    ) -> None:
        self.db.add(
            ProcedureRowTaskHistory(
                task_id=task.id,
                project_id=task.project_id,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                old_assignee_staff_id=old_assignee_staff_id
                if old_assignee_staff_id is not None
                else task.assignee_staff_id,
                new_assignee_staff_id=new_assignee_staff_id
                if new_assignee_staff_id is not None
                else task.assignee_staff_id,
                old_reviewer_staff_id=old_reviewer_staff_id
                if old_reviewer_staff_id is not None
                else task.reviewer_staff_id,
                new_reviewer_staff_id=new_reviewer_staff_id
                if new_reviewer_staff_id is not None
                else task.reviewer_staff_id,
                actor_user_id=actor_user_id,
                reason=reason,
                request_id=request_id,
                assignment_version=task.assignment_version,
                lock_version=task.lock_version,
                definition_revision_hash=task.definition_revision_hash,
                audit_cycle_snapshot=task.audit_cycle_snapshot,
                detail=detail or {},
            )
        )

    def _write_outbox(
        self,
        task: ProcedureRowTask,
        *,
        event_type: str,
        actor_user_id: UUID | None,
        request_id: str | None,
        from_status: str | None,
        to_status: str | None,
        detail: dict | None = None,
        delegation_batch_id: UUID | None = None,
    ) -> None:
        """在领域事务内写入 Delivery_Outbox 意图（Task 10 dispatcher 提交后异步投递）。

        aggregate_version 使用 task.lock_version（每次非 no-op 成功动作单调递增），保证同一
        task 的事件严格有序；idempotency_key 全局唯一（task + event + version）。
        """
        aggregate_version = task.lock_version
        idem = f"{task.id}:{event_type}:{aggregate_version}"
        payload = {
            "task_id": str(task.id),
            "project_id": str(task.project_id),
            "wp_index_id": str(task.wp_index_id),
            "wp_id": str(task.wp_id) if task.wp_id else None,
            "sheet_key": task.sheet_key,
            "definition_key": task.definition_key,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "assignment_version": task.assignment_version,
            "lock_version": task.lock_version,
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "assignee_staff_id": str(task.assignee_staff_id) if task.assignee_staff_id else None,
            "reviewer_staff_id": str(task.reviewer_staff_id) if task.reviewer_staff_id else None,
            "audit_cycle_snapshot": task.audit_cycle_snapshot,
            "detail": detail or {},
        }
        self.db.add(
            TaskEvent(
                project_id=task.project_id,
                event_type=f"{_EVENT_TYPE_PREFIX}{event_type}",
                payload=payload,
                status="queued",
                trace_id=(request_id or str(uuid.uuid4()))[:64],
                aggregate_type=AGGREGATE_PROCEDURE_ROW_TASK,
                aggregate_id=task.id,
                aggregate_version=aggregate_version,
                idempotency_key=idem[:128],
                delegation_batch_id=delegation_batch_id,
                available_at=_utcnow(),
            )
        )

    async def _mirror_projection(self, task: ProcedureRowTask) -> None:
        """把当前 task 状态精确镜像到 parsed_data.procedure_status（jsonb_set，禁止整列 RMW）。"""
        await self.projection.write_path(
            task.wp_id, task.sheet_key, task.definition_key, task_projection_value(task)
        )

    async def _emit(
        self,
        task: ProcedureRowTask,
        *,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        actor_user_id: UUID | None,
        request_id: str | None,
        reason: str | None = None,
        detail: dict | None = None,
        old_assignee_staff_id: UUID | None = None,
        new_assignee_staff_id: UUID | None = None,
        old_reviewer_staff_id: UUID | None = None,
        new_reviewer_staff_id: UUID | None = None,
        delegation_batch_id: UUID | None = None,
    ) -> None:
        """成功领域动作统一出口：history + 有序 outbox + 精确投影镜像，同事务（只 flush）。"""
        self._append_history(
            task,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=reason,
            detail=detail,
            old_assignee_staff_id=old_assignee_staff_id,
            new_assignee_staff_id=new_assignee_staff_id,
            old_reviewer_staff_id=old_reviewer_staff_id,
            new_reviewer_staff_id=new_reviewer_staff_id,
        )
        self._write_outbox(
            task,
            event_type=event_type,
            actor_user_id=actor_user_id,
            request_id=request_id,
            from_status=from_status,
            to_status=to_status,
            detail=detail,
            delegation_batch_id=delegation_batch_id,
        )
        await self._mirror_projection(task)
        await self.db.flush()

    @staticmethod
    def _require_role(actor_role: str | None, expected: str) -> None:
        """状态机角色边校验：actor_role 必须与该动作要求一致，否则 409 零副作用。"""
        if actor_role != expected:
            raise HTTPException(
                status_code=409,
                detail=f"非法动作 actor：需要 {expected}，实际 {actor_role or 'unknown'}",
            )

    @staticmethod
    def _check_lock_version(task: ProcedureRowTask, expected_lock_version: int | None) -> None:
        """乐观锁校验：expected_lock_version 不匹配 → 409（同版本并发最多一个成功）。"""
        if expected_lock_version is not None and task.lock_version != expected_lock_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "lock_version_conflict",
                    "expected": expected_lock_version,
                    "current": task.lock_version,
                },
            )

    # -- cancel（任意未终态 → cancelled）------------------------------------

    async def cancel(
        self,
        task: ProcedureRowTask,
        *,
        actor_user_id: UUID | None,
        reason: str,
        request_id: str | None = None,
        set_applicability: str | None = None,
        event_type: str = "cancel",
        detail: dict | None = None,
    ) -> bool:
        """把未终态任务转为 cancelled；可同时把 applicability 置为 not_applicable（细裁）。

        - 原因必填（422）。
        - reviewed 终态不可取消（409）。
        - 已 cancelled 且无 applicability 变化 → 业务 no-op（返回 ``False``，不写 history）。
        - 成功：workflow→cancelled、可选 applicability、lock_version+1、cancelled_at、追加 history。

        返回是否发生真实状态变化（供裁剪/方案统计真实 applied 数）。
        """
        if not reason or not str(reason).strip():
            raise HTTPException(status_code=422, detail="取消原因必填")

        if task.workflow_status == WORKFLOW_REVIEWED:
            raise HTTPException(status_code=409, detail="已复核任务不可取消")

        already_cancelled = task.workflow_status == WORKFLOW_CANCELLED
        applicability_change = (
            set_applicability is not None
            and task.applicability_status != set_applicability
        )
        if already_cancelled and not applicability_change:
            return False  # 幂等 no-op

        from_status = task.workflow_status
        if not already_cancelled:
            task.workflow_status = WORKFLOW_CANCELLED
            task.cancelled_at = _utcnow()
        if set_applicability is not None:
            task.applicability_status = set_applicability
        task.lock_version = (task.lock_version or 0) + 1
        task.updated_at = sa.func.now()

        await self._emit(
            task,
            event_type=event_type,
            from_status=from_status,
            to_status=WORKFLOW_CANCELLED,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=reason,
            detail={
                **(detail or {}),
                "set_applicability": set_applicability,
            },
        )
        return True

    # -- reopen（cancelled → unassigned）------------------------------------

    async def reopen(
        self,
        task: ProcedureRowTask,
        *,
        actor_user_id: UUID | None,
        request_id: str | None = None,
        set_applicability: str | None = None,
        reason: str | None = None,
        event_type: str = "reopen",
        detail: dict | None = None,
    ) -> bool:
        """把 cancelled 任务恢复为 unassigned（不保留 ack/assignee）。

        - 仅 cancelled 可 reopen（其余 409）。
        - 可同时把 applicability 置回 execute（细裁恢复）。
        - 清空 assignee/acknowledged/started/submitted/cancelled 时间；lock_version+1；追加 history。
        - **不自动恢复原执行人、不自动完成**：恢复后 workflow=unassigned，须由 Delegator 重新
          assign→ack（Property P9 / 需求 3.5、6.3）。

        返回是否发生真实状态变化。
        """
        if task.workflow_status != WORKFLOW_CANCELLED:
            raise HTTPException(status_code=409, detail="只有已取消任务可重开")

        task.workflow_status = WORKFLOW_UNASSIGNED
        task.assignee_staff_id = None
        task.acknowledged_at = None
        task.started_at = None
        task.submitted_at = None
        task.cancelled_at = None
        if set_applicability is not None:
            task.applicability_status = set_applicability
        task.lock_version = (task.lock_version or 0) + 1
        task.updated_at = sa.func.now()

        await self._emit(
            task,
            event_type=event_type,
            from_status=WORKFLOW_CANCELLED,
            to_status=WORKFLOW_UNASSIGNED,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=reason,
            detail={
                **(detail or {}),
                "set_applicability": set_applicability,
            },
        )
        return True

    # -- 粗裁 scope 状态写（WorkpaperScopeInstance）--------------------------

    async def set_scope_status(
        self,
        instance: ProcedureInstance,
        *,
        status: str,
        actor_user_id: UUID | None = None,
        reason: str | None = None,
    ) -> bool:
        """写 WorkpaperScopeInstance（ProcedureInstance）粗裁状态 execute/skip/not_applicable。

        粗裁状态写入同样收敛到本状态机入口（架构守卫只放行本类）。已是目标状态 → no-op（False）。
        """
        if status not in ("execute", "skip", "not_applicable"):
            raise HTTPException(status_code=422, detail=f"非法粗裁状态: {status}")
        if instance.status == status:
            return False
        instance.status = status
        if status in ("skip", "not_applicable"):
            instance.skip_reason = reason
        else:
            instance.skip_reason = None
        instance.updated_at = sa.func.now()
        await self.db.flush()
        return True

    # ======================================================================
    # 完整状态转换表（Design C7）：assign / reassign / acknowledge / start /
    # submit / request_changes / review。所有成功转换 = task update + history +
    # outbox + 精确 projection 同事务；非法边/actor/版本 → 409 零副作用。
    # ======================================================================

    def _result(self, task: ProcedureRowTask, *, changed: bool) -> dict:
        return {
            "task_id": str(task.id),
            "changed": changed,
            "workflow_status": task.workflow_status,
            "applicability_status": task.applicability_status,
            "assignment_version": task.assignment_version,
            "lock_version": task.lock_version,
        }

    async def assign(
        self,
        task: ProcedureRowTask,
        *,
        new_assignee_staff_id: UUID,
        actor_user_id: UUID | None,
        actor_role: str = ACTOR_DELEGATOR,
        request_id: str | None = None,
        new_reviewer_staff_id: UUID | None = None,
        due_at: datetime | None = None,
        expected_lock_version: int | None = None,
        reason: str | None = None,
        delegation_batch_id: UUID | None = None,
    ) -> dict:
        """unassigned → assigned（首次分配）。

        - 仅 Delegator；仅 unassigned（cancelled 必须先 reopen，否则 409）。
        - applicability 必须 execute；assignment_version+1、清 acknowledged_at（要求重新 ack）。
        - staff→user 归一与 SOD 由 procedure_authorization 在 router 前置校验。
        """
        self._require_role(actor_role, ACTOR_DELEGATOR)
        self._check_lock_version(task, expected_lock_version)
        if new_assignee_staff_id is None:
            raise HTTPException(status_code=422, detail="assign 需要执行人 staff id")
        if task.workflow_status != WORKFLOW_UNASSIGNED:
            raise HTTPException(
                status_code=409,
                detail=f"assign 仅允许 unassigned→assigned，当前 {task.workflow_status}",
            )
        if task.applicability_status != APPLICABILITY_EXECUTE:
            raise HTTPException(status_code=409, detail="不适用任务不可分配（applicability≠execute）")

        old_assignee = task.assignee_staff_id
        task.assignee_staff_id = new_assignee_staff_id
        if new_reviewer_staff_id is not None:
            task.reviewer_staff_id = new_reviewer_staff_id
        task.workflow_status = WORKFLOW_ASSIGNED
        task.assignment_version = (task.assignment_version or 0) + 1
        task.acknowledged_at = None
        task.assigned_at = _utcnow()
        if due_at is not None:
            task.due_at = due_at
        task.lock_version = (task.lock_version or 0) + 1
        task.updated_at = sa.func.now()

        await self._emit(
            task,
            event_type="assigned",
            from_status=WORKFLOW_UNASSIGNED,
            to_status=WORKFLOW_ASSIGNED,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=reason,
            old_assignee_staff_id=old_assignee,
            new_assignee_staff_id=new_assignee_staff_id,
            delegation_batch_id=delegation_batch_id,
        )
        return self._result(task, changed=True)

    async def reassign(
        self,
        task: ProcedureRowTask,
        *,
        new_assignee_staff_id: UUID,
        actor_user_id: UUID | None,
        reason: str,
        actor_role: str = ACTOR_DELEGATOR,
        request_id: str | None = None,
        expected_lock_version: int | None = None,
        delegation_batch_id: UUID | None = None,
    ) -> dict:
        """转派执行人（非终态任务换人）。

        - 仅 Delegator；转派理由 5–500 字符。
        - 新旧执行人相同 → 业务 no-op（不递增 assignment_version/lock_version，不写 history/outbox，
          Req 4.8 / Property P15）。
        - 换人 → assignment_version+1、清 ack、workflow 回到 assigned（要求重新 ack，Req 6.4）。
        """
        self._require_role(actor_role, ACTOR_DELEGATOR)
        self._check_lock_version(task, expected_lock_version)
        if new_assignee_staff_id is None:
            raise HTTPException(status_code=422, detail="reassign 需要执行人 staff id")
        r = (reason or "").strip()
        if not (5 <= len(r) <= 500):
            raise HTTPException(status_code=422, detail="转派理由长度须为 5–500 字符")
        if task.workflow_status in TERMINAL_WORKFLOW_STATES:
            raise HTTPException(status_code=409, detail=f"终态任务不可转派：{task.workflow_status}")
        if task.workflow_status == WORKFLOW_UNASSIGNED:
            raise HTTPException(status_code=409, detail="未分配任务请用 assign")

        # 同人 no-op（Req 4.8 / P15）
        if task.assignee_staff_id == new_assignee_staff_id:
            return self._result(task, changed=False)

        old_assignee = task.assignee_staff_id
        task.assignee_staff_id = new_assignee_staff_id
        task.workflow_status = WORKFLOW_ASSIGNED
        task.assignment_version = (task.assignment_version or 0) + 1
        task.acknowledged_at = None
        task.assigned_at = _utcnow()
        task.lock_version = (task.lock_version or 0) + 1
        task.updated_at = sa.func.now()

        await self._emit(
            task,
            event_type="reassigned",
            from_status=WORKFLOW_ASSIGNED,
            to_status=WORKFLOW_ASSIGNED,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=r,
            old_assignee_staff_id=old_assignee,
            new_assignee_staff_id=new_assignee_staff_id,
            delegation_batch_id=delegation_batch_id,
        )
        return self._result(task, changed=True)

    async def acknowledge(
        self,
        task: ProcedureRowTask,
        *,
        actor_user_id: UUID | None,
        actor_role: str = ACTOR_ASSIGNEE,
        request_id: str | None = None,
        expected_assignment_version: int | None = None,
        expected_lock_version: int | None = None,
    ) -> dict:
        """assigned → acknowledged（仅 assignee）。

        - expected_assignment_version 若给出须匹配当前 assignment_version（否则 409）。
        - 同一 assignment_version 重复 ack → 业务 no-op（不写 history/outbox、不递增 lock_version，
          Req 6.5 / Property P20）。
        """
        self._require_role(actor_role, ACTOR_ASSIGNEE)
        if (
            expected_assignment_version is not None
            and task.assignment_version != expected_assignment_version
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "assignment_version_conflict",
                    "expected": expected_assignment_version,
                    "current": task.assignment_version,
                },
            )
        # 重复 ack（当前 assignment_version 已确认）→ no-op
        if task.workflow_status == WORKFLOW_ACKNOWLEDGED:
            return self._result(task, changed=False)
        self._check_lock_version(task, expected_lock_version)
        if task.workflow_status != WORKFLOW_ASSIGNED:
            raise HTTPException(
                status_code=409,
                detail=f"acknowledge 仅允许 assigned→acknowledged，当前 {task.workflow_status}",
            )

        task.workflow_status = WORKFLOW_ACKNOWLEDGED
        task.acknowledged_at = _utcnow()
        task.lock_version = (task.lock_version or 0) + 1
        task.updated_at = sa.func.now()

        await self._emit(
            task,
            event_type="acknowledged",
            from_status=WORKFLOW_ASSIGNED,
            to_status=WORKFLOW_ACKNOWLEDGED,
            actor_user_id=actor_user_id,
            request_id=request_id,
        )
        return self._result(task, changed=True)

    async def start(
        self,
        task: ProcedureRowTask,
        *,
        actor_user_id: UUID | None,
        actor_role: str = ACTOR_ASSIGNEE,
        request_id: str | None = None,
        expected_lock_version: int | None = None,
    ) -> dict:
        """acknowledged / changes_requested → in_progress（仅 assignee）。

        - wp_id 必须非空（底稿已生成）；applicability 必须 execute；否则 409（Req 6.7）。
        - bare assigned 不可 start（须先 ack）。
        """
        self._require_role(actor_role, ACTOR_ASSIGNEE)
        self._check_lock_version(task, expected_lock_version)
        if task.workflow_status not in (WORKFLOW_ACKNOWLEDGED, WORKFLOW_CHANGES_REQUESTED):
            raise HTTPException(
                status_code=409,
                detail=f"start 仅允许 acknowledged/changes_requested→in_progress，当前 {task.workflow_status}",
            )
        if task.applicability_status != APPLICABILITY_EXECUTE:
            raise HTTPException(status_code=409, detail="不适用任务不可开始（applicability≠execute）")
        if task.wp_id is None:
            raise HTTPException(status_code=409, detail="底稿未生成（wp_id 为空），不可开始执行")

        from_status = task.workflow_status
        task.workflow_status = WORKFLOW_IN_PROGRESS
        task.started_at = _utcnow()
        task.lock_version = (task.lock_version or 0) + 1
        task.updated_at = sa.func.now()

        await self._emit(
            task,
            event_type="started",
            from_status=from_status,
            to_status=WORKFLOW_IN_PROGRESS,
            actor_user_id=actor_user_id,
            request_id=request_id,
        )
        return self._result(task, changed=True)

    async def submit(
        self,
        task: ProcedureRowTask,
        *,
        actor_user_id: UUID | None,
        execution_summary: str,
        evidence_snapshot: list,
        actor_role: str = ACTOR_ASSIGNEE,
        request_id: str | None = None,
        expected_lock_version: int | None = None,
    ) -> dict:
        """in_progress → submitted（仅 assignee）。

        - 执行说明非空 + 证据引用快照非空（否则 422，Req 6.7）。
        - applicability 必须 execute、wp_id 非空。
        """
        self._require_role(actor_role, ACTOR_ASSIGNEE)
        self._check_lock_version(task, expected_lock_version)
        if task.workflow_status != WORKFLOW_IN_PROGRESS:
            raise HTTPException(
                status_code=409,
                detail=f"submit 仅允许 in_progress→submitted，当前 {task.workflow_status}",
            )
        if task.applicability_status != APPLICABILITY_EXECUTE or task.wp_id is None:
            raise HTTPException(status_code=409, detail="不适用或底稿未生成，不可提交")
        if not execution_summary or not str(execution_summary).strip():
            raise HTTPException(status_code=422, detail="执行说明必填")
        if not evidence_snapshot or not isinstance(evidence_snapshot, list):
            raise HTTPException(status_code=422, detail="证据引用快照必填")

        task.workflow_status = WORKFLOW_SUBMITTED
        task.execution_summary = str(execution_summary).strip()
        task.evidence_snapshot = list(evidence_snapshot)
        task.submitted_at = _utcnow()
        task.lock_version = (task.lock_version or 0) + 1
        task.updated_at = sa.func.now()

        await self._emit(
            task,
            event_type="submitted",
            from_status=WORKFLOW_IN_PROGRESS,
            to_status=WORKFLOW_SUBMITTED,
            actor_user_id=actor_user_id,
            request_id=request_id,
        )
        return self._result(task, changed=True)

    async def request_changes(
        self,
        task: ProcedureRowTask,
        *,
        actor_user_id: UUID | None,
        reason: str,
        actor_role: str = ACTOR_REVIEWER,
        request_id: str | None = None,
        expected_lock_version: int | None = None,
        detail: dict | None = None,
    ) -> dict:
        """submitted → changes_requested（仅 Operation_Reviewer）。

        退回原因必填；IssueTicket 创建/复用由 ProcedureReviewService（Task 13）在同事务补充，
        本状态机只负责状态边与审计/outbox。
        """
        self._require_role(actor_role, ACTOR_REVIEWER)
        self._check_lock_version(task, expected_lock_version)
        if task.workflow_status != WORKFLOW_SUBMITTED:
            raise HTTPException(
                status_code=409,
                detail=f"request_changes 仅允许 submitted→changes_requested，当前 {task.workflow_status}",
            )
        r = (reason or "").strip()
        if not (1 <= len(r) <= 5000):
            raise HTTPException(status_code=422, detail="退回原因长度须为 1–5000 字符")

        task.workflow_status = WORKFLOW_CHANGES_REQUESTED
        task.lock_version = (task.lock_version or 0) + 1
        task.updated_at = sa.func.now()

        await self._emit(
            task,
            event_type="changes_requested",
            from_status=WORKFLOW_SUBMITTED,
            to_status=WORKFLOW_CHANGES_REQUESTED,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=r,
            detail=detail,
        )
        return self._result(task, changed=True)

    async def review(
        self,
        task: ProcedureRowTask,
        *,
        actor_user_id: UUID | None,
        actor_role: str = ACTOR_REVIEWER,
        request_id: str | None = None,
        expected_lock_version: int | None = None,
        open_issue_count: int = 0,
    ) -> dict:
        """submitted → reviewed（仅 Operation_Reviewer；程序行一级复核）。

        - reviewer_staff_id 缺失 → 409 reviewer_missing（阻止 review，零任务副作用；
          reviewer_missing 通知意图由 ReviewService/dispatcher 侧处理，Req 5.6）。
        - 关联 changes_requested IssueTicket 未全部 closed（open_issue_count>0）→ 409（Req 8.4）。
        - 一级复核 reviewed **不改变** 底稿/项目层 partner/QC/EQCR 复核门槛（Req 5.7-5.8 / P18）。
        """
        self._require_role(actor_role, ACTOR_REVIEWER)
        self._check_lock_version(task, expected_lock_version)
        if task.workflow_status != WORKFLOW_SUBMITTED:
            raise HTTPException(
                status_code=409,
                detail=f"review 仅允许 submitted→reviewed，当前 {task.workflow_status}",
            )
        if task.reviewer_staff_id is None:
            raise HTTPException(status_code=409, detail={"error": "reviewer_missing"})
        if open_issue_count and open_issue_count > 0:
            raise HTTPException(
                status_code=409,
                detail={"error": "open_issue_tickets", "open_issue_count": open_issue_count},
            )

        task.workflow_status = WORKFLOW_REVIEWED
        task.reviewed_at = _utcnow()
        task.lock_version = (task.lock_version or 0) + 1
        task.updated_at = sa.func.now()

        await self._emit(
            task,
            event_type="reviewed",
            from_status=WORKFLOW_SUBMITTED,
            to_status=WORKFLOW_REVIEWED,
            actor_user_id=actor_user_id,
            request_id=request_id,
        )
        return self._result(task, changed=True)

    # ======================================================================
    # backfill 迁移 seed（Task 15，需求 7.6-7.8 / Property P24/P34）
    #
    # 唯一被架构守卫放行写 workflow_status/applicability_status 的入口。backfill 用它把旧状态
    # 保守映射（map_legacy_status 结果）**一次性 seed** 到刚物化、尚未处理过的任务上：
    #   - 仅当任务处于默认 unassigned 且 migration_confidence 为空时才 seed（幂等：重复 backfill /
    #     中断恢复不覆盖已 seed 或已被真实委派/执行的任务）。
    #   - 写 workflow_status/applicability_status/migration_confidence/migration_detail。
    #   - 追加 append-only history（event_type=backfill_seed，保留旧状态来源/值/规则/冲突快照）。
    #   - **不写 outbox**（backfill 阶段 dispatcher 关闭，避免迁移触发通知风暴），
    #     **不镜像投影**（投影由 ProcedureProjectionService.rebuild 单独重建）。
    # ======================================================================

    async def seed_migrated_state(
        self,
        task: ProcedureRowTask,
        *,
        applicability: str,
        workflow: str,
        confidence: str,
        detail: dict,
        actor_user_id: UUID | None = None,
        request_id: str | None = None,
    ) -> bool:
        """把旧状态保守映射结果 seed 到刚物化的任务（幂等；仅默认/未 seed 时生效）。

        返回是否发生 seed（已被处理过/已委派的任务返回 False，不覆盖）。
        """
        # 幂等护栏：已 seed（migration_confidence 非空）或已脱离默认 unassigned 的任务不再 seed。
        already_seeded = task.migration_confidence is not None
        default_state = (
            task.workflow_status == WORKFLOW_UNASSIGNED
            and task.applicability_status == APPLICABILITY_EXECUTE
            and task.assignee_staff_id is None
        )
        if already_seeded or not default_state:
            return False

        # 默认映射（unassigned + execute + conservative）与当前一致 → 只标记 confidence/detail，
        # 不改状态字段但仍视为已处理（避免每次 backfill 重复扫描）。
        from_workflow = task.workflow_status
        task.applicability_status = applicability
        task.workflow_status = workflow
        if workflow == WORKFLOW_CANCELLED:
            task.cancelled_at = _utcnow()
        task.migration_confidence = confidence
        task.migration_detail = dict(detail or {})
        task.lock_version = (task.lock_version or 0) + 1
        task.updated_at = sa.func.now()

        self._append_history(
            task,
            event_type="backfill_seed",
            from_status=from_workflow,
            to_status=workflow,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason="legacy_backfill",
            detail={
                "migration_confidence": confidence,
                **(detail or {}),
            },
        )
        await self.db.flush()
        return True
