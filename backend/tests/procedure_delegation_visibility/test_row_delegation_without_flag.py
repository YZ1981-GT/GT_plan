# -*- coding: utf-8 -*-
"""程序行定义导入与逐行委派（spec procedure-chain-followup-closure R2 / 任务 2.1~2.4）。

真实 PostgreSQL，外层事务（``create_savepoint``，路由 commit 只动保存点），用例结束回滚。

- 委派预览先按当前模板版本导入定义（原先只有裁剪某一行时才写定义 ⇒ 新项目恒 0 个目标），物化只用当前版本
  （库里同模板码的旧定义不混进来），并把行任务绑到已生成的底稿（原先物化出的任务 wp_id 为空）；目标为 0 时说明原因。
- 控制台逐行委派：程序行任务开关关闭时也能按需建这一行的任务（只给委派人；自加的行 422、已裁剪 409），
  之后走既有的按任务委派预览 → 应用。
- 物化端点原先只要求登录：现只给委派人。
"""
from __future__ import annotations

import types
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel
from app.models.procedure_models import ProcedureRowDefinition, ProcedureRowTask
from app.services.procedure_delegation_service import ProcedureDelegationService
from app.services.procedure_row_definitions import current_definitions, ensure_current_definitions
from app.services.procedure_row_trim_service import trim_row

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
def _side_writes(monkeypatch):
    """操作日志 / 拒绝审计走独立事务，会在真库留下引用回滚数据的行 ⇒ 换成空操作。"""
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


def _data(resp):
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) else body


async def _member(s, project, *, role="auditor", assigned=("D",)):
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    a = await mk_assignment(s, project.id, staff.id, role=role)
    a.assigned_cycles = list(assigned) if assigned else None
    pu = await mk_project_user(s, project.id, user.id, scope_cycles=",".join(assigned) if assigned else None)
    pu.permission_level = PermissionLevel.edit
    await s.flush()
    return user, staff


async def _tasks(s, project_id) -> list[ProcedureRowTask]:
    return list((await s.execute(sa.select(ProcedureRowTask).where(
        ProcedureRowTask.project_id == project_id, ProcedureRowTask.is_deleted == sa.false(),
    ))).scalars().all())


# ---------------------------------------------------------------------------
# 定义导入
# ---------------------------------------------------------------------------
async def test_ensure_current_definitions_is_idempotent_and_keyed_by_current_template(db):
    current = {d["definition_key"] for d in current_definitions("D2A")}
    assert current, "D2A 模板应有程序行"
    _created, keys = await ensure_current_definitions(db, ["D2", "NO-SUCH-WP"])
    assert keys["D2"] == frozenset(current)
    assert keys["NO-SUCH-WP"] == frozenset(), "没有程序表模板的底稿：空集合"
    stored = set((await db.execute(sa.select(ProcedureRowDefinition.definition_key).where(
        ProcedureRowDefinition.definition_key.in_(sorted(current))))).scalars().all())
    assert stored == current
    again, _ = await ensure_current_definitions(db, ["D2"])
    assert again == 0, "已有的定义不重复写"


# ---------------------------------------------------------------------------
# 委派预览：导入 + 只用当前版本 + 绑定底稿 + 0 目标原因
# ---------------------------------------------------------------------------
async def test_preview_imports_current_definitions_binds_paper_and_skips_old_revisions(db):
    project = await mk_project(db)
    manager, _ = await _member(db, project, role="manager", assigned=None)
    _auditor, staff = await _member(db, project)
    wi = await mk_wp_index(db, project.id, wp_code="D2", wp_name="应收账款", audit_cycle="D")
    wp = await mk_working_paper(db, project.id, wi.id)
    # 库里同模板码的旧版本定义（不是当前模板里的行）：不得被物化
    stale_key = f"stale-{uuid.uuid4().hex}"
    db.add(ProcedureRowDefinition(
        definition_key=stale_key, template_code="D2A", template_revision_hash="old-rev", sheet_key="D2A",
        source_locator={"kind": "test"}, program_no="99", procedure_text="旧版本的程序", ref_snapshot=[],
        legacy_aliases=[], normalized_content={},
    ))
    await db.flush()

    out = await ProcedureDelegationService(db).preview(
        project.id, actor_user_id=manager.id,
        selector={"kind": "workpaper", "wp_index_ids": [str(wi.id)]}, assignee_staff_id=staff.id,
    )
    current = {d["definition_key"] for d in current_definitions("D2A")}
    tasks = await _tasks(db, project.id)
    assert {t.definition_key for t in tasks} == current, "只物化当前模板版本"
    assert stale_key not in {t.definition_key for t in tasks}
    assert all(t.wp_id == wp.id for t in tasks), "物化出的行任务绑到已生成的底稿"
    assert out["summary"]["targets"] == len(current) and out["hint"] is None
    prep = out["materialization"]
    assert (prep["tasks_created"], prep["tasks_bound"], prep["with_program_table"], prep["error"]) == \
        (len(current), len(current), 1, None)

    again = await ProcedureDelegationService(db).preview(
        project.id, actor_user_id=manager.id,
        selector={"kind": "workpaper", "wp_index_ids": [str(wi.id)]}, assignee_staff_id=staff.id,
    )
    assert (again["materialization"]["tasks_created"], again["materialization"]["tasks_bound"]) == (0, 0)
    assert len(await _tasks(db, project.id)) == len(current)


async def test_preview_without_program_table_explains_zero_targets(db):
    project = await mk_project(db)
    manager, _ = await _member(db, project, role="manager", assigned=None)
    _auditor, staff = await _member(db, project)
    wi = await mk_wp_index(db, project.id, wp_code="ZZ9", wp_name="没有程序表的底稿", audit_cycle="D")
    out = await ProcedureDelegationService(db).preview(
        project.id, actor_user_id=manager.id,
        selector={"kind": "workpaper", "wp_index_ids": [str(wi.id)]}, assignee_staff_id=staff.id,
    )
    assert out["summary"]["targets"] == 0
    assert out["hint"] == "所选底稿没有程序表模板（不在程序表库里），无法按程序行委派"


# ---------------------------------------------------------------------------
# 逐行委派（开关关闭也可用）
# ---------------------------------------------------------------------------
async def test_row_task_endpoint_then_delegate_the_row(db):
    project = await mk_project(db)
    manager, _ = await _member(db, project, role="manager", assigned=None)
    auditor, staff = await _member(db, project)
    wi = await mk_wp_index(db, project.id, wp_code="D2", wp_name="应收账款", audit_cycle="D")
    wp = await mk_working_paper(db, project.id, wi.id)
    # 路由里的 rollback（422 那次）会让会话里的 ORM 对象过期 ⇒ 先取出要用的 id
    pid, wp_id, manager_id, staff_id = project.id, wp.id, manager.id, staff.id
    url = f"/api/projects/{pid}/procedure-trim/workpapers/{wp_id}/program-rows/task"

    async with _client(db, _principal(auditor)) as c:
        assert (await c.post(url, json={"sheet_name": SHEET, "program_no": 2})).status_code == 403
    async with _client(db, _principal(manager)) as c:
        first = await c.post(url, json={"sheet_name": SHEET, "program_no": 2})
        assert first.status_code == 200, first.text
        ref = _data(first)
        assert ref["created"] is True and ref["template_code"] == "D2A" and len(ref["task_ids"]) == 1
        again = _data(await c.post(url, json={"sheet_name": SHEET, "program_no": "2"}))
        assert (again["created"], again["task_ids"]) == (False, ref["task_ids"]), "同一行不重复建任务"
        custom = await c.post(url, json={"sheet_name": SHEET, "program_no": 999})
        assert custom.status_code == 422 and "不能单独委派" in custom.text
    task = (await _tasks(db, pid))[0]
    assert (task.wp_id, task.program_no) == (wp_id, "2"), "按需建的任务绑定本底稿"

    svc = ProcedureDelegationService(db)
    selector = {"kind": "row", "task_ids": ref["task_ids"]}
    pv = await svc.preview(pid, actor_user_id=manager_id, selector=selector, assignee_staff_id=staff_id)
    assert pv["summary"]["targets"] == 1
    await svc.apply(pid, actor_user_id=manager_id, preview_id=uuid.UUID(pv["preview_id"]),
                    request_id=f"rowdel-{uuid.uuid4().hex[:8]}", selector=selector, assignee_staff_id=staff_id)
    await db.refresh(task)
    assert (task.assignee_staff_id, task.workflow_status) == (staff_id, "assigned")


async def test_row_task_endpoint_rejects_trimmed_row(db):
    project = await mk_project(db)
    manager, _ = await _member(db, project, role="manager", assigned=None)
    wi = await mk_wp_index(db, project.id, wp_code="D2", wp_name="应收账款", audit_cycle="D")
    wp = await mk_working_paper(db, project.id, wi.id)
    await trim_row(db, project.id, wp.id, SHEET, 3, actor_user_id=manager.id, reason="本期无此业务")
    async with _client(db, _principal(manager)) as c:
        r = await c.post(f"/api/projects/{project.id}/procedure-trim/workpapers/{wp.id}/program-rows/task",
                         json={"sheet_name": SHEET, "program_no": 3})
    assert r.status_code == 409 and "恢复执行后才能委派" in r.text


async def test_materialize_endpoints_are_delegator_only(db):
    project = await mk_project(db)
    manager, _ = await _member(db, project, role="manager", assigned=None)
    auditor, _ = await _member(db, project)
    wi = await mk_wp_index(db, project.id, wp_code="D2", wp_name="应收账款", audit_cycle="D")
    body = {"wp_index_ids": [str(wi.id)]}
    for path in ("materialize", "materialize-jobs"):
        url = f"/api/projects/{project.id}/procedure-row-tasks/{path}"
        async with _client(db, _principal(auditor)) as c:
            assert (await c.post(url, json=body)).status_code == 403, path
        async with _client(db, _principal(manager)) as c:
            assert (await c.post(url, json=body)).status_code == 200, path
