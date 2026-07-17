# Feature: procedure-delegation-visibility-isolation — Task 9 EntryIntegration（C10）续
"""Task 9 续接：html / status_transition / version snapshot·compare·search·list /
trial-balance writeback / procedure row task detail·conversation 路由接入 Wp_Bound_Gate 的
真实 app + PostgreSQL 集成测试。

Task 9 / Requirements 5.8–5.18, 7.5, 8.5, 8.10–8.12, 8.15, 9, 12.7–12.9。

覆盖本轮新接入 gate 的核心路由（每路由 allow / deny / cross-project 维度）：
  - GET  /api/projects/{pid}/workpapers/{wp_id}/html                     （html / read_html）
  - PUT  /api/projects/{pid}/working-papers/{wp_id}/status               （status / status_transition）
  - POST /api/projects/{pid}/workpapers/{wp_id}/versions                 （snapshot / version_snapshot）
  - POST /api/projects/{pid}/workpapers/{wp_id}/versions/compare         （snapshot / read_versions）
  - GET  /api/working-papers/{wp_id}/versions/search                     （version / read_versions）
  - GET  /api/workpapers/{wp_id}/versions                               （version / read_versions）
  - POST /api/s-estimate/{wp_id}/tb-writeback                            （save / tb_writeback）
  - GET  /api/projects/{pid}/procedure-row-tasks/{task_id}               （procedure_task / read_task）
  - GET  /api/projects/{pid}/procedure-row-tasks/{task_id}/conversation  （procedure_task / read_task）

真实 FastAPI app（app.main:app）+ 真实 PostgreSQL（audit_platform），每用例独立引擎/连接，
外层事务 + savepoint 隔离，用例结束整体回滚（绝不污染 dev 库）。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.deps import get_current_user
from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL

from ._factories import (
    IS_PG,
    mk_project,
    mk_project_user,
    mk_row_task,
    mk_staff,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (real app gate integration)"),
]


def _detail(resp) -> str | None:
    body = resp.json()
    if not isinstance(body, dict):
        return None
    return body.get("detail") or body.get("message")


class _Ctx:
    """每用例独立 PG 连接 + savepoint 隔离 + app 依赖覆盖。"""

    def __init__(self) -> None:
        self.engine = None
        self.conn = None
        self.trans = None
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        self.engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
        self.conn = await self.engine.connect()
        self.trans = await self.conn.begin()
        self.session = AsyncSession(
            bind=self.conn, join_transaction_mode="create_savepoint"
        )
        return self.session

    async def __aexit__(self, *exc) -> None:
        from app.main import app

        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        if self.session is not None:
            await self.session.close()
        if self.trans is not None:
            await self.trans.rollback()
        if self.conn is not None:
            await self.conn.close()
        if self.engine is not None:
            await self.engine.dispose()

    def bind_app(self, user):
        from app.main import app

        session = self.session

        async def _override_db():
            yield session

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_lead(s, *, scope="D", cycle="D"):
    proj = await mk_project(s)
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle=cycle)
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = user.id
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    await s.flush()
    return proj, user, wi, wp


async def _seed_outsider(s, proj):
    outsider = await mk_user(s)
    await mk_project_user(s, proj.id, outsider.id, scope_cycles="")
    await s.flush()
    return outsider


async def _mk_admin(s):
    admin = await mk_user(s, role="admin")
    await s.flush()
    return admin


# ---------------------------------------------------------------------------
# html  GET /api/projects/{pid}/workpapers/{wp_id}/html
# ---------------------------------------------------------------------------
async def test_html_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(f"/api/projects/{proj.id}/workpapers/{wp.id}/html")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_html_allow_lead_passes_gate():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/projects/{proj.id}/workpapers/{wp.id}/html")
        # gate 放行；合成底稿无可预览数据 → 下游 404/500，但绝不是 gate 的统一 404。
        if r.status_code == 404:
            assert _detail(r) != EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_html_cross_project_denied():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        other = await mk_project(s)
        wi2 = await mk_wp_index(s, other.id, wp_code="D2-1", audit_cycle="D")
        wp2 = await mk_working_paper(s, other.id, wi2.id)
        await s.flush()
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/projects/{other.id}/workpapers/{wp2.id}/html")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# status transition  PUT /api/projects/{pid}/working-papers/{wp_id}/status
# ---------------------------------------------------------------------------
async def test_status_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.put(
                f"/api/projects/{proj.id}/working-papers/{wp.id}/status",
                json={"status": "edit_complete"},
            )
        # require_project_access('edit') 或 gate 均阻断；绝不 200。
        assert r.status_code != 200
    finally:
        await ctx.__aexit__()


async def test_status_allow_admin_real_transition():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj = await mk_project(s)
        admin = await _mk_admin(s)
        wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
        wp = await mk_working_paper(s, proj.id, wi.id)  # status 默认 draft
        await s.flush()
        async with ctx.bind_app(admin) as c:
            r = await c.put(
                f"/api/projects/{proj.id}/working-papers/{wp.id}/status",
                json={"status": "edit_complete"},  # draft→edit_complete 合法迁移
            )
        # admin 过 gate（status_transition 真实 WpFileStatus 迁移已登记）+ 服务合法迁移 → 非 gate 404。
        assert not (r.status_code == 404 and _detail(r) == EXTERNAL_NOT_FOUND_DETAIL)
    finally:
        await ctx.__aexit__()


async def test_status_deny_admin_nonexistent_wp():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj = await mk_project(s)
        admin = await _mk_admin(s)
        await s.flush()
        async with ctx.bind_app(admin) as c:
            r = await c.put(
                f"/api/projects/{proj.id}/working-papers/{uuid4()}/status",
                json={"status": "edit_complete"},
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# version snapshot create  POST /api/projects/{pid}/workpapers/{wp_id}/versions
# ---------------------------------------------------------------------------
async def test_version_create_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.post(
                f"/api/projects/{proj.id}/workpapers/{wp.id}/versions",
                json={"snapshot_type": "manual", "description": "x"},
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_version_create_allow_lead_passes_gate():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.post(
                f"/api/projects/{proj.id}/workpapers/{wp.id}/versions",
                json={"snapshot_type": "manual", "description": "x"},
            )
        # lead 过 gate（version_snapshot 登记）；下游快照服务可能异常，但绝不是 gate 404。
        if r.status_code == 404:
            assert _detail(r) != EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# version compare  POST /api/projects/{pid}/workpapers/{wp_id}/versions/compare
# ---------------------------------------------------------------------------
async def test_version_compare_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.post(
                f"/api/projects/{proj.id}/workpapers/{wp.id}/versions/compare",
                json={"version_a_id": str(uuid4()), "version_b_id": str(uuid4())},
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# version search  GET /api/working-papers/{wp_id}/versions/search
# ---------------------------------------------------------------------------
async def test_version_search_allow_lead():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/working-papers/{wp.id}/versions/search?q=x")
        assert r.status_code == 200
    finally:
        await ctx.__aexit__()


async def test_version_search_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(f"/api/working-papers/{wp.id}/versions/search?q=x")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_version_search_nonexistent_404():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/working-papers/{uuid4()}/versions/search?q=x")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# wp_storage versions  GET /api/workpapers/{wp_id}/versions
# ---------------------------------------------------------------------------
async def test_storage_versions_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(f"/api/workpapers/{wp.id}/versions")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_storage_versions_allow_lead_passes_gate():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, lead, wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/workpapers/{wp.id}/versions")
        if r.status_code == 404:
            assert _detail(r) != EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# trial-balance writeback  POST /api/s-estimate/{wp_id}/tb-writeback
# ---------------------------------------------------------------------------
async def test_tb_writeback_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.post(
                f"/api/s-estimate/{wp.id}/tb-writeback",
                json={"account_code": "1234", "audited_amount": "100", "component_type": "s-estimate"},
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_tb_writeback_deny_admin_nonexistent_wp():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        await mk_project(s)
        admin = await _mk_admin(s)
        await s.flush()
        async with ctx.bind_app(admin) as c:
            r = await c.post(
                f"/api/s-estimate/{uuid4()}/tb-writeback",
                json={"account_code": "1234", "audited_amount": "100", "component_type": "s-estimate"},
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# procedure row task detail  GET /api/projects/{pid}/procedure-row-tasks/{task_id}
# ---------------------------------------------------------------------------
async def _seed_assignee_task(s, *, scope="D"):
    proj = await mk_project(s)
    user = await mk_user(s)
    staff = await mk_staff(s, user_id=user.id)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
    wp = await mk_working_paper(s, proj.id, wi.id)
    task = await mk_row_task(
        s, proj.id, wi.id, sheet_key="D2A", sheet_name="甲", wp_id=wp.id,
        assignee_staff_id=staff.id,
    )
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    await s.flush()
    return proj, user, wi, wp, task


async def test_procedure_detail_allow_assignee():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, user, wi, wp, task = await _seed_assignee_task(s)
        async with ctx.bind_app(user) as c:
            r = await c.get(f"/api/projects/{proj.id}/procedure-row-tasks/{task.id}")
        # 参与者（assignee）过 gate（read_task）+ 原生参与授权 → 200。
        assert r.status_code == 200
    finally:
        await ctx.__aexit__()


async def test_procedure_detail_deny_outsider():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _user, wi, wp, task = await _seed_assignee_task(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(f"/api/projects/{proj.id}/procedure-row-tasks/{task.id}")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_procedure_detail_cross_project_denied():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, user, wi, wp, task = await _seed_assignee_task(s)
        other = await mk_project(s)
        await s.flush()
        async with ctx.bind_app(user) as c:
            # 声明另一项目 → task→project 绑定不一致，统一 404
            r = await c.get(f"/api/projects/{other.id}/procedure-row-tasks/{task.id}")
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


# ---------------------------------------------------------------------------
# procedure conversation  GET /api/projects/{pid}/procedure-row-tasks/{task_id}/conversation
# ---------------------------------------------------------------------------
async def test_procedure_conversation_deny_outsider():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _user, wi, wp, task = await _seed_assignee_task(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(
                f"/api/projects/{proj.id}/procedure-row-tasks/{task.id}/conversation"
            )
        assert r.status_code == 404
        assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()


async def test_procedure_conversation_allow_assignee_passes_gate():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, user, wi, wp, task = await _seed_assignee_task(s)
        async with ctx.bind_app(user) as c:
            r = await c.get(
                f"/api/projects/{proj.id}/procedure-row-tasks/{task.id}/conversation"
            )
        # assignee 过 gate（read_task 可见性前置）；细粒度对话授权由原生逻辑处理，绝不是 gate 404。
        if r.status_code == 404:
            assert _detail(r) != EXTERNAL_NOT_FOUND_DETAIL
    finally:
        await ctx.__aexit__()
