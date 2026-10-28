# -*- coding: utf-8 -*-
"""程序表执行人填的状态 / 执行说明刷新后仍在（spec audit-year-calendar-fallback-ratchet R0 / 任务 0.1）。

真实 PostgreSQL，外层事务（``create_savepoint``，路由里的 commit 只动保存点），用例结束回滚。

根因：前端写字段覆盖用「路由年度 → 今年」与「传入的 sheetName」，读取方（render-config ``a-program-console`` 生成分支）
按项目审计年度与表码读 ⇒ 写进去的读不到。修法：render 结果回传 ``override_scope``，前端按它与项目审计年度写。
本用例走一遍真实链路：取渲染结果 → 执行人经真实接口按回传 scope + 项目审计年度写 → 再渲染能看到；
旧写法（今年 / 表名当 scope）写的仍然读不到（钉住两个根因）。
"""
from __future__ import annotations

import copy
import types

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel
from app.routers.wp_render_strategies import _a_program
from app.services.field_override_service import FieldOverrideService
from app.services.procedure_row_trim_service import resolve_row_tasks
from app.services.project_audit_year import PROJECT_AUDIT_YEAR_BIZ_SQL

from ._factories import IS_PG, mk_assignment, mk_project, mk_project_user, mk_staff, mk_user
from ._factories import mk_working_paper, mk_wp_index

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")]

SHEET = "应收账款实质性程序表D2A"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
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


@pytest.fixture(autouse=True)
def _no_side_writes(monkeypatch):
    """操作日志走独立事务，会在真库留下引用回滚数据的行 ⇒ 换成内存记录。"""
    from app.middleware import audit_log

    async def _log(**_kw):
        return None

    monkeypatch.setattr(audit_log, "_write_log", _log)


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
    return types.SimpleNamespace(id=user.id, role=user.role, username=user.username, email=user.email,
                                 is_active=True, is_deleted=False)


async def _render(s, project, wp, year, sheet_html_data=None):
    ctx = types.SimpleNamespace(
        db=s, project_id=project.id, wp_id=wp.id, working_paper=wp, wp_code="D2", year=year, business_category="C",
        classification=types.SimpleNamespace(sheet_name=SHEET), sheet_html_data=sheet_html_data,
        template_file_path=None, source_files=[],
    )
    return await _a_program.render(ctx)


def _rows(out) -> dict:
    return {str(p["program_no"]): p for p in out["programs"]}


async def test_executor_edits_survive_reload_when_written_at_returned_scope_and_project_year(db):
    s = db
    project = await mk_project(s)
    project.audit_year = 2025
    wi = await mk_wp_index(s, project.id, wp_code="D2", wp_name="应收账款", audit_cycle="D")
    wp = await mk_working_paper(s, project.id, wi.id)
    executor = await mk_user(s)
    staff = await mk_staff(s, user_id=executor.id)
    assignment = await mk_assignment(s, project.id, staff.id, role="auditor")
    assignment.assigned_cycles = ["D"]
    (await mk_project_user(s, project.id, executor.id)).permission_level = PermissionLevel.edit
    task = (await resolve_row_tasks(s, project.id, wp.id, SHEET, 2, create=True)).tasks[0]
    task.assignee_staff_id, task.workflow_status = staff.id, "assigned"
    await s.flush()
    # 读取方的年度（render-config 同一条 SQL）
    reader_year = (await s.execute(PROJECT_AUDIT_YEAR_BIZ_SQL, {"pid": str(project.id)})).first()[0]

    first = await _render(s, project, wp, reader_year)
    assert first["override_scope"] == "procedure_table:D2A", "回传的就是生成分支读覆盖的 scope（表码，不是表名）"
    before = _rows(first)
    assert {"2", "3", "4"} <= before.keys() and before["2"]["status"] == "pending"

    async with _client(s, _principal(executor)) as c:
        # 前端的单一来源：项目详情接口的审计年度（与读取方同一年度）
        r = await c.get(f"/api/projects/{project.id}")
        assert r.status_code == 200, r.text
        year = _data(r)["audit_year"]
        assert year == reader_year == 2025
        for field, value in (("status", "in_progress"), ("execution_summary", "已核对函证回函")):
            r = await c.post("/api/workpapers/field-overrides", json={
                "project_id": str(project.id), "year": year, "scope": first["override_scope"],
                "item_key": "2", "field": field, "value": value,
            })
            assert r.status_code == 200, r.text

    # 旧写法：今年（2026）/ 表名当 scope —— 读取方读不到，这就是「刷新后看不到」
    svc = FieldOverrideService(s)
    await svc.set(project_id=project.id, year=2026, scope="procedure_table:D2A", item_key="3",
                  field="status", value="completed", user_id=executor.id)
    await svc.set(project_id=project.id, year=2025, scope=f"procedure_table:{SHEET}", item_key="4",
                  field="status", value="completed", user_id=executor.id)
    await s.flush()

    after = _rows(await _render(s, project, wp, reader_year))
    assert (after["2"]["status"], after["2"]["execution_summary"]) == ("in_progress", "已核对函证回函")
    assert after["3"]["status"] == "pending", "年度写错 ⇒ 读不到"
    assert after["4"]["status"] == "pending", "scope 用表名 ⇒ 读不到"


async def test_persisted_sheet_also_returns_override_scope_on_a_copy(db):
    s = db
    project = await mk_project(s)
    wi = await mk_wp_index(s, project.id, wp_code="D2", wp_name="应收账款", audit_cycle="D")
    wp = await mk_working_paper(s, project.id, wi.id)
    page = {"programs": [{"id": "row-1", "program_no": 1, "program_desc": "检查", "status": "completed"}]}
    stored = copy.deepcopy(page)
    out = await _render(s, project, wp, 2025, sheet_html_data=stored)
    assert out is not stored and out["programs"] == page["programs"]
    assert out["override_scope"] == "procedure_table:D2A"
    assert stored == page, "只改本次响应的副本，不回写已存数据"
