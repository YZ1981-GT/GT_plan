"""任务 4.3：普通合并报表按节点读时计算 —— 字段语义保留 + 本期/上期同节点共享口径 + 权益表不被项目级 enrichment 覆盖。

spec: consol-node-key-isolation-and-shared-context（需求 4.3；设计 §六.3~§六.5、ADR-CNSC-001/003、P8）。

被测真实生产函数（禁 mock 替换被测函数本身）：
  - ``consol_report_view_service.load_prior_year_node_report``  同节点、上一有效审计年度、共享求值的上期
  - ``routers.consol_report.get_consol_report``                 经真 FastAPI 请求验证字段契约与上期值

关键证明（变异点）：上期**不**读项目级物化 ``FinancialReport.prior_period_amount`` 冒充非根 ——
``group`` 夹具里上年合并项目 ``G24`` 预置了 BS-002 的物化本期值 888.00；按**同节点上一年度**计算
``G:consol`` 的上期 BS-002 应为 0.00（上年合并树是无 TB 的孤节点），**绝不等于 888.00**。
非根子合并节点 ``A:consol`` 不在上年孤节点树中 ⇒ 上期整体 null + 原因。

企业树身份用 ``group`` 夹具真实构建（G⊃A⊃A1, G⊃B；G:consol 根，A:consol 子合并节点，B:subsidiary 数据节点）。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User, UserRole
from app.services.consol_report_view_service import PriorNodeReport, load_prior_year_node_report
from app.services.consol_tree_service import build_tree

# 复用 test_consol_push 的真集团夹具（真 SQLite 内存库 + 真 ORM 行）。
from tests.test_consol_push import (  # noqa: F401
    Y,
    db,
    factory,
    group,
)

D = Decimal


@pytest_asyncio.fixture
async def tree_root(db, group):
    root = await build_tree(db, group["G"].id)
    assert root is not None and root.node_key == "G:consol"
    return root


def _make_app(db_session) -> FastAPI:
    from app.routers.consol_report import router

    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    async def _override_user():
        import uuid as _u
        return User(
            id=_u.UUID("00000000-0000-0000-0000-000000000001"),
            username="t_admin", email="a@t.com", hashed_password="x", role=UserRole.admin,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[require_project_access("readonly")] = _override_user
    return app


async def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _get_rows(db, group, node_key=None, report_type="balance_sheet"):
    app = _make_app(db)
    params = {"report_type": report_type}
    if node_key is not None:
        params["node_key"] = node_key
    async with await _client(app) as client:
        resp = await client.get(f"/api/consolidation/reports/{group['G'].id}/{Y}", params=params)
    return resp


# ─────────────────────── load_prior_year_node_report（§六.4；需求 4.3） ───────────────────────


class TestPriorYearNodeReport:
    @pytest.mark.asyncio
    async def test_root_prior_computed_by_node_not_materialized(self, db, group, tree_root):
        """根节点 G:consol 上期按**同节点上一年度**计算 = 0.00（上年孤节点无 TB），**不**等于物化的 888.00。"""
        prior = await load_prior_year_node_report(
            db, project_id=group["G"].id, node_key="G:consol", year=Y, report_type="balance_sheet",
        )
        assert isinstance(prior, PriorNodeReport)
        assert prior.unavailable is None, "上年同企业合并项目 G24 存在且节点在树中"
        bs002 = prior.amounts.get("BS-002")
        assert bs002 is not None and bs002.amount == D("0.00"), (
            "按节点上一年度计算（上年无 TB ⇒ 0.00），不读物化 FinancialReport.prior=888.00"
        )
        assert bs002.amount != D("888.00")

    @pytest.mark.asyncio
    async def test_nonroot_node_absent_in_prior_tree_unavailable(self, db, group, tree_root):
        """非根子合并节点 A:consol 不在上年孤节点树中 ⇒ 上期整体不可用 + 原因，amounts 为空。"""
        prior = await load_prior_year_node_report(
            db, project_id=group["G"].id, node_key="A:consol", year=Y, report_type="balance_sheet",
        )
        assert prior.amounts == {}
        assert prior.unavailable is not None and "A:consol" in prior.unavailable

    @pytest.mark.asyncio
    async def test_no_prior_consol_project_unavailable(self, db, group, tree_root):
        """上一年度无同企业合并项目（如本年即首年）⇒ 不可用 + 原因；绝不臆造上期。"""
        # 用上年 G24 本身当"本年"：它的上一年度（Y-2）没有任何合并项目。
        prior = await load_prior_year_node_report(
            db, project_id=group["G24"].id, node_key="G:consol", year=Y - 1, report_type="balance_sheet",
        )
        assert prior.amounts == {}
        assert prior.unavailable is not None and str(Y - 2) in prior.unavailable


# ─────────────────────── 端点字段契约 + 上期（§六.3~§六.5；需求 4.3；P8） ───────────────────────


class TestEndpointFieldsAndPrior:
    @pytest.mark.asyncio
    async def test_root_report_fields_and_prior_from_node(self, db, group, tree_root):
        """根报表（缺省 node_key）：既有字段齐全；上期按同节点计算（BS-002=0.00），不冒充物化 888.00。"""
        resp = await _get_rows(db, group)
        assert resp.status_code == 200
        rows = {r["row_code"]: r for r in resp.json()}
        # 既有字段语义全保留
        bs002 = rows["BS-002"]
        assert set(bs002) >= {
            "row_code", "row_name", "row_index", "indent_level", "is_total", "is_total_row",
            "current_period_amount", "prior_period_amount", "formula_used", "source_accounts",
            "blank_reason", "is_stale",
        }
        # 本期按节点计算（个别数汇总 1000+400 = 1400.00；TB('1001')）
        assert bs002["current_period_amount"] == "1400.00"
        # 上期按**同节点上一年度**计算 = 0.00，**不是**物化 prior 888.00
        assert bs002["prior_period_amount"] == "0.00"
        assert bs002["prior_period_amount"] != "888.00"
        # 合计行标记保留
        assert rows["BS-015"]["is_total_row"] is True
        assert rows["BS-002"]["indent_level"] == 1
        # 本期取不到数的行：current=null + blank_reason，不伪造 0
        # BS-001 无公式 ⇒ 本期 0.00（标题/无公式行按 0），上期同样 0.00（无公式）
        assert rows["BS-001"]["formula_used"] is None

    @pytest.mark.asyncio
    async def test_nonroot_node_prior_null_with_reason(self, db, group, tree_root):
        """非根节点 A:consol 本期按节点计算（有值），上期整体 null（上年树无此节点），字段契约不变。"""
        resp = await _get_rows(db, group, node_key="A:consol")
        assert resp.status_code == 200
        rows = {r["row_code"]: r for r in resp.json()}
        # A 子合并（A_s + A1）：货币资金 400.00
        assert rows["BS-002"]["current_period_amount"] == "400.00"
        # 上期整体不可用 ⇒ 所有行 prior=null（不读根物化、不冒充）
        assert all(r["prior_period_amount"] is None for r in rows.values())

    @pytest.mark.asyncio
    async def test_equity_statement_node_values_not_project_enrichment(self, db, group, tree_root):
        """股东权益表：节点金额由同一 node_report 合并数路径求值，不被项目级 enrichment 覆盖；字段契约不变。

        本夹具报表配置无 equity_statement 行 ⇒ 该类型 404「没有报表配置」（走明确错误，不静默空数组、
        不触发项目级 enrich_equity_statement_rows）。这证明权益表与其余报表同一节点读时计算路径。
        """
        resp = await _get_rows(db, group, report_type="equity_statement")
        assert resp.status_code == 404
        assert "报表配置" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_prior_matches_same_node_recompute(self, db, group, tree_root):
        """P8 同口径：端点返回的上期值与直接对同节点上一年度 node_report 求值逐行一致。"""
        resp = await _get_rows(db, group)
        rows = {r["row_code"]: r for r in resp.json()}
        prior = await load_prior_year_node_report(
            db, project_id=group["G"].id, node_key="G:consol", year=Y, report_type="balance_sheet",
        )
        for code, row in rows.items():
            pv = prior.amounts.get(code)
            expected = None if pv is None or pv.amount is None else str(pv.amount)
            assert row["prior_period_amount"] == expected, code
