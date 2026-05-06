"""Phase 14: SoD 职责分离守卫服务

对齐 v2 WP-ENT-04 + 4.5.14 角色冲突与回避规则
编制/复核/签字/放行互斥矩阵 + 服务端强校验
"""
import uuid
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase14_enums import (
    SoDRole, TraceEventType, TraceObjectType, ReasonCode
)
from app.services.trace_event_service import trace_event_service, generate_trace_id

logger = logging.getLogger(__name__)

# SoD 互斥矩阵（对齐 v2 4.5.14）
# key: (已有角色, 目标角色) → 冲突描述
CONFLICT_MATRIX: dict[tuple[str, str], str] = {
    (SoDRole.preparer, SoDRole.partner_approver): "同人编制+终审同一底稿",
    (SoDRole.partner_approver, SoDRole.preparer): "同人编制+终审同一底稿",
    (SoDRole.preparer, SoDRole.reviewer): "经理复核本人编制底稿",
    (SoDRole.reviewer, SoDRole.preparer): "经理复核本人编制底稿",
    (SoDRole.qc_reviewer, SoDRole.preparer): "质控人员参与被抽查底稿修改",
    (SoDRole.preparer, SoDRole.qc_reviewer): "质控人员参与被抽查底稿修改",
}

# policy_code 映射
POLICY_CODES: dict[tuple[str, str], str] = {
    (SoDRole.preparer, SoDRole.partner_approver): "SOD_PREPARER_APPROVER_CONFLICT",
    (SoDRole.partner_approver, SoDRole.preparer): "SOD_PREPARER_APPROVER_CONFLICT",
    (SoDRole.preparer, SoDRole.reviewer): "SOD_PREPARER_REVIEWER_CONFLICT",
    (SoDRole.reviewer, SoDRole.preparer): "SOD_PREPARER_REVIEWER_CONFLICT",
    (SoDRole.qc_reviewer, SoDRole.preparer): "SOD_QC_PREPARER_CONFLICT",
    (SoDRole.preparer, SoDRole.qc_reviewer): "SOD_QC_PREPARER_CONFLICT",
}


@dataclass
class SoDCheckResult:
    allowed: bool
    conflict_type: Optional[str] = None
    policy_code: Optional[str] = None
    trace_id: str = ""


class SoDGuardService:
    """SoD 职责分离守卫"""

    async def check(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_role: str,
    ) -> SoDCheckResult:
        """校验角色冲突

        1. 查询 actor_id 在该底稿上的已有角色
        2. 与 target_role 做互斥矩阵比对
        3. 冲突时写 trace_events
        """
        trace_id = generate_trace_id()

        # 延迟导入避免循环依赖
        from app.models.workpaper_models import WorkingPaper

        # 查询底稿的角色分配
        stmt = select(WorkingPaper).where(WorkingPaper.id == wp_id)
        result = await db.execute(stmt)
        wp = result.scalar_one_or_none()

        if not wp:
            return SoDCheckResult(allowed=True, trace_id=trace_id)

        # 收集 actor_id 在此底稿上的已有角色
        existing_roles: list[str] = []
        if hasattr(wp, 'preparer_id') and wp.preparer_id == actor_id:
            existing_roles.append(SoDRole.preparer)
        if hasattr(wp, 'reviewer_id') and wp.reviewer_id == actor_id:
            existing_roles.append(SoDRole.reviewer)
        if hasattr(wp, 'partner_reviewed_by') and wp.partner_reviewed_by == actor_id:
            existing_roles.append(SoDRole.partner_approver)

        # 检查互斥矩阵
        for existing_role in existing_roles:
            conflict_key = (existing_role, target_role)
            if conflict_key in CONFLICT_MATRIX:
                conflict_type = CONFLICT_MATRIX[conflict_key]
                policy_code = POLICY_CODES.get(conflict_key, "SOD_CONFLICT_DETECTED")

                # 写 trace_events
                await trace_event_service.write(
                    db=db,
                    project_id=project_id,
                    event_type=TraceEventType.sod_checked,
                    object_type=TraceObjectType.workpaper,
                    object_id=wp_id,
                    actor_id=actor_id,
                    action=f"sod_check:{existing_role}->{target_role}",
                    decision="block",
                    reason_code=ReasonCode.SOD_CONFLICT,
                    trace_id=trace_id,
                )

                logger.warning(
                    f"[SOD_CONFLICT] actor={actor_id} wp={wp_id} "
                    f"existing={existing_role} target={target_role} "
                    f"conflict={conflict_type} trace={trace_id}"
                )

                return SoDCheckResult(
                    allowed=False,
                    conflict_type=conflict_type,
                    policy_code=policy_code,
                    trace_id=trace_id,
                )

        # 无冲突
        await trace_event_service.write(
            db=db,
            project_id=project_id,
            event_type=TraceEventType.sod_checked,
            object_type=TraceObjectType.workpaper,
            object_id=wp_id,
            actor_id=actor_id,
            action=f"sod_check:none->{target_role}",
            decision="allow",
            trace_id=trace_id,
        )

        return SoDCheckResult(allowed=True, trace_id=trace_id)

    async def check_assignment_independence(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        staff_id: uuid.UUID,
        new_role: str,
    ) -> None:
        """DB 级 EQCR 独立性校验（委托给 EqcrIndependenceRule）。"""
        await eqcr_independence_rule.check(db, project_id, staff_id, new_role)


# 全局单例
sod_guard_service = SoDGuardService()



# ---------------------------------------------------------------------------
# R5 任务 2：EQCR 独立性规则
# ---------------------------------------------------------------------------


class SodViolation(Exception):
    """SOD 违规异常，由规则在检出冲突时抛出。

    上层 router 捕获后返回 409 或 403，并在消息中带上违规描述。
    ``policy_code`` 用于前端做错误分类映射。
    """

    def __init__(self, message: str, *, policy_code: str = "SOD_VIOLATION") -> None:
        super().__init__(message)
        self.policy_code = policy_code
        self.message = message


class EqcrIndependenceRule:
    """EQCR 独立性规则 — 同项目内 EQCR 不得同时担任 signing_partner / manager / auditor。

    设计文档 ``.kiro/specs/refinement-round5-independent-review/design.md``
    "SOD 规则细节" 原文：

    - 若当前委派目标是 ``eqcr``：同项目内该人若已是 signing_partner / manager /
      auditor 中任一角色 → 拒绝。
    - 若当前委派目标是 signing_partner / manager / auditor：同项目内该人若
      已是 ``eqcr`` → 拒绝。
    - 其他 role（如 qc）与 EQCR 无冲突。
    - 跨项目不做限制：A 项目 EQCR，B 项目 manager 是合法场景。

    两种调用模式：

    - **DB 模式**（默认，单次新增/单次更新）：传入 ``proposed_roles=None``，
      规则去查 ``project_assignments`` 表中 ``is_deleted=False`` 的现存委派。
    - **批量模式**（``assignment_service.save_assignments``）：传入
      ``proposed_roles=[(staff_id, role), ...]`` 作为"本次将形成的终态"，
      规则只在该 list 内做冲突检查（原有数据会被批次软删除，不计入）。
    """

    CONFLICT_ROLES: frozenset[str] = frozenset(
        {"signing_partner", "manager", "auditor"}
    )
    POLICY_CODE = "SOD_EQCR_INDEPENDENCE_CONFLICT"

    async def check(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        staff_id: uuid.UUID,
        new_role: str,
        *,
        proposed_roles: Optional[list[tuple[uuid.UUID, str]]] = None,
    ) -> None:
        """校验一次委派是否违反 EQCR 独立性。

        无违规时无返回值；违规抛 :class:`SodViolation`。
        """
        # 非相关角色直接放行（例如 qc / 自定义 role）
        if new_role != "eqcr" and new_role not in self.CONFLICT_ROLES:
            return

        existing_roles = await self._collect_existing_roles(
            db,
            project_id=project_id,
            staff_id=staff_id,
            new_role=new_role,
            proposed_roles=proposed_roles,
        )

        if new_role == "eqcr":
            conflict = next(
                (r for r in existing_roles if r in self.CONFLICT_ROLES), None
            )
            if conflict is not None:
                raise SodViolation(
                    (
                        f"同项目内该人员已是 {conflict} 角色，"
                        "不能再担任 EQCR（独立复核合伙人）"
                    ),
                    policy_code=self.POLICY_CODE,
                )
        else:  # new_role in CONFLICT_ROLES
            if "eqcr" in existing_roles:
                raise SodViolation(
                    (
                        "同项目内该人员已是 EQCR（独立复核合伙人），"
                        f"不能再担任 {new_role}"
                    ),
                    policy_code=self.POLICY_CODE,
                )

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    async def _collect_existing_roles(
        self,
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
        staff_id: uuid.UUID,
        new_role: str,
        proposed_roles: Optional[list[tuple[uuid.UUID, str]]],
    ) -> list[str]:
        """收集同项目下同 staff 的已有角色（排除本次正在处理的 new_role）。"""
        if proposed_roles is not None:
            return [
                r
                for (sid, r) in proposed_roles
                if sid == staff_id and r != new_role
            ]

        # 延迟导入避免循环依赖
        from app.models.staff_models import ProjectAssignment

        stmt = select(ProjectAssignment.role).where(
            ProjectAssignment.project_id == project_id,
            ProjectAssignment.staff_id == staff_id,
            ProjectAssignment.is_deleted == False,  # noqa: E712
            ProjectAssignment.role != new_role,
        )
        result = await db.execute(stmt)
        return [row[0] for row in result.all()]


# 规则单例（对齐 ``sod_guard_service`` 命名风格）
eqcr_independence_rule = EqcrIndependenceRule()


# ---------------------------------------------------------------------------
# 兼容 API：供 test_eqcr_sod.py 和 assignment_service 调用
# ---------------------------------------------------------------------------


def validate_eqcr_sod_in_batch(assignments: list[dict]) -> None:
    """批内 EQCR 独立性预检（纯函数，不访问 DB）。

    遍历 assignments 列表，检查同一 staff_id 是否同时持有 eqcr 与
    signing_partner/manager/auditor/qc 角色。违规抛 :class:`SodViolation`。

    Args:
        assignments: [{"staff_id": str, "role": str}, ...]
    """
    if not assignments:
        return

    # 按 staff_id 分组收集角色
    staff_roles: dict[str, set[str]] = {}
    for item in assignments:
        sid = item.get("staff_id", "")
        role = item.get("role", "")
        if not sid or not role:
            continue
        staff_roles.setdefault(sid, set()).add(role)

    conflict_roles = EqcrIndependenceRule.CONFLICT_ROLES | {"qc"}

    for staff_id, roles in staff_roles.items():
        if "eqcr" not in roles:
            continue
        conflicts = roles & conflict_roles
        if conflicts:
            raise SodViolation(
                f"人员 {staff_id} 在同批次中同时持有 eqcr 与 {sorted(conflicts)} 角色，违反独立性",
                policy_code=EqcrIndependenceRule.POLICY_CODE,
            )



