# Feature: procedure-delegation-notification — Task 13 操作复核 / IssueTicket / 历史参与者授权
"""ProcedureReviewService 一级复核 + IssueTicket + 历史参与者授权：P17/P18/P25/P26 + PG 多轮集成。

Task 13 / 需求 5.4-5.8, 8.1-8.8 / Design C9、D6：

- **P17（reviewer fallback 决定性）**：Requirements 5.4/5.5/5.6 —— 严格依次 显式 →
  wp/wp_index reviewer 映射本项目唯一 active staff → 唯一 primary manager → reviewer_missing；
  重复/跨项目/inactive 不任取第一条。
- **P18（一级复核不改变高阶复核）**：Requirements 5.7/5.8 —— 任务 review 序列不改变底稿
  review_status/reviewer/status 等高阶复核状态与门槛。
- **P25（IssueTicket 关闭门槛）**：Requirements 8.3/8.4 —— 仅当全部关联 changes_requested
  IssueTicket closed 才能 reviewed；一个未关闭即 409。
- **P26（reviewer 转派历史可读、动作不可用）**：Requirements 8.5/8.6/8.7 —— 转派后历史参与者
  可读参与期间记录，但不获当前动作权限；对话授权基于并集，不依赖 initiator/target 单点。

数据库约束/事务在 PostgreSQL 验证；PBT 用项目 fast profile。
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
from app.models.base import Base, UserRole
from app.models.core import Notification, Project, User
from app.models.phase10_models import ReviewConversation, ReviewMessage
from app.models.phase15_models import IssueTicket
from app.models.procedure_models import ProcedureRowDefinition, ProcedureRowTask
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services.procedure_authorization import (
    ParticipantAccess,
    resolve_conversation_access,
)
from app.services.procedure_review_service import (
    REVIEWER_MISSING,
    ProcedureReviewService,
)
from app.services.procedure_task_transition_service import (
    ACTOR_ASSIGNEE,
    ACTOR_DELEGATOR,
    ACTOR_REVIEWER,
    ProcedureTaskTransitionService,
)

import app.models.procedure_models  # noqa: F401
import app.models.phase15_models  # noqa: F401
import app.models.phase10_models  # noqa: F401
import app.models.core  # noqa: F401
import app.models.staff_models  # noqa: F401
import app.models.workpaper_models  # noqa: F401

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
    async with factory() as s:
        s.add(Project(id=project_id, name="测试项目", client_name="客户"))
        await s.commit()
    return engine, factory, project_id


async def _add_user(factory, *, role=UserRole.auditor) -> uuid.UUID:
    uid = uuid.uuid4()
    async with factory() as s:
        s.add(
            User(
                id=uid,
                username=f"u_{uid.hex[:10]}",
                email=f"{uid.hex[:10]}@t.com",
                hashed_password="x",
                role=role,
            )
        )
        await s.commit()
    return uid


async def _add_staff(factory, *, user_id=None) -> uuid.UUID:
    sid = uuid.uuid4()
    async with factory() as s:
        s.add(StaffMember(id=sid, name=f"staff_{sid.hex[:6]}", user_id=user_id, source="custom"))
        await s.commit()
    return sid


async def _assign(factory, project_id, staff_id, role="auditor") -> None:
    async with factory() as s:
        s.add(ProjectAssignment(project_id=project_id, staff_id=staff_id, role=role))
        await s.commit()


async def _add_wp(factory, project_id, *, reviewer_user=None, wpindex_reviewer_user=None):
    wp_index_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    async with factory() as s:
        s.add(
            WpIndex(
                id=wp_index_id, project_id=project_id, wp_code="D2", wp_name="应收账款",
                audit_cycle="D", status=WpStatus.not_started, reviewer=wpindex_reviewer_user,
            )
        )
        s.add(
            WorkingPaper(
                id=wp_id, project_id=project_id, wp_index_id=wp_index_id,
                file_path="/tmp/D2.xlsx", source_type=WpSourceType.template,
                file_version=1, parsed_data={}, reviewer=reviewer_user,
            )
        )
        await s.commit()
    return wp_index_id, wp_id


async def _seed_task(
    factory, project_id, wp_index_id, *, wp_id=None, workflow="submitted",
    assignee=None, reviewer=None, lock_version=0, assignment_version=1,
):
    task_id = uuid.uuid4()
    dk = f"D2A::D2A::{uuid.uuid4().hex[:12]}"
    async with factory() as s:
        s.add(
            ProcedureRowDefinition(
                definition_key=dk, template_code="D2A", template_revision_hash="a" * 64,
                sheet_key="D2A", source_locator={}, program_no="1", procedure_text="程序文本",
                ref_snapshot=[], legacy_aliases=[], normalized_content={},
            )
        )
        s.add(
            ProcedureRowTask(
                id=task_id, project_id=project_id, wp_index_id=wp_index_id, wp_id=wp_id,
                definition_key=dk, sheet_key="D2A", wp_code="D2",
                definition_revision_hash="a" * 64, audit_cycle_snapshot="D",
                applicability_status="execute", workflow_status=workflow,
                assignee_staff_id=assignee, reviewer_staff_id=reviewer,
                lock_version=lock_version, assignment_version=assignment_version,
            )
        )
        await s.commit()
    return task_id, dk


async def _load_task(factory, task_id) -> ProcedureRowTask:
    async with factory() as s:
        return (
            await s.execute(sa.select(ProcedureRowTask).where(ProcedureRowTask.id == task_id))
        ).scalar_one()


# ===========================================================================
# P17：reviewer fallback 决定性
# Validates: Requirements 5.4, 5.5, 5.6
# ===========================================================================
class TestP17ReviewerFallback:
    def test_explicit_reviewer_wins(self):
        async def scenario():
            engine, factory, pid = await _make_env()
            try:
                ru = await _add_user(factory)
                rs = await _add_staff(factory, user_id=ru)
                wi, wp = await _add_wp(factory, pid)
                tid, _ = await _seed_task(factory, pid, wi, wp_id=wp, reviewer=rs)
                async with factory() as s:
                    svc = ProcedureReviewService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    staff_id, src = await svc.resolve_reviewer(task)
                assert src == "explicit" and staff_id == rs
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_wp_reviewer_maps_to_unique_project_staff(self):
        async def scenario():
            engine, factory, pid = await _make_env()
            try:
                ru = await _add_user(factory)
                rs = await _add_staff(factory, user_id=ru)
                await _assign(factory, pid, rs, role="manager")
                wi, wp = await _add_wp(factory, pid, reviewer_user=ru)
                tid, _ = await _seed_task(factory, pid, wi, wp_id=wp, reviewer=None)
                async with factory() as s:
                    svc = ProcedureReviewService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    staff_id, src = await svc.resolve_reviewer(task)
                assert src == "wp_reviewer" and staff_id == rs
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_duplicate_wp_reviewer_mapping_falls_through_not_first(self):
        """wp.reviewer 映射到 2 个 active project staff → 该层 None（不任取第一条），落到 primary manager。"""
        async def scenario():
            engine, factory, pid = await _make_env()
            try:
                ru = await _add_user(factory)
                # 同一 user_id 绑定两个 active staff，且都在本项目有 assignment → 重复不唯一
                s1 = await _add_staff(factory, user_id=ru)
                s2 = await _add_staff(factory, user_id=ru)
                await _assign(factory, pid, s1, role="auditor")
                await _assign(factory, pid, s2, role="auditor")
                # 唯一 primary manager 作为下一层
                mu = await _add_user(factory)
                ms = await _add_staff(factory, user_id=mu)
                await _assign(factory, pid, ms, role="manager")
                wi, wp = await _add_wp(factory, pid, reviewer_user=ru)
                tid, _ = await _seed_task(factory, pid, wi, wp_id=wp, reviewer=None)
                async with factory() as s:
                    svc = ProcedureReviewService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    staff_id, src = await svc.resolve_reviewer(task)
                assert src == "primary_manager" and staff_id == ms
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_reviewer_missing_when_nothing_resolves(self):
        async def scenario():
            engine, factory, pid = await _make_env()
            try:
                wi, wp = await _add_wp(factory, pid)
                tid, _ = await _seed_task(factory, pid, wi, wp_id=wp, reviewer=None)
                async with factory() as s:
                    svc = ProcedureReviewService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    staff_id, src = await svc.resolve_reviewer(task)
                assert staff_id is None and src == REVIEWER_MISSING
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_duplicate_primary_manager_is_reviewer_missing(self):
        """2 个 manager assignment → primary manager 层 None → reviewer_missing。"""
        async def scenario():
            engine, factory, pid = await _make_env()
            try:
                for _ in range(2):
                    mu = await _add_user(factory)
                    ms = await _add_staff(factory, user_id=mu)
                    await _assign(factory, pid, ms, role="manager")
                wi, wp = await _add_wp(factory, pid)
                tid, _ = await _seed_task(factory, pid, wi, wp_id=wp, reviewer=None)
                async with factory() as s:
                    svc = ProcedureReviewService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    _staff, src = await svc.resolve_reviewer(task)
                assert src == REVIEWER_MISSING
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    @given(
        has_explicit=st.booleans(),
        has_wp_reviewer=st.booleans(),
        n_managers=st.integers(min_value=0, max_value=2),
    )
    @settings(max_examples=5, deadline=None)
    def test_resolver_is_deterministic(self, has_explicit, has_wp_reviewer, n_managers):
        """任意成员图：resolve_reviewer 两次调用结果一致（决定性）。"""
        async def scenario():
            engine, factory, pid = await _make_env()
            try:
                reviewer_staff = None
                if has_explicit:
                    eu = await _add_user(factory)
                    reviewer_staff = await _add_staff(factory, user_id=eu)
                wp_reviewer_user = None
                if has_wp_reviewer:
                    wu = await _add_user(factory)
                    ws = await _add_staff(factory, user_id=wu)
                    await _assign(factory, pid, ws, role="auditor")
                    wp_reviewer_user = wu
                for _ in range(n_managers):
                    mu = await _add_user(factory)
                    ms = await _add_staff(factory, user_id=mu)
                    await _assign(factory, pid, ms, role="manager")
                wi, wp = await _add_wp(factory, pid, reviewer_user=wp_reviewer_user)
                tid, _ = await _seed_task(factory, pid, wi, wp_id=wp, reviewer=reviewer_staff)
                async with factory() as s:
                    svc = ProcedureReviewService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    r1 = await svc.resolve_reviewer(task)
                    r2 = await svc.resolve_reviewer(task)
                assert r1 == r2  # 决定性
                # 分层优先级自洽
                if has_explicit:
                    assert r1[1] == "explicit"
                elif has_wp_reviewer:
                    assert r1[1] == "wp_reviewer"
                elif n_managers == 1:
                    assert r1[1] == "primary_manager"
                else:
                    assert r1[1] == REVIEWER_MISSING
            finally:
                await engine.dispose()
        asyncio.run(scenario())


# ===========================================================================
# P18：一级复核不改变高阶复核
# Validates: Requirements 5.7, 5.8
# ===========================================================================
class TestP18FirstLevelReviewDoesNotTouchHigherReview:
    def test_review_leaves_workingpaper_higher_review_unchanged(self):
        async def scenario():
            engine, factory, pid = await _make_env()
            try:
                # reviewer + assignee
                ru = await _add_user(factory)
                rs = await _add_staff(factory, user_id=ru)
                au = await _add_user(factory)
                a_s = await _add_staff(factory, user_id=au)
                wi, wp = await _add_wp(factory, pid, reviewer_user=ru)
                tid, _ = await _seed_task(
                    factory, pid, wi, wp_id=wp, workflow="submitted",
                    assignee=a_s, reviewer=rs,
                )
                # 捕获底稿高阶复核前态
                async with factory() as s:
                    wpo = await s.get(WorkingPaper, wp)
                    before = (wpo.review_status, wpo.reviewer, wpo.status, wpo.file_version)
                # 程序行一级复核 reviewed（无未关闭 issue）
                async with factory() as s:
                    svc = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await svc.review(task, actor_user_id=ru, actor_role=ACTOR_REVIEWER, open_issue_count=0)
                    await s.commit()
                t = await _load_task(factory, tid)
                assert t.workflow_status == "reviewed"
                # 底稿高阶复核状态完全不变（P18）
                async with factory() as s:
                    wpo = await s.get(WorkingPaper, wp)
                    after = (wpo.review_status, wpo.reviewer, wpo.status, wpo.file_version)
                assert before == after
            finally:
                await engine.dispose()
        asyncio.run(scenario())


# ===========================================================================
# P25：IssueTicket 关闭门槛
# Validates: Requirements 8.3, 8.4
# ===========================================================================
class TestP25IssueTicketGate:
    def test_open_issue_blocks_review_close_unblocks(self):
        async def scenario():
            engine, factory, pid = await _make_env()
            try:
                ru = await _add_user(factory)
                rs = await _add_staff(factory, user_id=ru)
                au = await _add_user(factory)
                a_s = await _add_staff(factory, user_id=au)
                wi, wp = await _add_wp(factory, pid)
                tid, _ = await _seed_task(
                    factory, pid, wi, wp_id=wp, workflow="submitted", assignee=a_s, reviewer=rs,
                )
                # 退回：创建 review_comment IssueTicket
                async with factory() as s:
                    review = ProcedureReviewService(s)
                    trans = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await trans.request_changes(task, actor_user_id=ru, reason="缺证据", actor_role=ACTOR_REVIEWER)
                    conv = await review.ensure_conversation(task, actor_user_id=ru)
                    await review.create_or_reuse_issue_ticket(
                        task, actor_user_id=ru, reason="缺证据", conversation_id=conv.id
                    )
                    await s.commit()
                # 未关闭 → open_count=1
                async with factory() as s:
                    review = ProcedureReviewService(s)
                    assert await review.open_changes_requested_issue_count(tid) == 1
                # 助理修复后重新提交
                async with factory() as s:
                    trans = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await trans.start(task, actor_user_id=au, actor_role=ACTOR_ASSIGNEE)
                    await trans.submit(task, actor_user_id=au, execution_summary="已补",
                                       evidence_snapshot=["e2"], actor_role=ACTOR_ASSIGNEE)
                    await s.commit()
                # issue 仍未关闭 → review 被 409 阻止
                async with factory() as s:
                    review = ProcedureReviewService(s)
                    trans = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    open_count = await review.open_changes_requested_issue_count(tid)
                    with pytest.raises(HTTPException) as ei:
                        await trans.review(task, actor_user_id=ru, actor_role=ACTOR_REVIEWER,
                                           open_issue_count=open_count)
                    await s.rollback()
                assert ei.value.status_code == 409
                # 关闭 issue
                async with factory() as s:
                    review = ProcedureReviewService(s)
                    issues = await review.list_task_issues(tid)
                    await review.close_issue(tid, issues[0].id, actor_user_id=ru)
                    await s.commit()
                # 全部 closed → review 成功
                async with factory() as s:
                    review = ProcedureReviewService(s)
                    trans = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    open_count = await review.open_changes_requested_issue_count(tid)
                    assert open_count == 0
                    await trans.review(task, actor_user_id=ru, actor_role=ACTOR_REVIEWER,
                                       open_issue_count=open_count)
                    await s.commit()
                t = await _load_task(factory, tid)
                assert t.workflow_status == "reviewed"
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_create_or_reuse_does_not_duplicate_open_ticket(self):
        async def scenario():
            engine, factory, pid = await _make_env()
            try:
                ru = await _add_user(factory)
                rs = await _add_staff(factory, user_id=ru)
                au = await _add_user(factory)
                a_s = await _add_staff(factory, user_id=au)
                wi, wp = await _add_wp(factory, pid)
                tid, _ = await _seed_task(factory, pid, wi, wp_id=wp, workflow="submitted",
                                          assignee=a_s, reviewer=rs)
                async with factory() as s:
                    review = ProcedureReviewService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    conv = await review.ensure_conversation(task, actor_user_id=ru)
                    t1 = await review.create_or_reuse_issue_ticket(task, actor_user_id=ru, reason="a", conversation_id=conv.id)
                    t2 = await review.create_or_reuse_issue_ticket(task, actor_user_id=ru, reason="b", conversation_id=conv.id)
                    await s.commit()
                assert t1.id == t2.id  # 复用未关闭 ticket
                async with factory() as s:
                    cnt = (await s.execute(
                        sa.select(sa.func.count()).select_from(IssueTicket).where(IssueTicket.source_ref_id == tid)
                    )).scalar()
                assert cnt == 1
            finally:
                await engine.dispose()
        asyncio.run(scenario())


# ===========================================================================
# P26：reviewer 转派历史可读、动作不可用；对话授权基于并集
# Validates: Requirements 8.5, 8.6, 8.7
# ===========================================================================
class TestP26HistoryParticipantReadonly:
    def test_history_participant_readonly_and_union_authz(self):
        async def scenario():
            engine, factory, pid = await _make_env()
            try:
                # reviewer R、执行人 A1（后转派给 A2）
                ru = await _add_user(factory)
                rs = await _add_staff(factory, user_id=ru)
                u1 = await _add_user(factory)
                s1 = await _add_staff(factory, user_id=u1)
                u2 = await _add_user(factory)
                s2 = await _add_staff(factory, user_id=u2)
                # 无关用户（既非当前参与者、也非历史/issue/对话参与者）
                outsider = await _add_user(factory)
                await _add_staff(factory, user_id=outsider)
                wi, wp = await _add_wp(factory, pid)
                tid, _ = await _seed_task(
                    factory, pid, wi, wp_id=wp, workflow="acknowledged",
                    assignee=s1, reviewer=rs, assignment_version=1,
                )
                # 转派 A1→A2：history 记录旧执行人 s1（u1 成为历史参与者）
                async with factory() as s:
                    trans = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await trans.reassign(task, new_assignee_staff_id=s2, actor_user_id=ru,
                                         reason="更换执行人处理", actor_role=ACTOR_DELEGATOR)
                    await s.commit()
                # 建立对话（initiator=R,target=A2），并让 R 发消息
                async with factory() as s:
                    review = ProcedureReviewService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await review.add_message(task, sender_user_id=ru, content="请补充")
                    await s.commit()

                # 当前执行人 u2 → assignee（可动作）
                async with factory() as s:
                    r = await resolve_conversation_access(s, tid, await s.get(User, u2))
                assert r.access == ParticipantAccess.assignee
                # 当前 reviewer u_r → reviewer（可动作）
                async with factory() as s:
                    r = await resolve_conversation_access(s, tid, await s.get(User, ru))
                assert r.access == ParticipantAccess.reviewer
                # 历史执行人 u1（既非当前 assignee/reviewer，也非对话 initiator/target）
                #   → history_readonly（可读、不可动作）——证明授权基于并集非 initiator/target 单点
                async with factory() as s:
                    r = await resolve_conversation_access(s, tid, await s.get(User, u1))
                assert r.access == ParticipantAccess.history_readonly
                assert u1 in r.readonly_user_ids
                # 无关用户 → none
                async with factory() as s:
                    r = await resolve_conversation_access(s, tid, await s.get(User, outsider))
                assert r.access == ParticipantAccess.none
            finally:
                await engine.dispose()
        asyncio.run(scenario())

    def test_history_readonly_not_notified_but_current_participants_are(self):
        """comment 通知当前参与者（assignee/reviewer），历史只读参与者不自动收件（需求 8.7）。"""
        async def scenario():
            engine, factory, pid = await _make_env()
            try:
                ru = await _add_user(factory)
                rs = await _add_staff(factory, user_id=ru)
                u1 = await _add_user(factory)
                s1 = await _add_staff(factory, user_id=u1)
                u2 = await _add_user(factory)
                s2 = await _add_staff(factory, user_id=u2)
                wi, wp = await _add_wp(factory, pid)
                tid, _ = await _seed_task(factory, pid, wi, wp_id=wp, workflow="acknowledged",
                                          assignee=s1, reviewer=rs)
                async with factory() as s:
                    trans = ProcedureTaskTransitionService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await trans.reassign(task, new_assignee_staff_id=s2, actor_user_id=ru,
                                         reason="更换执行人处理", actor_role=ACTOR_DELEGATOR)
                    await s.commit()
                # reviewer 发消息：通知当前执行人 u2（不含发送者 ru、不含历史 u1）
                async with factory() as s:
                    review = ProcedureReviewService(s)
                    task = await s.get(ProcedureRowTask, tid)
                    await review.add_message(task, sender_user_id=ru, content="请看下")
                    await s.commit()
                async with factory() as s:
                    recips = set(
                        (await s.execute(sa.select(Notification.recipient_id))).scalars().all()
                    )
                assert u2 in recips
                assert ru not in recips   # 发送者不收
                assert u1 not in recips   # 历史只读参与者不自动收件
            finally:
                await engine.dispose()
        asyncio.run(scenario())


# ===========================================================================
# PostgreSQL 多轮集成：退回→回复→关闭 issue→再提交→通过
# ===========================================================================
async def _apply_v105(engine) -> None:
    sql = _V105.read_text(encoding="utf-8")
    for stmt in MigrationRunner._split_sql_statements(sql):
        async with engine.begin() as conn:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (review integration)")
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


@pytest.mark.asyncio
class TestPgMultiRoundReview:
    async def test_multi_round_reject_reply_close_resubmit_pass(self, pg_engine):
        """多轮：退回→回复→关闭 issue→再提交→通过（PG 真实约束 + IssueTicket 门槛）。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with factory() as s:
            picked = (
                await s.execute(
                    sa.text(
                        "SELECT wp.project_id, wp.wp_index_id, wp.id "
                        "FROM working_paper wp JOIN wp_index wi ON wi.id=wp.wp_index_id "
                        "WHERE wp.is_deleted=false AND wi.is_deleted=false LIMIT 1"
                    )
                )
            ).first()
            users = (await s.execute(sa.text("SELECT id FROM users LIMIT 2"))).scalars().all()
        if picked is None or len(users) < 2:
            pytest.skip("dev 库缺 project/wp/users 可复用")
        project_id, wp_index_id, wp_id = picked
        assignee_user, reviewer_user = users[0], users[1]

        # 播种两名程序行参与者 staff（各绑定一个既有 user），确保执行人/复核人为不同 staff。
        assignee_staff = uuid.uuid4()
        reviewer_staff = uuid.uuid4()
        async with factory() as s:
            await s.execute(
                sa.text(
                    "INSERT INTO staff_members (id, name, source, user_id, is_deleted) "
                    "VALUES (:id,:n,'custom',:u,false)"
                ),
                {"id": assignee_staff, "n": "T13执行人", "u": assignee_user},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO staff_members (id, name, source, user_id, is_deleted) "
                    "VALUES (:id,:n,'custom',:u,false)"
                ),
                {"id": reviewer_staff, "n": "T13复核人", "u": reviewer_user},
            )
            await s.commit()

        dk = f"D2A::D2A::{uuid.uuid4().hex[:12]}"
        tid = uuid.uuid4()
        async with factory() as s:
            await s.execute(
                sa.text(
                    "INSERT INTO procedure_row_definitions "
                    "(definition_key, template_code, template_revision_hash, sheet_key, procedure_text) "
                    "VALUES (:k,:tc,:h,:sk,:pt)"
                ),
                {"k": dk, "tc": "D2A", "h": "a" * 64, "sk": "D2A", "pt": "程序文本"},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO procedure_row_tasks "
                    "(id, project_id, wp_index_id, wp_id, definition_key, sheet_key, wp_code, "
                    " definition_revision_hash, audit_cycle_snapshot, applicability_status, "
                    " workflow_status, assignee_staff_id, reviewer_staff_id, assignment_version, lock_version) "
                    "VALUES (:id,:pid,:wi,:wp,:dk,:sk,'D2',:h,'D','execute','submitted',:asg,:rev,1,0)"
                ),
                {"id": tid, "pid": project_id, "wi": wp_index_id, "wp": wp_id, "dk": dk,
                 "sk": "D2A", "h": "a" * 64, "asg": assignee_staff, "rev": reviewer_staff},
            )
            await s.commit()

        created_issue_ids: list = []
        created_conv_ids: list = []
        try:
            # ---- Round 1：退回 ----
            async with factory() as s:
                review = ProcedureReviewService(s)
                trans = ProcedureTaskTransitionService(s)
                task = await s.get(ProcedureRowTask, tid)
                await trans.request_changes(task, actor_user_id=reviewer_user, reason="第一轮：缺凭证", actor_role=ACTOR_REVIEWER)
                conv = await review.ensure_conversation(task, actor_user_id=reviewer_user)
                created_conv_ids.append(conv.id)
                ticket = await review.create_or_reuse_issue_ticket(task, actor_user_id=reviewer_user, reason="第一轮：缺凭证", conversation_id=conv.id)
                created_issue_ids.append(ticket.id)
                await s.commit()

            # ---- 回复（助理发消息）----
            async with factory() as s:
                review = ProcedureReviewService(s)
                task = await s.get(ProcedureRowTask, tid)
                await review.add_message(task, sender_user_id=assignee_user, content="已补充凭证扫描件")
                await s.commit()

            # issue 未关闭 → review 阻止
            async with factory() as s:
                review = ProcedureReviewService(s)
                trans = ProcedureTaskTransitionService(s)
                task = await s.get(ProcedureRowTask, tid)
                await trans.start(task, actor_user_id=assignee_user, actor_role=ACTOR_ASSIGNEE)
                await trans.submit(task, actor_user_id=assignee_user, execution_summary="补充完成",
                                   evidence_snapshot=["v1"], actor_role=ACTOR_ASSIGNEE)
                await s.commit()
            async with factory() as s:
                review = ProcedureReviewService(s)
                trans = ProcedureTaskTransitionService(s)
                task = await s.get(ProcedureRowTask, tid)
                oc = await review.open_changes_requested_issue_count(tid)
                with pytest.raises(HTTPException) as ei:
                    await trans.review(task, actor_user_id=reviewer_user, actor_role=ACTOR_REVIEWER, open_issue_count=oc)
                await s.rollback()
            assert ei.value.status_code == 409

            # ---- 关闭 issue → 通过 ----
            async with factory() as s:
                review = ProcedureReviewService(s)
                for iid in created_issue_ids:
                    await review.close_issue(tid, iid, actor_user_id=reviewer_user)
                await s.commit()
            async with factory() as s:
                review = ProcedureReviewService(s)
                trans = ProcedureTaskTransitionService(s)
                task = await s.get(ProcedureRowTask, tid)
                oc = await review.open_changes_requested_issue_count(tid)
                assert oc == 0
                await trans.review(task, actor_user_id=reviewer_user, actor_role=ACTOR_REVIEWER, open_issue_count=oc)
                await s.commit()
            async with factory() as s:
                t = await s.get(ProcedureRowTask, tid)
                assert t.workflow_status == "reviewed"
        finally:
            async with factory() as s:
                await s.execute(sa.text("DELETE FROM notifications WHERE related_object_id=:id"), {"id": tid})
                for iid in created_issue_ids:
                    await s.execute(sa.text("DELETE FROM issue_tickets WHERE id=:id"), {"id": iid})
                for cid in created_conv_ids:
                    await s.execute(sa.text("DELETE FROM review_messages WHERE conversation_id=:id"), {"id": cid})
                    await s.execute(sa.text("DELETE FROM review_conversations WHERE id=:id"), {"id": cid})
                await s.execute(sa.text("DELETE FROM task_events WHERE aggregate_id=:id"), {"id": tid})
                await s.execute(sa.text("DELETE FROM procedure_row_task_history WHERE task_id=:id"), {"id": tid})
                await s.execute(sa.text("DELETE FROM procedure_row_tasks WHERE id=:id"), {"id": tid})
                await s.execute(sa.text("DELETE FROM procedure_row_definitions WHERE definition_key=:k"), {"k": dk})
                await s.execute(
                    sa.text("DELETE FROM staff_members WHERE id IN (:a,:r)"),
                    {"a": assignee_staff, "r": reviewer_staff},
                )
                await s.commit()
