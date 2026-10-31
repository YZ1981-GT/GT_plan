"""人员档案与登录账号绑定（spec batch-project-authorization-and-lock-hardening R6）。

规则：一个账号最多绑定一个未删除人员档案，一个档案最多绑定一个账号。共享库存在历史测试残留
（已删除账号挂着多份档案），不能直接建唯一索引，所以唯一性在锁内校验，所有绑定写入都走本模块。

锁序（design §9.2）：账号 FOR NO KEY UPDATE → 档案的有效委派 FOR SHARE → 档案 FOR NO KEY UPDATE
→ 重新读取有效委派。NO KEY UPDATE 不与外键检查的 KEY SHARE 冲突，委派保存与建项写成员行时
不会和绑定互等。只 flush 不 commit，由路由统一提交。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, ProjectUser, User
from app.models.procedure_models import ProcedureRowTask
from app.models.staff_models import ProjectAssignment, StaffMember

ALREADY_BOUND = "STAFF_ACCOUNT_ALREADY_BOUND"
BINDING_STALE = "STAFF_ACCOUNT_BINDING_STALE"
HAS_ASSIGNMENTS = "STAFF_HAS_ASSIGNMENTS"
SELF_LINK_REQUIRES_ADMIN = "STAFF_SELF_LINK_REQUIRES_ADMIN"
SOD_CONFLICT = "STAFF_ACCOUNT_SOD_CONFLICT"
_RESIGNED = "resigned"
_MAX_NAMED = 5


def _conflict(code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=409, detail={"error_code": code, "message": message, **extra})


def _active_assignments(staff_id: UUID):
    """档案在未删除项目上的有效委派；已删除项目上的委派不授予任何权限。"""
    return (
        sa.select(ProjectAssignment)
        .join(Project, Project.id == ProjectAssignment.project_id)
        .where(
            ProjectAssignment.staff_id == staff_id,
            ProjectAssignment.is_deleted == sa.false(),
            Project.is_deleted == sa.false(),
        )
        .order_by(ProjectAssignment.project_id, ProjectAssignment.id)
    )


async def _lock_user(db: AsyncSession, user_id: UUID):
    # SQLAlchemy 在 read=False 时把 key_share=True 渲染为 PostgreSQL 的 FOR NO KEY UPDATE。
    return (await db.execute(
        sa.select(User.id, User.username, User.is_active, User.is_deleted)
        .where(User.id == user_id)
        .with_for_update(key_share=True)
    )).one_or_none()


async def _lock_staff(db: AsyncSession, staff_id: UUID) -> StaffMember | None:
    # 先锁有效委派、再锁档案：与保存团队「先改委派、再给档案加 FOR SHARE」的顺序一致，不会互等。
    await _lock_live_assignments(db, staff_id)
    return await _lock_staff_row(db, staff_id)


async def _lock_live_assignments(db: AsyncSession, staff_id: UUID) -> None:
    await db.execute(_active_assignments(staff_id).with_for_update(read=True, of=ProjectAssignment))


async def _lock_staff_row(db: AsyncSession, staff_id: UUID) -> StaffMember | None:
    return (await db.execute(
        sa.select(StaffMember)
        .where(StaffMember.id == staff_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()


async def _assignment_projects(db: AsyncSession, staff_id: UUID) -> list[dict]:
    rows = (await db.execute(
        sa.select(ProjectAssignment.project_id, Project.name, ProjectAssignment.role)
        .join(Project, Project.id == ProjectAssignment.project_id)
        .where(
            ProjectAssignment.staff_id == staff_id,
            ProjectAssignment.is_deleted == sa.false(),
            Project.is_deleted == sa.false(),
        )
        .order_by(Project.name, ProjectAssignment.project_id)
    )).all()
    projects: dict[UUID, dict] = {}
    for project_id, name, role in rows:
        entry = projects.setdefault(project_id, {
            "project_id": str(project_id), "project_name": name or str(project_id), "roles": [],
        })
        if role not in entry["roles"]:
            entry["roles"].append(role)
    return list(projects.values())


async def _row_task_projects(db: AsyncSession, staff_id: UUID) -> set[UUID]:
    """档案作为程序行执行人 / 复核人的未删除项目：可见性按档案的账号匹配行任务，换绑要让这些项目失效。"""
    return set((await db.execute(
        sa.select(ProcedureRowTask.project_id)
        .join(Project, Project.id == ProcedureRowTask.project_id)
        .where(
            sa.or_(ProcedureRowTask.assignee_staff_id == staff_id, ProcedureRowTask.reviewer_staff_id == staff_id),
            ProcedureRowTask.is_deleted == sa.false(),
            ProcedureRowTask.workflow_status != "cancelled",
            Project.is_deleted == sa.false(),
        )
        .distinct()
    )).scalars().all())


async def _bump_epochs(db: AsyncSession, project_ids, *, actor_user_id: UUID | None, kind: str, staff_id: UUID) -> None:
    from app.services.wp_visibility.delegation_transaction import DelegationTransactionService

    epochs = DelegationTransactionService(db)
    for project_id in sorted(set(project_ids), key=str):
        # 账号 → 档案映射变化会改变委派权限与可见范围，即使成员行没变也要失效。
        await epochs.bump_policy_epoch(
            project_id, "membership", actor_user_id=actor_user_id,
            detail={"kind": kind, "staff_id": str(staff_id)},
        )


def _project_label(rows: list[dict]) -> str:
    names = "、".join(item["project_name"] for item in rows[:_MAX_NAMED])
    return names + (" 等" if len(rows) > _MAX_NAMED else "")


async def _sod_conflicts(db: AsyncSession, *, staff_id: UUID, user_id: UUID) -> list[dict]:
    """绑定后同一账号在同一项目既是独立复核（EQCR）又担任其他角色的项目。

    绑定只补缺失的成员行、不改已有行；账号已有的成员行（如无档案经理建项时写入的经理 / 编辑）与档案委派
    映射出的成员身份一边是 EQCR、另一边不是，就违反 EQCR 独立性（``EqcrIndependenceRule`` 只看委派，看不到成员行）。
    """
    from app.services.assignment_service import ROLE_MAP, resolve_member_mapping

    eqcr = ROLE_MAP["eqcr"]
    roles: dict[UUID, list[str]] = defaultdict(list)
    names: dict[UUID, str] = {}
    for project_id, name, role in (await db.execute(
        sa.select(ProjectAssignment.project_id, Project.name, ProjectAssignment.role)
        .join(Project, Project.id == ProjectAssignment.project_id)
        .where(
            ProjectAssignment.staff_id == staff_id,
            ProjectAssignment.is_deleted == sa.false(),
            Project.is_deleted == sa.false(),
        )
    )).all():
        roles[project_id].append(role)
        names[project_id] = name or str(project_id)
    if not roles:
        return []
    existing = {
        row.project_id: (row.role, row.permission_level)
        for row in (await db.execute(
            sa.select(ProjectUser.project_id, ProjectUser.role, ProjectUser.permission_level).where(
                ProjectUser.user_id == user_id,
                ProjectUser.project_id.in_(list(roles)),
                ProjectUser.is_deleted == sa.false(),
            )
        )).all()
    }
    return [
        {"project_id": str(project_id), "project_name": names[project_id]}
        for project_id in sorted(roles, key=lambda pid: (names[pid], str(pid)))
        if project_id in existing
        and (resolve_member_mapping(roles[project_id]) == eqcr) != (existing[project_id] == eqcr)
    ]


async def _sync_members(
    db: AsyncSession,
    *,
    staff_id: UUID,
    user_id: UUID,
    actor_user_id: UUID,
) -> tuple[int, list[UUID]]:
    """为档案的有效委派补建缺失的成员行；已有成员行不改（可能由其他途径授予了更合适的角色）。"""
    from app.services.assignment_service import resolve_member_mapping

    roles: dict[UUID, list[str]] = defaultdict(list)
    for assignment in (await db.execute(_active_assignments(staff_id))).scalars().all():
        roles[assignment.project_id].append(assignment.role)
    project_ids = sorted(roles, key=str)
    row_task_projects = await _row_task_projects(db, staff_id)
    if not project_ids:
        await _bump_epochs(db, row_task_projects, actor_user_id=actor_user_id,
                           kind="staff_account_bound", staff_id=staff_id)
        return 0, []
    existing = set((await db.execute(
        sa.select(ProjectUser.project_id).where(
            ProjectUser.user_id == user_id,
            ProjectUser.project_id.in_(project_ids),
            ProjectUser.is_deleted == sa.false(),
        )
    )).scalars().all())
    created = 0
    for project_id in project_ids:
        if project_id in existing:
            continue
        role, level = resolve_member_mapping(roles[project_id])
        try:
            async with db.begin_nested():
                db.add(ProjectUser(
                    project_id=project_id, user_id=user_id, role=role, permission_level=level,
                ))
                await db.flush()
        except IntegrityError:
            continue  # 并发写入方已建成员行：保留对方的取值
        created += 1
    await _bump_epochs(db, {*project_ids, *row_task_projects}, actor_user_id=actor_user_id,
                       kind="staff_account_bound", staff_id=staff_id)
    return created, project_ids


async def list_bindings(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(
        sa.select(
            StaffMember.id, StaffMember.user_id, StaffMember.name,
            StaffMember.employee_no, StaffMember.department, StaffMember.status,
        )
        .where(StaffMember.is_deleted == sa.false(), StaffMember.user_id.is_not(None))
        .order_by(StaffMember.user_id, StaffMember.created_at, StaffMember.id)
    )).all()
    return [
        {
            "user_id": str(row.user_id), "staff_id": str(row.id), "staff_name": row.name,
            "employee_no": row.employee_no, "department": row.department,
            "status": row.status or "active",
        }
        for row in rows
    ]


async def bind_staff_to_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    staff_id: UUID,
    actor_user_id: UUID,
    require_no_assignments: bool = False,
) -> dict:
    """``require_no_assignments``：本人按姓名自动关联时为 True，加锁后档案仍在项目团队中则拒绝。"""
    user = await _lock_user(db, user_id)
    if user is None or user.is_deleted:
        raise HTTPException(status_code=404, detail="账号不存在")
    if not user.is_active:
        raise HTTPException(status_code=422, detail="账号已停用，不能绑定人员档案")
    staff = await _lock_staff(db, staff_id)
    if staff is None or staff.is_deleted:
        raise HTTPException(status_code=404, detail="人员档案不存在")
    if (staff.status or "active") == _RESIGNED:
        raise HTTPException(status_code=422, detail="该人员已离职，不能绑定账号")
    if staff.user_id is not None and staff.user_id != user_id:
        raise _conflict(ALREADY_BOUND, "该人员档案已绑定其他账号，请先解除原绑定")
    others = await db.scalar(sa.select(sa.func.count()).select_from(StaffMember).where(
        StaffMember.user_id == user_id,
        StaffMember.is_deleted == sa.false(),
        StaffMember.id != staff_id,
    ))
    if others:
        raise _conflict(ALREADY_BOUND, "该账号已绑定其他人员档案，请先解除原绑定")
    result = {
        "user_id": str(user_id), "staff_id": str(staff.id), "staff_name": staff.name,
        "employee_no": staff.employee_no, "changed": False,
        "project_count": 0, "created_member_count": 0,
    }
    if staff.user_id == user_id:
        return result
    if require_no_assignments and await _assignment_projects(db, staff.id):
        # 锁内复查：自动关联会让本人获得该档案的委派权限，并发新增的委派也要拦住。
        raise _conflict(SELF_LINK_REQUIRES_ADMIN, "同名人员档案已在项目团队中，请联系管理员在用户管理中绑定")
    conflicts = await _sod_conflicts(db, staff_id=staff.id, user_id=user_id)
    if conflicts:
        raise _conflict(
            SOD_CONFLICT,
            f"绑定后该账号会在 {len(conflicts)} 个项目（{_project_label(conflicts)}）同时担任独立复核（EQCR）"
            "与其他角色，违反独立性要求，请先调整项目团队",
            projects=conflicts,
        )
    staff.user_id = user_id
    await db.flush()
    created, project_ids = await _sync_members(
        db, staff_id=staff.id, user_id=user_id, actor_user_id=actor_user_id,
    )
    return {**result, "changed": True, "project_count": len(project_ids), "created_member_count": created}


async def unbind_staff_from_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    staff_id: UUID,
    actor_user_id: UUID | None = None,
) -> dict:
    if await _lock_user(db, user_id) is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    staff = await _lock_staff(db, staff_id)
    if staff is None or staff.is_deleted or staff.user_id != user_id:
        raise _conflict(BINDING_STALE, "人员档案绑定已变化，请刷新后重试")
    projects = await _assignment_projects(db, staff.id)
    if projects:
        raise _conflict(
            HAS_ASSIGNMENTS,
            f"该人员仍在 {len(projects)} 个项目的团队中（{_project_label(projects)}），"
            "请先在项目团队中移除后再解除绑定",
            projects=projects,
        )
    staff.user_id = None
    await db.flush()
    # 程序行任务的可见性按档案的账号匹配：解绑即撤销，须让缓存的放行结论失效。
    await _bump_epochs(db, await _row_task_projects(db, staff.id), actor_user_id=actor_user_id,
                       kind="staff_account_unbound", staff_id=staff.id)
    return {"user_id": str(user_id), "staff_id": str(staff.id), "changed": True}


async def resolve_self_staff(db: AsyncSession, user: Any) -> dict:
    """``GET /api/staff/me/staff-id``：取本人档案（需求 R6.6）。

    同名档案恰好一份且未绑定、未离职、不在项目团队中才自动关联；没有任何同名档案才自动新建；
    其余情况（同名不唯一、已绑定他人、已离职、已在团队中）一律 409，由管理员在用户管理中绑定。
    """

    async def own_rows():
        return list((await db.execute(
            sa.select(StaffMember.id, StaffMember.name)
            .where(StaffMember.user_id == user.id, StaffMember.is_deleted == sa.false())
            .order_by(StaffMember.created_at, StaffMember.id)
        )).all())

    own = await own_rows()
    if len(own) > 1:
        raise _conflict(SELF_LINK_REQUIRES_ADMIN, "账号绑定了多个人员档案，请联系管理员在用户管理中处理")
    if own:
        return {"staff_id": str(own[0].id), "name": own[0].name}
    candidates = list((await db.execute(
        sa.select(StaffMember.id, StaffMember.user_id, StaffMember.status)
        .where(StaffMember.name == user.username, StaffMember.is_deleted == sa.false())
    )).all())
    if candidates:
        only = candidates[0]
        if len(candidates) != 1 or only.user_id is not None or (only.status or "active") == _RESIGNED:
            # 自动关联或另建一份都可能让当前账号拿到他人的委派权限 / 造出重名档案：交给管理员。
            raise _conflict(SELF_LINK_REQUIRES_ADMIN, "存在同名人员档案，请联系管理员在用户管理中绑定")
        bound = await bind_staff_to_user(
            db, user_id=user.id, staff_id=only.id, actor_user_id=user.id, require_no_assignments=True,
        )
        linked = {"staff_id": bound["staff_id"], "name": bound["staff_name"]}
        # 并发的另一请求已关联：本次没有改动，不再报自动关联（也不再写审计）。
        return {**linked, "auto_linked": True} if bound["changed"] else linked
    if await _lock_user(db, user.id) is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    own = await own_rows()  # 加锁后复查，避免并发请求各建一份
    if own:
        return {"staff_id": str(own[0].id), "name": own[0].name}
    staff = StaffMember(user_id=user.id, name=user.username, source="custom")
    db.add(staff)
    await db.flush()
    return {"staff_id": str(staff.id), "name": staff.name, "auto_created": True}


async def audit_binding_change(
    actor_user_id: UUID,
    *,
    action: str,
    staff_id: str,
    user_id: str,
    project_count: int = 0,
    entrypoint: str = "admin",
) -> None:
    try:
        from app.services.audit_logger_enhanced import audit_logger

        await audit_logger.log_action(
            user_id=actor_user_id,
            action=action,
            object_type="staff_account_binding",
            object_id=staff_id,
            details={"user_id": user_id, "project_count": project_count, "entrypoint": entrypoint},
        )
    except Exception:
        return  # 审计失败不回滚已提交的绑定，也不影响响应


__all__ = [
    "ALREADY_BOUND",
    "BINDING_STALE",
    "HAS_ASSIGNMENTS",
    "SELF_LINK_REQUIRES_ADMIN",
    "SOD_CONFLICT",
    "audit_binding_change",
    "bind_staff_to_user",
    "list_bindings",
    "resolve_self_staff",
    "unbind_staff_from_user",
]
