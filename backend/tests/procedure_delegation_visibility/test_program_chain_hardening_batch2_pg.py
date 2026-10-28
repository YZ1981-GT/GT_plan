# -*- coding: utf-8 -*-
"""程序表链路加固批 2（spec procedure-chain-hardening-and-java-contracts R4 / R6 / R8 / R19）。

真实 PostgreSQL，每个用例一个外层事务（``create_savepoint``，路由里的 commit / rollback 只动保存点），结束回滚。

- R4：细裁 / 恢复（控制台按行、任务级端点、裁剪方案行条目）同事务把**已有的**状态覆盖值对齐
  （裁剪 ⇒ not_applicable、恢复 ⇒ pending）；没有覆盖值不新建；恢复回执带原执行人。
- R6：整册嵌入的控制台没有表名 ⇒ 细裁 / 恢复 / 行归属按底稿编码定位程序表并落任务。
- R8：覆盖值批量端点一次请求一次提交，不能写的项逐条回报原因（不再逐字段静默吞错）。
- R19：程序行归属端点在路由上显式挂底稿门，注册表不重复挂。
"""
from __future__ import annotations

import types
import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel
from app.models.workpaper_field_override_models import WorkpaperFieldOverride
from app.services.field_override_service import FieldOverrideService
from app.services.procedure_row_trim_service import resolve_row_tasks, restore_row, trim_row
from app.services.procedure_trim_service import ProcedureTrimService

from ._factories import IS_PG, mk_assignment, mk_project, mk_project_user, mk_staff, mk_user
from ._factories import mk_working_paper, mk_wp_index

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")]

SHEET = "应收账款实质性程序表D2A"
SCOPE = "procedure_table:D2A"
YEAR = 2025


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


@pytest.fixture
def side_writes(monkeypatch):
    """操作日志 / 拒绝记录走独立事务，会在真库留下引用回滚数据的行 ⇒ 换成内存记录。"""
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


def _client(s: AsyncSession, user) -> AsyncClient:
    from app.main import app

    async def _db():
        yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _data(resp):
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) else body


def _principal(user):
    """路由里有 rollback（只回滚保存点）⇒ 不把 ORM 用户对象交给依赖，免得过期属性触发懒加载。"""
    return types.SimpleNamespace(id=user.id, role=user.role, username=user.username, email=user.email,
                                 is_active=True, is_deleted=False)


async def _member(s, project, *, role="auditor", assigned=("D",), level=PermissionLevel.edit):
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    a = await mk_assignment(s, project.id, staff.id, role=role)
    a.assigned_cycles = list(assigned) if assigned else None
    pu = await mk_project_user(s, project.id, user.id)
    pu.permission_level = level
    await s.flush()
    return user, staff


async def _paper(s, *, wp_code="D2", audit_cycle="D", with_year=True):
    project = await mk_project(s)
    if with_year:
        project.audit_period_end = date(YEAR, 12, 31)
    wi = await mk_wp_index(s, project.id, wp_code=wp_code, wp_name="应收账款", audit_cycle=audit_cycle)
    wp = await mk_working_paper(s, project.id, wi.id)
    await s.flush()
    return project, wi, wp


async def _assign(s, project, wp, program_no, staff):
    """测试捷径：直接把这一行的任务派给某人（委派链路另有专测）。"""
    task = (await resolve_row_tasks(s, project.id, wp.id, SHEET, program_no, create=True)).tasks[0]
    task.assignee_staff_id = staff.id
    task.workflow_status = "assigned"
    await s.flush()
    return task


async def _overrides(s, project_id) -> dict[tuple[str, str], object]:
    rows = (await s.execute(sa.select(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id))).scalars().all()
    return {(r.item_key, r.field): r.value for r in rows}


# ---------------------------------------------------------------------------
# R4：状态覆盖值与细裁对齐
# ---------------------------------------------------------------------------
async def test_console_trim_restore_align_existing_status_override(db):
    s = db
    project, _wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    _user, staff = await _member(s, project)
    await _assign(s, project, wp, 2, staff)
    fo = FieldOverrideService(s)
    await fo.set(project.id, YEAR, SCOPE, "2", "status", "in_progress")
    await fo.set(project.id, YEAR, SCOPE, "2", "execution_summary", "已发函")

    await trim_row(s, project.id, wp.id, SHEET, 2, actor_user_id=actor.id, reason="本期无此业务")
    got = await _overrides(s, project.id)
    assert got[("2", "status")] == "not_applicable", "裁剪后覆盖值里还是「执行中」⇒ 进度统计与恢复后页面都会错"
    assert got[("2", "execution_summary")] == "已发函", "只动状态，不动执行说明"

    back = await restore_row(s, project.id, wp.id, SHEET, "2", actor_user_id=actor.id)
    assert back["requires_reassign"] is True
    assert back["previous_assignees"] == [staff.name], "回执带原执行人，页面据此提示「原执行人已清除，请重新委派」"
    assert (await _overrides(s, project.id))[("2", "status")] == "pending", "恢复后无人执行，不能还显示执行中"


async def test_rows_without_status_override_get_none_created(db):
    s = db
    project, _wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    await FieldOverrideService(s).set(project.id, YEAR, SCOPE, "3", "execution_summary", "只有执行说明")
    await trim_row(s, project.id, wp.id, SHEET, 3, actor_user_id=actor.id, reason="不适用")
    await trim_row(s, project.id, wp.id, SHEET, 4, actor_user_id=actor.id, reason="不适用")
    await restore_row(s, project.id, wp.id, SHEET, 4, actor_user_id=actor.id)
    assert await _overrides(s, project.id) == {("3", "execution_summary"): "只有执行说明"}, (
        "没有状态覆盖值的行不新建（页面状态由任务投影给出，进度统计分母不变）")


async def test_status_override_matched_by_normalized_program_no(db):
    s = db
    project, _wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    await FieldOverrideService(s).set(project.id, YEAR, SCOPE, "05", "status", "completed")
    await trim_row(s, project.id, wp.id, SHEET, 5, actor_user_id=actor.id, reason="不适用")
    assert (await _overrides(s, project.id))[("05", "status")] == "not_applicable"


async def test_project_without_audit_year_is_skipped(db):
    s = db
    project, _wi, wp = await _paper(s, with_year=False)
    actor = await mk_user(s, "admin")
    await FieldOverrideService(s).set(project.id, YEAR, SCOPE, "2", "status", "in_progress")
    await trim_row(s, project.id, wp.id, SHEET, 2, actor_user_id=actor.id, reason="不适用")
    assert (await _overrides(s, project.id))[("2", "status")] == "in_progress", "取不到审计年度就不猜年度去改"


async def test_task_level_endpoints_align_and_report_previous_assignee(db):
    s = db
    project, _wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    _user, staff = await _member(s, project)
    task = await _assign(s, project, wp, 6, staff)
    await FieldOverrideService(s).set(project.id, YEAR, SCOPE, "6", "status", "in_progress")
    svc = ProcedureTrimService(s)
    await svc.set_row_not_applicable(project.id, task.id, actor_user_id=actor.id, reason="不适用")
    assert (await _overrides(s, project.id))[("6", "status")] == "not_applicable"
    out = await svc.restore_row_execute(project.id, task.id, actor_user_id=actor.id)
    assert out["previous_assignee_staff_id"] == str(staff.id)
    assert (await _overrides(s, project.id))[("6", "status")] == "pending"


async def test_scheme_row_entries_align_status_override(db):
    s = db
    project, _wi, wp = await _paper(s)
    actor = await mk_user(s, "admin")
    task = (await resolve_row_tasks(s, project.id, wp.id, SHEET, 7, create=True)).tasks[0]
    await FieldOverrideService(s).set(project.id, YEAR, SCOPE, "7", "status", "completed")
    svc = ProcedureTrimService(s)
    for target, expected in (("not_applicable", "not_applicable"), ("execute", "pending")):
        entries = [{"kind": "row", "template_code": "D2A", "sheet_key": "D2A",
                    "definition_key": task.definition_key, "target_applicability": target}]
        pv = await svc.preview_scheme(project.id, actor_user_id=actor.id, entries=entries)
        res = await svc.apply_scheme(project.id, actor_user_id=actor.id, preview_id=uuid.UUID(pv["preview_id"]),
                                     request_id=f"r4-{target}", entries=entries)
        assert res["applied"] == 1
        assert (await _overrides(s, project.id))[("7", "status")] == expected, f"方案行条目 {target} 后状态未对齐"


# ---------------------------------------------------------------------------
# R6：没有表名的嵌入控制台
# ---------------------------------------------------------------------------
async def test_embedded_console_rows_without_sheet_name(db, side_writes):
    s = db
    project, _wi, wp = await _paper(s, wp_code="A10", audit_cycle="A")
    manager, _ = await _member(s, project, role="manager", assigned=None)
    base = f"/api/projects/{project.id}/procedure-trim/workpapers/{wp.id}/program-rows"
    async with _client(s, _principal(manager)) as c:
        r = await c.post(f"{base}/not-applicable", json={"program_no": 1, "reason": "本期不涉及"})
        assert r.status_code == 200, r.text
        assert (_data(r)["template_code"], _data(r)["changed"]) == ("A10", True), "按底稿编码定位程序表并落任务"
        r = await c.post(f"{base}/restore", json={"program_no": "1"})
        assert r.status_code == 200 and _data(r)["requires_reassign"] is True, r.text
        r = await c.get(f"/api/workpapers/{wp.id}/program-row-access")
        assert r.status_code == 200, r.text
        assert (_data(r)["template_code"], _data(r)["full_power"]) == ("A10", True)


# ---------------------------------------------------------------------------
# R8：覆盖值批量端点
# ---------------------------------------------------------------------------
async def _team(s):
    project, wi, wp = await _paper(s)
    team = types.SimpleNamespace(project=project, wi=wi, wp=wp, admin=await mk_user(s, "admin"))
    team.assignee, team.a_staff = await _member(s, project)
    team.other, team.o_staff = await _member(s, project)
    await _assign(s, project, wp, 2, team.a_staff)
    await _assign(s, project, wp, 4, team.o_staff)
    return team


async def test_field_override_batch_saves_allowed_items_and_reports_the_rest(db, side_writes):
    s = db
    t = await _team(s)
    pid = str(t.project.id)
    url = "/api/workpapers/field-overrides/batch"
    items = [
        {"scope": SCOPE, "item_key": "2", "field": "execution_summary", "value": "已函证"},
        {"scope": SCOPE, "item_key": "4", "field": "execution_summary", "value": "改别人的"},
        {"scope": SCOPE, "item_key": "2", "field": "status", "value": "not_applicable"},
        {"scope": SCOPE, "item_key": "2", "field": "status", "value": "in_progress"},
    ]
    async with _client(s, _principal(t.assignee)) as c:
        r = await c.post(url, json={"project_id": pid, "year": YEAR, "items": items})
        assert r.status_code == 200, r.text
        got = _data(r)
        assert [(x["item_key"], x["field"]) for x in got["saved"]] == [("2", "execution_summary"), ("2", "status")]
        assert [(x["item_key"], x["field"], x["status"]) for x in got["failed"]] == [
            ("4", "execution_summary", 403), ("2", "status", 403)]
        assert all(x["reason"] for x in got["failed"]), "失败项逐条带原因"
    assert await _overrides(s, t.project.id) == {("2", "execution_summary"): "已函证", ("2", "status"): "in_progress"}

    stranger = await mk_user(s)
    async with _client(s, _principal(stranger)) as c:
        r = await c.post(url, json={"project_id": pid, "year": YEAR, "items": items[:1]})
        assert r.status_code == 403, "非项目成员整单拒绝"
        too_many = [{"scope": SCOPE, "item_key": str(i), "field": "execution_summary", "value": "x"} for i in range(201)]
        r = await c.post(url, json={"project_id": pid, "year": YEAR, "items": too_many})
        assert r.status_code == 422, "单次上限 200 项"


# ---------------------------------------------------------------------------
# R19：程序行归属端点显式挂底稿门，且只挂一次
# ---------------------------------------------------------------------------
async def test_program_row_access_route_declares_gate_once():
    from app.main import app
    from app.routers import wp_program_row_access
    from app.routers._wp_gate import dedicated_wp_gate

    assert any(getattr(d, "dependency", None) is dedicated_wp_gate for d in wp_program_row_access.router.dependencies), (
        "门禁写在路由上，不依赖注册表按路径注入")
    routes = [r for r in app.routes if getattr(r, "path", "") == "/api/workpapers/{wp_id}/program-row-access"]
    assert len(routes) == 1
    gates = [d for d in routes[0].dependencies if getattr(d, "dependency", None) is dedicated_wp_gate]
    assert len(gates) == 1, "注册表见到路由自带底稿门就不再挂（否则判两次、拒绝记两条）"


async def test_row_access_denial_recorded_once(db, side_writes):
    s = db
    project, _wi, wp = await _paper(s)
    outsider = await mk_user(s)
    await mk_project_user(s, project.id, outsider.id, scope_cycles="")
    async with _client(s, _principal(outsider)) as c:
        r = await c.get(f"/api/workpapers/{wp.id}/program-row-access", params={"sheet_name": SHEET})
    assert r.status_code == 404
    assert len(side_writes["denials"]) == 1, side_writes["denials"]
