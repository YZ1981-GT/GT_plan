"""两层委派、清空、scope expansion 与 epoch 原子事务（Task 7 / 组件 C12）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 2.1–2.15：两层委派语义与权威字段（Workpaper_Lead vs Row_Assignee/Operation_Reviewer
    分层但联动；``WorkingPaper.assigned_to``=user_id 权威，``ProcedureInstance.assigned_to``
    =staff_id 投影；两层互不覆盖；任一层缺值/变更保持另一层不变；lead 更新失败整体回滚）。
  - 3.7–3.15：清空必须显式指定目标层/目标 task；lead 清空同事务清 WP+投影；row 清空只清目标
    角色并保留另一 row 角色/lead/投影；同事务记录统一 delegation history；任一步失败逐字段回滚；
    禁止用 row 角色 staff 更新 Staff_Projection。
  - 6.1–6.8：跨循环默认拒绝；仅 delegator 显式 ``expand_scope=true`` + 非空 reason 才同事务扩权；
    扩权时同事务写 scope 并集 + 委派 + 审计；任一步失败回滚；撤销委派不自动缩 scope。
  - 14.20–14.21：权限/委派/history/scope/角色/项目成员变更同事务持久递增 policy epoch 并写
    invalidation outbox（不允许提交后 best-effort 才失效）。
Design: "Delegation transactions" 段 / Property 3（两层永不互相覆盖）/ Property 17
  （权限变更 + epoch/invalidation 同事务原子提交）。

**边界与约定**：
  - service 只 ``flush`` 不 ``commit``（router/调用方提交）。所有 epoch/history/投影/字段写入
    都在同一 flush 单元内，router 单次 commit 即原子；任一步 raise → 调用方回滚。
  - 严格 staff→user 映射复用 ``StaffUserMappingService``（Task 3）；唯一 wp_index 解析复用
    ``ProcedureWpResolver``（Task 4）。不重建 ProcedureRowTask 状态机、不改 scope_cycles 数据模型。
  - fail-closed：映射/解析/scope 校验任一不成立 → ``DelegationError``（调用方回滚），绝不静默降级。
  - asyncpg：``= ANY(:list)`` 而非 IN tuple；行锁用 ``with_for_update()`` 串行化并发转派。
  - 幂等：非空 ``request_id`` 命中既有 delegation history（同 project+layer+target+目标）→ 直接返回
    idempotent 结果，不重复写入、不重复递增 epoch。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import ProjectUser
from app.models.procedure_models import (
    ProcedureInstance,
    ProcedureRowTask,
    ProcedureRowTaskHistory,
)
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.models.wp_visibility_models import (
    WorkpaperDelegationHistory,
    WpVisibilityInvalidationOutbox,
    WpVisibilityPolicyEpoch,
)
from app.services.wp_visibility.delegation_guard import (  # 拒绝原因 / 错误类型自此导出（原定义处）
    DelegationError,
    DelegationGuardMixin,
    DelegationRejectReason,
)
from app.services.wp_visibility.procedure_wp_resolver import (
    ProcedureBindingSources,
    ProcedureWpResolver,
)
from app.services.wp_visibility.staff_user_mapping import StaffUserMappingService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 请求 / 结果契约
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LeadDelegationRequest:
    """Workpaper_Lead 层委派/转派/清空请求。

    ``staff_id`` 非空 = 委派/转派；``clear=True`` = 清空 lead（staff_id 忽略）。
    wp_index 由 identity 绑定来源联合唯一解析（procedure_instance_id / wp_id / wp_code / wp_index_id）。
    """

    project_id: UUID
    actor_user_id: UUID
    # 目标 staff（clear=True 时忽略）
    staff_id: UUID | None = None
    clear: bool = False
    # 投影目标（可选）：指定则只更新该实例的 Staff_Projection；否则更新 wp_index 下全部实例
    procedure_instance_id: UUID | None = None
    # wp_index identity 绑定来源
    wp_index_id: UUID | None = None
    wp_id: UUID | None = None
    wp_code: str | None = None
    procedure_code: str | None = None
    audit_cycle: str | None = None
    # scope 扩权
    expand_scope: bool = False
    scope_reason: str | None = None
    # 幂等
    request_id: str | None = None


@dataclass(frozen=True)
class RowDelegationRequest:
    """程序行层（Row_Assignee / Operation_Reviewer）委派/转派/清空请求。

    ``target_role`` 明确目标角色；``staff_id`` 非空 = 委派/转派；``clear=True`` = 清空该角色。
    只写明确的目标 ProcedureRowTask，绝不写 Staff_Projection（Req 3.15）。
    """

    project_id: UUID
    actor_user_id: UUID
    task_id: UUID
    target_role: Literal["assignee", "reviewer"]
    staff_id: UUID | None = None
    clear: bool = False
    expand_scope: bool = False
    scope_reason: str | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class DelegationResult:
    """委派事务结果（不可变）。"""

    ok: bool
    layer: str                       # 'lead' | 'row'
    target_role: str                 # 'lead' | 'assignee' | 'reviewer'
    action: str                      # 'assign' | 'reassign' | 'clear'
    wp_index_id: UUID | None
    user_id: UUID | None             # lead 层映射到的 users.id（row 层为该角色 staff 映射 user）
    staff_id: UUID | None
    epoch: int | None
    idempotent: bool = False


class DelegationTransactionService(DelegationGuardMixin):
    """两层委派原子事务编排器（只 flush；epoch/history/字段同事务）。

    裁剪拦截与有效循环范围校验见 :class:`DelegationGuardMixin`（``delegation_guard``）。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.mapping = StaffUserMappingService(db)
        self.resolver = ProcedureWpResolver(db)
        # 同一批委派内裁剪结果不变：每个项目只读一次
        self._trim_scope_cache: dict = {}
        # 批量委派时先收集缺少的循环、处理完统一报（用户一次看全、一次确认）；None = 立即报
        self._deferred_scope_gaps: dict[UUID, set[str]] | None = None

    # ==================================================================
    # Lead 层
    # ==================================================================
    async def delegate_lead(self, req: LeadDelegationRequest) -> DelegationResult:
        """Workpaper_Lead 层委派/转派/清空（两层联动、同事务、fail-closed）。"""
        # ---- 幂等命中 ----
        prior = await self._find_idempotent(
            req.request_id, req.project_id, layer="lead", target_role="lead"
        )
        if prior is not None:
            return DelegationResult(
                ok=True, layer="lead", target_role="lead",
                action=prior.action, wp_index_id=prior.wp_index_id,
                user_id=prior.new_user_id, staff_id=prior.new_staff_id,
                epoch=None, idempotent=True,
            )

        # ---- 只能委派保留项：已粗裁的底稿（含跟随科目的子表 / 程序表）不能设主编；清空不拦 ----
        if not req.clear:
            await self._reject_if_trimmed(req.project_id, req.wp_code)

        # ---- 唯一解析 wp_index（Req 4.11：解析失败即拒绝委派）----
        wp_index_id = await self._resolve_lead_wp_index(req)
        wp_index = await self._load_wp_index(req.project_id, wp_index_id)
        if wp_index is None:
            raise DelegationError(DelegationRejectReason.binding_conflict, "wp_index 不属于项目")
        if not req.clear:
            await self._reject_if_trimmed(req.project_id, wp_index.wp_code)

        # ---- 锁行（串行化并发转派）：working_paper + 目标 procedure_instance ----
        wp_rows = await self._lock_working_papers(req.project_id, wp_index_id)
        target_instances = await self._lock_projection_instances(req)

        # ---- 读取旧值快照 ----
        old_user_id = wp_rows[0].assigned_to if wp_rows else None
        old_staff_id = target_instances[0].assigned_to if target_instances else None

        if req.clear:
            action = "clear"
            new_user_id: UUID | None = None
            new_staff_id: UUID | None = None
            scope_before, scope_after = await self._current_scope_pair(
                req.project_id, old_user_id
            )
        else:
            if req.staff_id is None:
                raise DelegationError(
                    DelegationRejectReason.invalid_request, "非清空委派必须提供 staff_id"
                )
            # ---- 严格 staff→user 映射（Req 2.4–2.6 / 3.1–3.6）----
            mapping = await self.mapping.resolve_active_project_mapping(
                req.project_id, req.staff_id
            )
            if not mapping.ok or mapping.user_id is None:
                raise DelegationError(
                    DelegationRejectReason.mapping_invalid,
                    f"staff→user 映射不成立: {mapping.reason}",
                )
            new_user_id = mapping.user_id
            new_staff_id = req.staff_id
            # ---- 跨循环 scope 校验 + 可选扩权（Req 6.1–6.7）----
            scope_before, scope_after = await self._enforce_scope(
                req.project_id,
                new_user_id,
                wp_index.audit_cycle,
                req.expand_scope,
                req.scope_reason,
            )
            action = "reassign" if old_user_id is not None else "assign"

        # ---- 写两层字段（同事务）----
        # ① 权威：working_paper.assigned_to = user_id（wp_index 下全部 WP 行）
        for wp in wp_rows:
            wp.assigned_to = new_user_id
        # ①' 展示镜像：wp_index.assigned_to（进度 / 催办 / 归档完整性 / 关联图读它；原只有复核页指派会写，
        #     主编委派后各处显示旧人。spec procedure-trim-generation-delegation-chain 设计 §3.4）
        wp_index.assigned_to = new_user_id
        # ② 投影：procedure_instances.assigned_to = staff_id（Req 2.3；lead staff，非 row staff）
        now = datetime.now(timezone.utc)
        for inst in target_instances:
            inst.assigned_to = new_staff_id
            inst.assigned_at = now if new_staff_id is not None else None

        # ---- 统一 delegation history（Req 3.13）----
        await self._record_history(
            request_id=req.request_id,
            project_id=req.project_id,
            wp_index_id=wp_index_id,
            wp_id=(wp_rows[0].id if wp_rows else None),
            layer="lead",
            target_role="lead",
            action=action,
            task_id=None,
            sheet_key=None,
            old_user_id=old_user_id,
            new_user_id=new_user_id,
            old_staff_id=old_staff_id,
            new_staff_id=new_staff_id,
            actor_user_id=req.actor_user_id,
            reason=req.scope_reason,
            scope_before=scope_before,
            scope_after=scope_after,
        )

        # ---- policy epoch + invalidation outbox（同事务，Req 14.20）----
        epoch = await self._bump_epoch(
            req.project_id, "delegation", req.request_id, req.actor_user_id,
            {"layer": "lead", "action": action, "wp_index_id": str(wp_index_id)},
        )
        await self.db.flush()
        return DelegationResult(
            ok=True, layer="lead", target_role="lead", action=action,
            wp_index_id=wp_index_id, user_id=new_user_id, staff_id=new_staff_id,
            epoch=epoch, idempotent=False,
        )

    # ==================================================================
    # Row 层
    # ==================================================================
    async def delegate_row(self, req: RowDelegationRequest) -> DelegationResult:
        """程序行层委派/转派/清空（只写目标 task，绝不写投影；同事务、fail-closed）。"""
        if req.target_role not in ("assignee", "reviewer"):
            raise DelegationError(DelegationRejectReason.invalid_request, "target_role 非法")

        # ---- 幂等命中 ----
        prior = await self._find_idempotent(
            req.request_id, req.project_id, layer="row",
            target_role=req.target_role, task_id=req.task_id,
        )
        if prior is not None:
            return DelegationResult(
                ok=True, layer="row", target_role=req.target_role,
                action=prior.action, wp_index_id=prior.wp_index_id,
                user_id=prior.new_user_id, staff_id=prior.new_staff_id,
                epoch=None, idempotent=True,
            )

        # ---- 锁定目标 task（串行化并发转派）----
        task = (
            await self.db.execute(
                sa.select(ProcedureRowTask)
                .where(
                    ProcedureRowTask.id == req.task_id,
                    ProcedureRowTask.project_id == req.project_id,
                    ProcedureRowTask.is_deleted == sa.false(),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if task is None:
            raise DelegationError(DelegationRejectReason.task_not_found, "程序行任务不存在")

        field = "assignee_staff_id" if req.target_role == "assignee" else "reviewer_staff_id"
        old_staff_id: UUID | None = getattr(task, field)
        old_user_id = await self._staff_to_user(req.project_id, old_staff_id)

        if req.clear:
            action = "clear"
            new_staff_id: UUID | None = None
            new_user_id: UUID | None = None
            scope_before, scope_after = await self._current_scope_pair(
                req.project_id, old_user_id
            )
        else:
            if req.staff_id is None:
                raise DelegationError(
                    DelegationRejectReason.invalid_request, "非清空委派必须提供 staff_id"
                )
            mapping = await self.mapping.resolve_active_project_mapping(
                req.project_id, req.staff_id
            )
            if not mapping.ok or mapping.user_id is None:
                raise DelegationError(
                    DelegationRejectReason.mapping_invalid,
                    f"staff→user 映射不成立: {mapping.reason}",
                )
            new_staff_id = req.staff_id
            new_user_id = mapping.user_id
            # 只能委派保留项：细裁不适用 / 已取消的程序行、所在底稿已粗裁或在回收站的都拒绝
            wp_index = await self.assert_row_task_delegable(req.project_id, task)
            scope_before, scope_after = await self._enforce_scope(
                req.project_id, new_user_id, wp_index.audit_cycle, req.expand_scope, req.scope_reason
            )
            action = "reassign" if old_staff_id is not None else "assign"

        # ---- 只写目标 task 的目标角色（保留另一 row 角色 / lead / 投影，Req 3.12）----
        setattr(task, field, new_staff_id)
        now = datetime.now(timezone.utc)
        task.assigned_at = now if new_staff_id is not None else task.assigned_at

        # ---- 既有 task 历史（追加式）+ 统一 delegation history ----
        self.db.add(
            ProcedureRowTaskHistory(
                task_id=task.id,
                project_id=req.project_id,
                event_type=f"{req.target_role}_{action}",
                old_assignee_staff_id=(old_staff_id if req.target_role == "assignee" else None),
                new_assignee_staff_id=(new_staff_id if req.target_role == "assignee" else None),
                old_reviewer_staff_id=(old_staff_id if req.target_role == "reviewer" else None),
                new_reviewer_staff_id=(new_staff_id if req.target_role == "reviewer" else None),
                actor_user_id=req.actor_user_id,
                reason=req.scope_reason,
                request_id=req.request_id,
                assignment_version=task.assignment_version,
                lock_version=task.lock_version,
                definition_revision_hash=task.definition_revision_hash,
                audit_cycle_snapshot=task.audit_cycle_snapshot,
            )
        )
        await self._record_history(
            request_id=req.request_id,
            project_id=req.project_id,
            wp_index_id=task.wp_index_id,
            wp_id=task.wp_id,
            layer="row",
            target_role=req.target_role,
            action=action,
            task_id=task.id,
            sheet_key=task.sheet_key,
            old_user_id=old_user_id,
            new_user_id=new_user_id,
            old_staff_id=old_staff_id,
            new_staff_id=new_staff_id,
            actor_user_id=req.actor_user_id,
            reason=req.scope_reason,
            scope_before=scope_before,
            scope_after=scope_after,
        )
        epoch = await self._bump_epoch(
            req.project_id, "delegation", req.request_id, req.actor_user_id,
            {"layer": "row", "role": req.target_role, "action": action, "task_id": str(task.id)},
        )
        await self.db.flush()
        return DelegationResult(
            ok=True, layer="row", target_role=req.target_role, action=action,
            wp_index_id=task.wp_index_id, user_id=new_user_id, staff_id=new_staff_id,
            epoch=epoch, idempotent=False,
        )

    async def record_row_visibility_effects(
        self,
        *,
        project_id: UUID,
        task: "ProcedureRowTask",
        actor_user_id: UUID,
        old_assignee_staff_id: UUID | None,
        new_assignee_staff_id: UUID | None,
        old_reviewer_staff_id: UUID | None,
        new_reviewer_staff_id: UUID | None,
        request_id: str | None = None,
        reason: str | None = None,
    ) -> dict:
        """记录程序行委派/转派的 visibility 副作用（统一历史 + policy epoch + invalidation outbox）。

        由 ProcedureRowDelegationCoordinator 在 TransitionService 成功后同事务调用。
        不写 task 字段本身（那是 TransitionService 职责）；只写审计历史 + epoch + outbox。
        """
        # 判定 action
        if new_assignee_staff_id is None and old_assignee_staff_id is not None:
            action = "clear"
        elif old_assignee_staff_id is None:
            action = "assign"
        elif old_assignee_staff_id != new_assignee_staff_id:
            action = "reassign"
        elif old_reviewer_staff_id != new_reviewer_staff_id:
            action = "reviewer_update"
        else:
            action = "noop"

        # 判定 target_role
        if old_assignee_staff_id != new_assignee_staff_id:
            target_role = "assignee"
        else:
            target_role = "reviewer"

        old_user_id = await self._staff_to_user(project_id, old_assignee_staff_id)
        new_user_id = await self._staff_to_user(project_id, new_assignee_staff_id)
        scope_before, scope_after = await self._current_scope_pair(project_id, new_user_id or old_user_id)

        await self._record_history(
            request_id=request_id,
            project_id=project_id,
            wp_index_id=task.wp_index_id,
            wp_id=task.wp_id,
            layer="row",
            target_role=target_role,
            action=action,
            task_id=task.id,
            sheet_key=task.sheet_key,
            old_user_id=old_user_id,
            new_user_id=new_user_id,
            old_staff_id=old_assignee_staff_id if target_role == "assignee" else old_reviewer_staff_id,
            new_staff_id=new_assignee_staff_id if target_role == "assignee" else new_reviewer_staff_id,
            actor_user_id=actor_user_id,
            reason=reason,
            scope_before=scope_before,
            scope_after=scope_after,
        )
        epoch = await self._bump_epoch(
            project_id, "delegation", request_id, actor_user_id,
            {"layer": "row", "role": target_role, "action": action, "task_id": str(task.id)},
        )
        await self.db.flush()
        return {"epoch": epoch, "action": action, "target_role": target_role}

    # ==================================================================
    # 成员/角色变更入口共用：同事务 epoch + invalidation outbox（Req 14.20）
    # ==================================================================
    async def bump_policy_epoch(
        self,
        project_id: UUID,
        change_type: str,
        *,
        request_id: str | None = None,
        actor_user_id: UUID | None = None,
        detail: dict | None = None,
    ) -> int:
        """供 ProjectUser/ProjectAssignment/角色变更等入口在同一事务内调用。

        不能提交后 best-effort 才失效——调用方须在业务变更的同一事务（同一 flush 单元 / 同一
        router commit）内调用本方法，随后统一 commit 即原子。
        """
        return await self._bump_epoch(
            project_id, change_type, request_id, actor_user_id, detail or {}
        )

    # ==================================================================
    # 内部实现
    # ==================================================================
    async def _resolve_lead_wp_index(self, req: LeadDelegationRequest) -> UUID:
        """联合唯一解析 wp_index；解析失败 fail-closed（Req 4.11）。"""
        sources = ProcedureBindingSources(
            project_id=req.project_id,
            procedure_instance_id=req.procedure_instance_id,
            procedure_code=req.procedure_code,
            audit_cycle=req.audit_cycle,
            wp_index_id=req.wp_index_id,
            wp_id=req.wp_id,
            wp_code=req.wp_code,
        )
        resolution = await self.resolver.resolve(sources)
        if not resolution.ok or resolution.wp_index_id is None:
            raise DelegationError(
                DelegationRejectReason.binding_conflict,
                f"wp_index 解析失败: {resolution.reason}",
            )
        return resolution.wp_index_id

    async def _load_wp_index(
        self, project_id: UUID, wp_index_id: UUID
    ) -> WpIndex | None:
        return (
            await self.db.execute(
                sa.select(WpIndex).where(
                    WpIndex.id == wp_index_id,
                    WpIndex.project_id == project_id,
                    WpIndex.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()

    async def _lock_working_papers(
        self, project_id: UUID, wp_index_id: UUID
    ) -> list[WorkingPaper]:
        return list(
            (
                await self.db.execute(
                    sa.select(WorkingPaper)
                    .where(
                        WorkingPaper.project_id == project_id,
                        WorkingPaper.wp_index_id == wp_index_id,
                        WorkingPaper.is_deleted == sa.false(),
                    )
                    .order_by(WorkingPaper.file_version.desc())
                    .with_for_update()
                )
            ).scalars().all()
        )

    async def _lock_projection_instances(
        self, req: LeadDelegationRequest
    ) -> list[ProcedureInstance]:
        """锁定 lead 投影目标实例。

        - 指定 procedure_instance_id → 仅该实例（须属于项目）。
        - 否则按 wp_code（若提供）在项目内匹配全部实例。
        """
        if req.procedure_instance_id is not None:
            inst = (
                await self.db.execute(
                    sa.select(ProcedureInstance)
                    .where(
                        ProcedureInstance.id == req.procedure_instance_id,
                        ProcedureInstance.project_id == req.project_id,
                        ProcedureInstance.is_deleted == sa.false(),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if inst is None:
                raise DelegationError(
                    DelegationRejectReason.instance_not_found, "程序实例不存在"
                )
            return [inst]
        code = (req.wp_code or "").strip()
        if not code:
            return []
        return list(
            (
                await self.db.execute(
                    sa.select(ProcedureInstance)
                    .where(
                        ProcedureInstance.project_id == req.project_id,
                        ProcedureInstance.wp_code == code,
                        ProcedureInstance.is_deleted == sa.false(),
                    )
                    .with_for_update()
                )
            ).scalars().all()
        )

    async def _staff_to_user(
        self, project_id: UUID, staff_id: UUID | None
    ) -> UUID | None:
        if staff_id is None:
            return None
        resolution = await self.mapping.resolve_active_project_mapping(project_id, staff_id)
        return resolution.user_id if resolution.ok else None

    async def _current_scope_pair(
        self, project_id: UUID, user_id: UUID | None
    ) -> tuple[list[str], list[str]]:
        """清空/撤销时的 scope 快照；撤销不改 scope（Req 6.8），before==after。"""
        if user_id is None:
            return [], []
        raw = (
            await self.db.execute(
                sa.select(ProjectUser.scope_cycles).where(
                    ProjectUser.project_id == project_id,
                    ProjectUser.user_id == user_id,
                    ProjectUser.is_deleted == sa.false(),
                )
            )
        ).scalar()
        cur = sorted(self._parse_scope(raw))
        return cur, cur

    async def _find_idempotent(
        self,
        request_id: str | None,
        project_id: UUID,
        *,
        layer: str,
        target_role: str,
        task_id: UUID | None = None,
    ) -> WorkpaperDelegationHistory | None:
        """幂等命中：非空 request_id 已在同 project+layer+target(+task) 落过 history。"""
        rid = (request_id or "").strip()
        if not rid:
            return None
        conds = [
            WorkpaperDelegationHistory.request_id == rid,
            WorkpaperDelegationHistory.project_id == project_id,
            WorkpaperDelegationHistory.layer == layer,
            WorkpaperDelegationHistory.target_role == target_role,
        ]
        if task_id is not None:
            conds.append(WorkpaperDelegationHistory.task_id == task_id)
        return (
            await self.db.execute(
                sa.select(WorkpaperDelegationHistory)
                .where(*conds)
                .order_by(WorkpaperDelegationHistory.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _record_history(
        self,
        *,
        request_id: str | None,
        project_id: UUID,
        wp_index_id: UUID,
        wp_id: UUID | None,
        layer: str,
        target_role: str,
        action: str,
        task_id: UUID | None,
        sheet_key: str | None,
        old_user_id: UUID | None,
        new_user_id: UUID | None,
        old_staff_id: UUID | None,
        new_staff_id: UUID | None,
        actor_user_id: UUID,
        reason: str | None,
        scope_before: list[str],
        scope_after: list[str],
    ) -> None:
        self.db.add(
            WorkpaperDelegationHistory(
                request_id=request_id,
                project_id=project_id,
                wp_index_id=wp_index_id,
                wp_id=wp_id,
                layer=layer,
                target_role=target_role,
                action=action,
                task_id=task_id,
                sheet_key=sheet_key,
                old_user_id=old_user_id,
                new_user_id=new_user_id,
                old_staff_id=old_staff_id,
                new_staff_id=new_staff_id,
                actor_user_id=actor_user_id,
                reason=reason,
                scope_before=scope_before,
                scope_after=scope_after,
            )
        )

    async def _bump_epoch(
        self,
        project_id: UUID,
        change_type: str,
        request_id: str | None,
        actor_user_id: UUID | None,
        detail: dict,
    ) -> int:
        """持久单调递增 policy epoch + 写 invalidation outbox（同事务，Req 14.20）。"""
        stmt = (
            pg_insert(WpVisibilityPolicyEpoch)
            .values(project_id=project_id, epoch=1)
            .on_conflict_do_update(
                index_elements=[WpVisibilityPolicyEpoch.project_id],
                set_={
                    "epoch": WpVisibilityPolicyEpoch.epoch + 1,
                    "updated_at": sa.func.now(),
                },
            )
            .returning(WpVisibilityPolicyEpoch.epoch)
        )
        epoch = (await self.db.execute(stmt)).scalar_one()
        self.db.add(
            WpVisibilityInvalidationOutbox(
                project_id=project_id,
                epoch=epoch,
                change_type=change_type,
                request_id=request_id,
                actor_user_id=actor_user_id,
                detail=detail,
            )
        )
        return int(epoch)
