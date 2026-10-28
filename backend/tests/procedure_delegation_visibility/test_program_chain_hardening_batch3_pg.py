"""程序表链路加固批 3（spec procedure-chain-hardening-and-java-contracts R12 / R13）。

真实 PostgreSQL，每个用例一个外层事务（``create_savepoint``，路由里的 commit 只动保存点），结束回滚。

- R12：删除人员档案 —— 仍在项目团队里默认 409；确认撤权后同事务软删分配与成员行，并真实递增受影响项目的
  可见性策略版本（``wp_visibility_policy_epochs`` + 失效通知，PG upsert）。
- R13：委派预览前置失败（库错误）⇒ 回执 ``preparation_ready=False``、计数清零、已物化的行随保存点回滚；
  程序错误不再被吞成「导入失败」。
"""
from __future__ import annotations

import types

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel
from app.models.core import ProjectUser
from app.models.procedure_models import ProcedureRowTask
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.wp_visibility_models import WpVisibilityInvalidationOutbox, WpVisibilityPolicyEpoch
from app.services.procedure_delegation_service import ProcedureDelegationService
from app.services.procedure_task_materialization_service import ProcedureTaskMaterializationService

from ._factories import IS_PG, mk_assignment, mk_project, mk_project_user, mk_staff, mk_user
from ._factories import mk_working_paper, mk_wp_index

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")]


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    s = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield s
    finally:
        try:
            from app.main import app

            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)
        finally:
            await s.close()
            await trans.rollback()
            await conn.close()
            await engine.dispose()


@pytest.fixture(autouse=True)
def _side_writes(monkeypatch):
    """操作日志 / 拒绝记录走独立事务，会在真库留下引用回滚数据的行 ⇒ 换成空操作。"""
    from app.middleware import audit_log
    from app.services.wp_visibility.denial import DenialResponder

    async def _log(**_kw):
        return None

    async def _denial(self, **_kw):
        return None

    monkeypatch.setattr(audit_log, "_write_log", _log)
    monkeypatch.setattr(DenialResponder, "_write_outbox", _denial)


def _client(s: AsyncSession, user) -> AsyncClient:
    from app.main import app

    async def _db():
        yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _principal(user):
    return types.SimpleNamespace(id=user.id, role=user.role, username=user.username, email=user.email,
                                 is_active=True, is_deleted=False)


async def _epoch(s, project_id) -> int:
    value = (await s.execute(sa.select(WpVisibilityPolicyEpoch.epoch).where(
        WpVisibilityPolicyEpoch.project_id == project_id))).scalar_one_or_none()
    return int(value or 0)


# ---------------------------------------------------------------------------
# R12 删除人员档案
# ---------------------------------------------------------------------------
async def test_staff_delete_requires_confirmation_then_revokes_and_bumps_epoch(db):
    project = await mk_project(db)
    admin = await mk_user(db, role="admin")
    member = await mk_user(db)
    staff = await mk_staff(db, user_id=member.id)
    await mk_assignment(db, project.id, staff.id, role="auditor")
    pu = await mk_project_user(db, project.id, member.id)
    pu.permission_level = PermissionLevel.edit
    await db.flush()
    pid, staff_id, member_id = project.id, staff.id, member.id
    before = await _epoch(db, pid)

    async with _client(db, _principal(member)) as c:
        assert (await c.delete(f"/api/staff/{staff_id}")).status_code == 403, "非 admin 不能删人员档案"
    async with _client(db, _principal(admin)) as c:
        first = await c.delete(f"/api/staff/{staff_id}")
        assert first.status_code == 409, first.text
        detail = first.json()["message"]
        assert detail["error"] == "staff_has_assignments" and detail["projects"][0]["project_id"] == str(pid)
        assert await _epoch(db, pid) == before, "未确认：不撤权、不递增策略版本"
        second = await c.delete(f"/api/staff/{staff_id}", params={"revoke_assignments": "true"})
        assert second.status_code == 200, second.text

    live = sa.false()
    assert (await db.execute(sa.select(sa.func.count()).select_from(StaffMember).where(
        StaffMember.id == staff_id, StaffMember.is_deleted == live))).scalar_one() == 0
    assert (await db.execute(sa.select(sa.func.count()).select_from(ProjectAssignment).where(
        ProjectAssignment.staff_id == staff_id, ProjectAssignment.is_deleted == live))).scalar_one() == 0
    assert (await db.execute(sa.select(sa.func.count()).select_from(ProjectUser).where(
        ProjectUser.user_id == member_id, ProjectUser.project_id == pid, ProjectUser.is_deleted == live,
    ))).scalar_one() == 0, "其账号在该项目的成员行一并撤销"
    assert await _epoch(db, pid) == before + 1
    outbox = (await db.execute(
        sa.select(WpVisibilityInvalidationOutbox.change_type, WpVisibilityInvalidationOutbox.detail)
        .where(WpVisibilityInvalidationOutbox.project_id == pid)
        .order_by(WpVisibilityInvalidationOutbox.epoch.desc())
    )).first()
    assert outbox[0] == "membership" and outbox[1]["kind"] == "staff_removed"


# ---------------------------------------------------------------------------
# R13 委派预览前置就绪标记
# ---------------------------------------------------------------------------
async def _delegation_world(db):
    project = await mk_project(db)
    manager = await mk_user(db)
    m_staff = await mk_staff(db, user_id=manager.id)
    await mk_assignment(db, project.id, m_staff.id, role="manager")
    await mk_project_user(db, project.id, manager.id)
    auditor = await mk_user(db)
    a_staff = await mk_staff(db, user_id=auditor.id)
    a = await mk_assignment(db, project.id, a_staff.id, role="auditor")
    a.assigned_cycles = ["D"]
    pu = await mk_project_user(db, project.id, auditor.id, scope_cycles="D")
    pu.permission_level = PermissionLevel.edit
    wi = await mk_wp_index(db, project.id, wp_code="D2", wp_name="应收账款", audit_cycle="D")
    await mk_working_paper(db, project.id, wi.id)
    await db.flush()
    return project, manager, a_staff, wi


async def _preview(db, project, manager, staff, wi):
    return await ProcedureDelegationService(db).preview(
        project.id, actor_user_id=manager.id,
        selector={"kind": "workpaper", "wp_index_ids": [str(wi.id)]}, assignee_staff_id=staff.id,
    )


async def test_preview_preparation_failure_is_reported_not_ready(db, monkeypatch):
    project, manager, staff, wi = await _delegation_world(db)

    async def _db_down(self, project_id, wp_index_id, wp_id):
        raise OperationalError("UPDATE procedure_row_tasks", {}, Exception("connection reset"))

    monkeypatch.setattr(ProcedureTaskMaterializationService, "bind_working_paper", _db_down)
    out = await _preview(db, project, manager, staff, wi)
    prep = out["materialization"]
    assert out["preparation_ready"] is False and prep["ready"] is False
    assert prep["error"] == "程序行定义导入或任务生成失败：OperationalError"
    assert (prep["definitions_created"], prep["tasks_created"], prep["tasks_bound"]) == (0, 0, 0), \
        "绑定底稿前已物化的行随保存点回滚，计数不得照报"
    left = (await db.execute(sa.select(sa.func.count()).select_from(ProcedureRowTask).where(
        ProcedureRowTask.project_id == project.id))).scalar_one()
    assert left == 0 and out["summary"]["targets"] == 0
    assert out["hint"] == prep["error"]


async def test_preview_ready_and_programming_error_propagates(db, monkeypatch):
    project, manager, staff, wi = await _delegation_world(db)
    ok = await _preview(db, project, manager, staff, wi)
    assert ok["preparation_ready"] is True and ok["materialization"]["ready"] is True
    assert ok["summary"]["targets"] > 0

    async def _bug(self, project_id, wp_index_id, wp_id):
        raise AttributeError("'NoneType' object has no attribute 'id'")

    monkeypatch.setattr(ProcedureTaskMaterializationService, "bind_working_paper", _bug)
    with pytest.raises(AttributeError):
        await _preview(db, project, manager, staff, wi)
