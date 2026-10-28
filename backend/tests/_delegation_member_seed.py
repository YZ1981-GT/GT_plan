"""编制人改走底稿主编委派后的测试夹具（spec procedure-trim-generation-delegation-chain 任务 12），SQLite / PG 通用。

分配编制人（批量分配、复核页指派、增强批量分配、人员交接）都经 ``DelegationTransactionService.delegate_lead``：
被委派人须在本项目有团队分配且看得到目标循环；复核人须是本项目成员。旧夹具只建底稿不建成员，这里一处补齐。
"""
from __future__ import annotations

import uuid

from app.models.base import ProjectUserRole
from app.models.core import ProjectUser
from app.models.staff_models import ProjectAssignment, StaffMember


async def seed_delegation_members(
    db, project_id, assignee_user_id, cycles, reviewer_user_id=None, *, commit: bool = True,
) -> StaffMember:
    """建被委派人的人员记录 + 团队分配（审计员，勾选 ``cycles``）；给了 ``reviewer_user_id`` 再建其项目成员行。"""
    staff = StaffMember(id=uuid.uuid4(), user_id=assignee_user_id, name="编制人")
    db.add(staff)
    await db.flush()
    db.add(ProjectAssignment(project_id=project_id, staff_id=staff.id, role="auditor", assigned_cycles=list(cycles)))
    if reviewer_user_id is not None:
        db.add(ProjectUser(project_id=project_id, user_id=reviewer_user_id, role=ProjectUserRole.auditor))
    await (db.commit() if commit else db.flush())
    return staff
