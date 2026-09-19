# Feature: procedure-delegation-visibility-isolation — Task 9 EntryIntegration（C10）DEDICATED-SUB-ROUTE
"""专属组件 /{wp_id}/... 子路由经 router-level ``dedicated_wp_gate`` 依赖接入 Wp_Bound_Gate 的
真实 app + PostgreSQL 集成测试。

Task 9 / Requirements 5.8–5.18, 7.5, 8.5, 8.10–8.12, 8.15, 9, 12.7–12.9。

本测试证明「单一 router-level 依赖」这一 **共享机制** 在多个专属科目组件模块上一致工作，且
**未破坏合法 lead/admin 访问**（allow）、**阻断未委派/跨项目/不存在**（deny → 统一 404）。
按 family/method 抽样（不逐一穷举 469 路由）：
  - GET  detail   ：/api/l2-interest-payable/{wp_id}/accrual-check
  - GET  export   ：/api/l2-interest-payable/{wp_id}/export-data
  - POST save     ：/api/m1-dividends-payable/{wp_id}/validate-formulas
  - GET  detail   ：/api/m1-dividends-payable/{wp_id}/dividend-calculation
  - POST ai       ：/api/n2-taxes-payable/{wp_id}/contract-ocr
  - POST ai(渲染) ：/api/workpapers/{wp_id}/k1/ai-generate
  - POST 引擎     ：/api/projects/{pid}/workpapers/{wp_id}/h1/depreciation-calc

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
        self.session = AsyncSession(bind=self.conn, join_transaction_mode="create_savepoint")
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
        # raise_app_exceptions=False：部分被抽样的专属组件下游 handler 存在既有 bug（例如以
        # 复数表名 ``working_papers`` 查询）会抛异常。gate 是本测试关注点——放行后下游崩溃应表现为
        # 500 响应而非把异常抛回测试，从而 allow 用例可专注断言"非 gate 的统一 404"。
        # gate 自身的 ExternalNotFound/RateLimited 是 HTTPException，仍正常返回 404/429，不受影响。
        return AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        )


async def _seed_lead(s, *, scope="D", cycle="D", wp_code="D2-1"):
    proj = await mk_project(s)
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code=wp_code, audit_cycle=cycle)
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
# 通用断言：deny 用例必须是 gate 的统一 404；allow 用例绝不是 gate 的统一 404。
# ---------------------------------------------------------------------------
def _assert_gate_denied(r):
    assert r.status_code == 404
    assert _detail(r) == EXTERNAL_NOT_FOUND_DETAIL


def _assert_not_gate_denied(r):
    # gate 放行；下游业务可能因合成底稿数据 / AI 未启用返回 404/422/500/503，但绝不是 gate 的统一 404。
    if r.status_code == 404:
        assert _detail(r) != EXTERNAL_NOT_FOUND_DETAIL


# ═══════════════════════════════════════════════════════════════════════════
# l2-interest-payable：accrual-check (GET detail) / export-data (GET export)
# ═══════════════════════════════════════════════════════════════════════════
async def test_l2_accrual_check_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, _wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(f"/api/l2-interest-payable/{wp.id}/accrual-check")
        _assert_gate_denied(r)
    finally:
        await ctx.__aexit__()


async def test_l2_accrual_check_allow_lead():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        _proj, lead, _wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/l2-interest-payable/{wp.id}/accrual-check")
        _assert_not_gate_denied(r)
    finally:
        await ctx.__aexit__()


async def test_l2_accrual_check_nonexistent_404():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        _proj, lead, _wi, _wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/l2-interest-payable/{uuid4()}/accrual-check")
        _assert_gate_denied(r)
    finally:
        await ctx.__aexit__()


async def test_l2_export_data_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, _wi, wp = await _seed_lead(s)
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(f"/api/l2-interest-payable/{wp.id}/export-data")
        _assert_gate_denied(r)
    finally:
        await ctx.__aexit__()


async def test_l2_export_data_allow_lead():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        _proj, lead, _wi, wp = await _seed_lead(s)
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/l2-interest-payable/{wp.id}/export-data")
        _assert_not_gate_denied(r)
    finally:
        await ctx.__aexit__()


# ═══════════════════════════════════════════════════════════════════════════
# m1-dividends-payable：validate-formulas (POST save) / dividend-calculation (GET detail)
# ═══════════════════════════════════════════════════════════════════════════
async def test_m1_validate_formulas_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, _wi, wp = await _seed_lead(s, scope="M", cycle="M", wp_code="M1-1")
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.post(f"/api/m1-dividends-payable/{wp.id}/validate-formulas", json={})
        _assert_gate_denied(r)
    finally:
        await ctx.__aexit__()


async def test_m1_validate_formulas_allow_admin():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj = await mk_project(s)
        admin = await _mk_admin(s)
        wi = await mk_wp_index(s, proj.id, wp_code="M1-1", audit_cycle="M")
        wp = await mk_working_paper(s, proj.id, wi.id)
        await s.flush()
        async with ctx.bind_app(admin) as c:
            r = await c.post(f"/api/m1-dividends-payable/{wp.id}/validate-formulas", json={})
        _assert_not_gate_denied(r)
    finally:
        await ctx.__aexit__()


async def test_m1_validate_formulas_nonexistent_404():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj = await mk_project(s)
        admin = await _mk_admin(s)
        await s.flush()
        async with ctx.bind_app(admin) as c:
            r = await c.post(f"/api/m1-dividends-payable/{uuid4()}/validate-formulas", json={})
        _assert_gate_denied(r)
    finally:
        await ctx.__aexit__()


async def test_m1_dividend_calculation_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, _wi, wp = await _seed_lead(s, scope="M", cycle="M", wp_code="M1-1")
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.get(f"/api/m1-dividends-payable/{wp.id}/dividend-calculation")
        _assert_gate_denied(r)
    finally:
        await ctx.__aexit__()


async def test_m1_dividend_calculation_allow_lead():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        _proj, lead, _wi, wp = await _seed_lead(s, scope="M", cycle="M", wp_code="M1-1")
        async with ctx.bind_app(lead) as c:
            r = await c.get(f"/api/m1-dividends-payable/{wp.id}/dividend-calculation")
        _assert_not_gate_denied(r)
    finally:
        await ctx.__aexit__()


# ═══════════════════════════════════════════════════════════════════════════
# n2-taxes-payable：contract-ocr (POST ai)
# ═══════════════════════════════════════════════════════════════════════════
async def test_n2_contract_ocr_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, _wi, wp = await _seed_lead(s, scope="N", cycle="N", wp_code="N2-1")
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.post(f"/api/n2-taxes-payable/{wp.id}/contract-ocr", json={})
        _assert_gate_denied(r)
    finally:
        await ctx.__aexit__()


async def test_n2_contract_ocr_nonexistent_404():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj = await mk_project(s)
        admin = await _mk_admin(s)
        await s.flush()
        async with ctx.bind_app(admin) as c:
            r = await c.post(f"/api/n2-taxes-payable/{uuid4()}/contract-ocr", json={})
        _assert_gate_denied(r)
    finally:
        await ctx.__aexit__()


# ═══════════════════════════════════════════════════════════════════════════
# 渲染策略 AI 路由：/api/workpapers/{wp_id}/k1/ai-generate (POST ai)
# ═══════════════════════════════════════════════════════════════════════════
async def test_k1_ai_generate_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, _wi, wp = await _seed_lead(s, scope="K", cycle="K", wp_code="K1-1")
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.post(f"/api/workpapers/{wp.id}/k1/ai-generate", json={})
        _assert_gate_denied(r)
    finally:
        await ctx.__aexit__()


async def test_k1_ai_generate_allow_lead():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        _proj, lead, _wi, wp = await _seed_lead(s, scope="K", cycle="K", wp_code="K1-1")
        async with ctx.bind_app(lead) as c:
            r = await c.post(f"/api/workpapers/{wp.id}/k1/ai-generate", json={})
        _assert_not_gate_denied(r)
    finally:
        await ctx.__aexit__()


# ═══════════════════════════════════════════════════════════════════════════
# 引擎路由：/api/projects/{pid}/workpapers/{wp_id}/h1/depreciation-calc (POST)
# ═══════════════════════════════════════════════════════════════════════════
async def test_h1_depreciation_calc_deny_not_delegated():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj, _lead, _wi, wp = await _seed_lead(s, scope="H", cycle="H", wp_code="H1-1")
        outsider = await _seed_outsider(s, proj)
        async with ctx.bind_app(outsider) as c:
            r = await c.post(
                f"/api/projects/{proj.id}/workpapers/{wp.id}/h1/depreciation-calc", json={}
            )
        # 既有 require_project_access('edit') 或 gate 均阻断；绝不 200。
        assert r.status_code != 200
    finally:
        await ctx.__aexit__()


async def test_h1_depreciation_calc_deny_admin_nonexistent_wp():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    try:
        proj = await mk_project(s)
        admin = await _mk_admin(s)
        await s.flush()
        async with ctx.bind_app(admin) as c:
            r = await c.post(
                f"/api/projects/{proj.id}/workpapers/{uuid4()}/h1/depreciation-calc", json={}
            )
        _assert_gate_denied(r)
    finally:
        await ctx.__aexit__()


# ═══════════════════════════════════════════════════════════════════════════
# 机制自证：dedicated_wp_gate 分类 + 全量应用（无 DB）
# ═══════════════════════════════════════════════════════════════════════════
def test_dedicated_classifier_by_method():
    from app.routers._wp_gate import _classify_dedicated

    assert _classify_dedicated("GET") == ("workpaper.dedicated_subroute", "dedicated_read")
    assert _classify_dedicated("HEAD") == ("workpaper.dedicated_subroute", "dedicated_read")
    assert _classify_dedicated("POST") == ("workpaper.dedicated_subroute", "dedicated_write")
    assert _classify_dedicated("PUT") == ("workpaper.dedicated_subroute", "dedicated_write")
    assert _classify_dedicated("PATCH") == ("workpaper.dedicated_subroute", "dedicated_write")
    assert _classify_dedicated("DELETE") == ("workpaper.dedicated_subroute", "dedicated_delete")


def test_all_dedicated_routes_have_gate_dependency():
    """全部专属组件模块路由都挂上了 dedicated_wp_gate（机制覆盖完整，无遗漏）。"""
    from app.main import app
    from app.security.dedicated_component_routers import DEDICATED_COMPONENT_ROUTER_MODULES

    total = 0
    gated = 0
    for route in app.routes:
        ep = getattr(route, "endpoint", None)
        if ep is None:
            continue
        if getattr(ep, "__module__", None) in DEDICATED_COMPONENT_ROUTER_MODULES:
            total += 1
            deps = getattr(route, "dependencies", []) or []
            names = [getattr(getattr(d, "dependency", None), "__name__", "") for d in deps]
            if "dedicated_wp_gate" in names:
                gated += 1
    assert total > 400, f"expected the dedicated surface, got {total}"
    assert gated == total, f"{total - gated} dedicated routes missing the gate dependency"
