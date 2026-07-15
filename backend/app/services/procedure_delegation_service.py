"""三粒度程序行委派与安全 preview/apply 服务（Task 8）

Feature: procedure-delegation-notification
需求：4.1-4.10（三粒度 selector + 安全 preview/apply + 一次消费 + 原子/best_effort + 同人 no-op +
      转派理由 + assignment_version + owner 隔离）、6.4（assignment_version 与重新 ack）、
      10.7（每 task 独立 history/outbox 共享 delegation_batch_id）
Design：C6（ProcedureDelegationService + DelegationResolver）、D4（ProcedureOperationPreview 一次性凭证）、
        D8（有序 outbox 与聚合通知分离）
Properties：P11（selector 展开等价）、P12（preview token 防篡改与越权）、P13（最多一次消费）、
            P14（批量委派原子与 owner 隔离）、P15（同人委派业务 no-op）

职责：
- **DelegationResolver**：把 cycle / workpaper(wp_index) / row(task) 三种 selector **确定性** 展开为
  “当前粗裁保留（scope 非 skip/not_applicable）且 applicability=execute” 的 ProcedureRowTask 集合
  （Req 4.1 / P11）。三种 selector 统一走同一谓词，故 cycle/workpaper 展开集合 ==
  对全项目 tasks 应用范围+粗裁+applicability 谓词后的 row 集合。
- **materialize 前置**：preview 若发现目标 wp_index 存在未物化 definition 行，先经 Task 4 的
  ``materialize_job_store`` + ``ProcedureTaskMaterializationService.materialize`` 物化并返回
  ``status=materialization_pending``（不产生可消费 preview）；客户端 job 成功后重新请求 preview（Req 4.2 / 2.8）。
- **preview**：解析目标 + 分类（assign/reassign/unchanged/conflict/terminal），创建一次性
  ``ProcedureOperationPreview``（复用 Task 5 的 create_preview）；返回目标数 / 已分配 / 执行中 /
  已提交 / 冲突数 / 成员负载 / 受影响底稿 / 逐项双版本（lock+assignment）（Req 4.3）。
- **apply**：经 ``consume_and_apply`` 一次消费（防篡改/越权/过期/成员变化/版本变化 409，request_id 幂等）；
  默认整批原子（任一冲突 → 409 零写），显式 ``best_effort`` 才逐任务结果（Req 4.9 / P14）。
  每个真实委派经 ``ProcedureTaskTransitionService.assign/reassign``（**单一状态机入口** —
  架构守卫只放行该类写 workflow/applicability），首次分配/换人递增 assignment_version 并清 ack；
  同执行人重复分配为业务 no-op（Req 4.8 / P15）。所有 task 各写独立 history/outbox，
  **共享 delegation_batch_id**（Req 10.7 / D8）。
- **owner 隔离**：**绝不** 修改 ``WorkingPaper.assigned_to`` 或 ``ProjectAssignment.assigned_cycles``
  （Req 4.10 / P14）—— 本服务只经 TransitionService 写 ProcedureRowTask，不触碰底稿主编/循环责任范围。

约定：service 只 flush 不 commit；router 显式 commit。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance, ProcedureRowTask
from app.models.staff_models import ProjectAssignment
from app.models.workpaper_models import WpIndex
from app.services.procedure_authorization import (
    assert_sod_distinct,
    require_staff_active_user,
)
from app.services.procedure_definition_importer import canonical_json
from app.services.procedure_materialize_jobs import materialize_job_store
from app.services.procedure_operation_preview import consume_and_apply, create_preview
from app.services.procedure_task_materialization_service import (
    ProcedureTaskMaterializationService,
)
from app.services.procedure_task_transition_service import (
    APPLICABILITY_EXECUTE,
    TERMINAL_WORKFLOW_STATES,
    WORKFLOW_IN_PROGRESS,
    WORKFLOW_SUBMITTED,
    WORKFLOW_UNASSIGNED,
    ProcedureTaskTransitionService,
)

logger = logging.getLogger(__name__)

DELEGATE_OPERATION = "delegate"

# selector 粒度
SELECTOR_CYCLE = "cycle"
SELECTOR_WORKPAPER = "workpaper"
SELECTOR_ROW = "row"

# 冲突策略（Req 4.7）
CONFLICT_REJECT = "reject_on_conflict"  # default
CONFLICT_REPLACE = "replace_with_reason"

_TRIMMED_STATUSES = ("skip", "not_applicable")


class DelegationConflictError(HTTPException):
    """默认原子模式下存在冲突目标 → 409 零写（Req 4.9 / P14）。"""

    def __init__(self, conflict_task_ids: list[str]):
        super().__init__(
            status_code=409,
            detail={
                "error": "delegation_conflict",
                "message": "存在已被他人分配的目标任务；默认原子模式拒绝整批（可用 replace_with_reason 或 best_effort）",
                "conflict_task_ids": conflict_task_ids,
            },
        )


class ProcedureDelegationService:
    """三粒度委派：DelegationResolver + 安全 preview/apply。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.transition = ProcedureTaskTransitionService(db)
        self.materialization = ProcedureTaskMaterializationService(db)

    # ======================================================================
    # DelegationResolver（确定性展开，Req 4.1 / P11）
    # ======================================================================

    @staticmethod
    def canonical_selector(selector: dict) -> dict:
        """归一 selector 为 canonical 形式（preview 与 apply 的 request payload 须一致，防篡改）。"""
        kind = (selector or {}).get("kind")
        if kind == SELECTOR_CYCLE:
            cycle = str(selector.get("cycle", "")).strip()
            if not cycle:
                raise HTTPException(status_code=422, detail="cycle selector 缺 cycle")
            return {"kind": SELECTOR_CYCLE, "cycle": cycle}
        if kind == SELECTOR_WORKPAPER:
            ids = sorted(str(i) for i in (selector.get("wp_index_ids") or []))
            if not ids:
                raise HTTPException(status_code=422, detail="workpaper selector 缺 wp_index_ids")
            return {"kind": SELECTOR_WORKPAPER, "wp_index_ids": ids}
        if kind == SELECTOR_ROW:
            ids = sorted(str(i) for i in (selector.get("task_ids") or []))
            if not ids:
                raise HTTPException(status_code=422, detail="row selector 缺 task_ids")
            return {"kind": SELECTOR_ROW, "task_ids": ids}
        raise HTTPException(status_code=422, detail=f"非法 selector kind: {kind}")

    async def _trimmed_scopes(self, project_id: UUID) -> set[tuple[str, str]]:
        """粗裁为 skip/not_applicable 的范围集合 {(audit_cycle, wp_code)}（Req 4.1 粗裁保留过滤）。"""
        rows = (
            await self.db.execute(
                sa.select(ProcedureInstance.audit_cycle, ProcedureInstance.wp_code).where(
                    ProcedureInstance.project_id == project_id,
                    ProcedureInstance.is_deleted == sa.false(),
                    ProcedureInstance.status.in_(_TRIMMED_STATUSES),
                )
            )
        ).all()
        return {(r[0], r[1]) for r in rows}

    async def _candidate_tasks(
        self, project_id: UUID, canonical: dict, *, for_update: bool
    ) -> list[ProcedureRowTask]:
        """按 selector 粒度取候选 active 任务（尚未应用粗裁/applicability 谓词）。"""
        conds = [
            ProcedureRowTask.project_id == project_id,
            ProcedureRowTask.is_deleted == sa.false(),
        ]
        kind = canonical["kind"]
        if kind == SELECTOR_CYCLE:
            conds.append(ProcedureRowTask.audit_cycle_snapshot == canonical["cycle"])
        elif kind == SELECTOR_WORKPAPER:
            conds.append(
                ProcedureRowTask.wp_index_id.in_(
                    [UUID(i) for i in canonical["wp_index_ids"]]
                )
            )
        else:  # row
            conds.append(
                ProcedureRowTask.id.in_([UUID(i) for i in canonical["task_ids"]])
            )
        stmt = sa.select(ProcedureRowTask).where(*conds)
        if for_update:
            stmt = stmt.with_for_update()
        rows = (await self.db.execute(stmt)).scalars().all()
        return rows

    async def resolve_targets(
        self, project_id: UUID, canonical: dict, *, for_update: bool = False
    ) -> list[ProcedureRowTask]:
        """确定性展开为“粗裁保留且 applicability=execute”的目标任务集合（Req 4.1 / P11）。

        三种 selector 统一走同一谓词：applicability=execute + scope 非 skip/not_applicable。
        结果按 task id 稳定排序，保证 cycle/workpaper/row 展开等价可比较。
        """
        candidates = await self._candidate_tasks(project_id, canonical, for_update=for_update)
        trimmed = await self._trimmed_scopes(project_id)
        targets = [
            t
            for t in candidates
            if t.applicability_status == APPLICABILITY_EXECUTE
            and (t.audit_cycle_snapshot, t.wp_code) not in trimmed
        ]
        targets.sort(key=lambda t: str(t.id))
        return targets

    # ======================================================================
    # 分类（纯函数，preview 与 apply 共用）
    # ======================================================================

    def _classify(
        self,
        tasks: list[ProcedureRowTask],
        *,
        assignee_staff_id: UUID,
        unassigned_only: bool,
        conflict_policy: str,
    ) -> dict:
        """把目标任务分为 assign / reassign / unchanged / conflict / terminal / skipped_assigned。

        - terminal（reviewed/cancelled）：不可委派 → 跳过（不计冲突）。
        - workflow=unassigned：首次分配 → assign。
        - 同执行人：业务 no-op → unchanged（Req 4.8 / P15）。
        - 不同执行人：unassigned_only → 跳过；replace_with_reason → reassign；否则 → conflict。
        """
        plan: dict[str, list[ProcedureRowTask]] = {
            "assign": [],
            "reassign": [],
            "unchanged": [],
            "conflict": [],
            "terminal": [],
            "skipped_assigned": [],
        }
        for t in tasks:
            if t.workflow_status in TERMINAL_WORKFLOW_STATES:
                plan["terminal"].append(t)
                continue
            if t.workflow_status == WORKFLOW_UNASSIGNED or t.assignee_staff_id is None:
                plan["assign"].append(t)
                continue
            if t.assignee_staff_id == assignee_staff_id:
                plan["unchanged"].append(t)
                continue
            # 不同执行人（活动任务）
            if unassigned_only:
                plan["skipped_assigned"].append(t)
                continue
            if conflict_policy == CONFLICT_REPLACE:
                plan["reassign"].append(t)
            else:
                plan["conflict"].append(t)
        return plan

    # ======================================================================
    # 辅助：成员快照 / 负载 / request payload / materialize 检测
    # ======================================================================

    async def _membership_snapshot(self, project_id: UUID) -> list:
        """项目 active ProjectAssignment 快照（staff_id + role），稳定排序供 hash。"""
        rows = (
            await self.db.execute(
                sa.select(ProjectAssignment.staff_id, ProjectAssignment.role).where(
                    ProjectAssignment.project_id == project_id,
                    ProjectAssignment.is_deleted == sa.false(),
                )
            )
        ).all()
        return sorted([[str(r[0]), (r[1] or "").strip().lower()] for r in rows])

    async def _assignee_workload(self, project_id: UUID, staff_id: UUID) -> int:
        """执行人当前在本项目持有的非终态任务数（成员负载，Req 4.3）。"""
        return (
            await self.db.execute(
                sa.select(sa.func.count())
                .select_from(ProcedureRowTask)
                .where(
                    ProcedureRowTask.project_id == project_id,
                    ProcedureRowTask.assignee_staff_id == staff_id,
                    ProcedureRowTask.is_deleted == sa.false(),
                    ProcedureRowTask.workflow_status.notin_(list(TERMINAL_WORKFLOW_STATES)),
                )
            )
        ).scalar() or 0

    @staticmethod
    def _request_payload(
        canonical_selector: dict,
        *,
        assignee_staff_id: UUID,
        reviewer_staff_id: UUID | None,
        unassigned_only: bool,
        conflict_policy: str,
        reason: str | None,
        best_effort: bool,
        due_at: datetime | None,
    ) -> dict:
        """规范化 request payload（preview 与 apply 必须一致，防篡改，Req 4.4 / P12）。"""
        return {
            "operation": DELEGATE_OPERATION,
            "selector": canonical_selector,
            "assignee_staff_id": str(assignee_staff_id),
            "reviewer_staff_id": str(reviewer_staff_id) if reviewer_staff_id else None,
            "unassigned_only": bool(unassigned_only),
            "conflict_policy": conflict_policy,
            "reason": (reason or "").strip() or None,
            "best_effort": bool(best_effort),
            "due_at": due_at.isoformat() if due_at else None,
        }

    async def _candidate_wp_index_ids(
        self, project_id: UUID, canonical: dict
    ) -> list[UUID] | None:
        """materialize 检测用：cycle/workpaper 目标 wp_index 集合；row selector 无需物化（返回 None）。"""
        kind = canonical["kind"]
        if kind == SELECTOR_WORKPAPER:
            return [UUID(i) for i in canonical["wp_index_ids"]]
        if kind == SELECTOR_CYCLE:
            rows = (
                await self.db.execute(
                    sa.select(WpIndex.id).where(
                        WpIndex.project_id == project_id,
                        WpIndex.audit_cycle == canonical["cycle"],
                        WpIndex.is_deleted == sa.false(),
                    )
                )
            ).scalars().all()
            return list(rows)
        return None

    async def _count_unmaterialized(
        self, project_id: UUID, wp_index_ids: list[UUID]
    ) -> int:
        """统计目标 wp_index 中尚未物化（definition 存在但无 task）的行数（纯读）。"""
        total = 0
        for wp_index_id in wp_index_ids:
            overlay = await self.materialization.build_row_overlay(project_id, wp_index_id)
            total += sum(1 for r in overlay if r.get("materialization_required"))
        return total

    @staticmethod
    def _validate_reason_if_replace(conflict_policy: str, reason: str | None) -> None:
        """replace_with_reason 时转派理由须 5–500 字符（Req 4.7）。"""
        if conflict_policy == CONFLICT_REPLACE:
            r = (reason or "").strip()
            if not (5 <= len(r) <= 500):
                raise HTTPException(status_code=422, detail="转派理由长度须为 5–500 字符")

    # ======================================================================
    # preview（含 materialize 前置 job）
    # ======================================================================

    async def preview(
        self,
        project_id: UUID,
        *,
        actor_user_id: UUID,
        selector: dict,
        assignee_staff_id: UUID,
        reviewer_staff_id: UUID | None = None,
        unassigned_only: bool = False,
        conflict_policy: str = CONFLICT_REJECT,
        reason: str | None = None,
        best_effort: bool = False,
        due_at: datetime | None = None,
    ) -> dict:
        """委派预览：materialize 前置 + 解析目标 + 分类 + 创建一次性 preview（只 flush）。

        - selector 目标存在未物化行 → 触发前置 materialize job 并返回 ``status=materialization_pending``，
          不产生 preview；客户端 job 成功后重新请求（Req 2.8 / 4.2）。
        - 否则返回 ``status=ready`` + preview_id + 统计（Req 4.3）。
        """
        if conflict_policy not in (CONFLICT_REJECT, CONFLICT_REPLACE):
            raise HTTPException(status_code=422, detail=f"非法 conflict_policy: {conflict_policy}")
        canonical = self.canonical_selector(selector)
        self._validate_reason_if_replace(conflict_policy, reason)
        # 执行人/复核人身份校验（无 active user_id 禁止委派/设复核人）
        await require_staff_active_user(self.db, assignee_staff_id)
        if reviewer_staff_id is not None:
            await require_staff_active_user(self.db, reviewer_staff_id)
            await assert_sod_distinct(self.db, assignee_staff_id, reviewer_staff_id)

        # -- materialize 前置：cycle/workpaper 存在未物化行 → 触发 job 并返回 pending --
        wp_index_ids = await self._candidate_wp_index_ids(project_id, canonical)
        if wp_index_ids:
            pending = await self._count_unmaterialized(project_id, wp_index_ids)
            if pending > 0:
                job = await materialize_job_store.create(
                    str(project_id), [str(i) for i in wp_index_ids]
                )
                await materialize_job_store.mark(job.id, "running")
                result = await self.materialization.materialize(
                    project_id, wp_index_ids, actor_user_id=actor_user_id
                )
                await materialize_job_store.mark(job.id, "succeeded", result=result)
                logger.info(
                    "delegation preview 触发前置 materialize project=%s pending=%d job=%s",
                    project_id, pending, job.id,
                )
                return {
                    "status": "materialization_pending",
                    "materialize_job": (await materialize_job_store.get(job.id, str(project_id))).to_dict(),
                    "preview_id": None,
                    "message": "已触发前置物化 job；job 成功后请重新请求 preview",
                }

        # -- 解析目标 + 分类 --
        targets = await self.resolve_targets(project_id, canonical)
        plan = self._classify(
            targets,
            assignee_staff_id=assignee_staff_id,
            unassigned_only=unassigned_only,
            conflict_policy=conflict_policy,
        )
        target_versions = {str(t.id): t.lock_version for t in targets}
        workload = await self._assignee_workload(project_id, assignee_staff_id)
        membership = await self._membership_snapshot(project_id)

        payload = self._request_payload(
            canonical,
            assignee_staff_id=assignee_staff_id,
            reviewer_staff_id=reviewer_staff_id,
            unassigned_only=unassigned_only,
            conflict_policy=conflict_policy,
            reason=reason,
            best_effort=best_effort,
            due_at=due_at,
        )
        preview = await create_preview(
            self.db,
            actor_user_id=actor_user_id,
            project_id=project_id,
            operation=DELEGATE_OPERATION,
            request_payload=payload,
            target_versions=target_versions,
            membership_snapshot=membership,
            scheme_revision=None,
        )

        affected_wp_index = sorted({str(t.wp_index_id) for t in targets})
        affected_wp = sorted({str(t.wp_id) for t in targets if t.wp_id})
        already_assigned = sum(1 for t in targets if t.assignee_staff_id is not None)
        in_progress = sum(1 for t in targets if t.workflow_status == WORKFLOW_IN_PROGRESS)
        submitted = sum(1 for t in targets if t.workflow_status == WORKFLOW_SUBMITTED)

        return {
            "status": "ready",
            "preview_id": str(preview.id),
            "expires_at": preview.expires_at.isoformat(),
            "summary": {
                "targets": len(targets),
                "would_assign": len(plan["assign"]),
                "would_reassign": len(plan["reassign"]),
                "unchanged": len(plan["unchanged"]),
                "conflict": len(plan["conflict"]),
                "terminal": len(plan["terminal"]),
                "skipped_assigned": len(plan["skipped_assigned"]),
                "already_assigned": already_assigned,
                "in_progress": in_progress,
                "submitted": submitted,
            },
            "conflict_task_ids": [str(t.id) for t in plan["conflict"]],
            "membership_load": {
                "assignee_staff_id": str(assignee_staff_id),
                "active_task_count": workload,
            },
            "affected_workpapers": {
                "wp_index_ids": affected_wp_index,
                "wp_ids": affected_wp,
            },
            "target_versions": [
                {
                    "task_id": str(t.id),
                    "lock_version": t.lock_version,
                    "assignment_version": t.assignment_version,
                }
                for t in targets
            ],
        }

    # ======================================================================
    # apply（一次消费 + 原子/best_effort）
    # ======================================================================

    async def apply(
        self,
        project_id: UUID,
        *,
        actor_user_id: UUID,
        preview_id: UUID,
        request_id: str,
        selector: dict,
        assignee_staff_id: UUID,
        reviewer_staff_id: UUID | None = None,
        unassigned_only: bool = False,
        conflict_policy: str = CONFLICT_REJECT,
        reason: str | None = None,
        best_effort: bool = False,
        due_at: datetime | None = None,
    ) -> dict:
        """委派应用：一次消费 preview，经 TransitionService 真实 assign/reassign（只 flush）。

        - 默认整批原子：任一冲突 → 409 零写；best_effort → 逐任务结果（Req 4.9 / P14）。
        - 同人重复分配为 no-op（不递增 version / 无 history/outbox，Req 4.8 / P15）。
        - 每 task 独立 history/outbox，共享 delegation_batch_id（Req 10.7）。
        - **不修改** WorkingPaper.assigned_to / ProjectAssignment.assigned_cycles（Req 4.10）。
        - 目标 task lock_version 自 preview 后变化 → 409；相同 request_id 幂等返回旧 result。
        """
        if conflict_policy not in (CONFLICT_REJECT, CONFLICT_REPLACE):
            raise HTTPException(status_code=422, detail=f"非法 conflict_policy: {conflict_policy}")
        canonical = self.canonical_selector(selector)
        self._validate_reason_if_replace(conflict_policy, reason)
        payload = self._request_payload(
            canonical,
            assignee_staff_id=assignee_staff_id,
            reviewer_staff_id=reviewer_staff_id,
            unassigned_only=unassigned_only,
            conflict_policy=conflict_policy,
            reason=reason,
            best_effort=best_effort,
            due_at=due_at,
        )
        membership = await self._membership_snapshot(project_id)

        async def _apply_fn(db: AsyncSession, preview) -> dict:
            # 行锁复取目标，版本自 preview 后变化 → 409
            targets = await self.resolve_targets(project_id, canonical, for_update=True)
            current_versions = {str(t.id): t.lock_version for t in targets}
            if current_versions != dict(preview.target_versions or {}):
                raise HTTPException(status_code=409, detail="目标任务版本已变化，请重新预览")

            plan = self._classify(
                targets,
                assignee_staff_id=assignee_staff_id,
                unassigned_only=unassigned_only,
                conflict_policy=conflict_policy,
            )

            # 默认原子：任一冲突 → 409 零写（在任何写入前判定，Req 4.9 / P14）
            if plan["conflict"] and not best_effort:
                raise DelegationConflictError([str(t.id) for t in plan["conflict"]])

            batch_id = uuid.uuid4()
            applied = 0
            unchanged = 0
            failed = 0
            per_task: list[dict] = []

            async def _do_assign(t: ProcedureRowTask) -> dict:
                # 每 task SOD：assignee vs 生效 reviewer（新 reviewer 或既有 reviewer）
                effective_reviewer = reviewer_staff_id or t.reviewer_staff_id
                await assert_sod_distinct(db, assignee_staff_id, effective_reviewer)
                return await self.transition.assign(
                    t,
                    new_assignee_staff_id=assignee_staff_id,
                    actor_user_id=actor_user_id,
                    request_id=request_id,
                    new_reviewer_staff_id=reviewer_staff_id,
                    due_at=due_at,
                    reason=reason,
                    delegation_batch_id=batch_id,
                )

            async def _do_reassign(t: ProcedureRowTask) -> dict:
                effective_reviewer = reviewer_staff_id or t.reviewer_staff_id
                await assert_sod_distinct(db, assignee_staff_id, effective_reviewer)
                return await self.transition.reassign(
                    t,
                    new_assignee_staff_id=assignee_staff_id,
                    actor_user_id=actor_user_id,
                    reason=(reason or ""),
                    request_id=request_id,
                    delegation_batch_id=batch_id,
                )

            for kind, tasks_bucket, action in (
                ("assign", plan["assign"], _do_assign),
                ("reassign", plan["reassign"], _do_reassign),
            ):
                for t in tasks_bucket:
                    try:
                        r = await action(t)
                    except HTTPException as exc:
                        if not best_effort:
                            raise
                        failed += 1
                        per_task.append(
                            {"task_id": str(t.id), "action": kind, "status": "failed",
                             "error": exc.detail}
                        )
                        continue
                    if r.get("changed"):
                        applied += 1
                        per_task.append(
                            {"task_id": str(t.id), "action": kind, "status": "applied",
                             "assignment_version": r.get("assignment_version"),
                             "lock_version": r.get("lock_version")}
                        )
                    else:
                        unchanged += 1
                        per_task.append(
                            {"task_id": str(t.id), "action": kind, "status": "unchanged"}
                        )

            # 同人 no-op（Req 4.8 / P15）
            for t in plan["unchanged"]:
                unchanged += 1
                per_task.append({"task_id": str(t.id), "action": "assign", "status": "unchanged"})

            await db.flush()
            return {
                "delegation_batch_id": str(batch_id),
                "applied": applied,
                "unchanged": unchanged,
                "failed": failed,
                "conflict": len(plan["conflict"]),
                "terminal": len(plan["terminal"]),
                "skipped_assigned": len(plan["skipped_assigned"]),
                "best_effort": bool(best_effort),
                "per_task": per_task if best_effort else None,
            }

        return await consume_and_apply(
            self.db,
            preview_id=preview_id,
            actor_user_id=actor_user_id,
            project_id=project_id,
            operation=DELEGATE_OPERATION,
            request_payload=payload,
            request_id=request_id,
            current_membership_snapshot=membership,
            apply_fn=_apply_fn,
        )
