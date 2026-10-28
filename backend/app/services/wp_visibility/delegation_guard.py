"""委派前置拦截：只能委派保留项、被委派人须看得到（spec procedure-trim-generation-delegation-chain 需求 4）。

从 ``delegation_transaction`` 拆出（行数门）：拒绝原因与错误类型、裁剪 / 回收站拦截、有效循环范围校验与扩权。
``DelegationTransactionService`` 继承 :class:`DelegationGuardMixin`，调用方式与导入路径不变
（``delegation_transaction`` 仍导出 ``DelegationError`` / ``DelegationRejectReason``）。
"""

from __future__ import annotations

import enum
from uuid import UUID

import sqlalchemy as sa

from app.models.core import ProjectUser
from app.models.procedure_models import ProcedureRowTask
from app.models.workpaper_models import WpIndex


class DelegationRejectReason(str, enum.Enum):
    """委派拒绝原因（内部诊断；调用方回滚事务）。"""

    binding_conflict = "binding_conflict"    # procedure→wp_index 解析失败（Req 4.11）
    mapping_invalid = "mapping_invalid"       # staff→user 严格映射不成立（Req 3.1–3.6）
    out_of_scope = "out_of_scope"             # 跨循环且未显式扩权（Req 6.1）
    scope_reason_missing = "scope_reason_missing"  # 扩权缺非空理由（Req 6.3）
    clear_target_missing = "clear_target_missing"  # 清空未指定目标层/task（Req 3.7/3.8）
    task_not_found = "task_not_found"         # 目标 ProcedureRowTask 缺失/跨项目
    instance_not_found = "instance_not_found"  # 目标 ProcedureInstance 缺失/跨项目
    invalid_request = "invalid_request"       # 请求结构非法（如既非清空又无 staff）
    # spec procedure-trim-generation-delegation-chain 需求 4：只能委派保留项、被委派人须能看到
    trimmed = "trimmed"                       # 底稿已粗裁 / 程序行已细裁不适用
    recycled = "recycled"                     # 底稿已移入回收站
    trim_scope_unavailable = "trim_scope_unavailable"  # 读不到裁剪结果（fail-closed）
    not_project_member = "not_project_member"  # 被委派人没有本项目成员行，无从扩大可见范围


#: 拒绝原因 → HTTP 状态（其余 400）
_HTTP_STATUS = {
    DelegationRejectReason.trimmed: 409,
    DelegationRejectReason.recycled: 409,
    DelegationRejectReason.trim_scope_unavailable: 503,
}


class DelegationError(Exception):
    """委派事务失败（fail-closed）；调用方不应 commit，须回滚全部事务内变更。

    ``cycles``：跨循环被拒时被委派人缺少的循环（前端据此提示并带理由扩权重试）。
    """

    def __init__(self, reason: DelegationRejectReason, message: str = "", *, cycles: list[str] | None = None):
        self.reason = reason
        self.cycles = list(cycles or [])
        super().__init__(message or reason.value)

    @property
    def http_status(self) -> int:
        return _HTTP_STATUS.get(self.reason, 400)

    def http_detail(self, error: str = "lead_delegation_rejected") -> dict:
        """统一错误体：前端按 ``reason == "out_of_scope"`` 提示填写理由后带 ``expand_scope`` 重试。"""
        return {"error": error, "reason": self.reason.value, "message": str(self), "cycles": self.cycles}


class DelegationGuardMixin:
    """裁剪拦截 + 有效循环范围（宿主须提供 ``db`` / ``_load_wp_index`` 与两个缓存属性）。"""

    db: object
    _trim_scope_cache: dict
    _deferred_scope_gaps: dict[UUID, set[str]] | None

    @staticmethod
    def _parse_scope(raw: str | None) -> set[str]:
        if raw and isinstance(raw, str) and raw.strip():
            return {c.strip() for c in raw.split(",") if c.strip()}
        return set()

    async def assert_row_task_delegable(self, project_id: UUID, task: ProcedureRowTask) -> WpIndex:
        """程序行可委派：该行适用且未取消、所在底稿未进回收站、未被粗裁。返回所在底稿索引。"""
        if task.applicability_status != "execute" or task.workflow_status == "cancelled":
            raise DelegationError(DelegationRejectReason.trimmed, "该程序行已裁剪为不适用或已取消，不能委派")
        wp_index = await self._load_wp_index(project_id, task.wp_index_id)  # type: ignore[attr-defined]
        if wp_index is None:
            raise DelegationError(
                DelegationRejectReason.recycled, "该程序行所在底稿已移入回收站，不能委派；如需编制请先恢复底稿"
            )
        await self._reject_if_trimmed(project_id, wp_index.wp_code)
        return wp_index

    async def _reject_if_trimmed(self, project_id: UUID, wp_code: str | None) -> None:
        """底稿编码已在程序裁剪中标为不执行（含跟随科目的子表 / 程序表）⇒ 拒绝委派。读不到裁剪结果同样拒绝。"""
        from app.services.procedure_scope_retention import TrimScopeUnavailable, load_trimmed_scope

        if not (wp_code or "").strip():
            return
        cache = self._trim_scope_cache
        if project_id not in cache:
            try:
                cache[project_id] = await load_trimmed_scope(self.db, project_id)  # type: ignore[arg-type]
            except TrimScopeUnavailable as exc:
                raise DelegationError(
                    DelegationRejectReason.trim_scope_unavailable, "无法读取程序裁剪结果，暂不能委派，请稍后重试"
                ) from exc
        owner = cache[project_id].trim_owner(wp_code)
        if owner:
            follow = "" if owner == (wp_code or "").strip().upper() else f"（跟随 {owner}）"
            raise DelegationError(
                DelegationRejectReason.trimmed,
                f"底稿 {wp_code} 已在程序裁剪中标为不执行{follow}，不能委派；如需编制请先在程序裁剪中恢复执行",
            )

    async def _enforce_scope(
        self,
        project_id: UUID,
        user_id: UUID,
        audit_cycle: str | None,
        expand_scope: bool,
        scope_reason: str | None,
    ) -> tuple[list[str], list[str]]:
        """单个目标循环的 scope 校验 + 可选扩权（Req 6.1–6.7），见 :meth:`ensure_cycles_in_scope`。"""
        before, after, _added = await self.ensure_cycles_in_scope(
            project_id, user_id, [audit_cycle] if audit_cycle else [],
            expand_scope=expand_scope, scope_reason=scope_reason,
        )
        return before, after

    async def ensure_cycles_in_scope(
        self,
        project_id: UUID,
        user_id: UUID | None,
        cycles,
        *,
        expand_scope: bool,
        scope_reason: str | None,
        who: str = "被委派人",
    ) -> tuple[list[str], list[str], list[str]]:
        """被委派人的有效循环范围须覆盖 ``cycles``；返回 ``(before, after, added)``（排序后，供历史快照）。

        有效范围取 ``effective_scope.resolve_member_scope``（需求 5）：主管（经理 / 合伙人 / 质控 / EQCR）与系统
        管理员 ⇒ 全部循环、不校验；受限 = 团队分配勾选 ∪ ``project_users.scope_cycles``。原先只看
        ``scope_cycles``，团队分配勾选的循环不算、主管也被拦。
        - 都在范围内 → 不改，before == after。
        - 缺循环且未扩权 → 拒绝（Req 6.1），错误带缺少的循环；批量收集模式下只记下、处理完统一报。
        - 扩权：须非空理由（Req 6.3），同事务只把缺少的循环写进 ``scope_cycles``（Req 6.4）。
        - 被委派人没有本项目成员行 ⇒ 无从扩权，直接拒绝（``not_project_member``）。
        """
        from app.services.wp_visibility.effective_scope import resolve_member_scope

        wanted = sorted({str(c).strip() for c in cycles if str(c or "").strip()})
        if user_id is None:
            if wanted:
                raise DelegationError(
                    DelegationRejectReason.not_project_member, f"{who}没有关联可登录的用户账号，不能委派"
                )
            return [], [], []
        member = await resolve_member_scope(self.db, project_id, user_id)  # type: ignore[arg-type]
        before = sorted(member.cycles)
        missing = [] if member.is_supervisor else [c for c in wanted if c not in member.cycles]
        if not missing:
            return before, before, []
        if not member.is_member:
            raise DelegationError(
                DelegationRejectReason.not_project_member,
                f"{who}不是本项目成员，不能委派；请先在团队分配中加入", cycles=missing,
            )
        if not expand_scope:
            if self._deferred_scope_gaps is not None:
                self._deferred_scope_gaps.setdefault(user_id, set()).update(missing)
                return before, before, []
            raise DelegationError(
                DelegationRejectReason.out_of_scope,
                f"{who}的可见范围不含 {'、'.join(missing)} 循环（团队分配勾选："
                f"{'、'.join(sorted(member.assigned)) or '无'}），填写理由后可扩大其可见范围",
                cycles=missing,
            )
        if not (scope_reason or "").strip():
            raise DelegationError(
                DelegationRejectReason.scope_reason_missing, "扩大可见范围必须填写理由", cycles=missing
            )
        rows = list((
            await self.db.execute(  # type: ignore[attr-defined]
                sa.select(ProjectUser)
                .where(
                    ProjectUser.project_id == project_id,
                    ProjectUser.user_id == user_id,
                    ProjectUser.is_deleted == sa.false(),
                )
                .with_for_update()
            )
        ).scalars().all())
        if len(rows) != 1:
            raise DelegationError(
                DelegationRejectReason.mapping_invalid,
                f"{who}的项目成员记录不唯一（{len(rows)} 条），无法扩大可见范围", cycles=missing,
            )
        rows[0].scope_cycles = ",".join(sorted(self._parse_scope(rows[0].scope_cycles) | set(missing)))
        return before, sorted(member.cycles | set(missing)), missing

    def defer_scope_gaps(self) -> None:
        """批量委派开始：缺循环先记下不立即报（配合 :meth:`raise_deferred_scope_gaps`，同一事务内）。"""
        self._deferred_scope_gaps = {}

    def raise_deferred_scope_gaps(self) -> None:
        """批量委派结束：有缺少的循环就一次报全（调用方回滚整批）。"""
        gaps, self._deferred_scope_gaps = self._deferred_scope_gaps, None
        if not gaps:
            return
        cycles = sorted(set().union(*gaps.values()))
        who = f"{len(gaps)} 位被委派人" if len(gaps) > 1 else "被委派人"
        raise DelegationError(
            DelegationRejectReason.out_of_scope,
            f"{who}的可见范围不含 {'、'.join(cycles)} 循环，填写理由后可扩大其可见范围",
            cycles=cycles,
        )
