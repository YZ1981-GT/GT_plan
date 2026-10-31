"""人员档案绑定的真实 PostgreSQL 并发（spec batch-project-authorization-and-lock-hardening R6）。

在独立 schema 里复制所需表结构（不复制触发器，外键按 ``_FOREIGN_KEYS`` 单独补齐），绑定与委派保存都会写
只追加的失效发件箱，放在共享库 public 里会留下删不掉的记录；用例结束整体 DROP SCHEMA，不留任何残留。
"""
from __future__ import annotations

import asyncio
import contextlib
import uuid

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import engine as app_engine
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.staff_account_binding_service import (
    ALREADY_BOUND,
    HAS_ASSIGNMENTS,
    bind_staff_to_user,
    unbind_staff_from_user,
)

_TABLES = (
    "users", "staff_members", "projects", "project_users", "project_assignments",
    "wp_visibility_policy_epoch", "wp_visibility_invalidation_outbox", "notifications",
    "procedure_row_tasks",
)
_FOREIGN_KEYS = (
    ("staff_members", "user_id", "users"),
    ("project_users", "project_id", "projects"),
    ("project_users", "user_id", "users"),
    ("project_assignments", "project_id", "projects"),
    ("project_assignments", "staff_id", "staff_members"),
    ("wp_visibility_policy_epoch", "project_id", "projects"),
    ("wp_visibility_invalidation_outbox", "project_id", "projects"),
    ("notifications", "recipient_id", "users"),
)


def _url() -> str:
    url = settings.DATABASE_URL
    return url.replace("postgresql://", "postgresql+asyncpg://", 1) if url.startswith("postgresql://") else url


async def _bind_outcome(factory, barrier, *, user_id, staff_id):
    async with factory() as session:
        await barrier.wait()
        try:
            result = await bind_staff_to_user(
                session, user_id=user_id, staff_id=staff_id, actor_user_id=user_id,
            )
            await session.commit()
            return result
        except Exception as exc:  # noqa: BLE001 — 由断言区分预期冲突与死锁等异常
            await session.rollback()
            return exc


def _conflict_code(outcome) -> str | None:
    if isinstance(outcome, HTTPException) and isinstance(outcome.detail, dict):
        return outcome.detail.get("error_code")
    return None


@contextlib.asynccontextmanager
async def _isolated_schema():
    """独立 schema 里复制表结构并补齐外键，用完整体 DROP（只追加的发件箱不会留在 public）。"""
    if app_engine.dialect.name != "postgresql":
        pytest.skip("需要 PostgreSQL")
    schema = f"staff_binding_{uuid.uuid4().hex[:10]}"
    admin_engine = create_async_engine(_url(), poolclass=NullPool)
    async with admin_engine.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        for table in _TABLES:
            await connection.exec_driver_sql(
                f'CREATE TABLE "{schema}"."{table}" (LIKE public."{table}" '
                "INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES INCLUDING GENERATED)"
            )
        # LIKE 不复制外键；外键检查的 KEY SHARE 锁正是锁序问题的来源，必须补齐才能测出死锁。
        for table, column, target in _FOREIGN_KEYS:
            await connection.exec_driver_sql(
                f'ALTER TABLE "{schema}"."{table}" ADD FOREIGN KEY ("{column}") '
                f'REFERENCES "{schema}"."{target}" (id)'
            )
    engine = create_async_engine(
        _url(), poolclass=NullPool,
        connect_args={"server_settings": {"search_path": f'"{schema}",public'}},
    )
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin_engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_concurrent_binding_is_one_to_one_and_does_not_deadlock_with_assignment_save():
    async with _isolated_schema() as factory:
        async with factory() as setup:
            def person(tag: str) -> User:
                return User(username=f"bind_pg_{tag}", email=f"bind_pg_{tag}@example.test",
                            hashed_password="x", role=UserRole.auditor)

            u_same, u_left, u_right = person("same"), person("left"), person("right")
            s_first, s_second, s_shared = (
                StaffMember(name="并发档案一", employee_no="PG-BIND-1"),
                StaffMember(name="并发档案二", employee_no="PG-BIND-2"),
                StaffMember(name="并发共享档案", employee_no="PG-BIND-3"),
            )
            setup.add_all([u_same, u_left, u_right, s_first, s_second, s_shared])
            await setup.commit()
            ids = {key: value.id for key, value in {
                "u_same": u_same, "u_left": u_left, "u_right": u_right,
                "s_first": s_first, "s_second": s_second, "s_shared": s_shared,
            }.items()}

        # ① 两份档案同时绑定同一账号：只能一份成功。
        barrier = asyncio.Barrier(2)
        same_user = await asyncio.wait_for(asyncio.gather(
            _bind_outcome(factory, barrier, user_id=ids["u_same"], staff_id=ids["s_first"]),
            _bind_outcome(factory, barrier, user_id=ids["u_same"], staff_id=ids["s_second"]),
        ), timeout=10)
        assert sum(isinstance(item, dict) for item in same_user) == 1
        assert [_conflict_code(item) for item in same_user if not isinstance(item, dict)] == [ALREADY_BOUND]

        # ② 同一份档案同时绑定两个账号：只能一个成功。
        barrier = asyncio.Barrier(2)
        same_staff = await asyncio.wait_for(asyncio.gather(
            _bind_outcome(factory, barrier, user_id=ids["u_left"], staff_id=ids["s_shared"]),
            _bind_outcome(factory, barrier, user_id=ids["u_right"], staff_id=ids["s_shared"]),
        ), timeout=10)
        assert sum(isinstance(item, dict) for item in same_staff) == 1
        assert [_conflict_code(item) for item in same_staff if not isinstance(item, dict)] == [ALREADY_BOUND]

        async with factory() as verify:
            bound = (await verify.execute(sa.select(StaffMember.user_id, sa.func.count()).where(
                StaffMember.user_id.is_not(None),
            ).group_by(StaffMember.user_id))).all()
            assert all(count == 1 for _user, count in bound)

        # ③ 绑定与委派保存并发：两边都提交（无死锁），最终账号在项目里有委派对应的成员行。
        from app.services.assignment_service import AssignmentService

        for round_no in range(3):
            async with factory() as setup:
                user = User(username=f"bind_pg_race_{round_no}", email=f"bind_pg_race_{round_no}@example.test",
                            hashed_password="x", role=UserRole.auditor)
                staff = StaffMember(name=f"并发委派档案{round_no}", employee_no=f"PG-RACE-{round_no}")
                proj = Project(name=f"【测试】绑定并发{round_no}", client_name="【测试】绑定并发",
                               short_name="绑定并发", audit_year=2099, report_scope="standalone")
                setup.add_all([user, staff, proj])
                await setup.flush()
                setup.add(ProjectAssignment(project_id=proj.id, staff_id=staff.id, role="auditor"))
                await setup.commit()
                user_id, staff_id, project_id = user.id, staff.id, proj.id

            barrier = asyncio.Barrier(2)

            async def save_assignment():
                async with factory() as session:
                    await barrier.wait()
                    try:
                        await AssignmentService(session).save_assignments(
                            project_id, [{"staff_id": staff_id, "role": "manager"}], assigned_by=None,
                        )
                        await session.commit()
                        return "saved"
                    except Exception as exc:  # noqa: BLE001
                        await session.rollback()
                        return exc

            outcomes = await asyncio.wait_for(asyncio.gather(
                _bind_outcome(factory, barrier, user_id=user_id, staff_id=staff_id),
                save_assignment(),
            ), timeout=15)
            assert isinstance(outcomes[0], dict) and outcomes[1] == "saved", outcomes
            async with factory() as verify:
                member = (await verify.execute(sa.select(ProjectUser.role, ProjectUser.permission_level).where(
                    ProjectUser.project_id == project_id, ProjectUser.user_id == user_id,
                    ProjectUser.is_deleted == sa.false(),
                ))).all()
                assert member == [(ProjectUserRole.manager, PermissionLevel.edit)], (round_no, member)


async def _seed(factory, tag: str, *, bound: bool):
    async with factory() as session:
        user = User(username=f"bind_pg_{tag}", email=f"bind_pg_{tag}@example.test",
                    hashed_password="x", role=UserRole.auditor)
        staff = StaffMember(name=f"交错档案{tag}", employee_no=f"PG-ORDER-{tag}")
        proj = Project(name=f"【测试】交错{tag}", client_name="【测试】绑定交错", short_name=tag,
                       audit_year=2099, report_scope="standalone")
        session.add_all([user, staff, proj])
        await session.flush()
        if bound:
            staff.user_id = user.id
        await session.commit()
        return user.id, staff.id, proj.id


async def _save_team(session, project_id, staff_id) -> None:
    from app.services.assignment_service import AssignmentService

    await AssignmentService(session).save_assignments(
        project_id, [{"staff_id": staff_id, "role": "manager"}], assigned_by=None,
    )


async def _commit_save(factory, project_id, staff_id):
    async with factory() as session:
        await _save_team(session, project_id, staff_id)
        await session.commit()
        return "saved"


async def _commit_unbind(factory, user_id, staff_id):
    async with factory() as session:
        try:
            result = await unbind_staff_from_user(session, user_id=user_id, staff_id=staff_id)
            await session.commit()
            return result
        except Exception as exc:  # noqa: BLE001 — 由断言区分预期冲突
            await session.rollback()
            return exc


async def _state(factory, user_id, staff_id, project_id):
    async with factory() as verify:
        members = (await verify.execute(sa.select(ProjectUser.role, ProjectUser.permission_level).where(
            ProjectUser.project_id == project_id, ProjectUser.user_id == user_id,
            ProjectUser.is_deleted == sa.false(),
        ))).all()
        bound = await verify.scalar(sa.select(StaffMember.user_id).where(StaffMember.id == staff_id))
        team = await verify.scalar(sa.select(sa.func.count()).select_from(ProjectAssignment).where(
            ProjectAssignment.project_id == project_id, ProjectAssignment.staff_id == staff_id,
            ProjectAssignment.is_deleted == sa.false(),
        ))
        return members, bound, team


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_team_save_does_not_deadlock_with_binding_paused_between_its_two_locks(monkeypatch):
    """绑定已锁住委派、还没锁档案时开始保存团队（档案原本就在团队里）：保存须先等委派锁，
    而不是先占档案锁 —— 否则绑定再要档案锁时两边成环（PG 报死锁）。时序由事件控制，结果确定。"""
    from app.services import staff_account_binding_service as svc

    assignments_locked, go = asyncio.Event(), asyncio.Event()
    original = svc._lock_staff_row

    async def paused(db, staff_id):
        assignments_locked.set()
        await go.wait()
        return await original(db, staff_id)

    monkeypatch.setattr(svc, "_lock_staff_row", paused)
    async with _isolated_schema() as factory:
        user_id, staff_id, project_id = await _seed(factory, "paused", bound=False)
        async with factory() as setup:
            setup.add(ProjectAssignment(project_id=project_id, staff_id=staff_id, role="auditor"))
            await setup.commit()

        bind = asyncio.create_task(_bind_outcome(factory, asyncio.Barrier(1), user_id=user_id, staff_id=staff_id))
        await asyncio.wait_for(assignments_locked.wait(), timeout=5)

        async def save():
            try:
                return await _commit_save(factory, project_id, staff_id)
            except Exception as exc:  # noqa: BLE001 — 死锁等异常由断言报出
                return exc

        saving = asyncio.create_task(save())
        await asyncio.sleep(0.6)
        go.set()
        outcomes = await asyncio.wait_for(asyncio.gather(bind, saving), timeout=15)
        assert isinstance(outcomes[0], dict) and outcomes[1] == "saved", outcomes
        assert await _state(factory, user_id, staff_id, project_id) == (
            [(ProjectUserRole.manager, PermissionLevel.edit)], user_id, 1)


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_binding_and_team_save_serialize_on_staff_row_in_every_order():
    """档案原本不在项目团队里、保存团队把它加进来（复核 P1-2）：一方未提交时另一方必须等待，
    提交后读到对方的结果。原先保存团队读档案账号不加锁 ⇒ 绑定漏建成员行、解绑后残留成员行。"""
    async with _isolated_schema() as factory:
        # ① 绑定在前（未提交）、保存团队在后：保存须等绑定提交，再按新账号补成员行。
        user_id, staff_id, project_id = await _seed(factory, "bind_first", bound=False)
        async with factory() as binder:
            await bind_staff_to_user(binder, user_id=user_id, staff_id=staff_id, actor_user_id=user_id)
            save = asyncio.create_task(_commit_save(factory, project_id, staff_id))
            await asyncio.sleep(0.6)
            waited = not save.done()
            await binder.commit()
        assert await asyncio.wait_for(save, timeout=10) == "saved"
        assert await _state(factory, user_id, staff_id, project_id) == (
            [(ProjectUserRole.manager, PermissionLevel.edit)], user_id, 1)
        assert waited, "保存团队没有等待未提交的绑定"

        # ② 解绑在前（未提交）、保存团队在后：保存须等解绑提交，不得按旧账号写成员行。
        user_id, staff_id, project_id = await _seed(factory, "unbind_first", bound=True)
        async with factory() as unbinder:
            await unbind_staff_from_user(unbinder, user_id=user_id, staff_id=staff_id)
            save = asyncio.create_task(_commit_save(factory, project_id, staff_id))
            await asyncio.sleep(0.6)
            waited = not save.done()
            await unbinder.commit()
        assert await asyncio.wait_for(save, timeout=10) == "saved"
        assert await _state(factory, user_id, staff_id, project_id) == ([], None, 1)
        assert waited, "保存团队没有等待未提交的解绑"

        # ③ 保存团队在前（未提交）、解绑在后：解绑须等保存提交，再看到新委派而 409，不改数据。
        user_id, staff_id, project_id = await _seed(factory, "save_first", bound=True)
        async with factory() as saver:
            await _save_team(saver, project_id, staff_id)
            unbind = asyncio.create_task(_commit_unbind(factory, user_id, staff_id))
            await asyncio.sleep(0.6)
            waited = not unbind.done()
            await saver.commit()
        outcome = await asyncio.wait_for(unbind, timeout=10)
        assert _conflict_code(outcome) == HAS_ASSIGNMENTS, outcome
        assert await _state(factory, user_id, staff_id, project_id) == (
            [(ProjectUserRole.manager, PermissionLevel.edit)], user_id, 1)
        assert waited, "解绑没有等待未提交的团队保存"
