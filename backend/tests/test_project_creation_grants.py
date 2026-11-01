"""精确 USCC 建项授权、单建旁路和安全限流回归。"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.batch_project_execution import apply_validation_plan, create_validation_plan
from app.services.project_creation_grant_service import (
    authorize_creation_codes,
    grant_many,
    list_grants,
    revoke_grant,
)
from tests._batch_project_test_support import BRANCH, CHILD, PARENT, make_excel, row

pytest_plugins = ("tests._batch_project_fixtures",)


def user(name: str, role: UserRole) -> User:
    return User(
        username=name,
        email=f"{name}@example.test",
        hashed_password="x",
        role=role,
    )


@pytest.mark.asyncio
async def test_manager_exact_grant_crud_and_role_bypasses(db):
    manager, administrator = user("grant_manager", UserRole.manager), user("grant_admin", UserRole.admin)
    db.add_all([manager, administrator])
    await db.flush()

    with pytest.raises(Exception) as denied:
        await authorize_creation_codes(db, manager, [CHILD], entrypoint="test")
    assert getattr(denied.value, "status_code", None) == 403

    grants = await grant_many(
        db, manager_user_id=manager.id, company_codes=[CHILD], valid_until=None,
        reason="首次客户承接授权", actor=administrator,
    )
    assert len(grants) == 1
    first_id, first_version = grants[0].id, grants[0].version
    snapshots = await authorize_creation_codes(db, manager, [CHILD], entrypoint="test")
    assert snapshots == [{
        "id": str(first_id), "company_code": CHILD,
        "version": first_version, "valid_until": None,
    }]

    repeated = await grant_many(
        db, manager_user_id=manager.id, company_codes=[CHILD], valid_until=None,
        reason="首次客户承接授权", actor=administrator,
    )
    assert repeated[0].id == first_id
    assert repeated[0].version == first_version
    listed = await list_grants(db, manager_user_id=manager.id)
    assert [(item["company_code"], item["status"]) for item in listed] == [(CHILD, "active")]

    await revoke_grant(
        db, grant_id=first_id, expected_version=first_version,
        reason="客户承接安排变更", actor=administrator,
    )
    with pytest.raises(Exception) as revoked:
        await authorize_creation_codes(db, manager, [CHILD], entrypoint="test")
    assert getattr(revoked.value, "status_code", None) == 403
    restored = await grant_many(
        db, manager_user_id=manager.id, company_codes=[CHILD], valid_until=None,
        reason="重新取得承接授权", actor=administrator,
    )
    assert restored[0].id != first_id
    assert restored[0].version == 1

    for role in (UserRole.admin, UserRole.partner):
        actor = SimpleNamespace(id=uuid4(), role=SimpleNamespace(value=role.value))
        assert await authorize_creation_codes(db, actor, [BRANCH], entrypoint="test") == []


@pytest.mark.asyncio
async def test_grant_target_must_be_active_manager(db):
    administrator = user("grant_admin_target", UserRole.admin)
    auditor = user("grant_auditor_target", UserRole.auditor)
    db.add_all([administrator, auditor])
    await db.flush()
    with pytest.raises(Exception) as wrong_role:
        await grant_many(
            db, manager_user_id=auditor.id, company_codes=[CHILD], valid_until=None,
            reason="不应授权给审计员", actor=administrator,
        )
    assert getattr(wrong_role.value, "status_code", None) == 422


@pytest.mark.asyncio
async def test_revoked_grant_makes_persisted_plan_stale(db):
    manager = user("grant_plan_manager", UserRole.manager)
    administrator = user("grant_plan_admin", UserRole.admin)
    db.add_all([manager, administrator])
    await db.flush()
    db.add(StaffMember(user_id=manager.id, name="授权计划经理", employee_no="GRANT-MGR-1"))
    grant = (await grant_many(
        db, manager_user_id=manager.id, company_codes=[CHILD], valid_until=None,
        reason="批量计划授权", actor=administrator,
    ))[0]
    await db.commit()

    key = "grant-revocation-plan-0001"
    plan, validation, _ = await create_validation_plan(
        make_excel([row("授权撤销测试", CHILD, 2071)]), db,
        actor=manager, file_name="授权撤销.xlsx", mode="project", idempotency_key=key,
    )
    assert validation.valid is True
    await db.commit()
    await revoke_grant(
        db, grant_id=grant.id, expected_version=grant.version,
        reason="确认前撤销授权", actor=administrator,
    )
    await db.commit()

    with pytest.raises(Exception) as stale:
        await apply_validation_plan(db, plan_id=plan.id, actor=manager, idempotency_key=key)
    assert getattr(stale.value, "status_code", None) == 409
    assert getattr(stale.value, "detail", {}).get("error_code") == "BATCH_PLAN_STALE"
    assert await db.scalar(select(func.count()).select_from(Project).where(
        Project.company_code == CHILD, Project.audit_year == 2071,
    )) == 0


@pytest.mark.asyncio
async def test_single_project_route_uses_grant_and_ignores_spoofed_owners(db, monkeypatch):
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import project_wizard as project_router

    manager = user("single_grant_manager", UserRole.manager)
    administrator = user("single_grant_admin", UserRole.admin)
    spoof_manager = user("spoof_manager", UserRole.manager)
    spoof_partner = user("spoof_partner", UserRole.partner)
    db.add_all([manager, administrator, spoof_manager, spoof_partner])
    await db.flush()
    staff = StaffMember(user_id=manager.id, name="单建授权经理", employee_no="GRANT-MGR-2")
    db.add(staff)
    await grant_many(
        db, manager_user_id=manager.id, company_codes=[CHILD], valid_until=None,
        reason="单项目建项授权", actor=administrator,
    )
    await db.commit()

    async def no_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(project_router, "enforce_creation_rate_limit", no_limit)
    current = {"user": manager}

    async def override_db():
        yield db

    app = FastAPI()
    app.include_router(project_router.router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    body = {
        "client_name": "【测试】单建授权项目", "audit_year": 2072,
        "project_type": "annual", "accounting_standard": "enterprise",
        "company_code": CHILD, "short_name": "授权单建", "report_scope": "standalone",
        "manager_id": str(spoof_manager.id), "signing_partner_id": str(spoof_partner.id),
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/api/projects", json=body)
        assert created.status_code == 200, created.text
        project_id = UUID(created.json()["id"])
        project = await db.get(Project, project_id)
        assert project.manager_id == manager.id
        assert project.partner_id is None
        assert await db.scalar(select(func.count()).select_from(ProjectUser).where(
            ProjectUser.project_id == project_id,
            ProjectUser.user_id == manager.id,
            ProjectUser.role == ProjectUserRole.manager,
            ProjectUser.permission_level == PermissionLevel.edit,
            ProjectUser.is_deleted == False,  # noqa: E712
        )) == 1
        assert await db.scalar(select(func.count()).select_from(ProjectAssignment).where(
            ProjectAssignment.project_id == project_id,
            ProjectAssignment.staff_id == staff.id,
            ProjectAssignment.is_deleted == False,  # noqa: E712
        )) == 1

        denied_body = {**body, "company_code": BRANCH, "audit_year": 2073}
        denied = await client.post("/api/projects", json=denied_body)
        assert denied.status_code == 403

        current["user"] = spoof_partner
        partner_created = await client.post("/api/projects", json=denied_body)
        assert partner_created.status_code == 200, partner_created.text
        partner_project_id = UUID(partner_created.json()["id"])
        assert await db.scalar(select(func.count()).select_from(ProjectUser).where(
            ProjectUser.project_id == partner_project_id,
            ProjectUser.user_id == spoof_partner.id,
            ProjectUser.role == ProjectUserRole.partner,
            ProjectUser.permission_level == PermissionLevel.edit,
            ProjectUser.is_deleted == False,  # noqa: E712
        )) == 1

        current["user"] = user("route_auditor", UserRole.auditor)
        db.add(current["user"])
        await db.commit()
        wrong_role = await client.post(
            "/api/projects", json={**denied_body, "audit_year": 2074}
        )
        assert wrong_role.status_code == 403


@pytest.mark.asyncio
async def test_creation_rate_limit_is_typed_and_redis_failure_does_not_bypass_auth(monkeypatch):
    from app.services import project_creation_security as security

    class FakeRedis:
        def __init__(self):
            self.count = 0

        async def eval(self, *_args):
            self.count += 1
            return [self.count, 42]

    fake = FakeRedis()

    async def get_fake():
        return fake

    async def no_audit(*_args, **_kwargs):
        return None

    monkeypatch.setenv("GT_PROJECT_CREATION_RATE_PER_MINUTE", "2")
    monkeypatch.setattr(security, "_get_redis", get_fake)
    monkeypatch.setattr(security, "_audit_limit", no_audit)
    actor = SimpleNamespace(id=uuid4(), role=SimpleNamespace(value="manager"))
    await security.enforce_creation_rate_limit(actor, entrypoint="test")
    await security.enforce_creation_rate_limit(actor, entrypoint="test")
    with pytest.raises(Exception) as limited:
        await security.enforce_creation_rate_limit(actor, entrypoint="test")
    assert getattr(limited.value, "status_code", None) == 429
    assert getattr(limited.value, "headers", {})["Retry-After"] == "42"
    assert getattr(limited.value, "detail", {})["error_code"] == security.RATE_LIMIT_ERROR_CODE

    async def broken():
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(security, "_get_redis", broken)
    await security.enforce_creation_rate_limit(actor, entrypoint="test")


@pytest.mark.asyncio
async def test_grant_management_routes_are_admin_only(db, monkeypatch):
    from app.api import users as users_api
    from app.core.database import get_db
    from app.deps import get_current_user

    administrator = user("grant_route_admin", UserRole.admin)
    manager = user("grant_route_manager", UserRole.manager)
    partner = user("grant_route_partner", UserRole.partner)
    db.add_all([administrator, manager, partner])
    await db.commit()

    async def no_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(users_api, "audit_grant_change", no_audit)
    current = {"user": partner}

    async def override_db():
        yield db

    app = FastAPI()
    app.include_router(users_api.router, prefix="/api/users")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/users/project-creation-grants")).status_code == 403
        denied = await client.post(
            f"/api/users/project-creation-grants/{manager.id}",
            json={"company_codes": [CHILD], "reason": "partner 不可管理"},
        )
        assert denied.status_code == 403

        current["user"] = administrator
        granted = await client.post(
            f"/api/users/project-creation-grants/{manager.id}",
            json={"company_codes": [CHILD], "reason": "管理员授权客户承接"},
        )
        assert granted.status_code == 200, granted.text
        grant_id = granted.json()[0]["id"]
        listed = await client.get(
            "/api/users/project-creation-grants",
            params={"manager_user_id": str(manager.id)},
        )
        assert listed.status_code == 200
        assert listed.json()[0]["company_code"] == CHILD
        revoked = await client.post(
            f"/api/users/project-creation-grants/{grant_id}/revoke",
            json={"expected_version": 1, "reason": "客户承接负责人调整"},
        )
        assert revoked.status_code == 200
        assert revoked.json()["revoked"] is True


@pytest.mark.asyncio
async def test_denied_authorization_audit_contains_only_code_digest(db, monkeypatch):
    from app.services.audit_logger_enhanced import audit_logger

    manager = user("grant_audit_manager", UserRole.manager)
    db.add(manager)
    await db.commit()
    captured: list[dict] = []

    async def capture(**kwargs):
        captured.append(kwargs)
        return kwargs

    monkeypatch.setattr(audit_logger, "log_action", capture)
    with pytest.raises(Exception):
        await authorize_creation_codes(db, manager, [CHILD], entrypoint="batch_validate")
    assert len(captured) == 1
    serialized = str(captured[0])
    assert CHILD not in serialized
    details = captured[0]["details"]
    assert details["company_code_count"] == 1
    assert len(details["company_codes_sha256"]) == 64


@pytest.mark.asyncio
async def test_manager_must_hold_grants_for_new_row_parent_and_auto_root(db):
    manager = user("grant_auto_root_manager", UserRole.manager)
    administrator = user("grant_auto_root_admin", UserRole.admin)
    db.add_all([manager, administrator])
    await db.flush()
    await grant_many(
        db, manager_user_id=manager.id, company_codes=[CHILD], valid_until=None,
        reason="仅授权子公司", actor=administrator,
    )
    await db.commit()
    payload = make_excel([
        row("授权子公司", CHILD, 2075, parent=BRANCH, ultimate=BRANCH, relation="子公司")
    ])
    with pytest.raises(Exception) as missing_root:
        await create_validation_plan(
            payload, db, actor=manager, file_name="自动根授权.xlsx", mode="project",
            idempotency_key="grant-auto-root-denied-0001",
        )
    assert getattr(missing_root.value, "status_code", None) == 403

    await grant_many(
        db, manager_user_id=manager.id, company_codes=[BRANCH], valid_until=None,
        reason="补充授权最终控制方", actor=administrator,
    )
    await db.commit()
    plan, validation, _ = await create_validation_plan(
        payload, db, actor=manager, file_name="自动根授权.xlsx", mode="project",
        idempotency_key="grant-auto-root-allowed-0002",
    )
    assert validation.valid is True
    assert validation.summary.auto_root == 1
    assert len(plan.summary["_plan_dependencies"]["creation_grants"]) == 2


@pytest.mark.asyncio
async def test_ungranted_manager_is_rejected_before_project_inventory_query(db, monkeypatch):
    from app.services import batch_project_plan

    manager = user("grant_order_manager", UserRole.manager)
    db.add(manager)
    await db.commit()

    async def inventory_must_not_run(*_args, **_kwargs):
        raise AssertionError("project inventory queried before company grant")

    monkeypatch.setattr(batch_project_plan, "_load_year_projects", inventory_must_not_run)
    with pytest.raises(Exception) as denied:
        await batch_project_plan.analyze_batch(
            make_excel([row("未授权企业", CHILD, 2076)]),
            db, current_user=manager, mode="project",
        )
    assert getattr(denied.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_batch_plan_snapshots_grant_for_inventory_inferred_ultimate(db):
    """上级库存补出的最终控制方也必须授权，并进入持久计划快照。"""
    manager = user("grant_inferred_batch_manager", UserRole.manager)
    administrator = user("grant_inferred_batch_admin", UserRole.admin)
    db.add_all([manager, administrator])
    await db.flush()
    db.add(StaffMember(
        user_id=manager.id,
        name="推导授权批量经理",
        employee_no="GRANT-MGR-INFERRED-BATCH",
    ))
    parent = Project(
        name="【测试】授权推导上级",
        client_name="【测试】授权推导上级",
        short_name="授权推导上级",
        company_code=BRANCH,
        audit_year=2077,
        report_scope="standalone",
        ultimate_company_code=PARENT,
    )
    db.add(parent)
    await db.flush()
    db.add(ProjectUser(
        project_id=parent.id,
        user_id=manager.id,
        role=ProjectUserRole.manager,
        permission_level=PermissionLevel.edit,
    ))
    await grant_many(
        db,
        manager_user_id=manager.id,
        company_codes=[CHILD, BRANCH],
        valid_until=None,
        reason="授权子公司及直接上级",
        actor=administrator,
    )
    await db.commit()

    payload = make_excel([
        row("【测试】授权推导子公司", CHILD, 2077, parent=BRANCH, relation="子公司")
    ])
    with pytest.raises(Exception) as missing_ultimate:
        await create_validation_plan(
            payload,
            db,
            actor=manager,
            file_name="【测试】推导授权.xlsx",
            mode="project",
            idempotency_key="grant-inferred-batch-denied-0001",
        )
    assert getattr(missing_ultimate.value, "status_code", None) == 403

    await grant_many(
        db,
        manager_user_id=manager.id,
        company_codes=[PARENT],
        valid_until=None,
        reason="补充最终控制方授权",
        actor=administrator,
    )
    await db.commit()
    plan, validation, _ = await create_validation_plan(
        payload,
        db,
        actor=manager,
        file_name="【测试】推导授权.xlsx",
        mode="project",
        idempotency_key="grant-inferred-batch-allowed-0002",
    )
    assert validation.valid is True
    snapshots = plan.summary["_plan_dependencies"]["creation_grants"]
    assert {item["company_code"] for item in snapshots} == {CHILD, BRANCH, PARENT}
    result = await apply_validation_plan(
        db,
        plan_id=plan.id,
        actor=manager,
        idempotency_key="grant-inferred-batch-allowed-0002",
    )
    await db.commit()
    assert result.created_count == 1
    assert result.auto_root_count == 1


@pytest.mark.asyncio
async def test_single_create_rejects_inventory_inferred_ultimate_without_grant(db):
    """单建不能在首次授权后由 prepare_group_fields 偷渡未授权 ultimate。"""
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.project_creation_coordinator import create_project_for_actor

    manager = user("grant_inferred_single_manager", UserRole.manager)
    administrator = user("grant_inferred_single_admin", UserRole.admin)
    db.add_all([manager, administrator])
    await db.flush()
    db.add(StaffMember(
        user_id=manager.id,
        name="推导授权单建经理",
        employee_no="GRANT-MGR-INFERRED",
    ))
    parent = Project(
        name="【测试】单建推导上级",
        client_name="【测试】单建推导上级",
        short_name="单建推导上级",
        company_code=BRANCH,
        audit_year=2078,
        report_scope="standalone",
        ultimate_company_code=PARENT,
    )
    db.add(parent)
    await db.flush()
    db.add(ProjectUser(
        project_id=parent.id,
        user_id=manager.id,
        role=ProjectUserRole.manager,
        permission_level=PermissionLevel.edit,
    ))
    await grant_many(
        db,
        manager_user_id=manager.id,
        company_codes=[CHILD, BRANCH],
        valid_until=None,
        reason="授权子公司及直接上级",
        actor=administrator,
    )
    await db.commit()

    def request() -> BasicInfoSchema:
        return BasicInfoSchema(
            client_name="【测试】单建推导子公司",
            audit_year=2078,
            project_type="annual",
            accounting_standard="enterprise",
            company_code=CHILD,
            short_name="单建推导子公司",
            report_scope="standalone",
            parent_company_code=BRANCH,
            relation_to_parent="subsidiary",
        )

    with pytest.raises(Exception) as missing_ultimate:
        await create_project_for_actor(request(), db, manager)
    assert getattr(missing_ultimate.value, "status_code", None) == 403
    assert await db.scalar(select(func.count()).select_from(Project).where(
        Project.company_code == CHILD,
        Project.audit_year == 2078,
    )) == 0

    await grant_many(
        db,
        manager_user_id=manager.id,
        company_codes=[PARENT],
        valid_until=None,
        reason="补充最终控制方授权",
        actor=administrator,
    )
    await db.commit()
    created = await create_project_for_actor(request(), db, manager)
    assert created.ultimate_company_code == PARENT


@pytest.mark.asyncio
async def test_continuous_audit_revalidates_grant_and_initializes_manager_when_team_not_copied(db):
    from app.services.continuous_audit_service import ContinuousAuditService

    manager = user("grant_continuous_manager", UserRole.manager)
    administrator = user("grant_continuous_admin", UserRole.admin)
    db.add_all([manager, administrator])
    await db.flush()
    staff = StaffMember(
        user_id=manager.id,
        name="连续审计授权经理",
        employee_no="GRANT-MGR-CONTINUOUS",
    )
    prior = Project(
        name="【测试】连续审计授权_2079",
        client_name="【测试】连续审计授权",
        short_name="连续审计授权",
        company_code=CHILD,
        audit_year=2079,
        report_scope="standalone",
    )
    db.add_all([staff, prior])
    await db.flush()
    db.add(ProjectUser(
        project_id=prior.id,
        user_id=manager.id,
        role=ProjectUserRole.manager,
        permission_level=PermissionLevel.edit,
    ))
    await grant_many(
        db,
        manager_user_id=manager.id,
        company_codes=[CHILD],
        valid_until=None,
        reason="连续审计新年度建项",
        actor=administrator,
    )
    await db.commit()

    result = await ContinuousAuditService().create_next_year(
        db,
        prior.id,
        copy_team=False,
        copy_mapping=False,
        copy_procedures=False,
        actor=manager,
    )
    await db.commit()
    new_id = UUID(result["new_project_id"])
    created = await db.get(Project, new_id)
    assert created is not None
    assert created.created_by == manager.id
    assert created.manager_id == manager.id
    assert await db.scalar(select(func.count()).select_from(ProjectUser).where(
        ProjectUser.project_id == new_id,
        ProjectUser.user_id == manager.id,
        ProjectUser.role == ProjectUserRole.manager,
        ProjectUser.permission_level == PermissionLevel.edit,
        ProjectUser.is_deleted == False,  # noqa: E712
    )) == 1
    assert await db.scalar(select(func.count()).select_from(ProjectAssignment).where(
        ProjectAssignment.project_id == new_id,
        ProjectAssignment.staff_id == staff.id,
        ProjectAssignment.is_deleted == False,  # noqa: E712
    )) == 1


@pytest.mark.asyncio
async def test_inferred_ultimate_grant_does_not_grant_existing_project_access(db):
    """第二轮授权只放开库存判定，不能把 grant 当成既有 ultimate 项目权限。"""
    manager = user("grant_inferred_hidden_manager", UserRole.manager)
    administrator = user("grant_inferred_hidden_admin", UserRole.admin)
    db.add_all([manager, administrator])
    await db.flush()
    visible_parent = Project(
        name="【测试】可见直接上级",
        client_name="【测试】可见直接上级",
        short_name="可见直接上级",
        company_code=BRANCH,
        audit_year=2081,
        report_scope="standalone",
        ultimate_company_code=PARENT,
    )
    hidden_ultimate = Project(
        name="【测试】隐藏最终控制方",
        client_name="【测试】隐藏最终控制方",
        short_name="隐藏最终控制方",
        company_code=PARENT,
        audit_year=2081,
        report_scope="standalone",
        ultimate_company_code=PARENT,
    )
    db.add_all([visible_parent, hidden_ultimate])
    await db.flush()
    db.add(ProjectUser(
        project_id=visible_parent.id,
        user_id=manager.id,
        role=ProjectUserRole.manager,
        permission_level=PermissionLevel.edit,
    ))
    await grant_many(
        db,
        manager_user_id=manager.id,
        company_codes=[CHILD, BRANCH, PARENT],
        valid_until=None,
        reason="授权集团三码但不授予既有项目",
        actor=administrator,
    )
    await db.commit()

    plan, response, _ = await create_validation_plan(
        make_excel([
            row("【测试】隐藏控制方子公司", CHILD, 2081, parent=BRANCH, relation="子公司")
        ]),
        db,
        actor=manager,
        file_name="【测试】隐藏控制方.xlsx",
        mode="project",
        idempotency_key="grant-inferred-hidden-ultimate-0001",
    )
    assert response.valid is False
    messages = "；".join(message for item in response.errors for message in item.errors)
    assert "上级企业或最终控制方已有您无权维护的项目" in messages
    assert str(hidden_ultimate.id) not in messages
    assert plan.status == "invalid"


@pytest.mark.asyncio
async def test_grant_list_marks_unusable_manager_grants_suspended(db):
    manager = user("grant_suspended_manager", UserRole.manager)
    administrator = user("grant_suspended_admin", UserRole.admin)
    db.add_all([manager, administrator])
    await db.flush()
    await grant_many(
        db,
        manager_user_id=manager.id,
        company_codes=[CHILD],
        valid_until=None,
        reason="停用后状态展示",
        actor=administrator,
    )
    await db.commit()
    assert [item["status"] for item in await list_grants(db, manager_user_id=manager.id)] == ["active"]

    manager.is_active = False
    await db.commit()
    assert [item["status"] for item in await list_grants(db, manager_user_id=manager.id)] == ["suspended"]

    manager.is_active = True
    manager.role = UserRole.auditor
    await db.commit()
    assert [item["status"] for item in await list_grants(db, manager_user_id=manager.id)] == ["suspended"]
