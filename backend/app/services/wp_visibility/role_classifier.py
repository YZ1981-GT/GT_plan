"""唯一角色分类入口（Task 3 / 组件 C3）

Feature: procedure-delegation-visibility-isolation
Requirements: 1.1–1.11（唯一角色分类与 Non_Admin scope 上界）
Design: "Role Classification" / Property 1（唯一 & fail-closed）/ Property 5

分类顺序严格遵循 Req 1.2 → 1.5：
  1. system ``admin`` → Admin_User（忽略 scope_cycles，仍受 Action_Matrix；本任务只输出分类）。
  2. Non_Admin 同时满足以下三条唯一链路 → Supervisor：
       - 当前 user 唯一 active StaffMember；
       - 该 staff 在当前项目唯一 active ProjectAssignment，且 **角色权威** role ∈
         {partner, signing_partner, manager, qc, eqcr}；
       - 当前 user 在当前项目唯一 active ProjectUser（**scope 权威**）。
  3. 其余 → Restricted_User。
  4. 未知角色 / 角色未登记 / 映射数≠1 / 成员链路数≠1 / 查询异常 → fail-closed Restricted_User，
     不抛 500、不泄露内部错误。

**角色来源单一**：角色权威 = ProjectAssignment.role；scope 权威 = ProjectUser.scope_cycles。
禁止在两者之间任选角色来源。``scope_cycles`` 缺失/查询失败一律解释为空集（Req 1.9/1.10）。
Non_Admin 恒携带 scope 上界；Admin 恒空 scope（Req 1.8）。

纯读、无写副作用；service 约定只 flush 不 commit。所有分支 try/except 收敛到 Restricted。
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.wp_visibility.contracts import VisibilityContext, VisibilityRole

logger = logging.getLogger(__name__)

# Supervisor 允许的项目角色（**角色权威 = ProjectAssignment.role**，自由文本，规范化小写比较）。
# 含 qc/eqcr（复核类主管），比 Delegator 写权限角色集更宽。
SUPERVISOR_ASSIGNMENT_ROLES: frozenset[str] = frozenset(
    {"partner", "signing_partner", "manager", "qc", "eqcr"}
)


class VisibilityRoleClassifier:
    """唯一角色分类器：输出 Admin/Supervisor/Restricted 之一且唯一。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def classify(
        self, current_user: User, project_id: UUID
    ) -> VisibilityContext:
        """为当前 user 在指定项目产出唯一 ``VisibilityContext``（Req 1.1–1.11）。"""
        # ① system admin：唯一忽略 scope 的类别（Req 1.2/1.8）
        try:
            if current_user.role.value == "admin":
                return VisibilityContext(
                    user_id=current_user.id,
                    project_id=project_id,
                    role=VisibilityRole.admin,
                    is_admin=True,
                    scope_cycles=frozenset(),
                )
        except Exception as exc:  # noqa: BLE001 — role 缺失/异常 fail-closed
            logger.warning("角色分类：admin 判定异常 user=%s: %s", current_user.id, exc)
            return self._restricted(current_user.id, project_id, frozenset())

        # Non_Admin：先取 scope 上界（缺失/失败 → 空集，Req 1.9/1.10）
        scope_cycles = await self._resolve_scope_cycles(project_id, current_user.id)

        # ② 尝试 Supervisor（三条唯一链路 + 角色属于允许集合）
        try:
            if await self._is_supervisor(current_user.id, project_id):
                return VisibilityContext(
                    user_id=current_user.id,
                    project_id=project_id,
                    role=VisibilityRole.supervisor,
                    is_admin=False,
                    scope_cycles=scope_cycles,
                )
        except Exception as exc:  # noqa: BLE001 — 任意异常 fail-closed → Restricted
            logger.warning(
                "角色分类：supervisor 判定异常 user=%s project=%s: %s",
                current_user.id,
                project_id,
                exc,
            )
            return self._restricted(current_user.id, project_id, scope_cycles)

        # ③/④ 其余 → Restricted（Req 1.4/1.5）
        return self._restricted(current_user.id, project_id, scope_cycles)

    # ------------------------------------------------------------------
    # 内部：Supervisor 三条唯一链路
    # ------------------------------------------------------------------
    async def _is_supervisor(self, user_id: UUID, project_id: UUID) -> bool:
        """当前 user 是否满足 Supervisor 的三条唯一 active 链路（Req 1.3）。"""
        # (a) 唯一 active StaffMember（映射权威链路起点）
        staff_id = await self._unique_active_staff_id(user_id)
        if staff_id is None:
            return False

        # (b) 唯一 active ProjectAssignment（**角色权威**），role ∈ 允许集合
        role = await self._unique_active_assignment_role(project_id, staff_id)
        if role is None or role not in SUPERVISOR_ASSIGNMENT_ROLES:
            return False

        # (c) 唯一 active ProjectUser（**scope 权威**）
        if not await self._has_unique_active_project_user(project_id, user_id):
            return False

        return True

    async def _unique_active_staff_id(self, user_id: UUID) -> UUID | None:
        """当前 user → 唯一 active StaffMember.id；0 或 >1 均返回 None（Req 1.5）。"""
        rows = (
            await self.db.execute(
                sa.select(StaffMember.id).where(
                    StaffMember.user_id == user_id,
                    StaffMember.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
        return rows[0] if len(rows) == 1 else None

    async def _unique_active_assignment_role(
        self, project_id: UUID, staff_id: UUID
    ) -> str | None:
        """唯一 active ProjectAssignment 的规范化 role；0 或 >1 → None（Req 1.5）。"""
        rows = (
            await self.db.execute(
                sa.select(ProjectAssignment.role).where(
                    ProjectAssignment.project_id == project_id,
                    ProjectAssignment.staff_id == staff_id,
                    ProjectAssignment.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
        if len(rows) != 1:
            return None
        return (rows[0] or "").strip().lower()

    async def _has_unique_active_project_user(
        self, project_id: UUID, user_id: UUID
    ) -> bool:
        """当前 user 在项目内是否唯一 active ProjectUser（scope 权威链路，Req 1.5）。"""
        count = (
            await self.db.execute(
                sa.select(sa.func.count()).select_from(ProjectUser).where(
                    ProjectUser.project_id == project_id,
                    ProjectUser.user_id == user_id,
                    ProjectUser.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one()
        return count == 1

    # ------------------------------------------------------------------
    # 内部：scope_cycles（scope 权威 = ProjectUser.scope_cycles）
    # ------------------------------------------------------------------
    async def _resolve_scope_cycles(
        self, project_id: UUID, user_id: UUID
    ) -> frozenset[str]:
        """Non_Admin 的 scope 上界；缺失/查询失败一律空集（Req 1.9/1.10）。"""
        try:
            raw = (
                await self.db.execute(
                    sa.select(ProjectUser.scope_cycles).where(
                        ProjectUser.project_id == project_id,
                        ProjectUser.user_id == user_id,
                        ProjectUser.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalar()
        except Exception as exc:  # noqa: BLE001 — 查询失败 → 空集
            logger.warning(
                "角色分类：scope_cycles 查询异常 user=%s project=%s: %s",
                user_id,
                project_id,
                exc,
            )
            return frozenset()
        if raw and isinstance(raw, str) and raw.strip():
            return frozenset(c.strip() for c in raw.split(",") if c.strip())
        return frozenset()

    @staticmethod
    def _restricted(
        user_id: UUID, project_id: UUID, scope_cycles: frozenset[str]
    ) -> VisibilityContext:
        return VisibilityContext(
            user_id=user_id,
            project_id=project_id,
            role=VisibilityRole.restricted,
            is_admin=False,
            scope_cycles=scope_cycles,
        )
