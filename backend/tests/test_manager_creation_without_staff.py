"""经理没有人员档案时的建项兼容（spec batch-project-authorization-and-lock-hardening R7）。

四条创建入口在经理未绑定人员档案时照常建项：创建者只有项目成员（经理、编辑），没有团队委派；
绑定了多个人员档案仍按数据异常拒绝。
"""
from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from tests._batch_project_test_support import BRANCH, CHILD, PARENT, grant_manager_codes, make_excel, row

pytest_plugins = ("tests._batch_project_fixtures",)


def manager_account(name: str) -> User:
    return User(username=name, email=f"{name}@example.test", hashed_password="x", role=UserRole.manager)


async def creator_footprint(db, project_ids, user_id) -> tuple[int, int]:
    """(经理编辑成员行数, 团队委派行数)。"""
    members = await db.scalar(select(func.count()).select_from(ProjectUser).where(
        ProjectUser.project_id.in_(project_ids),
        ProjectUser.user_id == user_id,
        ProjectUser.role == ProjectUserRole.manager,
        ProjectUser.permission_level == PermissionLevel.edit,
        ProjectUser.is_deleted == False,  # noqa: E712
    ))
    assignments = await db.scalar(select(func.count()).select_from(ProjectAssignment).where(
        ProjectAssignment.project_id.in_(project_ids),
        ProjectAssignment.is_deleted == False,  # noqa: E712
    ))
    return int(members or 0), int(assignments or 0)


def wizard_app(db, current: dict, monkeypatch) -> FastAPI:
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import project_wizard as project_router

    async def no_limit(*_args, **_kwargs):
        return None

    async def override_db():
        yield db

    monkeypatch.setattr(project_router, "enforce_creation_rate_limit", no_limit)
    app = FastAPI()
    app.include_router(project_router.router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    return app


def single_body(code: str, year: int) -> dict:
    return {
        "client_name": "【测试】无档案经理单建", "audit_year": year,
        "project_type": "annual", "accounting_standard": "enterprise",
        "company_code": code, "short_name": "无档案单建", "report_scope": "standalone",
    }


@pytest.mark.asyncio
async def test_single_create_without_staff_writes_member_only(db, monkeypatch):
    manager = manager_account("nostaff_single_manager")
    db.add(manager)
    await db.flush()
    await grant_manager_codes(db, manager, CHILD)
    await db.commit()
    manager_id = manager.id
    app = wizard_app(db, {"user": manager}, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/projects", json=single_body(CHILD, 2091))
    assert created.status_code == 200, created.text
    project_id = UUID(created.json()["id"])
    assert (await db.get(Project, project_id)).manager_id == manager_id
    assert await creator_footprint(db, [project_id], manager_id) == (1, 0)


@pytest.mark.asyncio
async def test_single_create_with_duplicate_staff_is_still_rejected(db, monkeypatch):
    manager = manager_account("dupstaff_single_manager")
    db.add(manager)
    await db.flush()
    db.add_all([
        StaffMember(name="重复档案一", employee_no="DUP-1", user_id=manager.id),
        StaffMember(name="重复档案二", employee_no="DUP-2", user_id=manager.id),
    ])
    await grant_manager_codes(db, manager, CHILD)
    await db.commit()
    app = wizard_app(db, {"user": manager}, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        rejected = await client.post("/api/projects", json=single_body(CHILD, 2092))
    assert rejected.status_code == 403
    assert "未唯一绑定人员" in rejected.text
    assert await db.scalar(select(func.count()).select_from(Project).where(
        Project.company_code == CHILD, Project.audit_year == 2092,
    )) == 0


@pytest.mark.asyncio
async def test_batch_apply_without_staff_covers_created_rows_and_auto_root(db):
    from app.services.batch_project_execution import apply_validation_plan, create_validation_plan

    manager = manager_account("nostaff_batch_manager")
    db.add(manager)
    await db.flush()
    await grant_manager_codes(db, manager, CHILD, BRANCH)
    await db.commit()
    manager_id = manager.id
    key = "nostaff-batch-apply-0001"
    plan, validation, _ = await create_validation_plan(
        make_excel([row("【测试】无档案子公司", CHILD, 2093, parent=BRANCH, ultimate=BRANCH, relation="子公司")]),
        db, actor=manager, file_name="【测试】无档案批量.xlsx", mode="project", idempotency_key=key,
    )
    assert validation.valid is True, validation.errors
    await db.commit()
    result = await apply_validation_plan(db, plan_id=plan.id, actor=manager, idempotency_key=key)
    await db.commit()
    project_ids = [UUID(value) for value in [*result.project_ids, *result.root_project_ids]]
    assert result.created_count == 1 and result.auto_root_count == 1
    assert len(set(project_ids)) == 2
    assert await creator_footprint(db, project_ids, manager_id) == (2, 0)


@pytest.mark.asyncio
async def test_legacy_import_without_staff_writes_member_only(db):
    from app.services.batch_project_service import parse_and_import

    manager = manager_account("nostaff_legacy_manager")
    db.add(manager)
    await db.flush()
    await grant_manager_codes(db, manager, PARENT)
    await db.commit()
    manager_id = manager.id
    result = await parse_and_import(
        make_excel([row("【测试】无档案旧版导入", PARENT, 2094)]),
        db, current_user=manager, mode="project",
    )
    await db.commit()
    assert result.success_count == 1, result.failures
    project_ids = list((await db.execute(select(Project.id).where(
        Project.company_code == PARENT, Project.audit_year == 2094,
    ))).scalars().all())
    assert len(project_ids) == 1
    assert await creator_footprint(db, project_ids, manager_id) == (1, 0)


@pytest.mark.asyncio
async def test_continuous_audit_without_staff_writes_member_only(db):
    from app.services.continuous_audit_service import ContinuousAuditService

    manager = manager_account("nostaff_continuous_manager")
    prior = Project(
        name="【测试】无档案连续审计_2095", client_name="【测试】无档案连续审计",
        short_name="无档案连续审计", company_code=CHILD, audit_year=2095, report_scope="standalone",
    )
    db.add_all([manager, prior])
    await db.flush()
    db.add(ProjectUser(
        project_id=prior.id, user_id=manager.id,
        role=ProjectUserRole.manager, permission_level=PermissionLevel.edit,
    ))
    await grant_manager_codes(db, manager, CHILD)
    await db.commit()
    manager_id = manager.id
    result = await ContinuousAuditService().create_next_year(
        db, prior.id, copy_team=False, copy_mapping=False, copy_procedures=False, actor=manager,
    )
    await db.commit()
    new_id = UUID(result["new_project_id"])
    assert (await db.get(Project, new_id)).manager_id == manager_id
    assert await creator_footprint(db, [new_id], manager_id) == (1, 0)
