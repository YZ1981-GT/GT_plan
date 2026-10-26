"""写 stale 的端点项目鉴权（spec acnr-foundation-defect-closure D8 / 需求 10）。

原状（IDOR）：
- V2 ``POST /notify-cell-change`` 无项目鉴权即按任意 project_id 写 stale，年度写死 2025；
- linkage-bus ``POST /impact`` 无项目鉴权即写 stale、推 SSE；
- linkage-bus ``GET /impact-by-addr`` 是「会写库的 GET」，同样无项目鉴权。

现行：
- ``/impact`` 写 stale 走项目 edit 鉴权（``assert_project_permission(..., "edit")``）；年度缺省时按项目审计年度
  补齐，补不出 → 422 ``YEAR_REQUIRED``（不写死 2025）；非成员 403 且 ``on_change`` 0 次；
- ``/impact-by-addr`` 改为只读预览（``preview_impact``，不写库 / 不推 SSE / 不记审计），走 readonly 鉴权；
- ``notify-cell-change`` 下线：登录即 410，未登录 401，函数体只有 ``raise``、不触达数据。

经 HTTP 真发请求（权限世界 fixtures：真实成员行、生产门禁、生产注册；只 override 当前用户与会话），
``stale_engine`` 的写 / 读入口换成计数桩。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
import pytest_asyncio

from app.routers import address_registry_v2 as v2_module
from app.routers import linkage_bus as lb_module
from app.services import stale_propagation_engine as stale_module
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

PID = str(TARGET_PROJECT_ID)
# require_project_access("readonly") 与 assert_project_permission 共用同一判定实现，
# 前者的 dependency 闭包最终调后者，故两个端点都观测这一个门禁代码。
ASSERT_GATE = "app.deps.assert_project_permission"


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


def _stub_on_change(world):
    """stale_engine.on_change 换成计数桩（singleton 实例上若有同名实例属性先拿掉）。"""
    if "on_change" in vars(stale_module.stale_engine):
        world.monkeypatch.delattr(stale_module.stale_engine, "on_change")
    return world.stub(
        stale_module.StalePropagationEngine, "on_change",
        returns={"affected": [], "total": 0, "degraded": False},
    )


def _stub_preview(world):
    if "preview_impact" in vars(stale_module.stale_engine):
        world.monkeypatch.delattr(stale_module.stale_engine, "preview_impact")
    return world.stub(
        stale_module.StalePropagationEngine, "preview_impact",
        returns={"affected": [], "total": 0, "degraded": False}, awaitable=False,
    )


# ─── POST /api/linkage-bus/impact（写 stale，edit 级） ────────────────────────

_IMPACT_BODY = {"source_uri": "WP:D2:明细表D2-2:C10", "project_id": PID, "year": 2025}


@pytest.mark.parametrize("identity", ["edit_member", "admin_non_member"])
async def test_impact_allowed_identities_reach_engine(world, identity: str):
    """该放行的身份：edit 级成员（manager, edit）与全局 admin。on_change 恰 1 次且拿到请求里的项目与年度。
    （review / readonly 级在 test_impact_review_and_readonly_are_403 里断言 403。）
    """
    user = (await world.identity(identity)).user
    stub = _stub_on_change(world)
    async with world.client(lb_module.router, user=user) as client:
        resp = await client.post("/api/linkage-bus/impact", json=_IMPACT_BODY)
    assert resp.status_code == 200, resp.text
    assert stub.count == 1
    (args, kwargs) = stub.calls[0]
    called = {**dict(zip(("source_uri", "project_id", "year"), args)), **kwargs}
    assert called["project_id"] == PID
    assert called["year"] == 2025
    client.assert_passed(ASSERT_GATE, times=1)


@pytest.mark.parametrize("identity", ["readonly_member", "review_member", "project_eqcr", "qc_review_member"])
async def test_impact_review_and_readonly_are_403(world, identity: str):
    """readonly / review 级（含本项目 EQCR）写 stale → 403 且引擎 0 次。"""
    user = (await world.identity(identity)).user
    stub = _stub_on_change(world)
    async with world.client(lb_module.router, user=user) as client:
        resp = await client.post("/api/linkage-bus/impact", json=_IMPACT_BODY)
    assert resp.status_code == 403, resp.text
    assert stub.count == 0
    client.assert_passed(ASSERT_GATE, times=1)


async def test_impact_non_member_is_403_before_engine(world):
    user = (await world.non_member()).user
    stub = _stub_on_change(world)
    async with world.client(lb_module.router, user=user) as client:
        resp = await client.post("/api/linkage-bus/impact", json=_IMPACT_BODY)
    assert resp.status_code == 403, resp.text
    assert stub.count == 0
    client.assert_passed(ASSERT_GATE, times=1)


async def test_impact_anonymous_is_401(world):
    stub = _stub_on_change(world)
    async with world.client(lb_module.router, user=None) as client:
        resp = await client.post("/api/linkage-bus/impact", json=_IMPACT_BODY)
    assert resp.status_code == 401, resp.text
    assert stub.count == 0


async def test_impact_missing_year_and_no_project_year_is_422(world):
    """带 edit 权、不带 year，项目也补不出年度 → 422 YEAR_REQUIRED，引擎 0 次。

    SQLite 下 fetch_project_audit_year 的 PG 专有 SQL 跑不了，故在 router 模块上桩成返回 None
    （只替换「年度补齐来源」这一数据查询，不替换鉴权门禁）。
    """
    user = (await world.edit_member()).user
    stub = _stub_on_change(world)

    async def _no_year(_db, _pid):
        return None

    world.monkeypatch.setattr(lb_module, "fetch_project_audit_year", _no_year)
    body = {k: v for k, v in _IMPACT_BODY.items() if k != "year"}
    async with world.client(lb_module.router, user=user) as client:
        resp = await client.post("/api/linkage-bus/impact", json=body)
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["error_code"] == "YEAR_REQUIRED"
    assert stub.count == 0
    client.assert_passed(ASSERT_GATE, times=1)


async def test_impact_missing_year_backfilled_from_project(world):
    """带 edit 权、不带 year，项目能补出年度 → 200，引擎拿到补齐的年度。"""
    user = (await world.edit_member()).user
    stub = _stub_on_change(world)

    async def _year(_db, _pid):
        return 2024

    world.monkeypatch.setattr(lb_module, "fetch_project_audit_year", _year)
    body = {k: v for k, v in _IMPACT_BODY.items() if k != "year"}
    async with world.client(lb_module.router, user=user) as client:
        resp = await client.post("/api/linkage-bus/impact", json=body)
    assert resp.status_code == 200, resp.text
    assert stub.count == 1
    (args, kwargs) = stub.calls[0]
    called = {**dict(zip(("source_uri", "project_id", "year"), args)), **kwargs}
    assert called["year"] == 2024


# ─── GET /api/linkage-bus/impact-by-addr（只读预览，readonly 级） ──────────────


async def test_impact_by_addr_readonly_reaches_preview_not_write(world):
    """readonly 成员 → 200，走只读 preview_impact（不写库：on_change 0 次）。"""
    user = (await world.readonly_member()).user
    on_change = _stub_on_change(world)
    preview = _stub_preview(world)
    async with world.client(lb_module.router, user=user) as client:
        resp = await client.get(
            "/api/linkage-bus/impact-by-addr", params={"addr_id": "D2/D2-2/E100", "project_id": PID},
        )
    assert resp.status_code == 200, resp.text
    assert preview.count == 1
    assert on_change.count == 0  # 只读预览不写 stale
    # require_project_access("readonly") 的 dependency 闭包最终调 assert_project_permission
    client.assert_passed(ASSERT_GATE, times=1)


async def test_impact_by_addr_non_member_is_403_and_no_bfs(world):
    user = (await world.non_member()).user
    on_change = _stub_on_change(world)
    preview = _stub_preview(world)
    async with world.client(lb_module.router, user=user) as client:
        resp = await client.get(
            "/api/linkage-bus/impact-by-addr", params={"addr_id": "D2/D2-2/E100", "project_id": PID},
        )
    assert resp.status_code == 403, resp.text
    assert (on_change.count, preview.count) == (0, 0)
    client.assert_passed(ASSERT_GATE, times=1)


async def test_impact_by_addr_anonymous_is_401(world):
    on_change = _stub_on_change(world)
    preview = _stub_preview(world)
    async with world.client(lb_module.router, user=None) as client:
        resp = await client.get(
            "/api/linkage-bus/impact-by-addr", params={"addr_id": "D2/D2-2/E100", "project_id": PID},
        )
    assert resp.status_code == 401, resp.text
    assert (on_change.count, preview.count) == (0, 0)


# ─── POST /api/address-registry/v2/notify-cell-change（已下线） ───────────────


async def test_notify_cell_change_logged_in_is_410(world):
    user = (await world.edit_member()).user
    on_change = _stub_on_change(world)
    async with world.client(v2_module.router, user=user) as client:
        resp = await client.post(
            "/api/address-registry/v2/notify-cell-change",
            json={"wp_code": "D2", "sheet": "x", "cell": "C1", "project_id": PID},
        )
    assert resp.status_code == 410, resp.text
    assert resp.json()["detail"]["error_code"] == "ENDPOINT_GONE"
    assert on_change.count == 0  # 不触达数据


async def test_notify_cell_change_anonymous_is_401(world):
    async with world.client(v2_module.router, user=None) as client:
        resp = await client.post("/api/address-registry/v2/notify-cell-change", json={})
    assert resp.status_code == 401, resp.text


def test_notify_cell_change_body_is_only_raise():
    """AST：下线端点函数体只有 docstring + 一条 raise，不读请求体、不触达数据。"""
    src = Path(v2_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "notify_cell_change"
    )
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # 去 docstring
    assert len(body) == 1 and isinstance(body[0], ast.Raise), "下线端点函数体应只有一条 raise"
    # 签名不带请求体参数（不接收 project_id / wp_code 等）
    params = {a.arg for a in fn.args.args}
    assert "body" not in params, "下线端点不应再接收请求体"
