"""人员档案绑定登录账号（spec batch-project-authorization-and-lock-hardening R6）。

回滚会让会话里的 ORM 对象过期，再读属性会触发异步懒加载；所以各用例在提交后先取出 id。
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select

from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.staff_account_binding_service import (
    ALREADY_BOUND,
    BINDING_STALE,
    HAS_ASSIGNMENTS,
    SELF_LINK_REQUIRES_ADMIN,
    bind_staff_to_user,
    list_bindings,
    resolve_self_staff,
    unbind_staff_from_user,
)

pytest_plugins = ("tests._batch_project_fixtures",)


def account(name: str, role: UserRole = UserRole.auditor, *, active: bool = True) -> User:
    return User(
        username=name, email=f"{name}@example.test", hashed_password="x",
        role=role, is_active=active,
    )


def project(name: str, *, deleted: bool = False) -> Project:
    item = Project(
        name=f"【测试】{name}", client_name=f"【测试】{name}", short_name=name,
        company_code=None, audit_year=2090, report_scope="standalone",
    )
    item.is_deleted = deleted
    return item


async def members(db, user_id) -> list[tuple]:
    rows = (await db.execute(select(
        ProjectUser.project_id, ProjectUser.role, ProjectUser.permission_level,
    ).where(ProjectUser.user_id == user_id, ProjectUser.is_deleted == False))).all()  # noqa: E712
    return sorted((tuple(row) for row in rows), key=lambda row: str(row[0]))


async def bound_user(db, staff_id):
    return await db.scalar(select(StaffMember.user_id).where(StaffMember.id == staff_id))


def error_code(exc: pytest.ExceptionInfo) -> str | None:
    detail = getattr(exc.value, "detail", None)
    return detail.get("error_code") if isinstance(detail, dict) else None


@pytest.mark.asyncio
async def test_bind_is_one_to_one_idempotent_and_listed(db):
    admin = account("bind_admin", UserRole.admin)
    first, second = account("bind_first"), account("bind_second")
    staff_a = StaffMember(name="甲档案", employee_no="BIND-A")
    staff_b = StaffMember(name="乙档案", employee_no="BIND-B")
    db.add_all([admin, first, second, staff_a, staff_b])
    await db.commit()
    admin_id, first_id, second_id = admin.id, first.id, second.id
    staff_a_id, staff_b_id = staff_a.id, staff_b.id

    result = await bind_staff_to_user(db, user_id=first_id, staff_id=staff_a_id, actor_user_id=admin_id)
    await db.commit()
    assert result["changed"] is True and result["staff_name"] == "甲档案"
    again = await bind_staff_to_user(db, user_id=first_id, staff_id=staff_a_id, actor_user_id=admin_id)
    assert again["changed"] is False
    await db.commit()

    with pytest.raises(HTTPException) as staff_taken:
        await bind_staff_to_user(db, user_id=second_id, staff_id=staff_a_id, actor_user_id=admin_id)
    assert staff_taken.value.status_code == 409 and error_code(staff_taken) == ALREADY_BOUND
    await db.rollback()
    with pytest.raises(HTTPException) as user_taken:
        await bind_staff_to_user(db, user_id=first_id, staff_id=staff_b_id, actor_user_id=admin_id)
    assert user_taken.value.status_code == 409 and error_code(user_taken) == ALREADY_BOUND
    await db.rollback()

    listed = await list_bindings(db)
    assert [(item["user_id"], item["staff_name"]) for item in listed] == [(str(first_id), "甲档案")]
    assert await bound_user(db, staff_b_id) is None


@pytest.mark.asyncio
async def test_bind_rejects_inactive_user_and_resigned_or_deleted_staff(db):
    admin = account("bind_reject_admin", UserRole.admin)
    inactive = account("bind_inactive", active=False)
    active = account("bind_active")
    resigned = StaffMember(name="离职档案", employee_no="BIND-R", status="resigned")
    deleted = StaffMember(name="删除档案", employee_no="BIND-D")
    deleted.is_deleted = True
    usable = StaffMember(name="可用档案", employee_no="BIND-U")
    db.add_all([admin, inactive, active, resigned, deleted, usable])
    await db.commit()

    cases = [
        (inactive.id, usable.id, 422),
        (active.id, resigned.id, 422),
        (active.id, deleted.id, 404),
        (uuid4(), usable.id, 404),
    ]
    admin_id = admin.id
    for user_id, staff_id, status in cases:
        with pytest.raises(HTTPException) as rejected:
            await bind_staff_to_user(db, user_id=user_id, staff_id=staff_id, actor_user_id=admin_id)
        assert rejected.value.status_code == status
        await db.rollback()
    assert await db.scalar(select(func.count()).select_from(StaffMember).where(
        StaffMember.user_id.is_not(None),
    )) == 0


@pytest.mark.asyncio
async def test_bind_creates_missing_members_only_for_live_assignments(db):
    admin = account("bind_sync_admin", UserRole.admin)
    target = account("bind_sync_target")
    staff = StaffMember(name="委派档案", employee_no="BIND-S")
    live, kept, removed = project("委派同步"), project("已有成员"), project("已删除项目", deleted=True)
    db.add_all([admin, target, staff, live, kept, removed])
    await db.flush()
    db.add_all([
        ProjectAssignment(project_id=live.id, staff_id=staff.id, role="auditor"),
        ProjectAssignment(project_id=kept.id, staff_id=staff.id, role="auditor"),
        ProjectAssignment(project_id=removed.id, staff_id=staff.id, role="manager"),
        # 已有成员行（例如由建项授予的经理）不得被改成委派映射的较低角色。
        ProjectUser(project_id=kept.id, user_id=target.id, role=ProjectUserRole.manager,
                    permission_level=PermissionLevel.edit),
    ])
    await db.commit()
    live_id, kept_id, target_id = live.id, kept.id, target.id

    result = await bind_staff_to_user(db, user_id=target_id, staff_id=staff.id, actor_user_id=admin.id)
    await db.commit()
    assert result["project_count"] == 2 and result["created_member_count"] == 1
    assert await members(db, target_id) == sorted([
        (live_id, ProjectUserRole.auditor, PermissionLevel.edit),
        (kept_id, ProjectUserRole.manager, PermissionLevel.edit),
    ], key=lambda row: str(row[0]))


@pytest.mark.asyncio
async def test_unbind_requires_current_binding_and_no_live_assignments(db):
    target, other = account("unbind_target"), account("unbind_other")
    staff = StaffMember(name="解除档案", employee_no="UNBIND-S")
    live = project("解除阻断")
    db.add_all([target, other, staff, live])
    await db.flush()
    staff.user_id = target.id
    assignment = ProjectAssignment(project_id=live.id, staff_id=staff.id, role="auditor")
    db.add(assignment)
    await db.commit()
    target_id, other_id, staff_id, assignment_id = target.id, other.id, staff.id, assignment.id

    with pytest.raises(HTTPException) as stale:
        await unbind_staff_from_user(db, user_id=other_id, staff_id=staff_id)
    assert stale.value.status_code == 409 and error_code(stale) == BINDING_STALE
    await db.rollback()
    with pytest.raises(HTTPException) as blocked:
        await unbind_staff_from_user(db, user_id=target_id, staff_id=staff_id)
    assert blocked.value.status_code == 409 and error_code(blocked) == HAS_ASSIGNMENTS
    assert blocked.value.detail["projects"][0]["project_name"] == "【测试】解除阻断"
    await db.rollback()
    assert await bound_user(db, staff_id) == target_id

    removed = await db.get(ProjectAssignment, assignment_id)
    removed.is_deleted = True
    await db.commit()
    result = await unbind_staff_from_user(db, user_id=target_id, staff_id=staff_id)
    await db.commit()
    assert result["changed"] is True
    assert await bound_user(db, staff_id) is None


@pytest.mark.asyncio
async def test_self_service_links_only_unique_safe_candidate_and_creates_only_without_namesake(db):
    owner = account("hijack_owner")
    caller = account("同名甲")
    staff = StaffMember(name="同名甲", employee_no="SELF-A")
    linker = account("唯一乙")
    safe = StaffMember(name="唯一乙", employee_no="SELF-B")
    fresh = account("全新己")
    db.add_all([owner, caller, staff, linker, safe, fresh])
    await db.flush()
    staff.user_id = owner.id
    await db.commit()
    owner_id, staff_id, safe_id = owner.id, staff.id, safe.id
    caller_ns = SimpleNamespace(id=caller.id, username=caller.username)
    linker_ns = SimpleNamespace(id=linker.id, username=linker.username)
    fresh_ns = SimpleNamespace(id=fresh.id, username=fresh.username)

    # 唯一的同名档案已绑定他人：不改绑，也不另建重名档案（R6.6「完全无同名才新建」）。
    with pytest.raises(HTTPException) as refused:
        await resolve_self_staff(db, caller_ns)
    assert refused.value.status_code == 409 and error_code(refused) == SELF_LINK_REQUIRES_ADMIN
    await db.rollback()
    assert await bound_user(db, staff_id) == owner_id
    assert await db.scalar(select(func.count()).select_from(StaffMember).where(StaffMember.name == "同名甲")) == 1

    linked = await resolve_self_staff(db, linker_ns)
    await db.commit()
    assert linked["auto_linked"] is True and linked["staff_id"] == str(safe_id)
    assert await bound_user(db, safe_id) == linker_ns.id
    assert await resolve_self_staff(db, linker_ns) == {"staff_id": str(safe_id), "name": "唯一乙"}

    created = await resolve_self_staff(db, fresh_ns)
    await db.commit()
    assert created.get("auto_created") is True
    assert await bound_user(db, UUID(created["staff_id"])) == fresh_ns.id


@pytest.mark.asyncio
async def test_self_service_requires_admin_for_ambiguous_or_assigned_candidates(db):
    ambiguous = account("重名丙")
    assigned = account("委派丁")
    duplicated = account("多档案戊")
    half_bound = account("半绑庚")
    resigned = account("离职辛")
    other = account("半绑他人")
    live = project("自助关联")
    db.add_all([
        ambiguous, assigned, duplicated, half_bound, resigned, other, live,
        StaffMember(name="重名丙", employee_no="SELF-C1"),
        StaffMember(name="重名丙", employee_no="SELF-C2"),
        StaffMember(name="离职辛", employee_no="SELF-G", status="resigned"),
    ])
    await db.flush()
    # 两份同名、只有一份未绑定：同名不唯一，同样交给管理员（不按「剩下那份」猜）。
    db.add_all([
        StaffMember(name="半绑庚", employee_no="SELF-F1", user_id=other.id),
        StaffMember(name="半绑庚", employee_no="SELF-F2"),
    ])
    await db.flush()
    assigned_staff = StaffMember(name="委派丁", employee_no="SELF-D")
    db.add_all([
        assigned_staff,
        StaffMember(name="档案一", employee_no="SELF-E1", user_id=duplicated.id),
        StaffMember(name="档案二", employee_no="SELF-E2", user_id=duplicated.id),
    ])
    await db.flush()
    db.add(ProjectAssignment(project_id=live.id, staff_id=assigned_staff.id, role="manager"))
    await db.commit()
    callers = [
        SimpleNamespace(id=item.id, username=item.username)
        for item in (ambiguous, assigned, duplicated, half_bound, resigned)
    ]
    assigned_staff_id, assigned_user_id = assigned_staff.id, assigned.id

    for caller in callers:
        with pytest.raises(HTTPException) as refused:
            await resolve_self_staff(db, caller)
        assert refused.value.status_code == 409 and error_code(refused) == SELF_LINK_REQUIRES_ADMIN, caller.username
        await db.rollback()
    assert await bound_user(db, assigned_staff_id) is None
    assert await members(db, assigned_user_id) == []
    assert await db.scalar(select(func.count()).select_from(StaffMember).where(
        StaffMember.name.in_(["重名丙", "委派丁", "半绑庚", "离职辛"]),
    )) == 6
    assert await db.scalar(select(func.count()).select_from(StaffMember).where(
        StaffMember.user_id.in_([item.id for item in callers if item.username != "多档案戊"]),
    )) == 0


@pytest.mark.asyncio
async def test_self_service_reentry_without_change_is_not_reported_as_auto_link(db, monkeypatch):
    from app.services import staff_account_binding_service as svc

    caller = account("重入壬")
    staff = StaffMember(name="重入壬", employee_no="SELF-H")
    db.add_all([caller, staff])
    await db.commit()
    caller_ns = SimpleNamespace(id=caller.id, username=caller.username)
    calls: list[dict] = []

    async def already_linked(_db, **kwargs):
        # 并发的另一请求已在锁内完成关联：本请求加锁后看到的是「已是本人」，没有改动。
        calls.append(kwargs)
        return {"user_id": str(caller.id), "staff_id": str(staff.id), "staff_name": "重入壬", "changed": False}

    monkeypatch.setattr(svc, "bind_staff_to_user", already_linked)
    assert await resolve_self_staff(db, caller_ns) == {"staff_id": str(staff.id), "name": "重入壬"}
    assert calls and calls[0]["require_no_assignments"] is True


@pytest.mark.asyncio
async def test_bind_refuses_eqcr_conflict_with_existing_membership(db):
    """无档案经理建项后只有成员行（经理 / 编辑）：再绑定一份在同项目担任 EQCR 的档案会让他兼任两种角色。"""
    from app.services.staff_account_binding_service import SOD_CONFLICT

    admin = account("sod_admin", UserRole.admin)
    manager = account("sod_manager", UserRole.manager)
    reviewer = account("sod_reviewer")
    eqcr_staff = StaffMember(name="独立复核档案", employee_no="SOD-E")
    manager_staff = StaffMember(name="经理档案", employee_no="SOD-M")
    own, other = project("经理自建"), project("复核他项")
    db.add_all([admin, manager, reviewer, eqcr_staff, manager_staff, own, other])
    await db.flush()
    db.add_all([
        ProjectUser(project_id=own.id, user_id=manager.id, role=ProjectUserRole.manager,
                    permission_level=PermissionLevel.edit),
        ProjectAssignment(project_id=own.id, staff_id=eqcr_staff.id, role="eqcr"),
        ProjectAssignment(project_id=other.id, staff_id=eqcr_staff.id, role="eqcr"),
        # 反向：账号已是某项目的 EQCR 成员，再绑一份在该项目当经理的档案
        ProjectUser(project_id=other.id, user_id=reviewer.id, role=ProjectUserRole.partner,
                    permission_level=PermissionLevel.review),
        ProjectAssignment(project_id=other.id, staff_id=manager_staff.id, role="manager"),
    ])
    await db.commit()
    ids = (admin.id, manager.id, reviewer.id, eqcr_staff.id, manager_staff.id)
    admin_id, manager_id, reviewer_id, eqcr_staff_id, manager_staff_id = ids

    for user_id, staff_id, project_name in (
        (manager_id, eqcr_staff_id, "【测试】经理自建"),
        (reviewer_id, manager_staff_id, "【测试】复核他项"),
    ):
        with pytest.raises(HTTPException) as refused:
            await bind_staff_to_user(db, user_id=user_id, staff_id=staff_id, actor_user_id=admin_id)
        assert refused.value.status_code == 409 and error_code(refused) == SOD_CONFLICT
        assert [item["project_name"] for item in refused.value.detail["projects"]] == [project_name]
        await db.rollback()
        assert await bound_user(db, staff_id) is None

    # 不冲突的组合照常绑定：EQCR 档案绑到在这些项目都没有成员行的账号
    clean = account("sod_clean")
    db.add(clean)
    await db.commit()
    result = await bind_staff_to_user(db, user_id=clean.id, staff_id=eqcr_staff_id, actor_user_id=admin_id)
    await db.commit()
    assert result["changed"] is True and result["created_member_count"] == 2


@pytest.mark.asyncio
async def test_bind_and_unbind_invalidate_projects_with_row_tasks(db, monkeypatch):
    """程序行任务按档案的账号授予底稿可见：绑定 / 解绑都要让这些项目的可见性缓存失效。"""
    from app.models.procedure_models import ProcedureRowTask
    from app.services.wp_visibility.delegation_transaction import DelegationTransactionService

    admin, target = account("epoch_admin", UserRole.admin), account("epoch_target")
    staff = StaffMember(name="行任务档案", employee_no="EPOCH-S")
    team, row_only, cancelled, gone = project("团队项目"), project("行任务项目"), project("已取消任务"), project(
        "已删除项目", deleted=True)
    db.add_all([admin, target, staff, team, row_only, cancelled, gone])
    await db.flush()

    def row_task(project_id, **extra):
        return ProcedureRowTask(
            project_id=project_id, wp_index_id=uuid4(), definition_key="EPOCH-DEF", sheet_key="S1",
            definition_revision_hash="0" * 64, audit_cycle_snapshot="D", **extra,
        )

    db.add_all([
        ProjectAssignment(project_id=team.id, staff_id=staff.id, role="auditor"),
        row_task(row_only.id, reviewer_staff_id=staff.id),
        row_task(cancelled.id, assignee_staff_id=staff.id, workflow_status="cancelled"),
        row_task(gone.id, assignee_staff_id=staff.id),
    ])
    await db.commit()
    bumped: list[tuple] = []

    async def spy(self, project_id, change_type, **kwargs):
        bumped.append((project_id, kwargs["detail"]["kind"]))
        return 1

    monkeypatch.setattr(DelegationTransactionService, "bump_policy_epoch", spy)
    team_id, row_only_id, target_id, staff_id = team.id, row_only.id, target.id, staff.id

    await bind_staff_to_user(db, user_id=target_id, staff_id=staff_id, actor_user_id=admin.id)
    await db.commit()
    assert sorted(bumped, key=lambda item: str(item[0])) == sorted(
        [(team_id, "staff_account_bound"), (row_only_id, "staff_account_bound")], key=lambda item: str(item[0]))

    bumped.clear()
    removed = (await db.execute(select(ProjectAssignment).where(ProjectAssignment.staff_id == staff_id))).scalar_one()
    removed.is_deleted = True
    await db.commit()
    await unbind_staff_from_user(db, user_id=target_id, staff_id=staff_id, actor_user_id=admin.id)
    await db.commit()
    assert bumped == [(row_only_id, "staff_account_unbound")]


@pytest.mark.asyncio
async def test_binding_routes_are_admin_only_and_report_unbind_conflict(db, monkeypatch):
    from app.api import users as users_api
    from app.core.database import get_db
    from app.deps import get_current_user

    admin, partner, target = account("route_bind_admin", UserRole.admin), account(
        "route_bind_partner", UserRole.partner), account("route_bind_target")
    staff = StaffMember(name="路由档案", employee_no="ROUTE-S")
    db.add_all([admin, partner, target, staff])
    await db.commit()
    target_id, staff_id = target.id, staff.id
    audits: list[str] = []

    async def capture(*_args, **kwargs):
        audits.append(kwargs["action"])

    monkeypatch.setattr(users_api, "audit_binding_change", capture)
    current = {"user": partner}

    async def override_db():
        yield db

    app = FastAPI()
    app.include_router(users_api.router, prefix="/api/users")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    body = {"staff_id": str(staff_id)}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/users/staff-bindings")).status_code == 403
        assert (await client.post(f"/api/users/{target_id}/staff-binding", json=body)).status_code == 403

        current["user"] = admin
        bound = await client.post(f"/api/users/{target_id}/staff-binding", json=body)
        assert bound.status_code == 200, bound.text
        assert bound.json()["changed"] is True
        listed = await client.get("/api/users/staff-bindings")
        assert [item["staff_name"] for item in listed.json()] == ["路由档案"]
        unbound = await client.post(f"/api/users/{target_id}/staff-binding/unbind", json=body)
        assert unbound.status_code == 200, unbound.text
        stale = await client.post(f"/api/users/{target_id}/staff-binding/unbind", json=body)
        assert stale.status_code == 409
    assert audits == ["user.staff_binding.bound", "user.staff_binding.unbound"]


def test_frontend_binding_paths_match_mounted_routes_verbatim():
    """前端 apiPaths 的绑定路径 ↔ 应用实际挂载的路由逐字一致（拼错即 404，前端单测 mock 了接口看不出）。"""
    import re
    from pathlib import Path

    from fastapi.routing import APIRoute

    from app.main import app

    src = (
        Path(__file__).resolve().parents[2] / "audit-platform/frontend/src/services/apiPaths/system.ts"
    ).read_text(encoding="utf-8")
    # 块尾是独占一行的「},」；不能用 [^}]，路径模板里的 ${userId} 自带右花括号。
    block = re.search(r"staffBindings:\s*\{(?P<body>.*?)\n\s*\},", src, re.S)
    assert block, "apiPaths/system.ts 未声明 users.staffBindings"
    declared = dict(re.findall(
        r"(\w+):\s*(?:\(userId: string\)\s*=>\s*)?[`']([^`']+)[`']", block.group("body"),
    ))
    methods = {"list": "GET", "bind": "POST", "unbind": "POST"}
    assert set(declared) == set(methods)
    wanted = {(methods[key], path.replace("${userId}", "{user_id}")) for key, path in declared.items()}
    assert wanted == {
        ("GET", "/api/users/staff-bindings"),
        ("POST", "/api/users/{user_id}/staff-binding"),
        ("POST", "/api/users/{user_id}/staff-binding/unbind"),
    }
    routes = [route for route in app.routes if isinstance(route, APIRoute)]
    mounted = {(method, route.path) for route in routes for method in route.methods}
    assert wanted <= mounted, f"未挂载：{sorted(wanted - mounted)}"

    # 绑定弹窗的候选来自 GET /api/staff?unbound_only=true（staffBindingApi.searchUnboundStaff）
    staff_list = [route for route in routes if route.path == "/api/staff" and "GET" in route.methods]
    assert len(staff_list) == 1
    assert "unbound_only" in {param.name for param in staff_list[0].dependant.query_params}
