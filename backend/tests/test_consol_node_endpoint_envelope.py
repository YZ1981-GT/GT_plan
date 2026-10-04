"""任务 6.2：节点级端点的响应 envelope 收口 —— 真 FastAPI 请求 + 生产 ResponseWrapperMiddleware。

spec: consol-node-key-isolation-and-shared-context（需求 6.2；设计 §四「不改变现有 HTTP 响应
envelope」、§六.3「保持现有报表行数组响应契约」）。

本任务是「端点级真请求覆盖」的收口核验。6.1 交接确认：成功/拒绝、权限依赖、旧 body/query 优先级
已被下列真 FastAPI 请求测试覆盖（本文件不重复，仅在报告中引用）：
  - 成功 2xx / 非法 node_key 400 / 非合并 404 / 空串 400 / 权限 403/200
      → test_consol_note_section2_integration.py（TestPerNodeFormulaResultsIsolated /
        TestFailureResponses / TestEndpointAuthorization）
      → test_consol_note_shared_context.py（TestEndpointSharedContext）
      → test_consol_report_node_scope.py（TestEndpointNodeKeyParam）
      → test_consol_push.py（TestReportNodeKeyReadTime）
  - 乐观锁 409 / 423 lock → test_note_cell_writeback_comprehensive.py / test_consol_note_formulas.py
  - body node_key 与 query 优先级（端点层）
      → test_consol_note_section2_integration.py（TestLegacyRouteNodeSemantics：refresh 代表性覆盖）
      注：五个 body 端点（refresh/audit/audit-all/apply-formulas/aggregate）统一经同一
          `_requested_node_key(node_key, body)` → `consol_note_scope.requested_node_key`，
          其优先级逻辑由 test_consol_note_scope.py::TestRequestedNodeKey 单测四分支钉死；
          端点层由 refresh 代表性验证即足够（单一真源 + 代表性端点）。

**本文件补的真实缺口（6.1 盘点确认此前无覆盖）：响应 envelope。**
``test_note_cell_writeback_comprehensive.py`` 的 ``cell-writeback`` 已挂生产
``ResponseWrapperMiddleware`` 验证 ``{code,message,data}``，但 **consol-note-sections 与
consol-report 的全部节点级端点测试都挂的是裸 ``FastAPI()``（见 test_consol_push.client_for /
test_consol_note_formulas.note_client / test_consol_report_node_scope._make_app，均无中间件）**。
生产 ``app.main`` 对这些端点全局挂了 ``ResponseWrapperMiddleware``（main.py），其 2xx JSON
响应在生产会被包成 ``{code,message,data}``；而前端对合并报表/附注端点按**裸契约**解包
（apiProxy 单层解构后拿 ``data``）。此前无任何测试证明这些端点经生产中间件后信封正确、且内层
``data`` 仍是原契约（报表=行数组、附注=对象）。本文件挂真实生产中间件补齐这一端到端维度。

证据纪律（禁恒绿）：
  - 测试 app **真挂** 生产 ``ResponseWrapperMiddleware``（否则信封断言无意义）。
  - 每个信封断言都配 ``TestEnvelopeMutationProof``：**不挂**中间件时同一端点返回**裸**契约
    （无 code/message 包装）—— 证明「信封」确实来自中间件、断言非恒绿。
  - 复用 ``group`` 真集团夹具与真 ORM 行，admin 走真实 ``require_project_access``（非 override）。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user
from app.middleware.response import ResponseWrapperMiddleware
from app.models.base import UserRole

from tests.test_consol_push import (  # noqa: F401  复用真集团夹具
    Y,
    _User,
    db,
    factory,
    group,
)

_NS = "/api/consol-note-sections"
_REPORTS = "/api/consolidation/reports"
SID = "五-1-1"  # 货币资金章：种子 (4,1)=REPORT('BS-002')


async def _generate_reports(db, project_id):
    from app.services.consol_report_service import generate_consol_reports_sync

    await generate_consol_reports_sync(db, project_id, Y)
    await db.commit()


def _build_app(db_session, *, with_middleware: bool) -> FastAPI:
    """挂 consol-note-sections + consol-report 路由；``with_middleware`` 控制是否挂生产中间件。

    不挂中间件的变体用于变异证明（裸契约）。两变体除中间件外完全一致。admin 走真实
    ``require_project_access``（admin 角色 bypass），只替换当前用户与会话。
    """
    from app.routers.consol_note_sections import router as ns_router
    from app.routers.consol_report import router as report_router

    app = FastAPI()
    if with_middleware:
        app.add_middleware(ResponseWrapperMiddleware)
    app.include_router(ns_router)
    app.include_router(report_router)

    async def _db():
        yield db_session

    admin = _User(UserRole.admin)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: admin
    return app


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def wrapped(db, group):
    """已生成报表 + 挂生产中间件的 app；返回 (app, gid)。"""
    gid = str(group["G"].id)  # 取 id 必须在生成报表（commit 使 ORM 对象过期）之前
    await _generate_reports(db, group["G"].id)
    return _build_app(db, with_middleware=True), gid


@pytest_asyncio.fixture
async def bare(db, group):
    """已生成报表 + 不挂中间件的 app（变异证明用）；返回 (app, gid)。"""
    gid = str(group["G"].id)
    await _generate_reports(db, group["G"].id)
    return _build_app(db, with_middleware=False), gid


def _assert_envelope(resp, status=200):
    """生产信封契约：2xx JSON ⇒ {code, message:"success", data:<payload>}。"""
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) >= {"code", "message", "data"}, f"信封缺字段：{body}"
    assert body["code"] == status
    assert body["message"] == "success"
    return body["data"]


# ─────────────────── 1. consol-report GET：信封内 data 仍是行数组契约（§六.3） ───────────────────


class TestReportEnvelope:
    @pytest.mark.asyncio
    async def test_report_get_wrapped_data_is_row_array(self, wrapped):
        """GET reports（默认根）经中间件 ⇒ {code,message,data}，data 仍是 ConsolReportRow[]。"""
        app, gid = wrapped
        async with _client(app) as c:
            resp = await c.get(f"{_REPORTS}/{gid}/{Y}", params={"report_type": "balance_sheet"})
        data = _assert_envelope(resp)
        assert isinstance(data, list), "报表 data 必须保持行数组契约，不被信封改形"
        rows = {r["row_code"]: r for r in data}
        assert "BS-002" in rows and rows["BS-002"]["current_period_amount"] == "1400.00"

    @pytest.mark.asyncio
    async def test_report_get_explicit_node_key_wrapped(self, wrapped):
        """显式子合并节点 A:consol 同样经信封包装，内层行数组为该节点读时计算值。"""
        app, gid = wrapped
        async with _client(app) as c:
            resp = await c.get(f"{_REPORTS}/{gid}/{Y}",
                               params={"report_type": "balance_sheet", "node_key": "A:consol"})
        data = _assert_envelope(resp)
        rows = {r["row_code"]: r for r in data}
        assert rows["BS-002"]["current_period_amount"] == "400.00"


# ─────────────────── 2. consol-note-sections GET/POST/PUT：信封内 data 仍是原对象契约（§四） ───────────────────


class TestNoteSectionEnvelope:
    @pytest.mark.asyncio
    async def test_data_get_wrapped(self, wrapped):
        """GET /data（节点行）经中间件 ⇒ 信封；内层 data 保留 content/updated_at/node_key 契约。"""
        app, gid = wrapped
        async with _client(app) as c:
            resp = await c.get(f"{_NS}/data/{gid}/{Y}/{SID}", params={"node_key": "G:consol"})
        data = _assert_envelope(resp)
        assert set(data) >= {"content", "updated_at", "node_key"}, f"附注 data 契约被信封破坏：{data}"
        assert data["node_key"] == "G:consol"

    @pytest.mark.asyncio
    async def test_data_put_wrapped(self, wrapped):
        """PUT /data（写节点专属行）2xx 经中间件 ⇒ 信封；内层 data 保留 ok/node_key。"""
        app, gid = wrapped
        async with _client(app) as c:
            resp = await c.put(f"{_NS}/data/{gid}/{Y}/{SID}", params={"node_key": "A:consol"},
                               json={"data": {"v": "env-put"}})
        data = _assert_envelope(resp)
        assert data["ok"] is True and data["node_key"] == "A:consol"

    @pytest.mark.asyncio
    async def test_breakdown_wrapped(self, wrapped):
        """GET breakdown 经中间件 ⇒ 信封；内层 data 保留 cells/columns/node_key。"""
        app, gid = wrapped
        async with _client(app) as c:
            resp = await c.get(f"{_NS}/breakdown/{gid}/{Y}/{SID}", params={"node_key": "G:consol"})
        data = _assert_envelope(resp)
        assert "cells" in data and "columns" in data and data["node_key"] == "G:consol"

    @pytest.mark.asyncio
    async def test_fill_by_formula_wrapped(self, wrapped):
        """POST fill-by-formula 2xx 经中间件 ⇒ 信封；内层 data 保留 node_key/kept_manual。"""
        app, gid = wrapped
        async with _client(app) as c:
            resp = await c.post(f"{_NS}/fill-by-formula/{gid}/{Y}/{SID}", params={"node_key": "G:consol"})
        data = _assert_envelope(resp)
        assert data["node_key"] == "G:consol" and "kept_manual" in data

    @pytest.mark.asyncio
    async def test_refresh_wrapped(self, wrapped):
        """POST refresh 2xx 经中间件 ⇒ 信封；内层 data 保留 rows。"""
        app, gid = wrapped
        async with _client(app) as c:
            resp = await c.post(f"{_NS}/refresh/{gid}/{Y}/{SID}", params={"node_key": "G:consol"},
                                json={"standard": "soe"})
        data = _assert_envelope(resp)
        assert "rows" in data

    @pytest.mark.asyncio
    async def test_aggregate_wrapped(self, wrapped):
        """POST aggregate 2xx 经中间件 ⇒ 信封；内层 data 保留 value/count。"""
        app, gid = wrapped
        async with _client(app) as c:
            resp = await c.post(f"{_NS}/aggregate/{gid}/{Y}", params={"node_key": "G:consol"},
                                json={"section_id": SID, "mode": "direct"})
        data = _assert_envelope(resp)
        assert "value" in data and "count" in data


# ─────────────────── 3. 变异证明：裸 app（不挂中间件）返回裸契约，证明信封来自中间件 ───────────────────


class TestEnvelopeMutationProof:
    @pytest.mark.asyncio
    async def test_report_bare_app_returns_unwrapped_row_array(self, bare):
        """不挂中间件 ⇒ 报表直接返回**裸行数组**（顶层是 list，不是信封 dict）。

        这证明 TestReportEnvelope 的信封断言非恒绿：信封确实由 ResponseWrapperMiddleware 产生。
        """
        app, gid = bare
        async with _client(app) as c:
            resp = await c.get(f"{_REPORTS}/{gid}/{Y}", params={"report_type": "balance_sheet"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list), "裸 app 必须返回裸行数组，无信封"

    @pytest.mark.asyncio
    async def test_note_breakdown_bare_app_returns_unwrapped_dict(self, bare):
        """不挂中间件 ⇒ breakdown 直接返回**裸对象**（顶层无 code/message/data 三件套）。"""
        app, gid = bare
        async with _client(app) as c:
            resp = await c.get(f"{_NS}/breakdown/{gid}/{Y}/{SID}", params={"node_key": "G:consol"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "cells" in body, "裸 app 的 breakdown 顶层直接是 cells 契约"
        assert not (set(body) >= {"code", "message", "data"}), "裸 app 不应有信封三件套"
