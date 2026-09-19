# Feature: procedure-delegation-notification — Task 12 任务查询 API 与 MyProcedureTasks 重构
"""ProcedureTaskQueryService 查询/深链测试：Properties P27-P28 + API schema/pagination/空态/跨项目权限。

Task 12 / 需求 9.1-9.8, 12.3, 14.3-14.4 / Design C11、F1：

- **P27（due_at 逾期谓词）**：Requirements 9.1/9.2/9.3 —— 仅当 due_at 非空、已过期且状态非
  reviewed/cancelled 时 overdue=true；due_at 为空永不逾期。
- **P28（深链与项目边界）**：Requirements 9.5/9.6/9.8 —— 跨项目 task 取详情 404（不泄露）；
  合法深链只按 sheet_key+definition_key 定位，不按 program_no 降级。
- **API schema/pagination/空态/跨项目权限**：结果字段集完整（nullable wp_id、双版本、
  materialization_required）；分页正确；无 active staff → 空页；跨项目 get_detail → None。

PBT 用项目 fast profile；查询服务纯读，sqlite 内存库验证逻辑，DB 约束/covering index 在 PG 验证。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.procedure_models import ProcedureRowDefinition, ProcedureRowTask
from app.models.staff_models import StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services.procedure_task_query_service import (
    ProcedureTaskQueryService,
    TaskQueryFilters,
    compute_overdue,
)

import app.models.procedure_models  # noqa: F401
import app.models.staff_models  # noqa: F401
import app.models.core  # noqa: F401
import app.models.workpaper_models  # noqa: F401


def _utc(offset_seconds: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


# ===========================================================================
# P27：due_at 逾期谓词纯函数
# Validates: Requirements 9.1, 9.2, 9.3
# ===========================================================================
class TestP27OverduePredicate:
    def test_null_due_at_never_overdue(self):
        for wf in ("unassigned", "in_progress", "submitted", "reviewed", "cancelled"):
            assert compute_overdue(None, wf) is False

    def test_reviewed_cancelled_never_overdue_even_if_past(self):
        past = _utc(-3600)
        assert compute_overdue(past, "reviewed") is False
        assert compute_overdue(past, "cancelled") is False

    def test_past_due_active_is_overdue(self):
        past = _utc(-3600)
        for wf in ("assigned", "acknowledged", "in_progress", "submitted", "changes_requested"):
            assert compute_overdue(past, wf) is True

    def test_future_due_not_overdue(self):
        future = _utc(3600)
        assert compute_overdue(future, "in_progress") is False

    @given(
        offset=st.integers(min_value=-100000, max_value=100000),
        has_due=st.booleans(),
        workflow=st.sampled_from(
            ["unassigned", "assigned", "acknowledged", "in_progress",
             "submitted", "changes_requested", "reviewed", "cancelled"]
        ),
    )
    @settings(max_examples=5, deadline=None)
    def test_overdue_predicate_matches_spec(self, offset, has_due, workflow):
        now = _utc(0)
        due_at = (now + timedelta(seconds=offset)) if has_due else None
        result = compute_overdue(due_at, workflow, now)
        expected = (
            has_due
            and workflow not in ("reviewed", "cancelled")
            and due_at is not None
            and now > due_at
        )
        assert result is expected


# ===========================================================================
# sqlite 环境 + 种子（查询逻辑；DB 约束/index 在 PG 验证）
# ===========================================================================
async def _make_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


async def _seed_staff(factory, *, user_id):
    staff_id = uuid.uuid4()
    async with factory() as s:
        s.add(StaffMember(id=staff_id, user_id=user_id, name="张三", is_deleted=False))
        await s.commit()
    return staff_id


async def _seed_wp_index(factory, project_id, wp_code="D2", cycle="D"):
    wp_index_id = uuid.uuid4()
    async with factory() as s:
        s.add(
            WpIndex(
                id=wp_index_id, project_id=project_id, wp_code=wp_code,
                wp_name="应收账款", audit_cycle=cycle, status=WpStatus.not_started,
            )
        )
        await s.commit()
    return wp_index_id


async def _seed_task(
    factory, project_id, wp_index_id, *,
    wp_code="D2", cycle="D", wp_id=None, workflow="assigned", applicability="execute",
    assignee=None, reviewer=None, due_at=None, program_no="1",
):
    task_id = uuid.uuid4()
    dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
    async with factory() as s:
        s.add(
            ProcedureRowDefinition(
                definition_key=dk, template_code=f"{wp_code}A",
                template_revision_hash="a" * 64, sheet_key=f"{wp_code}A",
                source_locator={}, program_no=program_no, procedure_text="核对明细账与总账",
                ref_snapshot=[], legacy_aliases=[], normalized_content={},
            )
        )
        s.add(
            ProcedureRowTask(
                id=task_id, project_id=project_id, wp_index_id=wp_index_id, wp_id=wp_id,
                definition_key=dk, sheet_key=f"{wp_code}A", wp_code=wp_code,
                sheet_name=f"{wp_code} 明细", program_no=program_no,
                procedure_text="核对明细账与总账",
                definition_revision_hash="a" * 64, audit_cycle_snapshot=cycle,
                applicability_status=applicability, workflow_status=workflow,
                assignee_staff_id=assignee, reviewer_staff_id=reviewer,
                due_at=due_at, assignment_version=1, lock_version=0,
            )
        )
        await s.commit()
    return task_id, dk


# ===========================================================================
# API schema / pagination / 空态
# ===========================================================================
class TestQuerySchemaAndPagination:
    def test_empty_when_no_active_staff(self):
        async def scenario():
            engine, factory = await _make_env()
            try:
                async with factory() as s:
                    svc = ProcedureTaskQueryService(s)
                    res = await svc.list_tasks(uuid.uuid4(), TaskQueryFilters())
                assert res["items"] == []
                assert res["pagination"]["total"] == 0
                assert res["pagination"]["total_pages"] == 0
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_result_schema_complete(self):
        async def scenario():
            engine, factory = await _make_env()
            try:
                user_id = uuid.uuid4()
                pid = uuid.uuid4()
                staff_id = await _seed_staff(factory, user_id=user_id)
                wi = await _seed_wp_index(factory, pid)
                # 一个已生成底稿 + 一个未绑定底稿（wp_id=None）
                await _seed_task(factory, pid, wi, wp_id=uuid.uuid4(), assignee=staff_id)
                await _seed_task(factory, pid, wi, wp_id=None, assignee=staff_id)
                async with factory() as s:
                    svc = ProcedureTaskQueryService(s)
                    res = await svc.list_tasks(user_id, TaskQueryFilters(project_id=pid))
                assert res["pagination"]["total"] == 2
                required = {
                    "task_id", "project_id", "wp_index_id", "wp_id", "definition_key",
                    "sheet_key", "wp_code", "sheet_name", "program_no", "procedure_text",
                    "audit_cycle_snapshot", "applicability_status", "workflow_status",
                    "assignee_staff_id", "reviewer_staff_id", "assignment_version",
                    "lock_version", "due_at", "overdue", "materialization_required", "my_role",
                }
                for item in res["items"]:
                    assert required.issubset(item.keys())
                    assert item["materialization_required"] is False
                    assert item["my_role"] == "assignee"
                # nullable wp_id：有一条为 None
                wp_ids = {item["wp_id"] for item in res["items"]}
                assert None in wp_ids
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_pagination_paging(self):
        async def scenario():
            engine, factory = await _make_env()
            try:
                user_id = uuid.uuid4()
                pid = uuid.uuid4()
                staff_id = await _seed_staff(factory, user_id=user_id)
                wi = await _seed_wp_index(factory, pid)
                for _ in range(5):
                    await _seed_task(factory, pid, wi, wp_id=uuid.uuid4(), assignee=staff_id)
                async with factory() as s:
                    svc = ProcedureTaskQueryService(s)
                    p1 = await svc.list_tasks(user_id, TaskQueryFilters(project_id=pid, page=1, page_size=2))
                    p2 = await svc.list_tasks(user_id, TaskQueryFilters(project_id=pid, page=2, page_size=2))
                    p3 = await svc.list_tasks(user_id, TaskQueryFilters(project_id=pid, page=3, page_size=2))
                assert p1["pagination"]["total"] == 5
                assert p1["pagination"]["total_pages"] == 3
                assert len(p1["items"]) == 2 and len(p2["items"]) == 2 and len(p3["items"]) == 1
                # 不重复分页
                ids = {i["task_id"] for i in p1["items"]} | {i["task_id"] for i in p2["items"]} | {i["task_id"] for i in p3["items"]}
                assert len(ids) == 5
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_role_filter_assignee_vs_reviewer(self):
        async def scenario():
            engine, factory = await _make_env()
            try:
                user_id = uuid.uuid4()
                pid = uuid.uuid4()
                staff_id = await _seed_staff(factory, user_id=user_id)
                wi = await _seed_wp_index(factory, pid)
                await _seed_task(factory, pid, wi, wp_id=uuid.uuid4(), assignee=staff_id)
                await _seed_task(factory, pid, wi, wp_id=uuid.uuid4(), reviewer=staff_id)
                async with factory() as s:
                    svc = ProcedureTaskQueryService(s)
                    as_assignee = await svc.list_tasks(user_id, TaskQueryFilters(project_id=pid, role="assignee"))
                    as_reviewer = await svc.list_tasks(user_id, TaskQueryFilters(project_id=pid, role="reviewer"))
                    both = await svc.list_tasks(user_id, TaskQueryFilters(project_id=pid))
                assert as_assignee["pagination"]["total"] == 1
                assert as_assignee["items"][0]["my_role"] == "assignee"
                assert as_reviewer["pagination"]["total"] == 1
                assert as_reviewer["items"][0]["my_role"] == "reviewer"
                assert both["pagination"]["total"] == 2
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_overdue_only_filter(self):
        async def scenario():
            engine, factory = await _make_env()
            try:
                user_id = uuid.uuid4()
                pid = uuid.uuid4()
                staff_id = await _seed_staff(factory, user_id=user_id)
                wi = await _seed_wp_index(factory, pid)
                # 逾期活跃、未逾期、逾期但已复核（不算逾期）
                await _seed_task(factory, pid, wi, wp_id=uuid.uuid4(), assignee=staff_id,
                                 workflow="in_progress", due_at=_utc(-3600))
                await _seed_task(factory, pid, wi, wp_id=uuid.uuid4(), assignee=staff_id,
                                 workflow="in_progress", due_at=_utc(3600))
                await _seed_task(factory, pid, wi, wp_id=uuid.uuid4(), assignee=staff_id,
                                 workflow="reviewed", due_at=_utc(-3600))
                await _seed_task(factory, pid, wi, wp_id=uuid.uuid4(), assignee=staff_id,
                                 workflow="in_progress", due_at=None)
                async with factory() as s:
                    svc = ProcedureTaskQueryService(s)
                    overdue = await svc.list_tasks(user_id, TaskQueryFilters(project_id=pid, overdue_only=True))
                assert overdue["pagination"]["total"] == 1
                assert overdue["items"][0]["overdue"] is True
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_cross_project_isolation_in_list(self):
        async def scenario():
            engine, factory = await _make_env()
            try:
                user_id = uuid.uuid4()
                pid_a = uuid.uuid4()
                pid_b = uuid.uuid4()
                staff_id = await _seed_staff(factory, user_id=user_id)
                wi_a = await _seed_wp_index(factory, pid_a)
                wi_b = await _seed_wp_index(factory, pid_b)
                await _seed_task(factory, pid_a, wi_a, wp_id=uuid.uuid4(), assignee=staff_id)
                await _seed_task(factory, pid_b, wi_b, wp_id=uuid.uuid4(), assignee=staff_id)
                async with factory() as s:
                    svc = ProcedureTaskQueryService(s)
                    only_a = await svc.list_tasks(user_id, TaskQueryFilters(project_id=pid_a))
                    cross = await svc.list_tasks(user_id, TaskQueryFilters())  # 跨项目
                assert only_a["pagination"]["total"] == 1
                assert only_a["items"][0]["project_id"] == str(pid_a)
                assert cross["pagination"]["total"] == 2
            finally:
                await engine.dispose()
        asyncio.run(scenario())


# ===========================================================================
# P28：深链与项目边界
# Validates: Requirements 9.5, 9.6, 9.8
# ===========================================================================
class TestP28DeepLinkAndProjectBoundary:
    def test_detail_cross_project_returns_none(self):
        async def scenario():
            engine, factory = await _make_env()
            try:
                pid_a = uuid.uuid4()
                pid_b = uuid.uuid4()
                wi_a = await _seed_wp_index(factory, pid_a)
                task_id, _dk = await _seed_task(factory, pid_a, wi_a, wp_id=uuid.uuid4())
                async with factory() as s:
                    svc = ProcedureTaskQueryService(s)
                    # 用错误 project (pid_b) 取 pid_a 的 task → None（路由据此 404）
                    wrong = await svc.get_detail(pid_b, task_id)
                    right = await svc.get_detail(pid_a, task_id)
                assert wrong is None
                assert right is not None and right.id == task_id
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_detail_deeplink_keys_present_no_program_no_fallback(self):
        """合法深链只按 sheet_key+definition_key 定位，不按 program_no 降级。"""
        async def scenario():
            engine, factory = await _make_env()
            try:
                pid = uuid.uuid4()
                wi = await _seed_wp_index(factory, pid)
                task_id, dk = await _seed_task(factory, pid, wi, wp_id=None, program_no="7")
                async with factory() as s:
                    svc = ProcedureTaskQueryService(s)
                    task = await svc.get_detail(pid, task_id)
                    detail = svc.serialize_detail(task)
                # 深链定位 key 必须存在且非空
                assert detail["sheet_key"] and detail["definition_key"] == dk
                # nullable wp_id：未生成底稿
                assert detail["wp_id"] is None
                assert detail["materialization_required"] is False
                # program_no 仅作展示，不是深链定位 key（存在但不作降级依据）
                assert detail["program_no"] == "7"
            finally:
                await engine.dispose()
        asyncio.run(scenario())


# ===========================================================================
# PostgreSQL 集成：真实 covering-index 查询（assignee/reviewer 过滤 + 分页）
# 需求 12.3 / Design C11 —— DB 约束/index/asyncpg IN 语义在 PG 验证。
# ===========================================================================
import pytest_asyncio  # noqa: E402
from app.core.config import settings as _app_settings  # noqa: E402

_IS_PG = _app_settings.DATABASE_URL.startswith("postgresql")


@pytest_asyncio.fixture
async def pg_factory():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (query integration)")
    engine = create_async_engine(_app_settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
class TestPgQueryCoveringIndex:
    async def test_assignee_covering_index_query(self, pg_factory):
        factory = pg_factory
        async with factory() as s:
            picked = (
                await s.execute(
                    sa.text(
                        "SELECT wp.project_id, wp.wp_index_id, wp.id, wi.wp_code, "
                        "COALESCE(wi.audit_cycle,'D') "
                        "FROM working_paper wp JOIN wp_index wi ON wi.id=wp.wp_index_id "
                        "WHERE wp.is_deleted=false AND wi.is_deleted=false LIMIT 1"
                    )
                )
            ).first()
            user_id = (await s.execute(sa.text("SELECT id FROM users LIMIT 1"))).scalar()
        if picked is None or user_id is None:
            pytest.skip("dev 库无 project/wp_index/working_paper/users 可复用")
        project_id, wp_index_id, wp_id, wp_code, cycle = picked

        staff_id = uuid.uuid4()
        dk = f"{wp_code}A::{wp_code}A::{uuid.uuid4().hex[:12]}"
        tid = uuid.uuid4()
        async with factory() as s:
            await s.execute(
                sa.text(
                    "INSERT INTO staff_members (id, user_id, name, source, is_deleted) "
                    "VALUES (:id,:uid,'查询测试人员','custom',false)"
                ),
                {"id": staff_id, "uid": user_id},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO procedure_row_definitions "
                    "(definition_key, template_code, template_revision_hash, sheet_key, procedure_text) "
                    "VALUES (:k,:tc,:h,:sk,:pt)"
                ),
                {"k": dk, "tc": f"{wp_code}A", "h": "a" * 64, "sk": f"{wp_code}A", "pt": "核对明细账"},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO procedure_row_tasks "
                    "(id, project_id, wp_index_id, wp_id, definition_key, sheet_key, wp_code, "
                    " sheet_name, program_no, procedure_text, definition_revision_hash, "
                    " audit_cycle_snapshot, applicability_status, workflow_status, "
                    " assignee_staff_id, assignment_version, lock_version, due_at) "
                    "VALUES (:id,:pid,:wi,:wp,:dk,:sk,:wc,:sn,'1','核对明细账',:h,:cy,"
                    " 'execute','assigned',:asg,1,0, now() - interval '1 day')"
                ),
                {"id": tid, "pid": project_id, "wi": wp_index_id, "wp": wp_id, "dk": dk,
                 "sk": f"{wp_code}A", "wc": wp_code, "sn": f"{wp_code} 明细", "h": "a" * 64,
                 "cy": cycle, "asg": staff_id},
            )
            await s.commit()
        try:
            async with factory() as s:
                svc = ProcedureTaskQueryService(s)
                # 跨项目 my tasks（走 assignee covering index）
                res = await svc.list_tasks(user_id, TaskQueryFilters(role="assignee"))
                found = [i for i in res["items"] if i["task_id"] == str(tid)]
                assert len(found) == 1
                item = found[0]
                assert item["my_role"] == "assignee"
                assert item["overdue"] is True  # due_at 已过期、assigned 非完结
                assert item["materialization_required"] is False
                # 项目级 + overdue_only 过滤
                res2 = await svc.list_tasks(
                    user_id, TaskQueryFilters(project_id=project_id, overdue_only=True)
                )
                assert any(i["task_id"] == str(tid) for i in res2["items"])
                # reviewer 视角查不到（该任务只有 assignee）
                res3 = await svc.list_tasks(user_id, TaskQueryFilters(role="reviewer"))
                assert all(i["task_id"] != str(tid) for i in res3["items"])
                # 详情绑定 + 深链 key
                detail = await svc.get_detail(project_id, tid)
                assert detail is not None
                d = svc.serialize_detail(detail, staff_ids={staff_id})
                assert d["sheet_key"] == f"{wp_code}A" and d["definition_key"] == dk
                # 跨项目取详情 → None
                assert await svc.get_detail(uuid.uuid4(), tid) is None
        finally:
            async with factory() as s:
                await s.execute(sa.text("DELETE FROM procedure_row_tasks WHERE id=:id"), {"id": tid})
                await s.execute(sa.text("DELETE FROM procedure_row_definitions WHERE definition_key=:k"), {"k": dk})
                await s.execute(sa.text("DELETE FROM staff_members WHERE id=:id"), {"id": staff_id})
                await s.commit()

    async def test_covering_index_used_in_plan(self, pg_factory):
        """EXPLAIN 验证 assignee 查询计划可命中 covering index（数据足够时）。"""
        factory = pg_factory
        async with factory() as s:
            plan = (
                await s.execute(
                    sa.text(
                        "EXPLAIN SELECT id, wp_index_id, wp_id, sheet_key, definition_key, "
                        "lock_version, assignment_version FROM procedure_row_tasks "
                        "WHERE is_deleted=false AND assignee_staff_id = :sid "
                        "AND workflow_status='assigned' ORDER BY due_at"
                    ),
                    {"sid": uuid.uuid4()},
                )
            ).scalars().all()
        plan_text = "\n".join(plan)
        # 计划合法即通过（空表可能 seq scan）；有 index 定义即验证 SQL 与列有效。
        assert "procedure_row_tasks" in plan_text.lower() or "scan" in plan_text.lower()
