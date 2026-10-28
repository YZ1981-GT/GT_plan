"""删除人员档案（spec procedure-chain-hardening-and-java-contracts R12）。

原先 ``DELETE /api/staff/{id}`` 只要求登录、直接软删人员档案：项目分配与项目成员行原样留下 ⇒ 团队页里多出
「已删除的人」，其登录账号照样能进这些项目、照样被委派。

现在：有有效项目分配时默认拒绝（:class:`StaffHasAssignments`，路由回 409 并列出项目）；调用方确认撤权后同事务：
软删这些分配 → 关联的登录用户在这些项目里若再没有别的有效分配（同一账号可关联多份人员档案），软删其项目成员行 →
每个受影响项目递增可见性策略版本（membership，同事务写失效通知）→ 软删人员档案。只 flush 不 commit。
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, ProjectUser
from app.models.staff_models import ProjectAssignment, StaffMember

STAFF_HAS_ASSIGNMENTS = "staff_has_assignments"
_MAX_NAMED = 5


class StaffHasAssignments(Exception):
    """人员仍在项目团队中、调用方未确认撤权。``projects``：``[{project_id, project_name, roles}]``。"""

    def __init__(self, projects: list[dict]):
        super().__init__(STAFF_HAS_ASSIGNMENTS)
        self.projects = projects

    def http_detail(self) -> dict:
        names = "、".join(p["project_name"] for p in self.projects[:_MAX_NAMED])
        more = " 等" if len(self.projects) > _MAX_NAMED else ""
        return {
            "error": STAFF_HAS_ASSIGNMENTS,
            "message": f"该人员仍在 {len(self.projects)} 个项目的团队中（{names}{more}），"
                       "确认删除将同时撤销其在这些项目的团队分配与项目成员权限",
            "projects": self.projects,
        }


async def active_assignment_projects(db: AsyncSession, staff_id: UUID) -> tuple[list[ProjectAssignment], list[dict]]:
    """人员的有效项目分配，及按项目归并的清单（项目名、该人员在项目里的角色）。"""
    rows = (await db.execute(
        sa.select(ProjectAssignment, Project.name)
        .join(Project, Project.id == ProjectAssignment.project_id, isouter=True)
        .where(ProjectAssignment.staff_id == staff_id, ProjectAssignment.is_deleted == sa.false())
        .order_by(Project.name, ProjectAssignment.project_id)
    )).all()
    projects: dict[UUID, dict] = {}
    for assignment, name in rows:
        entry = projects.setdefault(assignment.project_id, {
            "project_id": str(assignment.project_id), "project_name": name or str(assignment.project_id), "roles": [],
        })
        if assignment.role not in entry["roles"]:
            entry["roles"].append(assignment.role)
    return [a for a, _ in rows], list(projects.values())


async def remove_staff(
    db: AsyncSession, staff: StaffMember, *, revoke_assignments: bool, actor_user_id: UUID | None
) -> dict:
    """软删人员档案；有有效分配且未确认撤权 ⇒ 抛 :class:`StaffHasAssignments`（不做任何改动）。"""
    assignments, projects = await active_assignment_projects(db, staff.id)
    if assignments and not revoke_assignments:
        raise StaffHasAssignments(projects)
    project_ids = sorted({a.project_id for a in assignments}, key=str)
    for assignment in assignments:
        assignment.soft_delete()
    revoked_members = 0
    if staff.user_id is not None and project_ids:
        # 同一登录账号经别的人员档案仍在该项目团队里 ⇒ 保留其成员行
        still_assigned = set((await db.execute(
            sa.select(ProjectAssignment.project_id)
            .join(StaffMember, StaffMember.id == ProjectAssignment.staff_id)
            .where(
                StaffMember.user_id == staff.user_id,
                StaffMember.id != staff.id,
                StaffMember.is_deleted == sa.false(),
                ProjectAssignment.project_id.in_(project_ids),
                ProjectAssignment.is_deleted == sa.false(),
            )
        )).scalars())
        revoke_in = [pid for pid in project_ids if pid not in still_assigned]
        if revoke_in:
            members = (await db.execute(sa.select(ProjectUser).where(
                ProjectUser.user_id == staff.user_id,
                ProjectUser.project_id.in_(revoke_in),
                ProjectUser.is_deleted == sa.false(),
            ))).scalars().all()
            for member in members:
                member.soft_delete()
            revoked_members = len(members)
    if project_ids:
        from app.services.wp_visibility.delegation_transaction import DelegationTransactionService

        epochs = DelegationTransactionService(db)
        for pid in project_ids:
            await epochs.bump_policy_epoch(pid, "membership", actor_user_id=actor_user_id,
                                           detail={"kind": "staff_removed", "staff_id": str(staff.id)})
    staff.soft_delete()
    await db.flush()
    return {"revoked_assignments": len(assignments), "revoked_members": revoked_members, "projects": projects}
