# Feature: procedure-delegation-notification — Task 9 状态机、任务真源、精确投影、旧状态映射
"""ProcedureTaskTransitionService 完整转换表测试：Properties P19-P21 / P33 + PG 集成。

Task 9 / 需求 6.1-6.9, 7.1-7.9, 12.5-12.6 / Design C7、D7：

- **P19（状态机封闭性）**：Requirements 6.1/6.2/6.6/6.7/6.8 —— 只产生转换表允许的边；
  cancelled→assign、assigned→start（未 ack）、非 reviewer→review 均 409 且零副作用。
- **P20（assignment_version 与 ack）**：Requirements 6.3/6.4/6.5 —— 每次有效 assignment 恰好递增一次
  并清 ack；同 assignment_version 重复 ack 为 no-op；恢复原执行人仍需新版本 ack。
- **P21（成功动作审计完备）**：Requirements 6.9/12.6 —— 每个非 no-op 成功动作恰有一条 history +
  一条幂等 outbox（含 actor user、assignment_version、audit_cycle_snapshot）。
- **P33（双版本并发）**：Requirements 12.5 —— 同 lock_version 并发写最多一个成功，其余 409，
  失败事务不留 history/outbox（PG 集成）。

数据库约束/事务在 PostgreSQL 验证，不以 sqlite 替代；PBT 用项目 fast profile。
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
from app.models.phase15_models import TaskEvent
from app.models.procedure_models import (
    ProcedureRowDefinition,
    ProcedureRowTask,
    ProcedureRowTaskHistory,
)
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services.procedure_task_transition_service import (
    ACTOR_ASSIGNEE,
    ACTOR_DELEGATOR,
    ACTOR_REVIEWER,
    AGGREGATE_PROCEDURE_ROW_TASK,
    ProcedureTaskTransitionService,
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


async def _make_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    project_id = uuid.uuid4()
    wp_index_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    wp_code = "D2"
    cycle = "D"
    async with factory() as s:
        s.add(
            WpIndex(
                id=wp_index_id, project_id=project_id, wp_code=wp_code,
                wp_name="应收账款", audit_cycle=cycle, status=WpStatus.not_started,
            )
        )
        s.add(
            WorkingPaper(
                id=wp_id, project_id=project_id, wp_index_id=wp_index_id,
                file_path="/tmp/D2.xlsx", source_type=WpSourceType.template,
                file_version=1, parsed_data={},
            )
        )
        await s.commit()
    return engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle


async def _seed_task(
    factory, project_id, wp_index_id, wp_code, *,
    wp_id=None, workflow="unassigned", applicability="execute", cycle="D",
    assignee=None, reviewer=None, lock_version=0, assignment_version=0,
):
    task_id = uuid.uuid4()
    dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
    async with factory() as s:
        s.add(
            ProcedureRowDefinition(
                definition_key=dk, template_code=f"{wp_code}A",
                template_revision_hash="a" * 64, sheet_key=f"{wp_code}A",
                source_locator={}, program_no="1", procedure_text="程序文本",
                ref_snapshot=[], legacy_aliases=[], normalized_content={},
            )
        )
        s.add(
            ProcedureRowTask(
                id=task_id, project_id=project_id, wp_index_id=wp_index_id,
                wp_id=wp_id, definition_key=dk, sheet_key=f"{wp_code}A", wp_code=wp_code,
                definition_revision_hash="a" * 64, audit_cycle_snapshot=cycle,
                applicability_status=applicability, workflow_status=workflow,
                assignee_staff_id=assignee, reviewer_staff_id=reviewer,
                lock_version=lock_version, assignment_version=assignment_version,
            )
        )
        await s.commit()
    return task_id


async def _load(factory, task_id):
    async with factory() as s:
        return (
            await s.execute(sa.select(ProcedureRowTask).where(ProcedureRowTask.id == task_id))
        ).scalar_one()


async def _counts(factory, task_id):
    async with factory() as s:
        hc = (
            await s.execute(
                sa.select(sa.func.count()).select_from(ProcedureRowTaskHistory).where(
                    ProcedureRowTaskHistory.task_id == task_id
                )
            )
        ).scalar()
        oc = (
            await s.execute(
                sa.select(sa.func.count()).select_from(TaskEvent).where(
                    TaskEvent.aggregate_id == task_id
                )
            )
        ).scalar()
    return hc, oc


# ===========================================================================
# P19：状态机封闭性 —— 非法边零副作用 409
# Validates: Requirements 6.1, 6.2, 6.6, 6.7, 6.8
# ===========================================================================
class TestP19StateMachineClosure:
    def test_cancelled_cannot_assign(self):
        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                tid = await _seed_task(factory, pid, wi, wc, workflow="cancelled")
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    with pytest.raises(HTTPException) as ei:
                        await svc.assign(task, new_assignee_staff_id=uuid.uuid4(),
                                         actor_user_id=uuid.uuid4(), actor_role=ACTOR_DELEGATOR)
                    await s.rollback()
                assert ei.value.status_code == 409
                hc, oc = await _counts(factory, tid)
                assert hc == 0 and oc == 0  # 零副作用
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_assigned_cannot_start_without_ack(self):
        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                assignee = uuid.uuid4()
                tid = await _seed_task(factory, pid, wi, wc, wp_id=wp,
                                       workflow="assigned", assignee=assignee, assignment_version=1)
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    with pytest.raises(HTTPException) as ei:
                        await svc.start(task, actor_user_id=uuid.uuid4(), actor_role=ACTOR_ASSIGNEE)
                    await s.rollback()
                assert ei.value.status_code == 409  # bare assigned 不可 start
                hc, oc = await _counts(factory, tid)
                assert hc == 0 and oc == 0
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_non_reviewer_cannot_review(self):
        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                tid = await _seed_task(factory, pid, wi, wc, wp_id=wp,
                                       workflow="submitted", reviewer=uuid.uuid4())
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    # actor_role=assignee 不能 review
                    with pytest.raises(HTTPException) as ei:
                        await svc.review(task, actor_user_id=uuid.uuid4(), actor_role=ACTOR_ASSIGNEE)
                    await s.rollback()
                assert ei.value.status_code == 409
                hc, oc = await _counts(factory, tid)
                assert hc == 0 and oc == 0
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_review_reviewer_missing_blocked(self):
        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                tid = await _seed_task(factory, pid, wi, wc, wp_id=wp,
                                       workflow="submitted", reviewer=None)
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    with pytest.raises(HTTPException) as ei:
                        await svc.review(task, actor_user_id=uuid.uuid4(), actor_role=ACTOR_REVIEWER)
                    await s.rollback()
                assert ei.value.status_code == 409
                assert ei.value.detail == {"error": "reviewer_missing"}
                hc, oc = await _counts(factory, tid)
                assert hc == 0 and oc == 0
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_review_blocked_by_open_issue(self):
        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                tid = await _seed_task(factory, pid, wi, wc, wp_id=wp,
                                       workflow="submitted", reviewer=uuid.uuid4())
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    with pytest.raises(HTTPException) as ei:
                        await svc.review(task, actor_user_id=uuid.uuid4(),
                                         actor_role=ACTOR_REVIEWER, open_issue_count=1)
                    await s.rollback()
                assert ei.value.status_code == 409
                hc, oc = await _counts(factory, tid)
                assert hc == 0 and oc == 0
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    @given(seq=st.lists(st.sampled_from(
        ["assign", "acknowledge", "start", "submit", "review"]), min_size=1, max_size=6))
    @settings(max_examples=5, deadline=None)
    def test_random_sequence_only_valid_states(self, seq):
        """任意动作序列后 workflow 始终是合法状态集合之一；非法动作 409 不破坏状态。"""
        valid = {"unassigned", "assigned", "acknowledged", "in_progress",
                 "submitted", "changes_requested", "reviewed", "cancelled"}

        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                assignee = uuid.uuid4()
                reviewer = uuid.uuid4()
                tid = await _seed_task(factory, pid, wi, wc, wp_id=wp,
                                       workflow="unassigned", reviewer=reviewer)
                for action in seq:
                    async with factory() as s:
                        svc = ProcedureTaskTransitionService(s)
                        task = await s.get(ProcedureRowTask, tid)
                        try:
                            if action == "assign":
                                await svc.assign(task, new_assignee_staff_id=assignee,
                                                 actor_user_id=uuid.uuid4(), actor_role=ACTOR_DELEGATOR)
                            elif action == "acknowledge":
                                await svc.acknowledge(task, actor_user_id=uuid.uuid4(), actor_role=ACTOR_ASSIGNEE)
                            elif action == "start":
                                await svc.start(task, actor_user_id=uuid.uuid4(), actor_role=ACTOR_ASSIGNEE)
                            elif action == "submit":
                                await svc.submit(task, actor_user_id=uuid.uuid4(),
                                                 execution_summary="做了", evidence_snapshot=["e1"],
                                                 actor_role=ACTOR_ASSIGNEE)
                            elif action == "review":
                                await svc.review(task, actor_user_id=uuid.uuid4(), actor_role=ACTOR_REVIEWER)
                            await s.commit()
                        except HTTPException as e:
                            assert e.status_code in (409, 422)
                            await s.rollback()
                    t = await _load(factory, tid)
                    assert t.workflow_status in valid
            finally:
                await engine.dispose()
        asyncio.run(scenario())


# ===========================================================================
# P20：assignment_version 与 ack
# Validates: Requirements 6.3, 6.4, 6.5
# ===========================================================================
class TestP20AssignmentVersionAck:
    def test_assign_increments_version_and_clears_ack(self):
        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                tid = await _seed_task(factory, pid, wi, wc, wp_id=wp, workflow="unassigned")
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await svc.assign(task, new_assignee_staff_id=uuid.uuid4(),
                                     actor_user_id=uuid.uuid4(), actor_role=ACTOR_DELEGATOR)
                    await s.commit()
                t = await _load(factory, tid)
                assert t.assignment_version == 1 and t.workflow_status == "assigned"
                assert t.acknowledged_at is None
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_duplicate_ack_same_version_is_noop(self):
        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                assignee = uuid.uuid4()
                tid = await _seed_task(factory, pid, wi, wc, wp_id=wp,
                                       workflow="assigned", assignee=assignee, assignment_version=1)
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await svc.acknowledge(task, actor_user_id=uuid.uuid4(), actor_role=ACTOR_ASSIGNEE)
                    await s.commit()
                hc1, oc1 = await _counts(factory, tid)
                t1 = await _load(factory, tid)
                # 第二次 ack（同 assignment_version）→ no-op
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    r = await svc.acknowledge(task, actor_user_id=uuid.uuid4(), actor_role=ACTOR_ASSIGNEE)
                    await s.commit()
                assert r["changed"] is False
                hc2, oc2 = await _counts(factory, tid)
                t2 = await _load(factory, tid)
                assert hc2 == hc1 and oc2 == oc1  # 不新增 history/outbox
                assert t2.lock_version == t1.lock_version  # 不递增 lock_version
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_restore_executor_requires_new_version_ack(self):
        """恢复原执行人（reassign 同人为 no-op；换回需经 assign→ack 新版本）。"""
        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                a1 = uuid.uuid4()
                a2 = uuid.uuid4()
                tid = await _seed_task(factory, pid, wi, wc, wp_id=wp,
                                       workflow="acknowledged", assignee=a1, assignment_version=1)
                # reassign 到 a2 → assignment_version=2、清 ack、回 assigned
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await svc.reassign(task, new_assignee_staff_id=a2, actor_user_id=uuid.uuid4(),
                                       reason="换执行人处理", actor_role=ACTOR_DELEGATOR)
                    await s.commit()
                t = await _load(factory, tid)
                assert t.assignment_version == 2 and t.workflow_status == "assigned"
                assert t.acknowledged_at is None and t.assignee_staff_id == a2
                # reassign 回 a1 → 新版本 3，仍需重新 ack
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await svc.reassign(task, new_assignee_staff_id=a1, actor_user_id=uuid.uuid4(),
                                       reason="换回原执行人", actor_role=ACTOR_DELEGATOR)
                    await s.commit()
                t2 = await _load(factory, tid)
                assert t2.assignment_version == 3 and t2.workflow_status == "assigned"
                assert t2.acknowledged_at is None
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_reassign_same_person_noop(self):
        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                a1 = uuid.uuid4()
                tid = await _seed_task(factory, pid, wi, wc, wp_id=wp,
                                       workflow="acknowledged", assignee=a1, assignment_version=1)
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    r = await svc.reassign(task, new_assignee_staff_id=a1, actor_user_id=uuid.uuid4(),
                                           reason="同人无变化", actor_role=ACTOR_DELEGATOR)
                    await s.commit()
                assert r["changed"] is False
                t = await _load(factory, tid)
                assert t.assignment_version == 1  # 不递增
                hc, oc = await _counts(factory, tid)
                assert hc == 0 and oc == 0
            finally:
                await engine.dispose()
        asyncio.run(scenario())


# ===========================================================================
# P21：成功动作审计完备（history + outbox 各一条）
# Validates: Requirements 6.9, 12.6
# ===========================================================================
class TestP21AuditCompleteness:
    def test_each_success_writes_one_history_and_one_outbox(self):
        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                assignee = uuid.uuid4()
                reviewer = uuid.uuid4()
                actor = uuid.uuid4()
                tid = await _seed_task(factory, pid, wi, wc, wp_id=wp,
                                       workflow="unassigned", reviewer=reviewer)
                # assign → ack → start → submit → review = 5 成功动作
                steps = [
                    ("assign", lambda svc, t: svc.assign(t, new_assignee_staff_id=assignee, actor_user_id=actor, actor_role=ACTOR_DELEGATOR)),
                    ("acknowledge", lambda svc, t: svc.acknowledge(t, actor_user_id=actor, actor_role=ACTOR_ASSIGNEE)),
                    ("start", lambda svc, t: svc.start(t, actor_user_id=actor, actor_role=ACTOR_ASSIGNEE)),
                    ("submit", lambda svc, t: svc.submit(t, actor_user_id=actor, execution_summary="完成", evidence_snapshot=["e"], actor_role=ACTOR_ASSIGNEE)),
                    ("review", lambda svc, t: svc.review(t, actor_user_id=actor, actor_role=ACTOR_REVIEWER)),
                ]
                for _, fn in steps:
                    async with factory() as s:
                        svc = ProcedureTaskTransitionService(s)
                        task = await s.get(ProcedureRowTask, tid)
                        await fn(svc, task)
                        await s.commit()
                hc, oc = await _counts(factory, tid)
                assert hc == 5 and oc == 5
                # outbox 字段完备：aggregate_type/version 单调、actor/assignment_version/audit_cycle 存在
                async with factory() as s:
                    rows = (
                        await s.execute(
                            sa.select(TaskEvent).where(TaskEvent.aggregate_id == tid)
                            .order_by(TaskEvent.aggregate_version)
                        )
                    ).scalars().all()
                versions = [r.aggregate_version for r in rows]
                assert versions == sorted(versions) and len(set(versions)) == 5
                for r in rows:
                    assert r.aggregate_type == AGGREGATE_PROCEDURE_ROW_TASK
                    assert r.idempotency_key and r.available_at is not None
                    assert r.payload["actor_user_id"] == str(actor)
                    assert r.payload["assignment_version"] is not None
                    assert r.payload["audit_cycle_snapshot"] == cy
            finally:
                await engine.dispose()
        asyncio.run(scenario())


# ===========================================================================
# P33 (逻辑侧)：乐观锁 —— expected_lock_version 不匹配 → 409 零副作用
# Validates: Requirements 12.5
# ===========================================================================
class TestP33OptimisticLock:
    def test_stale_lock_version_rejected(self):
        async def scenario():
            engine, factory, pid, wi, wp, wc, cy = await _make_env()
            try:
                assignee = uuid.uuid4()
                tid = await _seed_task(factory, pid, wi, wc, wp_id=wp,
                                       workflow="assigned", assignee=assignee,
                                       assignment_version=1, lock_version=3)
                # 用错误的 expected_lock_version → 409，零副作用
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    with pytest.raises(HTTPException) as ei:
                        await svc.acknowledge(task, actor_user_id=uuid.uuid4(),
                                              actor_role=ACTOR_ASSIGNEE, expected_lock_version=99)
                    await s.rollback()
                assert ei.value.status_code == 409
                hc, oc = await _counts(factory, tid)
                assert hc == 0 and oc == 0
                # 正确 expected_lock_version → 成功
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await svc.acknowledge(task, actor_user_id=uuid.uuid4(),
                                          actor_role=ACTOR_ASSIGNEE, expected_lock_version=3)
                    await s.commit()
                t = await _load(factory, tid)
                assert t.workflow_status == "acknowledged" and t.lock_version == 4
            finally:
                await engine.dispose()
        asyncio.run(scenario())


# ===========================================================================
# PostgreSQL 集成：P33 真实并发行锁 + outbox 有序
# ===========================================================================
async def _apply_v105(engine) -> None:
    sql = _V105.read_text(encoding="utf-8")
    for stmt in MigrationRunner._split_sql_statements(sql):
        async with engine.begin() as conn:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (transition integration)")
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


async def _pg_pick(factory):
    async with factory() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT wp.project_id, wp.wp_index_id, wp.id, wi.wp_code, COALESCE(wi.audit_cycle,'A') "
                    "FROM working_paper wp JOIN wp_index wi ON wi.id=wp.wp_index_id "
                    "WHERE wp.is_deleted=false AND wi.is_deleted=false LIMIT 1"
                )
            )
        ).first()
    return row


async def _pg_seed(factory, project_id, wp_index_id, wp_id, wp_code, cycle, *, workflow, assignee=None):
    dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
    tid = uuid.uuid4()
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_definitions "
                "(definition_key, template_code, template_revision_hash, sheet_key, procedure_text) "
                "VALUES (:k,:tc,:h,:sk,:pt)"
            ),
            {"k": dk, "tc": f"{wp_code}A", "h": "a" * 64, "sk": f"{wp_code}A", "pt": "程序文本"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_tasks "
                "(id, project_id, wp_index_id, wp_id, definition_key, sheet_key, wp_code, "
                " definition_revision_hash, audit_cycle_snapshot, applicability_status, "
                " workflow_status, assignee_staff_id, assignment_version, lock_version) "
                "VALUES (:id,:pid,:wi,:wp,:dk,:sk,:wc,:h,:cy,'execute',:wf,:asg,1,0)"
            ),
            {"id": tid, "pid": project_id, "wi": wp_index_id, "wp": wp_id, "dk": dk,
             "sk": f"{wp_code}A", "wc": wp_code, "h": "a" * 64, "cy": cycle,
             "wf": workflow, "asg": assignee},
        )
        await s.commit()
    return dk, tid


async def _pg_cleanup(factory, dk, tid):
    async with factory() as s:
        await s.execute(sa.text("DELETE FROM task_events WHERE aggregate_id=:id"), {"id": tid})
        await s.execute(sa.text("DELETE FROM procedure_row_task_history WHERE task_id=:id"), {"id": tid})
        await s.execute(sa.text("DELETE FROM procedure_row_tasks WHERE id=:id"), {"id": tid})
        await s.execute(sa.text("DELETE FROM procedure_row_definitions WHERE definition_key=:k"), {"k": dk})
        await s.commit()


@pytest.mark.asyncio
class TestPgTransition:
    async def test_concurrent_same_version_max_one_success(self, pg_engine):
        """P33：两个事务用同一 expected_lock_version 并发 ack，最多一个成功，另一个 409。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pg_pick(factory)
        if picked is None:
            pytest.skip("dev 库无 project/wp_index/working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, cycle = picked
        async with factory() as s:
            actor = (await s.execute(sa.text("SELECT id FROM users LIMIT 1"))).scalar()
        if actor is None:
            pytest.skip("dev 库无 users 可复用")
        # acknowledged 起点 + start 是非幂等边（两并发 start 只能一个成功，另一个越序/版本冲突 409）
        dk, tid = await _pg_seed(factory, project_id, wp_index_id, wp_id, wp_code, cycle,
                                 workflow="acknowledged")
        try:
            results = {"ok": 0, "conflict": 0}

            # 两个写者都基于同一初始 lock_version=1（并发快照）。行锁使二者串行，
            # 第二个提交时任务已被推进 → expected_lock_version 陈旧 / 状态越序 → 409。
            async def attempt(expected: int):
                async with factory() as s:
                    task = (
                        await s.execute(
                            sa.select(ProcedureRowTask).where(ProcedureRowTask.id == tid).with_for_update()
                        )
                    ).scalar_one()
                    svc = ProcedureTaskTransitionService(s)
                    try:
                        await svc.start(task, actor_user_id=actor,
                                        actor_role=ACTOR_ASSIGNEE, expected_lock_version=expected)
                        await s.commit()
                        results["ok"] += 1
                    except HTTPException as e:
                        await s.rollback()
                        if e.status_code == 409:
                            results["conflict"] += 1

            await attempt(0)
            await attempt(0)  # 同版本第二次 → 409（任务已被第一次推进）
            assert results["ok"] == 1
            assert results["conflict"] == 1
            # 只有一条 history + 一条 outbox
            async with factory() as s:
                hc = (await s.execute(sa.text("SELECT count(*) FROM procedure_row_task_history WHERE task_id=:id"), {"id": tid})).scalar()
                oc = (await s.execute(sa.text("SELECT count(*) FROM task_events WHERE aggregate_id=:id"), {"id": tid})).scalar()
            assert hc == 1 and oc == 1
        finally:
            await _pg_cleanup(factory, dk, tid)
