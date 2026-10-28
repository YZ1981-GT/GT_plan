"""程序行委派的保留项判定与被委派人可见范围（spec procedure-trim-generation-delegation-chain 需求 4）。

从 ``procedure_delegation_service`` 拆出（行数门）。``ProcedureDelegationService`` 继承
:class:`DelegationTargetScopeMixin`；程序行状态转换端点的分配 / 转派也复用同一组方法。

- 保留项：所在底稿未进回收站，且按 ``procedure_scope_retention`` 判定未被粗裁（读不到裁剪结果 503）。
- 可见范围：执行人 / 复核人的有效循环范围（``effective_scope``）须覆盖目标任务所在底稿的循环；缺了 ⇒
  400 ``out_of_scope``（带 ``cycles`` 与 ``scope_gaps``），带 ``expand_scope + scope_reason`` ⇒ 同事务只把
  缺少的循环写进 ``project_users.scope_cycles`` 并递增可见性策略版本（change_type ``scope``）。
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException

from app.models.procedure_models import ProcedureRowTask
from app.models.workpaper_models import WpIndex
from app.services.procedure_authorization import normalize_staff_to_user
from app.services.procedure_scope_retention import (
    TrimScopeUnavailable,
    TrimmedScope,
    load_trimmed_scope,
)

#: 程序行委派拒绝体的 ``error``（``reason`` / ``cycles`` 与底稿主编委派同一结构）
ROW_DELEGATION_REJECTED = "row_delegation_rejected"
_IN_CHUNK = 500


class DelegationTargetScopeMixin:
    """宿主须提供 ``db``、``_trim_scopes``（dict）与 ``coordinator``（含 ``visibility``）。"""

    db: object
    _trim_scopes: dict

    async def _trim_scope(self, project_id: UUID) -> TrimmedScope:
        """项目粗裁结果；读不到 ⇒ 503，不按「没有裁剪」继续委派（fail-closed）。"""
        if project_id not in self._trim_scopes:
            try:
                self._trim_scopes[project_id] = await load_trimmed_scope(self.db, project_id)  # type: ignore[arg-type]
            except TrimScopeUnavailable as exc:
                raise HTTPException(
                    status_code=503,
                    detail={"error": "trim_scope_unavailable", "message": "无法读取程序裁剪结果，暂不能委派，请稍后重试"},
                ) from exc
        return self._trim_scopes[project_id]

    async def _live_wp_index_meta(self, project_id: UUID, wp_index_ids) -> dict[UUID, tuple[str, str]]:
        """未进回收站的底稿索引 ``{id: (编码, 循环)}``（软删的不在结果里）。"""
        ids = sorted({i for i in wp_index_ids if i is not None}, key=str)
        meta: dict[UUID, tuple[str, str]] = {}
        for i in range(0, len(ids), _IN_CHUNK):
            rows = await self.db.execute(  # type: ignore[attr-defined]
                sa.select(WpIndex.id, WpIndex.wp_code, WpIndex.audit_cycle).where(
                    WpIndex.project_id == project_id,
                    WpIndex.id.in_(ids[i:i + _IN_CHUNK]),
                    WpIndex.is_deleted == sa.false(),
                )
            )
            meta.update({r[0]: (r[1] or "", (r[2] or "").strip()) for r in rows.all()})
        return meta

    async def _retained_wp_index_ids(self, project_id: UUID, wp_index_ids) -> list[UUID]:
        """保留项：未进回收站且未被粗裁的底稿索引（保持输入顺序）。"""
        meta = await self._live_wp_index_meta(project_id, wp_index_ids)
        scope = await self._trim_scope(project_id)
        return [i for i in wp_index_ids if i in meta and not scope.is_trimmed(meta[i][0])]

    @staticmethod
    def scope_demands(
        plan: dict,
        *,
        assignee_staff_id: UUID,
        reviewer_staff_id: UUID | None,
        cycle_of: dict,
    ) -> list[tuple[str, UUID, list[str]]]:
        """谁需要看到哪些循环：执行人 = 将分配 / 转派的任务；复核人 = 将分配 / 改复核人的任务。"""

        def _cycles(tasks: list[ProcedureRowTask]) -> list[str]:
            return sorted({cycle_of.get(t.wp_index_id) or "" for t in tasks} - {""})

        demands = [("assignee", assignee_staff_id, _cycles(plan.get("assign", []) + plan.get("reassign", [])))]
        if reviewer_staff_id is not None:
            demands.append((
                "reviewer", reviewer_staff_id,
                _cycles(plan.get("assign", []) + plan.get("reviewer_update", [])),
            ))
        return [d for d in demands if d[2]]

    async def scope_gaps(self, project_id: UUID, demands) -> list[dict]:
        """各被委派人有效循环范围缺少的循环（preview 展示与 apply 校验同一口径；主管 / 系统管理员不缺）。"""
        from app.models.staff_models import StaffMember
        from app.services.wp_visibility.effective_scope import resolve_member_scope

        gaps: list[dict] = []
        for role, staff_id, cycles in demands:
            user_id = await normalize_staff_to_user(self.db, staff_id)  # type: ignore[arg-type]
            member = await resolve_member_scope(self.db, project_id, user_id) if user_id else None  # type: ignore[arg-type]
            if member is not None and member.is_supervisor:
                continue
            have = member.cycles if member is not None else frozenset()
            missing = [c for c in cycles if c not in have]
            if not missing:
                continue
            name = (await self.db.execute(  # type: ignore[attr-defined]
                sa.select(StaffMember.name).where(StaffMember.id == staff_id)
            )).scalar()
            gaps.append({
                "role": role,
                "staff_id": str(staff_id),
                "name": name or "",
                "cycles": missing,
                "is_member": bool(member is not None and member.is_member),
            })
        return gaps

    async def enforce_scope(
        self,
        project_id: UUID,
        demands,
        *,
        expand_scope: bool,
        scope_reason: str | None,
        actor_user_id: UUID,
        request_id: str | None,
    ) -> list[dict]:
        """写入前校验：缺循环 ⇒ 400 零写（带 ``cycles`` / ``scope_gaps``）；带理由扩权 ⇒ 同事务写入并递增策略版本。

        返回实际扩大的 ``[{role, staff_id, cycles}]``。
        """
        from app.services.wp_visibility.delegation_guard import DelegationError, DelegationRejectReason

        gaps = await self.scope_gaps(project_id, demands)
        if not gaps:
            return []

        def _who(g: dict) -> str:
            return f"{'执行人' if g['role'] == 'assignee' else '复核人'}{g['name']}"

        outsiders = [g for g in gaps if not g["is_member"]]
        reason: DelegationRejectReason | None = None
        message = ""
        if outsiders:
            reason = DelegationRejectReason.not_project_member
            message = f"{'、'.join(_who(g) for g in outsiders)}不是本项目成员，不能委派；请先在团队分配中加入"
        elif not expand_scope:
            reason = DelegationRejectReason.out_of_scope
            message = "；".join(
                f"{_who(g)}的可见范围不含 {'、'.join(g['cycles'])} 循环" for g in gaps
            ) + "，填写理由后可扩大其可见范围"
        elif not (scope_reason or "").strip():
            reason = DelegationRejectReason.scope_reason_missing
            message = "扩大可见范围必须填写理由"
        if reason is not None:
            cycles = sorted({c for g in gaps for c in g["cycles"]})
            detail = DelegationError(reason, message, cycles=cycles).http_detail(ROW_DELEGATION_REJECTED)
            raise HTTPException(status_code=400, detail={**detail, "scope_gaps": gaps})

        deleg = self.coordinator.visibility  # type: ignore[attr-defined]
        expanded: list[dict] = []
        for g in gaps:
            user_id = await normalize_staff_to_user(self.db, UUID(g["staff_id"]))  # type: ignore[arg-type]
            try:
                _before, _after, added = await deleg.ensure_cycles_in_scope(
                    project_id, user_id, g["cycles"], expand_scope=True, scope_reason=scope_reason, who=_who(g)
                )
            except DelegationError as exc:
                raise HTTPException(
                    status_code=exc.http_status, detail=exc.http_detail(ROW_DELEGATION_REJECTED)
                ) from exc
            if added:
                expanded.append({"role": g["role"], "staff_id": g["staff_id"], "cycles": added})
        if expanded:
            await deleg.bump_policy_epoch(
                project_id, "scope", request_id=request_id, actor_user_id=actor_user_id,
                detail={"expanded": expanded, "reason": (scope_reason or "").strip()},
            )
        return expanded
