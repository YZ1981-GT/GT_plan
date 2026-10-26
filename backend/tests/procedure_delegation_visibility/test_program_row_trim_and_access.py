# -*- coding: utf-8 -*-
"""程序表按行裁剪与行级编辑隔离（spec procedure-trim-generation-delegation-chain 需求 6 / 7，任务 15~17）。

真实 PostgreSQL，每个用例一个外层事务（``create_savepoint``，路由里的 commit / rollback 只动保存点），结束回滚。

- 按行裁剪 / 恢复：只为这一行建任务并绑定底稿；同一程序号的新旧定义任务一起裁、一起恢复；恢复没有任务的行
  不建任务；自加行 / 无模板的表 422；别的项目的底稿 404；裁掉的行委派被拒。
- 渲染投影：任务不适用 ⇒ 行显示不适用 + 理由；恢复后页面仍是不适用 ⇒ 显示待执行；页面里旧的「不适用」（没有
  任务裁过）不动；已存数据不被就地改写。
- 行归属：执行人只拿到本人的有效行；主编 / 经理 / admin 全部；能否裁剪 = 项目委派人。
- 字段覆盖：受限用户只能写本人的行、不能借覆盖裁剪；主编 / 主管 / admin 不受限。
- 真实 app：按行裁剪接口只给委派人；行归属接口经底稿可见性门；字段覆盖要求项目成员。
"""
from __future__ import annotations

import copy
import types
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel
from app.models.procedure_models import ProcedureRowDefinition, ProcedureRowTask, ProcedureRowTaskHistory
from app.routers.wp_render_strategies import _a_program
from app.services.procedure_delegation_service import ProcedureDelegationService
from app.services.procedure_row_trim_service import resolve_row_tasks, restore_row, trim_row
from app.services.wp_visibility.delegation_transaction import (
    DelegationError,
    DelegationRejectReason,
    DelegationTransactionService,
    RowDelegationRequest,
)
from app.services.wp_visibility.program_row_guard import assert_program_override_allowed, resolve_row_access

from ._factories import IS_PG, mk_assignment, mk_project, mk_project_user, mk_row_task, mk_staff, mk_user
from ._factories import mk_working_paper, mk_wp_index

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")]

SHEET = "应收账款实质性程序表D2A"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    # 与生产 get_db 同口径（expire_on_commit=False）：路由 commit 后还要读刚写的行
    s = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield s
    finally:
        from app.main import app

        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        await s.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


def _client(s: AsyncSession, user) -> AsyncClient:
    from app.main import app

    async def _db():
        yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _data(resp) -> dict:
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) else body


async def _member(s, project, *, role="auditor", assigned=("D",), level=PermissionLevel.edit):
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    a = await mk_assignment(s, project.id, staff.id, role=role)
    a.assigned_cycles = list(assigned) if assigned else None
    pu = await mk_project_user(s, project.id, user.id)
    pu.permission_level = level
    await s.flush()
    return user, staff


async def _paper(s):
    project = await mk_project(s)
    wi = await mk_wp_index(s, project.id, wp_code="D2", wp_name="应收账款", audit_cycle="D")
    wp = await mk_working_paper(s, project.id, wi.id)
    return project, wi, wp


async def _tasks(s, project_id) -> list[ProcedureRowTask]:
    return list((await s.execute(sa.select(ProcedureRowTask).where(
        ProcedureRowTask.project_id == project_id).order_by(ProcedureRowTask.created_at, ProcedureRowTask.id)
    )).scalars().all())


async def _events(s, task_id) -> list[tuple]:
    return [tuple(r) for r in (await s.execute(sa.select(
        ProcedureRowTaskHistory.event_type, ProcedureRowTaskHistory.reason,
    ).where(ProcedureRowTaskHistory.task_id == task_id).order_by(ProcedureRowTaskHistory.lock_version))).all()]


async def _assign(s, project, wp, program_no, staff):
    """测试捷径：直接把这一行的任务派给某人（委派链路另有专测）。"""
    task = (await resolve_row_tasks(s, project.id, wp.id, SHEET, program_no, create=True)).tasks[0]
    task.assignee_staff_id = staff.id
    task.workflow_status = "assigned"
    await s.flush()
    return task


# ---------------------------------------------------------------------------
# 按行裁剪 / 恢复
# ---------------------------------------------------------------------------
async def test_trim_restore_round_trip_on_single_bound_task(db):
    s = db
    project, wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")

    out = await trim_row(s, project.id, wp.id, SHEET, 1, actor_user_id=actor.id, reason="本期无此业务")
    assert (out["changed"], out["applicability_status"]) == (True, "not_applicable")
    assert (out["template_code"], out["program_no"]) == ("D2A", "1")
    tasks = await _tasks(s, project.id)
    assert len(tasks) == 1, "只为这一行建任务，不整表物化"
    task = tasks[0]
    assert out["task_ids"] == [str(task.id)]
    assert (task.wp_id, task.wp_index_id, task.sheet_key, task.program_no) == (wp.id, wi.id, "D2A", "1")
    assert (task.applicability_status, task.workflow_status) == ("not_applicable", "cancelled")
    definition = await s.scalar(sa.select(ProcedureRowDefinition).where(
        ProcedureRowDefinition.definition_key == task.definition_key))
    assert definition is not None and definition.template_code == "D2A" and definition.program_no == "1"

    again = await trim_row(s, project.id, wp.id, SHEET, "1.0", actor_user_id=actor.id, reason="再裁一次")
    assert again["changed"] is False and again["task_ids"] == [str(task.id)], "程序号口径统一，已裁不重复记"

    back = await restore_row(s, project.id, wp.id, SHEET, "1", actor_user_id=actor.id, reason="有业务了")
    assert (back["changed"], back["requires_reassign"]) == (True, True)
    await s.refresh(task)
    assert (task.applicability_status, task.workflow_status) == ("execute", "unassigned")

    noop = await restore_row(s, project.id, wp.id, SHEET, 1, actor_user_id=actor.id)
    assert (noop["changed"], noop["requires_reassign"], noop["task_ids"]) == (False, False, [])
    assert await _events(s, task.id) == [("trim_not_applicable", "本期无此业务"), ("trim_restore", "有业务了")]


async def test_same_program_no_tasks_trimmed_and_restored_together(db):
    """模板改版后同一行有新旧两条定义的任务：按程序号一起裁、一起恢复（旧的不适用任务也能恢复）。"""
    s = db
    project, wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    old = await mk_row_task(s, project.id, wi.id, sheet_key="D2A", wp_code="D2")
    new = await mk_row_task(s, project.id, wi.id, sheet_key="D2A", wp_code="D2")
    other = await mk_row_task(s, project.id, wi.id, sheet_key="D2A", wp_code="D2")
    old.program_no, new.program_no, other.program_no = "2", "2.0", "3"
    old.applicability_status, old.workflow_status = "not_applicable", "cancelled"
    await s.flush()

    out = await trim_row(s, project.id, wp.id, SHEET, 2, actor_user_id=actor.id, reason="不适用")
    assert out["changed"] is True and set(out["task_ids"]) == {str(old.id), str(new.id)}
    assert len(await _tasks(s, project.id)) == 3, "已有任务就不再新建"
    for t in (old, new, other):
        await s.refresh(t)
    assert (new.applicability_status, other.applicability_status) == ("not_applicable", "execute")
    assert old.wp_id == wp.id and new.wp_id == wp.id and other.wp_id is None, "只绑定这一行的任务"

    back = await restore_row(s, project.id, wp.id, SHEET, "2", actor_user_id=actor.id)
    assert back["changed"] is True and set(back["task_ids"]) == {str(old.id), str(new.id)}
    for t in (old, new):
        await s.refresh(t)
        assert (t.applicability_status, t.workflow_status) == ("execute", "unassigned")


async def test_restore_untrimmed_row_creates_nothing_and_leaves_other_cancellations(db):
    s = db
    project, wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    before = await s.scalar(sa.select(sa.func.count()).select_from(ProcedureRowDefinition))
    out = await restore_row(s, project.id, wp.id, SHEET, 3, actor_user_id=actor.id)
    assert (out["changed"], out["task_ids"], out["requires_reassign"]) == (False, [], False)
    assert await _tasks(s, project.id) == []
    assert await s.scalar(sa.select(sa.func.count()).select_from(ProcedureRowDefinition)) == before

    cancelled = await mk_row_task(s, project.id, wi.id, sheet_key="D2A", wp_code="D2")  # 别的原因取消（仍适用）
    cancelled.program_no, cancelled.workflow_status = "6", "cancelled"
    await s.flush()
    out = await restore_row(s, project.id, wp.id, SHEET, 6, actor_user_id=actor.id)
    assert out["changed"] is False and out["task_ids"] == []
    await s.refresh(cancelled)
    assert (cancelled.workflow_status, cancelled.applicability_status) == ("cancelled", "execute"), "细裁只恢复不适用的任务"


async def test_rows_without_task_or_template_and_foreign_workpaper(db):
    s = db
    project, wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    wi_q = await mk_wp_index(s, project.id, wp_code="Q1", audit_cycle="Q")
    wp_q = await mk_working_paper(s, project.id, wi_q.id)
    other_project, _owi, other_wp = await _paper(s)

    for wp_id, sheet, no in ((wp.id, SHEET, 999), (wp_q.id, "自定义程序表", 1)):
        with pytest.raises(HTTPException) as ei:
            await trim_row(s, project.id, wp_id, sheet, no, actor_user_id=actor.id, reason="x")
        assert ei.value.status_code == 422 and ei.value.detail["error"] == "row_trim_unsupported"
        noop = await restore_row(s, project.id, wp_id, sheet, no, actor_user_id=actor.id)
        assert noop["changed"] is False, "没有任务的行恢复 = 无变化（页面上的标记由控制台自己改回）"
    with pytest.raises(HTTPException) as ei:
        await trim_row(s, project.id, other_wp.id, SHEET, 1, actor_user_id=actor.id, reason="x")
    assert ei.value.status_code == 404, "底稿必须属于路径上的项目"
    assert await _tasks(s, project.id) == [] and await _tasks(s, other_project.id) == []

    beyond = await mk_row_task(s, project.id, wi.id, sheet_key="D2A", wp_code="D2")  # 如 xlsx 来源定义的任务
    beyond.program_no = "21"
    await s.flush()
    out = await trim_row(s, project.id, wp.id, SHEET, 21, actor_user_id=actor.id, reason="不适用")
    assert out["task_ids"] == [str(beyond.id)] and out["changed"] is True, "已有任务就不看模板"


async def test_trimmed_row_cannot_be_delegated(db):
    s = db
    project, _wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    _user, staff = await _member(s, project)
    out = await trim_row(s, project.id, wp.id, SHEET, 1, actor_user_id=actor.id, reason="不适用")
    task_id = uuid.UUID(out["task_ids"][0])

    with pytest.raises(DelegationError) as ei:
        await DelegationTransactionService(s).delegate_row(RowDelegationRequest(
            project_id=project.id, actor_user_id=actor.id, task_id=task_id, target_role="assignee", staff_id=staff.id))
    assert ei.value.reason == DelegationRejectReason.trimmed
    for selector in ({"kind": "row", "task_ids": [str(task_id)]}, {"kind": "cycle", "cycle": "D"}):
        assert await ProcedureDelegationService(s).resolve_targets(project.id, selector) == [], "委派目标只取适用行"


# ---------------------------------------------------------------------------
# 渲染投影
# ---------------------------------------------------------------------------
_PAGE = {"programs": [
    {"id": "row-1", "program_no": 1, "status": "completed", "execution_summary": "已执行"},
    {"id": "row-2", "program_no": 2, "status": "pending"},
    {"id": "row-3", "program_no": 3, "status": "not_applicable", "trim_reason": "页面里裁的"},
]}


async def test_projection_follows_row_tasks_and_keeps_legacy_page_trims(db):
    s = db
    project, _wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    ctx = types.SimpleNamespace(db=s, project_id=project.id, working_paper=wp, wp_code="D2")
    legacy = await mk_row_task(s, project.id, wp.wp_index_id, sheet_key="D2A", wp_code="D2")  # 适用、从未细裁
    legacy.program_no = "3"
    await s.flush()
    page = copy.deepcopy(_PAGE)
    assert await _a_program.project_row_applicability(ctx, page, "D2A") is False and page == _PAGE

    await trim_row(s, project.id, wp.id, SHEET, 1, actor_user_id=actor.id, reason="本期无此业务")
    trimmed = copy.deepcopy(_PAGE)
    assert await _a_program.project_row_applicability(ctx, trimmed, "D2A") is True
    assert (trimmed["programs"][0]["status"], trimmed["programs"][0]["trim_reason"]) == ("not_applicable", "本期无此业务")
    assert trimmed["programs"][1:] == _PAGE["programs"][1:], "没细裁过的行（含页面里旧的不适用，有没有任务都一样）不动"

    await restore_row(s, project.id, wp.id, SHEET, 1, actor_user_id=actor.id)
    stale = copy.deepcopy(trimmed)  # 页面还停在「不适用」（恢复后没保存过）
    assert await _a_program.project_row_applicability(ctx, stale, "D2A") is True
    assert stale["programs"][0]["status"] == "pending" and "trim_reason" not in stale["programs"][0]
    assert stale["programs"][2]["status"] == "not_applicable"
    fresh = copy.deepcopy(_PAGE)
    assert await _a_program.project_row_applicability(ctx, fresh, "D2A") is False, "恢复后页面里的执行状态照旧"

    # 裁剪方案的恢复（scheme_restore）同样算恢复：控制台裁、方案恢复后页面不得停在不适用
    from app.services.procedure_task_transition_service import ProcedureTaskTransitionService

    await trim_row(s, project.id, wp.id, SHEET, 2, actor_user_id=actor.id, reason="先裁")
    task2 = (await resolve_row_tasks(s, project.id, wp.id, SHEET, 2, create=False)).tasks[0]
    await ProcedureTaskTransitionService(s).reopen(task2, actor_user_id=actor.id, set_applicability="execute",
                                                   reason="scheme_restore", event_type="scheme_restore")
    via_scheme = copy.deepcopy(_PAGE)
    via_scheme["programs"][1]["status"] = "not_applicable"
    assert await _a_program.project_row_applicability(ctx, via_scheme, "D2A") is True
    assert via_scheme["programs"][1]["status"] == "pending"


async def test_projection_ignores_coarse_trim_cascade_and_restore(db):
    """粗裁级联取消 / 恢复执行是整张底稿的决定：恢复后页面原有的不适用（旧的页面裁剪、模板默认）照旧。"""
    from app.services.procedure_task_transition_service import ProcedureTaskTransitionService

    s = db
    project, wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    task = await mk_row_task(s, project.id, wi.id, sheet_key="D2A", wp_code="D2", wp_id=wp.id)
    task.program_no = "3"
    await s.flush()
    svc = ProcedureTaskTransitionService(s)
    await svc.cancel(task, actor_user_id=actor.id, reason="scheme_scope_cascade",
                     set_applicability="not_applicable", event_type="scheme_scope_cascade")
    await svc.reopen(task, actor_user_id=actor.id, set_applicability="execute", reason="scheme_scope_restore",
                     event_type="scheme_scope_restore")
    ctx = types.SimpleNamespace(db=s, project_id=project.id, working_paper=wp, wp_code="D2")
    page = copy.deepcopy(_PAGE)
    assert await _a_program.project_row_applicability(ctx, page, "D2A") is False and page == _PAGE


async def test_render_persisted_sheet_projects_on_copy(db):
    s = db
    project, _wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    ctx = types.SimpleNamespace(
        db=s, project_id=project.id, working_paper=wp, wp_code="D2",
        classification=types.SimpleNamespace(sheet_name=SHEET), sheet_html_data=copy.deepcopy(_PAGE),
    )
    first = await _a_program.render(ctx)
    assert first["programs"] == _PAGE["programs"], "没有细裁任务 ⇒ 内容同已存数据"
    assert first["override_scope"] == "procedure_table:D2A", "副本里回传字段覆盖 scope（audit-year R0）"
    await trim_row(s, project.id, wp.id, SHEET, 2, actor_user_id=actor.id, reason="不适用")
    out = await _a_program.render(ctx)
    assert out["programs"][1]["status"] == "not_applicable"
    assert ctx.sheet_html_data == _PAGE, "投影只改本次响应的副本，不就地改写已存数据"


# ---------------------------------------------------------------------------
# 行归属与字段覆盖
# ---------------------------------------------------------------------------
async def _team(s):
    project, wi, wp = await _paper(s)
    team = types.SimpleNamespace(project=project, wi=wi, wp=wp, admin=await mk_user(s, "admin"))
    team.assignee, team.a_staff = await _member(s, project)
    team.other, team.o_staff = await _member(s, project)
    team.bystander, _ = await _member(s, project)
    team.lead, _ = await _member(s, project)
    team.manager, _ = await _member(s, project, role="manager", assigned=None)
    wp.assigned_to = team.lead.id
    await _assign(s, project, wp, 2, team.a_staff)
    await _assign(s, project, wp, 4, team.o_staff)
    await _assign(s, project, wp, 5, team.a_staff)
    await trim_row(s, project.id, wp.id, SHEET, 5, actor_user_id=team.admin.id, reason="不适用")
    return team


async def test_row_access_by_identity(db):
    s = db
    t = await _team(s)
    names = {"2": t.a_staff.name, "4": t.o_staff.name}

    access = await resolve_row_access(s, t.assignee, t.wp, SHEET)
    assert (access.full_power, access.can_trim, access.template_code) == (False, False, "D2A")
    assert access.own_program_nos == {"2"}, "已裁掉的第 5 行不再算本人的"
    assert access.assignees == names
    assert (await resolve_row_access(s, t.bystander, t.wp, SHEET)).own_program_nos == frozenset()
    lead = await resolve_row_access(s, t.lead, t.wp, SHEET)
    assert (lead.full_power, lead.can_trim) == (True, False), "主编可改全部行，但裁剪只归委派人"
    for user in (t.manager, t.admin):
        got = await resolve_row_access(s, user, t.wp, SHEET)
        assert (got.full_power, got.can_trim) == (True, True)
    assert access.to_dict()["own_program_nos"] == ["2"]


async def test_program_override_only_own_rows_for_restricted(db):
    s = db
    t = await _team(s)
    pid = t.project.id
    for scope in ("procedure_table:D2A", f"procedure_table:{SHEET}"):
        await assert_program_override_allowed(s, t.assignee, pid, scope, "2", "execution_summary", "已函证")
        for item_key, field_name, value in (("4", "execution_summary", "x"), ("2", "status", "not_applicable")):
            with pytest.raises(HTTPException) as ei:
                await assert_program_override_allowed(s, t.assignee, pid, scope, item_key, field_name, value)
            assert ei.value.status_code == 403
        await assert_program_override_allowed(s, t.lead, pid, scope, "4", "execution_summary", "主编改")
        with pytest.raises(HTTPException):
            await assert_program_override_allowed(s, t.lead, pid, scope, "4", "status", "not_applicable")
        for user in (t.manager, t.admin):
            await assert_program_override_allowed(s, user, pid, scope, "4", "status", "not_applicable")
    await assert_program_override_allowed(s, t.bystander, pid, "audit_sheet:D2-1", "r1", "amount", 1)


# ---------------------------------------------------------------------------
# 真实 app（替换掉两处独立事务写入：操作日志、拒绝审计 —— 否则会在真库留下引用回滚数据的行）
# ---------------------------------------------------------------------------
@pytest.fixture
def side_writes(monkeypatch):
    from app.middleware import audit_log
    from app.services.wp_visibility.denial import DenialResponder

    seen: dict[str, list] = {"logs": [], "denials": []}

    async def _log(**kw):
        seen["logs"].append(kw)

    async def _denial(self, **kw):
        seen["denials"].append(kw)

    monkeypatch.setattr(audit_log, "_write_log", _log)
    monkeypatch.setattr(DenialResponder, "_write_outbox", _denial)
    return seen


def _principal(user):
    """请求身份用快照：路由里的 rollback 会让会话里的 ORM 对象过期，再读属性就触发同步加载。"""
    return types.SimpleNamespace(id=user.id, role=user.role, username=user.username, email=user.email,
                                 is_active=True, is_deleted=False)


async def test_row_trim_endpoints_only_for_delegators(db, side_writes):
    s = db
    t = await _team(s)
    pid, wp_id = t.project.id, t.wp.id
    base = f"/api/projects/{pid}/procedure-trim/workpapers/{wp_id}/program-rows"
    body = {"sheet_name": SHEET, "program_no": 3, "reason": "本期无此业务"}
    for user in (t.assignee, t.lead):
        async with _client(s, _principal(user)) as c:
            assert (await c.post(f"{base}/not-applicable", json=body)).status_code == 403
    async with _client(s, _principal(t.manager)) as c:
        assert (await c.post(f"{base}/not-applicable", json={**body, "reason": "  "})).status_code == 422
        r = await c.post(f"{base}/not-applicable", json=body)
        assert r.status_code == 200 and _data(r)["changed"] is True
        r = await c.post(f"{base}/restore", json={"sheet_name": SHEET, "program_no": "3"})
        assert r.status_code == 200 and _data(r)["requires_reassign"] is True
        r = await c.post(f"{base}/not-applicable", json={**body, "program_no": 999})
        # 平台错误信封把 detail 放在 message（前端拦截器补回 detail）；控制台据 error 码只在页面上标记
        assert r.status_code == 422 and r.json()["message"]["error"] == "row_trim_unsupported"
    events = (await s.execute(sa.select(ProcedureRowTaskHistory.event_type).join(
        ProcedureRowTask, ProcedureRowTask.id == ProcedureRowTaskHistory.task_id,
    ).where(ProcedureRowTask.project_id == pid, ProcedureRowTask.program_no == "3")
        .order_by(ProcedureRowTaskHistory.lock_version))).scalars().all()
    assert events == ["trim_not_applicable", "trim_restore"], "两次成功请求都已提交"
    assert len(side_writes["logs"]) == 2


async def test_row_access_endpoint_goes_through_visibility_gate(db, side_writes):
    s = db
    t = await _team(s)
    outsider = await mk_user(s)
    await mk_project_user(s, t.project.id, outsider.id, scope_cycles="")
    url = f"/api/workpapers/{t.wp.id}/program-row-access"
    async with _client(s, _principal(t.assignee)) as c:
        r = await c.get(url, params={"sheet_name": SHEET})
    assert r.status_code == 200
    got = _data(r)
    assert (got["full_power"], got["can_trim"], got["own_program_nos"]) == (False, False, ["2"])
    assert got["assignees"] == {"2": t.a_staff.name, "4": t.o_staff.name}
    async with _client(s, _principal(outsider)) as c:
        assert (await c.get(url, params={"sheet_name": SHEET})).status_code == 404
    assert [d["reason"] for d in side_writes["denials"]], "拒绝走统一可见性门（记拒绝原因）"


async def test_field_override_endpoints_require_member_and_own_row(db, side_writes):
    s = db
    t = await _team(s)
    pid = str(t.project.id)
    stranger = await mk_user(s)
    url = "/api/workpapers/field-overrides"
    body = {"project_id": pid, "year": 2025, "scope": "procedure_table:D2A", "field": "execution_summary"}
    async with _client(s, _principal(t.assignee)) as c:
        assert (await c.post(url, json={**body, "item_key": "4", "value": "改别人的"})).status_code == 403
        assert (await c.post(url, json={**body, "item_key": "2", "value": "已函证"})).status_code == 200
        r = await c.get(url, params={"project_id": pid, "year": 2025, "scope": "procedure_table:D2A"})
        assert r.status_code == 200 and _data(r)["2"]["execution_summary"] == "已函证"
    async with _client(s, _principal(stranger)) as c:
        r = await c.get(url, params={"project_id": pid, "year": 2025, "scope": "procedure_table:D2A"})
        assert r.status_code == 403, "原先只校验登录，可读任意项目的覆盖值"
