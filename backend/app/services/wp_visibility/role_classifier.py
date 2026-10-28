"""唯一角色分类入口（Task 3 / 组件 C3）

Feature: procedure-delegation-visibility-isolation
Requirements: 1.1–1.11（唯一角色分类与 Non_Admin scope 上界）
Design: "Role Classification" / Property 1（唯一 & fail-closed）/ Property 5

分类顺序严格遵循 Req 1.2 → 1.5：
  1. system ``admin`` → Admin_User（忽略 scope_cycles，仍受 Action_Matrix；本任务只输出分类）。
  2. Non_Admin 满足以下条件 → Supervisor：
       - 当前 user 唯一 active StaffMember；
       - 该 staff 在当前项目**任一** active ProjectAssignment 的 **角色权威** role 属于合伙人 / 签字合伙人 /
         项目经理 / 质控 / EQCR（含中文别名）；
       - 当前 user 在当前项目唯一 active ProjectUser（**scope 权威**）。
  3. 其余 → Restricted_User。
  4. 未知角色 / 角色未登记 / 映射数≠1 / 成员链路数≠1 / 查询异常 → fail-closed Restricted_User，
     不抛 500、不泄露内部错误。

**角色来源单一**：角色权威 = ProjectAssignment.role。scope 上界 = 有效循环范围：Supervisor 为本项目
全部循环；Restricted 为团队分配勾选（``assigned_cycles``）∪ ``ProjectUser.scope_cycles``（委派扩大），
缺失 / 查询失败一律解释为空集（Req 1.9/1.10）。Non_Admin 恒携带 scope 上界；Admin 恒空 scope（Req 1.8）。

2026-10-24 用户裁决（spec procedure-trim-generation-delegation-chain 需求 5）：经理、合伙人、质控、EQCR
默认看全部循环，审计员按团队分配勾选的循环。主管判定与范围都取 ``effective_scope.resolve_member_scope``
（委派的跨循环校验、``get_user_scope_cycles`` 同一来源）。原先只认唯一一条委派且只认英文角色码、
范围只读 ``ProjectUser.scope_cycles``（团队分配勾选不算、主管也被截断）。

纯读、无写副作用；service 约定只 flush 不 commit。所有分支 try/except 收敛到 Restricted。
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.services.wp_visibility.contracts import VisibilityContext, VisibilityRole
from app.services.wp_visibility.effective_scope import (
    SUPERVISOR_ROLES,
    MemberScope,
    resolve_member_scope,
)

logger = logging.getLogger(__name__)

# Supervisor 允许的项目角色（**角色权威 = ProjectAssignment.role**，自由文本，规范化小写比较）：
# 委派角色映射到合伙人 / 经理 / 质控项目角色的全部写法（英文代码 + 中文别名），与有效范围同一来源。
SUPERVISOR_ASSIGNMENT_ROLES: frozenset[str] = SUPERVISOR_ROLES


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

        # Non_Admin：主管判定与 scope 上界同一来源（任意异常 → Restricted 空 scope，Req 1.5/1.9/1.10）
        member = await self._member_scope(project_id, current_user.id)
        if member.is_supervisor:
            return VisibilityContext(
                user_id=current_user.id,
                project_id=project_id,
                role=VisibilityRole.supervisor,
                is_admin=False,
                scope_cycles=member.cycles,
            )

        # ③/④ 其余 → Restricted（Req 1.4/1.5）
        return self._restricted(current_user.id, project_id, member.cycles)

    async def _member_scope(self, project_id: UUID, user_id: UUID) -> MemberScope:
        """有效循环范围；查询异常 fail-closed 为受限空集。

        ``is_admin`` 只认本次分类的 ``current_user``（上面已短路），库里的系统角色若是 admin 而本次
        user 不是，按受限处理，不借库里的值升级。
        """
        try:
            member = await resolve_member_scope(self.db, project_id, user_id)
        except Exception as exc:  # noqa: BLE001 — 任意异常 fail-closed → Restricted
            logger.warning(
                "角色分类：有效范围判定异常 user=%s project=%s: %s", user_id, project_id, exc
            )
            return MemberScope(False, frozenset(), frozenset(), frozenset(), frozenset())
        if member.is_admin:
            return MemberScope(False, frozenset(), member.assigned, member.expanded, member.roles,
                               member.is_member, True)
        return member

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
