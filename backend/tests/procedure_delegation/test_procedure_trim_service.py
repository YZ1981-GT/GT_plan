# Feature: procedure-delegation-notification — Task 6 重建粗裁/细裁与方案应用
"""ProcedureTrimService / ProcedureTaskTransitionService 测试：Properties P9-P10 + PG 集成。

Task 6 / 需求 3.3-3.8, 4.2-4.6 / Design C4、D4：

- **P9（裁剪与 workflow 正交）**：Requirements 3.3, 3.4, 3.5, 6.2, 6.3 —— SQLite Hypothesis，
  细裁 not_applicable → workflow=cancelled（绝不伪造 submitted/reviewed）；恢复 → reopen（cancelled→
  unassigned）+ applicability=execute，清 assignee/ack，须重新 assign→ack。
- **P10（方案 applied 真实）**：Requirements 3.6, 3.7 —— SQLite + PG，applied == 真实发生字段变化的
  task/scope 数；无变化 applied=0；unchanged/conflict 不计入 applied。
- **PG 集成**：preview 后目标版本变化 → apply 409；无变化 → applied=0；legacy UUID 无法唯一转换 →
  409 migration_conflict；一次消费 + request_id 幂等。

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
from app.services.procedure_trim_service import (
    ProcedureTrimService,
    TrimSchemeError,
    build_row_key,
    build_scope_key,
)
from app.services.procedure_task_transition_service import (
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

# 非终态 workflow（可被 cancel 的起点）。
_NON_TERMINAL = [
    "unassigned",
    "assigned",
    "acknowledged",
    "in_progress",
    "submitted",
    "changes_requested",
]


# ===========================================================================
# SQLite 环境 + 种子
# ===========================================================================


async def _make_sqlite_env():
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
                id=wp_index_id,
                project_id=project_id,
                wp_code=wp_code,
                wp_name="应收账款",
                audit_cycle=cycle,
                status=WpStatus.not_started,
            )
        )
        s.add(
            WorkingPaper(
                id=wp_id,
                project_id=project_id,
                wp_index_id=wp_index_id,
                file_path="/tmp/D2.xlsx",
                source_type=WpSourceType.template,
                file_version=1,
                parsed_data={},
            )
        )
        await s.commit()
    return engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle


async def _seed_definition(factory, template_code, sheet_key, definition_key, *, revision="a" * 64, text="程序文本", aliases=None):
    async with factory() as s:
        s.add(
            ProcedureRowDefinition(
                definition_key=definition_key,
                template_code=template_code,
                template_revision_hash=revision,
                sheet_key=sheet_key,
                source_locator={},
                program_no="1",
                procedure_text=text,
                ref_snapshot=[],
                legacy_aliases=aliases or [],
                normalized_content={},
            )
        )
        await s.commit()


async def _seed_task(
    factory, project_id, wp_index_id, wp_code, sheet_key, definition_key, *,
    revision="a" * 64, workflow="assigned", applicability="execute", cycle="D",
    assignee=None, lock_version=1, assignment_version=1,
):
    task_id = uuid.uuid4()
    async with factory() as s:
        s.add(
            ProcedureRowTask(
                id=task_id,
                project_id=project_id,
                wp_index_id=wp_index_id,
                definition_key=definition_key,
                sheet_key=sheet_key,
                wp_code=wp_code,
                definition_revision_hash=revision,
                audit_cycle_snapshot=cycle,
                applicability_status=applicability,
                workflow_status=workflow,
                assignee_staff_id=assignee,
                acknowledged_at=None,
                lock_version=lock_version,
                assignment_version=assignment_version,
            )
        )
        await s.commit()
    return task_id


async def _task_state(factory, task_id):
    async with factory() as s:
        return (
            await s.execute(
                sa.select(
                    ProcedureRowTask.applicability_status,
                    ProcedureRowTask.workflow_status,
                    ProcedureRowTask.assignee_staff_id,
                    ProcedureRowTask.acknowledged_at,
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
# P9：裁剪与 workflow 正交（SQLite Hypothesis）
# Validates: Requirements 3.3, 3.4, 3.5, 6.2, 6.3
# ===========================================================================
class TestP9TrimWorkflowOrthogonal:
    @given(workflow=st.sampled_from(_NON_TERMINAL))
    @settings(max_examples=5, deadline=None)
    def test_not_applicable_cancels_and_restore_reopens(self, workflow):
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle = await _make_sqlite_env()
            try:
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                assignee = uuid.uuid4()
                task_id = await _seed_task(
                    factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk,
                    workflow=workflow, applicability="execute", cycle=cycle, assignee=assignee,
                )
                # 细裁 → not_applicable：applicability=not_applicable + workflow=cancelled
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    r = await svc.set_row_not_applicable(
                        project_id, task_id, actor_user_id=None, reason="无相关业务"
                    )
                    await s.commit()
                assert r["changed"] is True
                st_after = await _task_state(factory, task_id)
                assert st_after[0] == "not_applicable"  # applicability
                # P9 核心：绝不伪造 submitted/reviewed
                assert st_after[1] == "cancelled"
                assert st_after[1] not in ("submitted", "reviewed")

                # 恢复 → execute：reopen（cancelled→unassigned），清 assignee/ack，须重新 assign→ack
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    r2 = await svc.restore_row_execute(
                        project_id, task_id, actor_user_id=None
                    )
                    await s.commit()
                assert r2["changed"] is True
                assert r2["requires_reassign"] is True
                st_restore = await _task_state(factory, task_id)
                assert st_restore[0] == "execute"       # applicability 恢复
                assert st_restore[1] == "unassigned"    # 不自动完成，回到 unassigned
                assert st_restore[2] is None             # assignee 清空
                assert st_restore[3] is None             # ack 清空
                # 两次成功动作各写一条 history
                assert await _history_count(factory, task_id) == 2
            finally:
                await engine.dispose()

        asyncio.run(scenario())

    def test_reopen_requires_cancelled_state(self):
        """非 cancelled 任务 reopen → 409（状态机封闭性）。"""
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle = await _make_sqlite_env()
            try:
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                task_id = await _seed_task(
                    factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk,
                    workflow="assigned",
                )
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    with pytest.raises(HTTPException) as ei:
                        await svc.restore_row_execute(project_id, task_id, actor_user_id=None)
                    await s.rollback()
                assert ei.value.status_code == 409
            finally:
                await engine.dispose()

        asyncio.run(scenario())

    def test_cancel_reviewed_rejected(self):
        """已复核任务 cancel → 409（reviewed 终态）。"""
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle = await _make_sqlite_env()
            try:
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                task_id = await _seed_task(
                    factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk,
                    workflow="reviewed",
                )
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    with pytest.raises(HTTPException) as ei:
                        await svc.set_row_not_applicable(
                            project_id, task_id, actor_user_id=None, reason="x"
                        )
                    await s.rollback()
                assert ei.value.status_code == 409
            finally:
                await engine.dispose()

        asyncio.run(scenario())

    def test_cancel_requires_reason(self):
        """cancel 原因必填 → 422。"""
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle = await _make_sqlite_env()
            try:
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                task_id = await _seed_task(
                    factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk,
                )
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    with pytest.raises(HTTPException) as ei:
                        await svc.set_row_not_applicable(
                            project_id, task_id, actor_user_id=None, reason="  "
                        )
                    await s.rollback()
                assert ei.value.status_code == 422
            finally:
                await engine.dispose()

        asyncio.run(scenario())


# ===========================================================================
# P10：方案 applied 真实（SQLite）
# Validates: Requirements 3.6, 3.7
# ===========================================================================
class TestP10SchemeAppliedReal:
    def test_canonical_keys(self):
        assert build_scope_key("D", "D2") == "scope:D:D2"
        assert build_row_key("D2A", "D2A", "D2A::D2A::abcd") == "row:D2A:D2A:D2A::D2A::abcd"

    def test_row_scheme_applies_real_changes(self):
        """行方案 not_applicable：applied == 真实 cancel 的 task 数（2）。"""
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle = await _make_sqlite_env()
            try:
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                t1 = await _seed_task(factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk, workflow="assigned")
                t2 = await _seed_task(factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk, workflow="in_progress")
                entries = [
                    {"kind": "row", "template_code": f"{wp_code}A", "sheet_key": f"{wp_code}A",
                     "definition_key": dk, "target_applicability": "not_applicable"}
                ]
                user_id = uuid.uuid4()
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    pv = await svc.preview_scheme(project_id, actor_user_id=user_id, entries=entries)
                    await s.commit()
                assert pv["summary"]["would_change"] == 2
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    res = await svc.apply_scheme(
                        project_id, actor_user_id=user_id,
                        preview_id=uuid.UUID(pv["preview_id"]), request_id="req-1", entries=entries,
                    )
                    await s.commit()
                assert res["applied"] == 2
                assert res["unchanged"] == 0
                for tid in (t1, t2):
                    stt = await _task_state(factory, tid)
                    assert stt[0] == "not_applicable" and stt[1] == "cancelled"
            finally:
                await engine.dispose()

        asyncio.run(scenario())

    def test_no_change_applied_zero(self):
        """目标已达成（already not_applicable）→ applied=0，unchanged 计数。"""
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle = await _make_sqlite_env()
            try:
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                await _seed_task(
                    factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk,
                    workflow="cancelled", applicability="not_applicable",
                )
                entries = [
                    {"kind": "row", "template_code": f"{wp_code}A", "sheet_key": f"{wp_code}A",
                     "definition_key": dk, "target_applicability": "not_applicable"}
                ]
                user_id = uuid.uuid4()
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    pv = await svc.preview_scheme(project_id, actor_user_id=user_id, entries=entries)
                    await s.commit()
                assert pv["summary"]["would_change"] == 0
                assert pv["summary"]["unchanged"] == 1
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    res = await svc.apply_scheme(
                        project_id, actor_user_id=user_id,
                        preview_id=uuid.UUID(pv["preview_id"]), request_id="req-nc", entries=entries,
                    )
                    await s.commit()
                assert res["applied"] == 0
                assert res["unchanged"] == 1
            finally:
                await engine.dispose()

        asyncio.run(scenario())

    def test_scope_scheme_sets_status_and_cascades(self):
        """粗裁范围 not_applicable：instance 状态变 + 级联取消未终态 tasks（applied 真实）。"""
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle = await _make_sqlite_env()
            try:
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                # 一个 scope instance + 2 tasks
                inst_id = uuid.uuid4()
                async with factory() as s:
                    s.add(
                        ProcedureInstance(
                            id=inst_id, project_id=project_id, audit_cycle=cycle,
                            procedure_code=wp_code, procedure_name="应收账款", status="execute",
                            wp_code=wp_code,
                        )
                    )
                    await s.commit()
                await _seed_task(factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk, workflow="assigned", cycle=cycle)
                dk2 = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk2)
                await _seed_task(factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk2, workflow="reviewed", cycle=cycle)
                entries = [
                    {"kind": "scope", "cycle": cycle, "wp_index_code": wp_code, "target_status": "not_applicable"}
                ]
                user_id = uuid.uuid4()
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    pv = await svc.preview_scheme(project_id, actor_user_id=user_id, entries=entries)
                    await s.commit()
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    res = await svc.apply_scheme(
                        project_id, actor_user_id=user_id,
                        preview_id=uuid.UUID(pv["preview_id"]), request_id="req-scope", entries=entries,
                    )
                    await s.commit()
                # 1 instance status + 1 未终态 task cancel（reviewed task 不动）
                assert res["applied"] == 2
                async with factory() as s:
                    inst_status = (
                        await s.execute(
                            sa.select(ProcedureInstance.status).where(ProcedureInstance.id == inst_id)
                        )
                    ).scalar()
                assert inst_status == "not_applicable"
            finally:
                await engine.dispose()

        asyncio.run(scenario())

    def test_legacy_uuid_key_migration_conflict_409(self):
        """legacy UUID key 无法唯一转换 → apply 409 migration_conflict（不猜测）。"""
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle = await _make_sqlite_env()
            try:
                # legacy 定义无别名匹配 → 无法唯一转换
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                entries = [
                    {"kind": "row", "template_code": f"{wp_code}A", "sheet_key": f"{wp_code}A",
                     "definition_key": "row-7", "target_applicability": "not_applicable"}
                ]
                user_id = uuid.uuid4()
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    pv = await svc.preview_scheme(project_id, actor_user_id=user_id, entries=entries)
                    await s.commit()
                assert pv["summary"]["migration_conflict"] == 1
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    with pytest.raises(TrimSchemeError) as ei:
                        await svc.apply_scheme(
                            project_id, actor_user_id=user_id,
                            preview_id=uuid.UUID(pv["preview_id"]), request_id="req-legacy", entries=entries,
                        )
                    await s.rollback()
                assert ei.value.status_code == 409
            finally:
                await engine.dispose()

        asyncio.run(scenario())

    def test_version_change_after_preview_409(self):
        """preview 后目标 task lock_version 变化 → apply 409（版本冲突）。"""
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle = await _make_sqlite_env()
            try:
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                task_id = await _seed_task(factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk, workflow="assigned")
                entries = [
                    {"kind": "row", "template_code": f"{wp_code}A", "sheet_key": f"{wp_code}A",
                     "definition_key": dk, "target_applicability": "not_applicable"}
                ]
                user_id = uuid.uuid4()
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    pv = await svc.preview_scheme(project_id, actor_user_id=user_id, entries=entries)
                    await s.commit()
                # 外部 bump lock_version
                async with factory() as s:
                    await s.execute(
                        sa.update(ProcedureRowTask)
                        .where(ProcedureRowTask.id == task_id)
                        .values(lock_version=ProcedureRowTask.lock_version + 1)
                    )
                    await s.commit()
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    with pytest.raises(HTTPException) as ei:
                        await svc.apply_scheme(
                            project_id, actor_user_id=user_id,
                            preview_id=uuid.UUID(pv["preview_id"]), request_id="req-ver", entries=entries,
                        )
                    await s.rollback()
                assert ei.value.status_code == 409
            finally:
                await engine.dispose()

        asyncio.run(scenario())

    def test_one_time_consume_idempotent(self):
        """一次消费：相同 request_id 幂等返回旧 result；不同 request_id → 409 已消费。"""
        async def scenario():
            engine, factory, project_id, wp_index_id, wp_id, wp_code, cycle = await _make_sqlite_env()
            try:
                dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
                await _seed_definition(factory, f"{wp_code}A", f"{wp_code}A", dk)
                await _seed_task(factory, project_id, wp_index_id, wp_code, f"{wp_code}A", dk, workflow="assigned")
                entries = [
                    {"kind": "row", "template_code": f"{wp_code}A", "sheet_key": f"{wp_code}A",
                     "definition_key": dk, "target_applicability": "not_applicable"}
                ]
                user_id = uuid.uuid4()
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    pv = await svc.preview_scheme(project_id, actor_user_id=user_id, entries=entries)
                    await s.commit()
                pvid = uuid.UUID(pv["preview_id"])
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    r1 = await svc.apply_scheme(
                        project_id, actor_user_id=user_id, preview_id=pvid, request_id="c-1", entries=entries
                    )
                    await s.commit()
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    r_replay = await svc.apply_scheme(
                        project_id, actor_user_id=user_id, preview_id=pvid, request_id="c-1", entries=entries
                    )
                    await s.commit()
                assert r_replay == r1
                async with factory() as s:
                    svc = ProcedureTrimService(s)
                    with pytest.raises(HTTPException) as ei:
                        await svc.apply_scheme(
                            project_id, actor_user_id=user_id, preview_id=pvid, request_id="c-2", entries=entries
                        )
                    await s.rollback()
                assert ei.value.status_code == 409
            finally:
                await engine.dispose()

        asyncio.run(scenario())


# ===========================================================================
# PostgreSQL 集成：真实约束/事务下的方案 apply（版本/无变化/legacy 409）
# ===========================================================================
async def _apply_v105(engine) -> None:
    sql = _V105.read_text(encoding="utf-8")
    for stmt in MigrationRunner._split_sql_statements(sql):
        async with engine.begin() as conn:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (trim scheme apply integration)")
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


async def _pick_project_wp_index(factory):
    async with factory() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT wp.project_id, wp.wp_index_id, wi.wp_code, COALESCE(wi.audit_cycle, 'A') "
                    "FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id "
                    "WHERE wp.is_deleted = false AND wi.is_deleted = false LIMIT 1"
                )
            )
        ).first()
    return row


async def _pick_user(factory):
    async with factory() as s:
        row = (await s.execute(sa.text("SELECT id FROM users LIMIT 1"))).first()
    return row[0] if row else None


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


async def _pg_insert_task(factory, project_id, wp_index_id, wp_code, sheet_key, definition_key, revision, cycle):
    task_id = uuid.uuid4()
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_tasks "
                "(id, project_id, wp_index_id, definition_key, sheet_key, wp_code, "
                " definition_revision_hash, audit_cycle_snapshot, applicability_status, "
                " workflow_status, assignment_version, lock_version) "
                "VALUES (:id, :pid, :wi, :dk, :sk, :wc, :h, :cy, 'execute', 'assigned', 1, 1)"
            ),
            {"id": task_id, "pid": project_id, "wi": wp_index_id, "dk": definition_key,
             "sk": sheet_key, "wc": wp_code, "h": revision, "cy": cycle},
        )
        await s.commit()
    return task_id


async def _pg_cleanup(factory, definition_keys, task_ids):
    async with factory() as s:
        for tid in task_ids:
            await s.execute(sa.text("DELETE FROM procedure_row_task_history WHERE task_id=:id"), {"id": tid})
        for tid in task_ids:
            await s.execute(sa.text("DELETE FROM procedure_row_tasks WHERE id=:id"), {"id": tid})
        for k in definition_keys:
            await s.execute(sa.text("DELETE FROM procedure_row_definitions WHERE definition_key=:k"), {"k": k})
        await s.commit()


@pytest.mark.asyncio
class TestPgTrimScheme:
    async def test_row_scheme_apply_and_version_conflict(self, pg_engine):
        """PG：真实 apply 迁 not_applicable；preview 后版本变化 → 二次 409。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp_index(factory)
        user_id = await _pick_user(factory)
        if picked is None or user_id is None:
            pytest.skip("dev 库无可复用 project/wp_index/user")
        project_id, wp_index_id, wp_code, cycle = picked
        tmpl = f"{wp_code}A"
        dk = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        rev = "a" * 64
        await _pg_insert_definition(factory, tmpl, tmpl, dk, rev)
        task_id = await _pg_insert_task(factory, project_id, wp_index_id, wp_code, tmpl, dk, rev, cycle)
        entries = [
            {"kind": "row", "template_code": tmpl, "sheet_key": tmpl,
             "definition_key": dk, "target_applicability": "not_applicable"}
        ]
        try:
            async with factory() as s:
                svc = ProcedureTrimService(s)
                pv = await svc.preview_scheme(project_id, actor_user_id=user_id, entries=entries)
                await s.commit()
            assert pv["summary"]["would_change"] == 1
            async with factory() as s:
                svc = ProcedureTrimService(s)
                res = await svc.apply_scheme(
                    project_id, actor_user_id=user_id,
                    preview_id=uuid.UUID(pv["preview_id"]), request_id="pg-1", entries=entries,
                )
                await s.commit()
            assert res["applied"] == 1
            async with factory() as s:
                row = (
                    await s.execute(
                        sa.text("SELECT applicability_status, workflow_status FROM procedure_row_tasks WHERE id=:id"),
                        {"id": task_id},
                    )
                ).first()
            assert row[0] == "not_applicable" and row[1] == "cancelled"

            # 新 preview → 外部 bump 版本 → apply 409
            async with factory() as s:
                svc = ProcedureTrimService(s)
                pv2 = await svc.preview_scheme(project_id, actor_user_id=user_id, entries=[
                    {"kind": "row", "template_code": tmpl, "sheet_key": tmpl,
                     "definition_key": dk, "target_applicability": "execute"}
                ])
                await s.commit()
            async with factory() as s:
                await s.execute(
                    sa.text("UPDATE procedure_row_tasks SET lock_version=lock_version+1 WHERE id=:id"),
                    {"id": task_id},
                )
                await s.commit()
            async with factory() as s:
                svc = ProcedureTrimService(s)
                with pytest.raises(HTTPException) as ei:
                    await svc.apply_scheme(
                        project_id, actor_user_id=user_id,
                        preview_id=uuid.UUID(pv2["preview_id"]), request_id="pg-ver", entries=[
                            {"kind": "row", "template_code": tmpl, "sheet_key": tmpl,
                             "definition_key": dk, "target_applicability": "execute"}
                        ],
                    )
                await s.rollback()
            assert ei.value.status_code == 409
        finally:
            await _pg_cleanup(factory, [dk], [task_id])

    async def test_legacy_uuid_conflict_409(self, pg_engine):
        """PG：legacy UUID key 无法唯一转换 → apply 409 migration_conflict。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp_index(factory)
        user_id = await _pick_user(factory)
        if picked is None or user_id is None:
            pytest.skip("dev 库无可复用 project/wp_index/user")
        project_id, wp_index_id, wp_code, cycle = picked
        tmpl = f"{wp_code}A"
        dk = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        rev = "a" * 64
        await _pg_insert_definition(factory, tmpl, tmpl, dk, rev)
        entries = [
            {"kind": "row", "template_code": tmpl, "sheet_key": tmpl,
             "definition_key": "legacy-" + uuid.uuid4().hex[:8], "target_applicability": "not_applicable"}
        ]
        try:
            async with factory() as s:
                svc = ProcedureTrimService(s)
                pv = await svc.preview_scheme(project_id, actor_user_id=user_id, entries=entries)
                await s.commit()
            assert pv["summary"]["migration_conflict"] == 1
            async with factory() as s:
                svc = ProcedureTrimService(s)
                with pytest.raises(HTTPException) as ei:
                    await svc.apply_scheme(
                        project_id, actor_user_id=user_id,
                        preview_id=uuid.UUID(pv["preview_id"]), request_id="pg-legacy", entries=entries,
                    )
                await s.rollback()
            assert ei.value.status_code == 409
        finally:
            await _pg_cleanup(factory, [dk], [])
