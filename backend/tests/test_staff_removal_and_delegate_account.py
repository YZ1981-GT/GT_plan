"""删除人员档案 / 委派选到不可用人员（spec procedure-chain-hardening-and-java-contracts R12）。

SQLite 真 ORM + 真实路由：
- ``DELETE /api/staff/{id}`` 只有 admin 能删；仍在项目团队里 ⇒ 默认 409 列出项目、不做任何改动；
  ``revoke_assignments=true`` ⇒ 同事务软删分配、该账号在这些项目里再无别的分配时软删成员行、每个受影响项目递增策略版本。
  （策略版本的写入是 PG 语法，这里在类上替换成记录调用；真库路径见 test_program_chain_hardening_batch3_pg.py）
- 委派 / 设复核人时所选人员档案已删、没关联账号、账号停用或删除，422 文案分别写明原因与处理办法。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole, UserRole  # noqa: E402
from app.models.core import Project, ProjectUser, User  # noqa: E402
from app.models.staff_models import ProjectAssignment, StaffMember  # noqa: E402
from app.routers import staff as staff_router  # noqa: E402
from app.services.procedure_authorization import (  # noqa: E402
    STAFF_ACCOUNT_DISABLED_MESSAGE,
    STAFF_NO_ACCOUNT_MESSAGE,
    STAFF_NOT_FOUND_MESSAGE,
    require_staff_active_user,
)
from app.services.wp_visibility.delegation_transaction import DelegationTransactionService  # noqa: E402
from tests._sqlite_fk import enable_sqlite_foreign_keys  # noqa: E402

pytestmark = pytest.mark.asyncio


def _user(name: str, role: UserRole = UserRole.auditor, **kw) -> User:
    return User(id=uuid.uuid4(), username=name, email=f"{name}@example.com", hashed_password="x", role=role,
                is_active=kw.pop("is_active", True), **kw)


@pytest.fixture
async def world(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    enable_sqlite_foreign_keys(engine)  # 与 PG 一样检查外键（R20）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    epochs: list[tuple] = []

    async def _bump(self, project_id, change_type, **kw):
        epochs.append((project_id, change_type, kw.get("detail")))
        return len(epochs)

    monkeypatch.setattr(DelegationTransactionService, "bump_policy_epoch", _bump)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        admin, manager, member = _user("rm_admin", UserRole.admin), _user("rm_manager", UserRole.manager), _user("rm_member")
        p1 = Project(id=uuid.uuid4(), name="【测试】人员删除甲", client_name="甲", status=ProjectStatus.execution)
        p2 = Project(id=uuid.uuid4(), name="【测试】人员删除乙", client_name="乙", status=ProjectStatus.execution)
        db.add_all([admin, manager, member, p1, p2])
        await db.flush()
        staff = StaffMember(name="待删人员", user_id=member.id)
        twin = StaffMember(name="同账号另一份档案", user_id=member.id)  # 同一账号可关联多份人员档案
        db.add_all([staff, twin])
        await db.flush()
        db.add_all([
            ProjectAssignment(project_id=p1.id, staff_id=staff.id, role="auditor"),
            ProjectAssignment(project_id=p2.id, staff_id=staff.id, role="auditor"),
            ProjectAssignment(project_id=p2.id, staff_id=twin.id, role="manager"),
            ProjectUser(project_id=p1.id, user_id=member.id, role=ProjectUserRole.auditor,
                        permission_level=PermissionLevel.edit),
            ProjectUser(project_id=p2.id, user_id=member.id, role=ProjectUserRole.manager,
                        permission_level=PermissionLevel.edit),
        ])
        await db.commit()
        current = {"user": admin}
        api = FastAPI()
        api.include_router(staff_router.router)

        async def _db():
            yield db

        api.dependency_overrides[get_db] = _db
        api.dependency_overrides[get_current_user] = lambda: current["user"]
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://staff") as http:
            yield {"http": http, "db": db, "staff": staff, "twin": twin, "member": member, "p1": p1, "p2": p2,
                   "admin": admin, "manager": manager, "current": current, "epochs": epochs}
    await engine.dispose()


async def _live(db, model, **where) -> int:
    stmt = sa.select(sa.func.count()).select_from(model).where(model.is_deleted == sa.false())
    for key, value in where.items():
        stmt = stmt.where(getattr(model, key) == value)
    return (await db.execute(stmt)).scalar_one()


async def test_only_admin_may_delete_staff(world):
    world["current"]["user"] = world["manager"]
    r = await world["http"].delete(f"/api/staff/{world['staff'].id}", params={"revoke_assignments": "true"})
    assert r.status_code == 403, "原先只要求登录：任何人都能删人员档案"
    assert await _live(world["db"], StaffMember, id=world["staff"].id) == 1


async def test_delete_with_assignments_requires_confirmation_and_changes_nothing(world):
    r = await world["http"].delete(f"/api/staff/{world['staff'].id}")
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "staff_has_assignments"
    assert sorted(p["project_name"] for p in detail["projects"]) == sorted(["【测试】人员删除甲", "【测试】人员删除乙"])
    assert all(p["roles"] == ["auditor"] for p in detail["projects"])
    assert "确认删除将同时撤销其在这些项目的团队分配与项目成员权限" in detail["message"]
    db = world["db"]
    assert await _live(db, StaffMember, id=world["staff"].id) == 1
    assert await _live(db, ProjectAssignment, staff_id=world["staff"].id) == 2
    assert await _live(db, ProjectUser, user_id=world["member"].id) == 2
    assert world["epochs"] == []


async def test_confirmed_delete_revokes_assignments_and_members_in_one_transaction(world):
    r = await world["http"].delete(f"/api/staff/{world['staff'].id}", params={"revoke_assignments": "true"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["revoked_assignments"] == 2 and body["revoked_members"] == 1
    db = world["db"]
    assert await _live(db, StaffMember, id=world["staff"].id) == 0
    assert await _live(db, ProjectAssignment, staff_id=world["staff"].id) == 0
    assert await _live(db, ProjectUser, user_id=world["member"].id, project_id=world["p1"].id) == 0
    assert await _live(db, ProjectUser, user_id=world["member"].id, project_id=world["p2"].id) == 1, \
        "同账号另一份档案仍在乙项目团队里 ⇒ 乙项目成员行保留"
    assert sorted(str(e[0]) for e in world["epochs"]) == sorted([str(world["p1"].id), str(world["p2"].id)])
    assert {e[1] for e in world["epochs"]} == {"membership"}


async def test_delete_without_assignments_and_seed_guard(world):
    db = world["db"]
    loose = StaffMember(name="没有分配的人")
    seed = StaffMember(name="初始导入", source="seed")
    db.add_all([loose, seed])
    await db.commit()
    assert (await world["http"].delete(f"/api/staff/{seed.id}")).status_code == 400
    r = await world["http"].delete(f"/api/staff/{loose.id}")
    assert r.status_code == 200 and r.json()["revoked_assignments"] == 0
    assert world["epochs"] == []


async def test_delegate_rejects_unusable_staff_with_reason_and_remedy(world):
    db = world["db"]
    disabled = _user("rm_disabled", is_active=False)
    gone = _user("rm_gone", is_deleted=True)
    db.add_all([disabled, gone])
    await db.flush()
    cases = {
        "no_account": (StaffMember(name="甲某"), STAFF_NO_ACCOUNT_MESSAGE.format(name="甲某")),
        "disabled": (StaffMember(name="乙某", user_id=disabled.id), STAFF_ACCOUNT_DISABLED_MESSAGE.format(name="乙某")),
        "user_deleted": (StaffMember(name="丙某", user_id=gone.id), STAFF_ACCOUNT_DISABLED_MESSAGE.format(name="丙某")),
        "staff_deleted": (StaffMember(name="丁某", user_id=world["member"].id, is_deleted=True), STAFF_NOT_FOUND_MESSAGE),
    }
    db.add_all([s for s, _ in cases.values()])
    await db.flush()
    for key, (staff, message) in cases.items():
        with pytest.raises(HTTPException) as ei:
            await require_staff_active_user(db, staff.id)
        assert ei.value.status_code == 422 and ei.value.detail == message, key
    assert "请在人员管理中为其关联账号" in STAFF_NO_ACCOUNT_MESSAGE
    assert "请在用户管理中启用该账号" in STAFF_ACCOUNT_DISABLED_MESSAGE
    assert await require_staff_active_user(db, world["staff"].id) == world["member"].id
