# Feature: procedure-delegation-notification — Task 8 三粒度 delegation 与安全 preview/apply
"""ProcedureDelegationService 测试：Properties P11-P15 + PostgreSQL 集成。

Task 8 / 需求 4.1-4.10, 6.4, 10.7 / Design C6、D4、D8：

- **P11（selector 展开等价）**：Requirements 4.1, 4.3 —— SQLite Hypothesis，cycle/workpaper selector
  展开集合 == 对全项目 tasks 应用范围+粗裁+applicability 谓词后的 row selector 集合。
- **P12（preview token 防篡改与越权）**：Requirements 4.2, 4.4, 4.5 —— PG，单点变化（request hash /
  actor / project / operation / TTL / 目标版本 / 成员快照）→ apply 409 零副作用。
- **P13（preview 最多一次消费）**：Requirements 4.5, 4.6 —— PG，一次消费 + request_id 幂等 + 二次 409。
- **P14（批量委派原子与 owner 隔离）**：Requirements 4.9, 4.10 —— PG，任一冲突 → 全批零写；
  委派不改 WorkingPaper.assigned_to / ProjectAssignment.assigned_cycles。
- **P15（同人委派业务 no-op）**：Requirements 4.8 —— SQLite，重复同执行人委派不递增 version、无 history/outbox。

数据库约束/事务在 PostgreSQL 验证，不以 sqlite 替代（memory 铁律）；PBT 用项目 fast profile。
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings as app_settings
from app.core.migration_runner import MigrationRunner
from app.models.base import Base
from app.models.procedure_models import (
    ProcedureInstance,
    ProcedureRowDefinition,
    ProcedureRowTask,
    ProcedureRowTaskHistory,
)
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services.procedure_delegation_service import (
    CONFLICT_REJECT,
    CONFLICT_REPLACE,
    DelegationConflictError,
    ProcedureDelegationService,
)

import app.models.procedure_models  # noqa: F401
import app.models.phase15_models  # noqa: F401
import app.models.core  # noqa: F401
import app.models.staff_models  # noqa: F401

_V105 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V105__procedure_row_tasks.sql"
)
_IS_PG = app_settings.DATABASE_URL.startswith("postgresql")


# ===========================================================================
# SQLite 环境 + 种子
# ===========================================================================


async def _make_sqlite_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    project_id = uuid.uuid4()
    async with factory() as s:
        await s.commit()
    return engine, factory, project_id


async def _seed_user_staff(factory, *, name="张三"):
    """在 SQLite 建 user + active staff(user_id) + project_assignment 供委派/SOD 校验。"""
    from app.models.core import User, UserRole
    from app.models.staff_models import StaffMember

    user_id = uuid.uuid4()
    staff_id = uuid.uuid4()
    async with factory() as s:
        s.add(
            User(
                id=user_id,
                username=f"u_{uuid.uuid4().hex[:8]}",
                email=f"{uuid.uuid4().hex[:8]}@x.com",
                hashed_password="x",
                role=UserRole.auditor,
            )
        )
        s.add(StaffMember(id=staff_id, user_id=user_id, name=name, source="custom"))
        await s.commit()
    return user_id, staff_id


async def _seed_wp_index(factory, project_id, wp_code, cycle):
    wp_index_id = uuid.uuid4()
    async with factory() as s:
        s.add(
            WpIndex(
                id=wp_index_id,
                project_id=project_id,
                wp_code=wp_code,
                wp_name=wp_code,
                audit_cycle=cycle,
                status=WpStatus.not_started,
            )
        )
        await s.commit()
    return wp_index_id


async def _seed_definition(factory, template_code, sheet_key, definition_key, *, revision="a" * 64):
    async with factory() as s:
        s.add(
            ProcedureRowDefinition(
                definition_key=definition_key,
                template_code=template_code,
                template_revision_hash=revision,
                sheet_key=sheet_key,
                source_locator={},
                program_no="1",
                procedure_text="程序文本",
                ref_snapshot=[],
                legacy_aliases=[],
                normalized_content={},
            )
        )
        await s.commit()


async def _seed_task(
    factory, project_id, wp_index_id, wp_code, sheet_key, definition_key, *,
    revision="a" * 64, workflow="unassigned", applicability="execute", cycle="D",
    assignee=None, lock_version=0, assignment_version=0, wp_id=None,
):
    task_id = uuid.uuid4()
    async with factory() as s:
        s.add(
            ProcedureRowTask(
                id=task_id,
                project_id=project_id,
                wp_index_id=wp_index_id,
                wp_id=wp_id,
                definition_key=definition_key,
                sheet_key=sheet_key,
                wp_code=wp_code,
                definition_revision_hash=revision,
                audit_cycle_snapshot=cycle,
                applicability_status=applicability,
                workflow_status=workflow,
                assignee_staff_id=assignee,
                lock_version=lock_version,
                assignment_version=assignment_version,
            )
        )
        await s.commit()
    return task_id


async def _seed_scope_instance(factory, project_id, cycle, wp_code, status):
    async with factory() as s:
        s.add(
            ProcedureInstance(
                id=uuid.uuid4(),
                project_id=project_id,
                audit_cycle=cycle,
                procedure_code=wp_code,
                procedure_name=wp_code,
                status=status,
                wp_code=wp_code,
            )
        )
        await s.commit()


async def _task_state(factory, task_id):
    async with factory() as s:
        return (
            await s.execute(
                sa.select(
                    ProcedureRowTask.workflow_status,
                    ProcedureRowTask.assignee_staff_id,
                    ProcedureRowTask.assignment_version,
                    ProcedureRowTask.lock_version,
                ).where(ProcedureRowTask.id == task_id)
            )
        ).first()


async def _history_count(factory, task_id):
    async with factory() as s:
        return (
            await s.execute(
                sa.select(sa.func.count()).select_from(ProcedureRowTaskHistory).where(
                    ProcedureRowTaskHistory.task_id == task_id
                )
            )
        ).scalar()


# ===========================================================================
# P11：selector 展开等价（SQLite Hypothesis）
# Validates: Requirements 4.1, 4.3
# ===========================================================================
class TestP11SelectorEquivalence:
    @given(
        applicabilities=st.lists(st.sampled_from(["execute", "not_applicable"]), min_size=1, max_size=6),
        trim_scope=st.booleans(),
    )
    @settings(max_examples=5, deadline=None)
    def test_cycle_workpaper_row_expand_equivalent(self, applicabilities, trim_scope):
        async def scenario():
            engine, factory, project_id = await _make_sqlite_env()
            try:
                cycle = "D"
                wp_code = "D2"
                wp_index_id = await _seed_wp_index(factory, project_id, wp_code, cycle)
                if trim_scope:
                    await _seed_scope_instance(factory, project_id, cycle, wp_code, "skip")
                all_task_ids: list[uuid.UUID] = []
                for i, app in enumerate(applicabilities):
                    dk = f"{wp_code}A::{wp_code}A::{i:04x}"
                    await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                    tid = await _seed_task(
                        factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk,
                        applicability=app, cycle=cycle,
                    )
                    all_task_ids.append(tid)

                async with factory() as s:
                    svc = ProcedureDelegationService(s)
                    cyc = await svc.resolve_targets(project_id, {"kind": "cycle", "cycle": cycle})
                    wpk = await svc.resolve_targets(
                        project_id, {"kind": "workpaper", "wp_index_ids": [str(wp_index_id)]}
                    )
                    row = await svc.resolve_targets(
                        project_id,
                        {"kind": "row", "task_ids": [str(t) for t in all_task_ids]},
                    )
                cyc_ids = {str(t.id) for t in cyc}
                wpk_ids = {str(t.id) for t in wpk}
                row_ids = {str(t.id) for t in row}
                # 三种 selector 展开等价
                assert cyc_ids == wpk_ids == row_ids
                # 谓词正确：粗裁保留 + applicability=execute
                if trim_scope:
                    assert cyc_ids == set()
                else:
                    expected = {
                        str(tid)
                        for tid, app in zip(all_task_ids, applicabilities)
                        if app == "execute"
                    }
                    assert cyc_ids == expected
            finally:
                await engine.dispose()

        asyncio.run(scenario())


# ===========================================================================
# P15：同人委派业务 no-op（SQLite）
# Validates: Requirements 4.8
# ===========================================================================
class TestP15SameAssigneeNoop:
    def test_same_assignee_is_business_noop(self):
        async def scenario():
            engine, factory, project_id = await _make_sqlite_env()
            try:
                cycle, wp_code = "D", "D2"
                wp_index_id = await _seed_wp_index(factory, project_id, wp_code, cycle)
                actor_user, staff_id = await _seed_user_staff(factory)
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                # 任务已分配给 staff_id（assigned, version=1）
                task_id = await _seed_task(
                    factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk,
                    workflow="assigned", assignee=staff_id, assignment_version=1, lock_version=1,
                )
                before = await _task_state(factory, task_id)
                before_hist = await _history_count(factory, task_id)
                selector = {"kind": "row", "task_ids": [str(task_id)]}

                async with factory() as s:
                    svc = ProcedureDelegationService(s)
                    pv = await svc.preview(
                        project_id, actor_user_id=actor_user, selector=selector,
                        assignee_staff_id=staff_id,
                    )
                    await s.commit()
                assert pv["status"] == "ready"
                assert pv["summary"]["unchanged"] == 1
                assert pv["summary"]["would_assign"] == 0
                assert pv["summary"]["would_reassign"] == 0

                async with factory() as s:
                    svc = ProcedureDelegationService(s)
                    res = await svc.apply(
                        project_id, actor_user_id=actor_user,
                        preview_id=uuid.UUID(pv["preview_id"]), request_id="noop-1",
                        selector=selector, assignee_staff_id=staff_id,
                    )
                    await s.commit()
                assert res["applied"] == 0
                assert res["unchanged"] == 1

                after = await _task_state(factory, task_id)
                after_hist = await _history_count(factory, task_id)
                # 无版本递增、无新 history/outbox
                assert after[2] == before[2]  # assignment_version 不变
                assert after[3] == before[3]  # lock_version 不变
                assert after_hist == before_hist
            finally:
                await engine.dispose()

        asyncio.run(scenario())

    def test_first_assign_and_reassign_bump_version_and_clear_ack(self):
        """首次分配递增 assignment_version；换人（replace_with_reason）再递增并清 ack。"""
        async def scenario():
            engine, factory, project_id = await _make_sqlite_env()
            try:
                cycle, wp_code = "D", "D2"
                wp_index_id = await _seed_wp_index(factory, project_id, wp_code, cycle)
                actor_user, staff_a = await _seed_user_staff(factory, name="甲")
                _actor_b, staff_b = await _seed_user_staff(factory, name="乙")
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                task_id = await _seed_task(
                    factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk,
                    workflow="unassigned",
                )
                selector = {"kind": "row", "task_ids": [str(task_id)]}
                # 首次分配 → staff_a
                async with factory() as s:
                    svc = ProcedureDelegationService(s)
                    pv = await svc.preview(project_id, actor_user_id=actor_user, selector=selector, assignee_staff_id=staff_a)
                    await s.commit()
                async with factory() as s:
                    svc = ProcedureDelegationService(s)
                    await svc.apply(project_id, actor_user_id=actor_user, preview_id=uuid.UUID(pv["preview_id"]), request_id="a1", selector=selector, assignee_staff_id=staff_a)
                    await s.commit()
                st1 = await _task_state(factory, task_id)
                assert st1[0] == "assigned" and st1[1] == staff_a and st1[2] == 1

                # 换人 → staff_b（replace_with_reason）
                async with factory() as s:
                    svc = ProcedureDelegationService(s)
                    pv2 = await svc.preview(
                        project_id, actor_user_id=actor_user, selector=selector,
                        assignee_staff_id=staff_b, conflict_policy=CONFLICT_REPLACE, reason="人员调整测试",
                    )
                    await s.commit()
                assert pv2["summary"]["would_reassign"] == 1
                async with factory() as s:
                    svc = ProcedureDelegationService(s)
                    res2 = await svc.apply(
                        project_id, actor_user_id=actor_user, preview_id=uuid.UUID(pv2["preview_id"]),
                        request_id="b1", selector=selector, assignee_staff_id=staff_b,
                        conflict_policy=CONFLICT_REPLACE, reason="人员调整测试",
                    )
                    await s.commit()
                assert res2["applied"] == 1
                st2 = await _task_state(factory, task_id)
                assert st2[1] == staff_b and st2[2] == 2  # assignment_version 再增
            finally:
                await engine.dispose()

        asyncio.run(scenario())

    def test_reject_on_conflict_default_atomic_zero_write(self):
        """默认 reject_on_conflict：不同执行人 → apply 409 零写（SQLite 行为层）。"""
        async def scenario():
            engine, factory, project_id = await _make_sqlite_env()
            try:
                cycle, wp_code = "D", "D2"
                wp_index_id = await _seed_wp_index(factory, project_id, wp_code, cycle)
                actor_user, staff_a = await _seed_user_staff(factory, name="甲")
                _b, staff_b = await _seed_user_staff(factory, name="乙")
                # 两个任务：t1 未分配、t2 已分配给 staff_a
                dk1 = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                dk2 = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk1)
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk2)
                t1 = await _seed_task(factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk1, workflow="unassigned")
                t2 = await _seed_task(
                    factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk2,
                    workflow="assigned", assignee=staff_a, assignment_version=1, lock_version=1,
                )
                selector = {"kind": "row", "task_ids": [str(t1), str(t2)]}
                # 委派给 staff_b（默认 reject）：t2 冲突 → 整批 409
                async with factory() as s:
                    svc = ProcedureDelegationService(s)
                    pv = await svc.preview(project_id, actor_user_id=actor_user, selector=selector, assignee_staff_id=staff_b)
                    await s.commit()
                assert pv["summary"]["conflict"] == 1
                async with factory() as s:
                    svc = ProcedureDelegationService(s)
                    with pytest.raises(DelegationConflictError) as ei:
                        await svc.apply(project_id, actor_user_id=actor_user, preview_id=uuid.UUID(pv["preview_id"]), request_id="c1", selector=selector, assignee_staff_id=staff_b)
                    await s.rollback()
                assert ei.value.status_code == 409
                # 零写：t1 仍 unassigned
                st1 = await _task_state(factory, t1)
                assert st1[0] == "unassigned" and st1[1] is None
                assert await _history_count(factory, t1) == 0
            finally:
                await engine.dispose()

        asyncio.run(scenario())


# ===========================================================================
# PostgreSQL 集成：P12/P13/P14（真实约束/事务/一次消费）
# ===========================================================================
async def _apply_v105(engine) -> None:
    sql = _V105.read_text(encoding="utf-8")
    for stmt in MigrationRunner._split_sql_statements(sql):
        async with engine.begin() as conn:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (delegation apply integration)")
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    await _apply_v105(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _pick_project_wp(factory):
    async with factory() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT wp.project_id, wp.wp_index_id, wp.id, wi.wp_code, COALESCE(wi.audit_cycle,'A') "
                    "FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id "
                    "WHERE wp.is_deleted=false AND wi.is_deleted=false LIMIT 1"
                )
            )
        ).first()
    return row


async def _pick_user(factory):
    async with factory() as s:
        row = (await s.execute(sa.text("SELECT id FROM users LIMIT 1"))).first()
    return row[0] if row else None


async def _insert_staff(factory, user_id, name):
    staff_id = uuid.uuid4()
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO staff_members (id, user_id, name, source, is_deleted) "
                "VALUES (:id, :uid, :n, 'custom', false)"
            ),
            {"id": staff_id, "uid": user_id, "n": name},
        )
        await s.commit()
    return staff_id


async def _pg_insert_definition(factory, template_code, sheet_key, definition_key, revision):
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_definitions "
                "(definition_key, template_code, template_revision_hash, sheet_key, procedure_text) "
                "VALUES (:k, :tc, :h, :sk, :pt)"
            ),
            {"k": definition_key, "tc": template_code, "h": revision, "sk": sheet_key, "pt": "程序文本"},
        )
        await s.commit()


async def _pg_insert_task(
    factory, project_id, wp_index_id, wp_code, sheet_key, definition_key, revision, cycle,
    *, workflow="unassigned", assignee=None, wp_id=None,
):
    task_id = uuid.uuid4()
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_tasks "
                "(id, project_id, wp_index_id, wp_id, definition_key, sheet_key, wp_code, "
                " definition_revision_hash, audit_cycle_snapshot, applicability_status, "
                " workflow_status, assignee_staff_id, assignment_version, lock_version) "
                "VALUES (:id, :pid, :wi, :wp, :dk, :sk, :wc, :h, :cy, 'execute', "
                " :wf, :asg, :av, 0)"
            ),
            {"id": task_id, "pid": project_id, "wi": wp_index_id, "wp": wp_id, "dk": definition_key,
             "sk": sheet_key, "wc": wp_code, "h": revision, "cy": cycle, "wf": workflow,
             "asg": assignee, "av": 1 if assignee else 0},
        )
        await s.commit()
    return task_id


async def _pg_task_row(factory, task_id):
    async with factory() as s:
        return (
            await s.execute(
                sa.text(
                    "SELECT workflow_status, assignee_staff_id, assignment_version, lock_version "
                    "FROM procedure_row_tasks WHERE id=:id"
                ),
                {"id": task_id},
            )
        ).first()


async def _pg_history_count(factory, task_id):
    async with factory() as s:
        return (
            await s.execute(
                sa.text("SELECT count(*) FROM procedure_row_task_history WHERE task_id=:id"),
                {"id": task_id},
            )
        ).scalar()


async def _pg_outbox_count(factory, batch_or_task):
    async with factory() as s:
        return (
            await s.execute(
                sa.text("SELECT count(*) FROM task_events WHERE aggregate_id=:id"),
                {"id": batch_or_task},
            )
        ).scalar()


async def _pg_cleanup(factory, definition_keys, task_ids, staff_ids, preview_ids=None):
    async with factory() as s:
        for tid in task_ids:
            await s.execute(sa.text("DELETE FROM procedure_row_task_history WHERE task_id=:id"), {"id": tid})
            await s.execute(sa.text("DELETE FROM task_events WHERE aggregate_id=:id"), {"id": tid})
            await s.execute(sa.text("DELETE FROM procedure_row_tasks WHERE id=:id"), {"id": tid})
        for k in definition_keys:
            await s.execute(sa.text("DELETE FROM procedure_row_definitions WHERE definition_key=:k"), {"k": k})
        for pid in (preview_ids or []):
            await s.execute(sa.text("DELETE FROM procedure_operation_previews WHERE id=:id"), {"id": pid})
        for sid in staff_ids:
            await s.execute(sa.text("DELETE FROM staff_members WHERE id=:id"), {"id": sid})
        await s.commit()


@pytest.mark.asyncio
class TestPgDelegation:
    async def test_one_time_consume_and_idempotent(self, pg_engine):
        """P13：一次消费；相同 request_id 幂等；不同 request_id → 409。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp(factory)
        user_id = await _pick_user(factory)
        if picked is None or user_id is None:
            pytest.skip("dev 库无可复用 project/wp_index/user")
        project_id, wp_index_id, _wp_id, wp_code, cycle = picked
        tmpl = f"{wp_code}A"
        dk = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        rev = "a" * 64
        staff_id = await _insert_staff(factory, user_id, "委派测试甲")
        await _pg_insert_definition(factory, tmpl, tmpl, dk, rev)
        task_id = await _pg_insert_task(factory, project_id, wp_index_id, wp_code, tmpl, dk, rev, cycle)
        selector = {"kind": "row", "task_ids": [str(task_id)]}
        pv_id = None
        try:
            async with factory() as s:
                svc = ProcedureDelegationService(s)
                pv = await svc.preview(project_id, actor_user_id=user_id, selector=selector, assignee_staff_id=staff_id)
                await s.commit()
            pv_id = uuid.UUID(pv["preview_id"])
            async with factory() as s:
                svc = ProcedureDelegationService(s)
                r1 = await svc.apply(project_id, actor_user_id=user_id, preview_id=pv_id, request_id="one-1", selector=selector, assignee_staff_id=staff_id)
                await s.commit()
            assert r1["applied"] == 1
            # 相同 request_id → 幂等旧 result
            async with factory() as s:
                svc = ProcedureDelegationService(s)
                r_replay = await svc.apply(project_id, actor_user_id=user_id, preview_id=pv_id, request_id="one-1", selector=selector, assignee_staff_id=staff_id)
                await s.commit()
            assert r_replay == r1
            # 不同 request_id → 409 已消费
            async with factory() as s:
                svc = ProcedureDelegationService(s)
                with pytest.raises(HTTPException) as ei:
                    await svc.apply(project_id, actor_user_id=user_id, preview_id=pv_id, request_id="one-2", selector=selector, assignee_staff_id=staff_id)
                await s.rollback()
            assert ei.value.status_code == 409
            # 真实分配 + 一条 history/outbox
            row = await _pg_task_row(factory, task_id)
            assert row[0] == "assigned" and row[1] == staff_id and row[2] == 1
            assert await _pg_history_count(factory, task_id) == 1
            assert await _pg_outbox_count(factory, task_id) == 1
        finally:
            await _pg_cleanup(factory, [dk], [task_id], [staff_id], [pv_id] if pv_id else [])

    async def test_tamper_and_version_change_409(self, pg_engine):
        """P12：request payload 篡改 / 目标版本变化 → apply 409 零副作用。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp(factory)
        user_id = await _pick_user(factory)
        if picked is None or user_id is None:
            pytest.skip("dev 库无可复用 project/wp_index/user")
        project_id, wp_index_id, _wp_id, wp_code, cycle = picked
        tmpl = f"{wp_code}A"
        dk = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        rev = "b" * 64
        staff_a = await _insert_staff(factory, user_id, "委派甲")
        staff_b = await _insert_staff(factory, user_id, "委派乙")
        await _pg_insert_definition(factory, tmpl, tmpl, dk, rev)
        task_id = await _pg_insert_task(factory, project_id, wp_index_id, wp_code, tmpl, dk, rev, cycle)
        selector = {"kind": "row", "task_ids": [str(task_id)]}
        pv_id = None
        try:
            async with factory() as s:
                svc = ProcedureDelegationService(s)
                pv = await svc.preview(project_id, actor_user_id=user_id, selector=selector, assignee_staff_id=staff_a)
                await s.commit()
            pv_id = uuid.UUID(pv["preview_id"])
            # 篡改：apply 用不同 assignee（request hash 不匹配）→ 409
            async with factory() as s:
                svc = ProcedureDelegationService(s)
                with pytest.raises(HTTPException) as ei:
                    await svc.apply(project_id, actor_user_id=user_id, preview_id=pv_id, request_id="tamper-1", selector=selector, assignee_staff_id=staff_b)
                await s.rollback()
            assert ei.value.status_code == 409
            # 未写入
            row = await _pg_task_row(factory, task_id)
            assert row[0] == "unassigned"
            assert await _pg_history_count(factory, task_id) == 0

            # 版本变化：外部 bump lock_version 后 apply（正确 payload）→ 409
            async with factory() as s:
                await s.execute(sa.text("UPDATE procedure_row_tasks SET lock_version=lock_version+1 WHERE id=:id"), {"id": task_id})
                await s.commit()
            async with factory() as s:
                svc = ProcedureDelegationService(s)
                with pytest.raises(HTTPException) as ei:
                    await svc.apply(project_id, actor_user_id=user_id, preview_id=pv_id, request_id="ver-1", selector=selector, assignee_staff_id=staff_a)
                await s.rollback()
            assert ei.value.status_code == 409
        finally:
            await _pg_cleanup(factory, [dk], [task_id], [staff_a, staff_b], [pv_id] if pv_id else [])

    async def test_batch_atomic_conflict_zero_write_and_owner_isolation(self, pg_engine):
        """P14：默认原子——任一冲突全批零写；委派不改 WorkingPaper.assigned_to。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp(factory)
        user_id = await _pick_user(factory)
        if picked is None or user_id is None:
            pytest.skip("dev 库无可复用 project/wp_index/user")
        project_id, wp_index_id, wp_id, wp_code, cycle = picked
        tmpl = f"{wp_code}A"
        dk1 = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        dk2 = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        rev = "c" * 64
        staff_a = await _insert_staff(factory, user_id, "批量甲")
        staff_b = await _insert_staff(factory, user_id, "批量乙")
        await _pg_insert_definition(factory, tmpl, tmpl, dk1, rev)
        await _pg_insert_definition(factory, tmpl, tmpl, dk2, rev)
        t1 = await _pg_insert_task(factory, project_id, wp_index_id, wp_code, tmpl, dk1, rev, cycle)
        t2 = await _pg_insert_task(
            factory, project_id, wp_index_id, wp_code, tmpl, dk2, rev, cycle,
            workflow="assigned", assignee=staff_a,
        )
        # 记录 WorkingPaper.assigned_to 基线
        async with factory() as s:
            wp_assignee_before = (
                await s.execute(sa.text("SELECT assigned_to FROM working_paper WHERE id=:id"), {"id": wp_id})
            ).scalar()
        selector = {"kind": "row", "task_ids": [str(t1), str(t2)]}
        pv_id = None
        try:
            async with factory() as s:
                svc = ProcedureDelegationService(s)
                pv = await svc.preview(project_id, actor_user_id=user_id, selector=selector, assignee_staff_id=staff_b)
                await s.commit()
            pv_id = uuid.UUID(pv["preview_id"])
            assert pv["summary"]["conflict"] == 1
            # 默认原子：t2 冲突 → 整批 409 零写
            async with factory() as s:
                svc = ProcedureDelegationService(s)
                with pytest.raises(HTTPException) as ei:
                    await svc.apply(project_id, actor_user_id=user_id, preview_id=pv_id, request_id="batch-1", selector=selector, assignee_staff_id=staff_b)
                await s.rollback()
            assert ei.value.status_code == 409
            # t1 未被分配（零写）
            r1 = await _pg_task_row(factory, t1)
            assert r1[0] == "unassigned" and r1[1] is None
            assert await _pg_history_count(factory, t1) == 0
            # owner 隔离：WorkingPaper.assigned_to 未变
            async with factory() as s:
                wp_assignee_after = (
                    await s.execute(sa.text("SELECT assigned_to FROM working_paper WHERE id=:id"), {"id": wp_id})
                ).scalar()
            assert wp_assignee_after == wp_assignee_before
        finally:
            await _pg_cleanup(factory, [dk1, dk2], [t1, t2], [staff_a, staff_b], [pv_id] if pv_id else [])

    async def test_best_effort_partial_and_shared_batch_id(self, pg_engine):
        """best_effort：冲突不阻断整批；成功任务共享 delegation_batch_id（逐任务 history/outbox）。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp(factory)
        user_id = await _pick_user(factory)
        if picked is None or user_id is None:
            pytest.skip("dev 库无可复用 project/wp_index/user")
        project_id, wp_index_id, _wp_id, wp_code, cycle = picked
        tmpl = f"{wp_code}A"
        dk1 = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        dk2 = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        rev = "d" * 64
        staff_a = await _insert_staff(factory, user_id, "尽力甲")
        staff_b = await _insert_staff(factory, user_id, "尽力乙")
        await _pg_insert_definition(factory, tmpl, tmpl, dk1, rev)
        await _pg_insert_definition(factory, tmpl, tmpl, dk2, rev)
        t1 = await _pg_insert_task(factory, project_id, wp_index_id, wp_code, tmpl, dk1, rev, cycle)
        t2 = await _pg_insert_task(
            factory, project_id, wp_index_id, wp_code, tmpl, dk2, rev, cycle,
            workflow="assigned", assignee=staff_a,
        )
        selector = {"kind": "row", "task_ids": [str(t1), str(t2)]}
        pv_id = None
        try:
            # replace_with_reason + best_effort：t1 assign、t2 reassign 均成功，共享 batch id
            async with factory() as s:
                svc = ProcedureDelegationService(s)
                pv = await svc.preview(
                    project_id, actor_user_id=user_id, selector=selector, assignee_staff_id=staff_b,
                    conflict_policy=CONFLICT_REPLACE, reason="尽力交付批量委派", best_effort=True,
                )
                await s.commit()
            pv_id = uuid.UUID(pv["preview_id"])
            async with factory() as s:
                svc = ProcedureDelegationService(s)
                res = await svc.apply(
                    project_id, actor_user_id=user_id, preview_id=pv_id, request_id="be-1",
                    selector=selector, assignee_staff_id=staff_b,
                    conflict_policy=CONFLICT_REPLACE, reason="尽力交付批量委派", best_effort=True,
                )
                await s.commit()
            assert res["applied"] == 2
            batch_id = res["delegation_batch_id"]
            # 逐任务 history + outbox 且共享 batch id
            assert await _pg_history_count(factory, t1) == 1
            assert await _pg_history_count(factory, t2) == 1
            async with factory() as s:
                cnt = (
                    await s.execute(
                        sa.text("SELECT count(*) FROM task_events WHERE delegation_batch_id=:b"),
                        {"b": batch_id},
                    )
                ).scalar()
            assert cnt == 2
        finally:
            await _pg_cleanup(factory, [dk1, dk2], [t1, t2], [staff_a, staff_b], [pv_id] if pv_id else [])
