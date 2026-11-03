"""创建者可见本项目底稿（spec batch-project-authorization-and-lock-hardening R8）。

被测：``effective_scope.resolve_member_scope``——创建者只要有成员行就按主管待遇，
被移出团队后不再放行。
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember

pytest_plugins = ("tests._batch_project_fixtures",)


def _user(name: str, role: UserRole = UserRole.manager) -> User:
    return User(username=name, email=f"{name}@t.example", hashed_password="x", role=role, is_active=True)


def _project(name: str, *, created_by: uuid.UUID | None = None) -> Project:
    return Project(
        name=f"【测试】{name}", client_name=f"【测试】{name}", short_name=name,
        audit_year=2090, report_scope="standalone", created_by=created_by,
    )


@pytest.mark.asyncio
async def test_creator_without_assignments_is_supervisor(db):
    """创建者没有人员档案和委派，只有 manager/edit 成员行 → 主管看全部循环。"""
    from app.services.wp_visibility.effective_scope import resolve_member_scope

    user = _user("creator_mgr")
    db.add(user)
    await db.flush()
    project = _project("创建者可见", created_by=user.id)
    db.add(project)
    await db.flush()
    db.add(ProjectUser(project_id=project.id, user_id=user.id,
                       role=ProjectUserRole.manager, permission_level=PermissionLevel.edit))
    await db.commit()

    scope = await resolve_member_scope(db, project.id, user.id)
    assert scope.is_supervisor is True
    assert scope.is_member is True
    assert "A" in scope.cycles and "N" in scope.cycles


@pytest.mark.asyncio
async def test_creator_removed_from_team_loses_supervisor(db):
    """创建者被移出团队（成员行全部软删）⇒ 不再按创建者放行。"""
    from app.services.wp_visibility.effective_scope import resolve_member_scope

    user = _user("creator_gone")
    db.add(user)
    await db.flush()
    project = _project("被移出团队", created_by=user.id)
    db.add(project)
    await db.flush()
    member = ProjectUser(project_id=project.id, user_id=user.id,
                         role=ProjectUserRole.manager, permission_level=PermissionLevel.edit)
    db.add(member)
    await db.commit()
    member.is_deleted = True
    await db.commit()

    scope = await resolve_member_scope(db, project.id, user.id)
    assert scope.is_supervisor is False
    assert scope.is_member is False


@pytest.mark.asyncio
async def test_non_creator_member_without_assignments_is_not_supervisor(db):
    """非创建者的 manager/edit 成员（如被其他方式加入）没有委派 → 不是主管。"""
    from app.services.wp_visibility.effective_scope import resolve_member_scope

    creator, other = _user("actual_creator"), _user("other_member")
    db.add_all([creator, other])
    await db.flush()
    project = _project("他人创建", created_by=creator.id)
    db.add(project)
    await db.flush()
    db.add(ProjectUser(project_id=project.id, user_id=other.id,
                       role=ProjectUserRole.manager, permission_level=PermissionLevel.edit))
    await db.commit()

    scope = await resolve_member_scope(db, other.id, project.id)
    # 注意参数顺序：resolve_member_scope(db, project_id, user_id)
    scope = await resolve_member_scope(db, project.id, other.id)
    assert scope.is_supervisor is False
    assert scope.is_member is True


@pytest.mark.asyncio
async def test_creator_who_is_also_supervisor_via_assignment_still_works(db):
    """创建者同时有委派（有档案的经理建项）→ 走原来的唯一链路主管判定，不冲突。"""
    from app.services.wp_visibility.effective_scope import resolve_member_scope

    user = _user("creator_with_staff")
    staff = StaffMember(name="经理档案", employee_no="CV-1")
    db.add_all([user, staff])
    await db.flush()
    staff.user_id = user.id
    project = _project("有委派创建者", created_by=user.id)
    db.add(project)
    await db.flush()
    db.add_all([
        ProjectUser(project_id=project.id, user_id=user.id,
                    role=ProjectUserRole.manager, permission_level=PermissionLevel.edit),
        ProjectAssignment(project_id=project.id, staff_id=staff.id, role="manager"),
    ])
    await db.commit()

    scope = await resolve_member_scope(db, project.id, user.id)
    assert scope.is_supervisor is True
    assert "manager" in scope.roles


@pytest.mark.asyncio
async def test_partner_creator_is_supervisor(db):
    """合伙人建项只写 partner/edit 成员行 → 创建者按主管放行。"""
    from app.services.wp_visibility.effective_scope import resolve_member_scope

    user = _user("partner_creator", UserRole.partner)
    db.add(user)
    await db.flush()
    project = _project("合伙人创建", created_by=user.id)
    db.add(project)
    await db.flush()
    db.add(ProjectUser(project_id=project.id, user_id=user.id,
                       role=ProjectUserRole.partner, permission_level=PermissionLevel.edit))
    await db.commit()

    scope = await resolve_member_scope(db, project.id, user.id)
    assert scope.is_supervisor is True
    assert scope.is_member is True
