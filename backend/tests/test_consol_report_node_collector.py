"""任务 4.5：普通合并报表按节点读时计算 —— section 4 综合收口（真 ORM/SQLite 集团 + 真 FastAPI 请求）。

spec: consol-node-key-isolation-and-shared-context（需求 4.1~4.5；设计 §六、P5、P8、ADR-CNSC-001/003）。

本文件是 4.1~4.4 的**综合收口**，只补齐任务 4.5 清单里尚未被充分显式覆盖的点，不重复既有测试：
  - 4.1 入参 / 节点 / 年度校验 → `test_consol_report_node_scope.py` 已覆盖，这里纳入综合矩阵复证。
  - 4.2 节点金额读时计算 → `test_consol_push.py::TestViews` + 4.1 端点读时计算已覆盖。
  - 4.3 字段契约 + 本期/上期同节点共享口径 + 权益表不被 enrichment 覆盖 → `test_consol_report_node_prior.py`。
  - 4.4 读路径不写 FinancialReport → `test_consol_report_node_no_fr_write.py`。

4.5 显式补缺口（既有测试未充分覆盖者）：
  1. **至少两个「同企业不同角色」节点各自正确且互不串用**：公司 A 有 `A:consol`（合并角色,
     含子公司 A1）与 `A:parent`（母公司本部数据角色）两个节点；公司 G 有 `G:consol` 与 `G:parent`。
     同企业两节点金额各自正确、互不覆盖（这是 ADR-CNSC-001「同企业多角色会撞车」的正面反证）。
  2. **全部报表字段契约**：真 FastAPI 响应里 `ConsolReportRow[]` 全部 12 字段齐全且语义正确
     （类型 / 合计标记一致性 / 缩进 / is_stale 恒 False 读时计算）。
  3. **节点金额与同节点 trial / breakdown 逐行对拍（P5/P8）**：GET reports 的每行本期金额 ==
     同节点 `trial_view` 合并数列；汇总节点再与 `breakdown_view` 各列之和 == 合计逐行一致。
  4. **缺省根兼容 / 非法节点 / 上期缺失原因 / 非根不读根物化值**：纳入综合矩阵一次性收口。

被测真实生产函数（禁 mock 替换被测函数本身；禁恒绿）：
  - ``routers.consol_report.get_consol_report``                 经真 FastAPI 请求（ASGITransport）
  - ``consol_report_view_service.trial_view`` / ``breakdown_view``  同节点共享求值口径对拍锚点
  - ``consol_report_view_service.load_view_context`` / ``load_prior_year_node_report``
  - 真 ``FinancialReport`` 物化行（G24 BS-002=888.00）作「非根不读根物化值」的投毒锚点

企业树身份用 ``group`` 夹具真实构建（G⊃A⊃A1, G⊃B）。probe 现算确认的真值（scripts/analyze/_cnsc45_probe.py）：
  A:consol  BS-006=80.00（含 A1）  ；A:parent BS-006=0.00（只本部）  —— 同企业 A 两角色 BS-006 不同。
  G:consol  BS-006=400.00         ；G:parent BS-006=320.00           —— 同企业 G 两角色 BS-006 不同。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User, UserRole
from app.models.report_models import FinancialReport, FinancialReportType
from app.services.consol_report_view_service import (
    breakdown_view,
    load_view_context,
    trial_view,
)
from app.services.consol_tree_service import build_tree

# 复用 test_consol_push 的真集团夹具（真 SQLite 内存库 + 真 ORM 行）。
from tests.test_consol_push import (  # noqa: F401
    Y,
    db,
    factory,
    group,
)

D = Decimal

# ConsolReportRow 的全部字段（设计 §六.3，需求 4.3）。
_ROW_FIELDS = {
    "row_code",
    "row_name",
    "row_index",
    "indent_level",
    "is_total_row",
    "is_total",
    "current_period_amount",
    "prior_period_amount",
    "formula_used",
    "source_accounts",
    "blank_reason",
    "is_stale",
}


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


async def _get(db, project, node_key=None, report_type="balance_sheet"):
    app = _make_app(db)
    params = {"report_type": report_type}
    if node_key is not None:
        params["node_key"] = node_key
    async with await _client(app) as client:
        return await client.get(f"/api/consolidation/reports/{project.id}/{Y}", params=params)


# ───────────────── 1. 同企业不同角色节点：各自正确且互不串用（需求 4.1/4.2，ADR-CNSC-001） ─────────────────


class TestSameCompanyDifferentRoleNodes:
    """公司 A 的 `A:consol` 与 `A:parent` 是同企业不同角色的两个节点 —— 读取结果各自正确、互不覆盖。

    这是 ADR-CNSC-001「同企业多角色会撞车」的**正面反证**：若端点按 company_code 推断节点身份，
    `A:consol` 与 `A:parent` 会读到同一份数据；真实实现按精确 node_key 读时计算 ⇒ 两者 BS-006 不同。
    """

    @pytest.mark.asyncio
    async def test_company_a_consol_vs_parent_differ(self, db, group, tree_root):
        """A:consol（含子公司 A1，BS-006=80）≠ A:parent（只本部，BS-006=0）；BS-002/BS-045 恰相同但来源不同。"""
        resp_consol = await _get(db, group["G"], node_key="A:consol")
        resp_parent = await _get(db, group["G"], node_key="A:parent")
        assert resp_consol.status_code == 200 and resp_parent.status_code == 200, (
            resp_consol.text, resp_parent.text,
        )
        consol = {r["row_code"]: r for r in resp_consol.json()}
        parent = {r["row_code"]: r for r in resp_parent.json()}
        # 同企业 A 两角色：应收账款（BS-006）不同 —— consol 纳入 A1 的 80，parent 不纳入
        assert consol["BS-006"]["current_period_amount"] == "80.00"
        assert parent["BS-006"]["current_period_amount"] == "0.00"
        assert consol["BS-006"]["current_period_amount"] != parent["BS-006"]["current_period_amount"]
        # 两节点都 200 且是独立行数组（互不串用：consol 的值不是 parent 的值）
        assert consol["BS-002"]["current_period_amount"] == "400.00"
        assert parent["BS-002"]["current_period_amount"] == "400.00"

    @pytest.mark.asyncio
    async def test_company_g_consol_vs_parent_differ(self, db, group, tree_root):
        """G:consol（BS-006=400，含全集团）≠ G:parent（BS-006=320，只母公司本部）—— 同企业 G 两角色。"""
        resp_consol = await _get(db, group["G"], node_key="G:consol")
        resp_parent = await _get(db, group["G"], node_key="G:parent")
        assert resp_consol.status_code == 200 and resp_parent.status_code == 200
        consol = {r["row_code"]: r for r in resp_consol.json()}
        parent = {r["row_code"]: r for r in resp_parent.json()}
        assert consol["BS-006"]["current_period_amount"] == "400.00"
        assert parent["BS-006"]["current_period_amount"] == "320.00"
        assert consol["BS-006"]["current_period_amount"] != parent["BS-006"]["current_period_amount"]

    @pytest.mark.asyncio
    async def test_three_role_nodes_of_company_a_each_matches_trial(self, db, group, tree_root):
        """公司 A 的三个角色节点 consol / parent / consol_elim 各自读时计算，与同节点 trial 逐行一致。

        consol_elim 是 A 的差额（抵销）节点，本夹具 A 无归属抵销分录 ⇒ 全 0.00；与 consol/parent 判然不同。
        三个节点同属公司 A，证明「同企业多角色」在读取层完全隔离、各走各的 node_measures。
        """
        ctx = await load_view_context(db, group["G"].id)
        for nk in ("A:consol", "A:parent", "A:consol_elim"):
            resp = await _get(db, group["G"], node_key=nk)
            assert resp.status_code == 200, (nk, resp.text)
            rows = {r["row_code"]: r for r in resp.json()}
            trial = {r["row_code"]: r for r in (
                await trial_view(ctx.basis, ctx.rows, report_type="balance_sheet", node_key=nk)
            )["rows"]}
            for code, row in rows.items():
                assert row["current_period_amount"] == trial[code]["consolidated"], (nk, code)
        # consol_elim 节点全 0（无归属抵销），与 consol/parent 不等 —— 同企业角色隔离的佐证
        elim = {r["row_code"]: r for r in (await _get(db, group["G"], node_key="A:consol_elim")).json()}
        assert elim["BS-006"]["current_period_amount"] == "0.00"


# ───────────────── 2. 全部报表字段契约（需求 4.3，设计 §六.3） ─────────────────


class TestFullFieldContract:
    @pytest.mark.asyncio
    async def test_all_fields_present_and_typed_for_every_row(self, db, group, tree_root):
        """每行 12 字段齐全、类型正确；is_total/is_total_row 一致；is_stale 读时计算恒 False。"""
        resp = await _get(db, group["G"])  # 缺省根
        assert resp.status_code == 200
        rows = resp.json()
        assert isinstance(rows, list) and len(rows) > 0
        for r in rows:
            assert set(r) >= _ROW_FIELDS, f"行 {r.get('row_code')} 缺字段：{_ROW_FIELDS - set(r)}"
            # 类型：字符串字段
            assert isinstance(r["row_code"], str) and r["row_code"]
            assert isinstance(r["row_name"], str)
            # 数值元数据字段
            assert isinstance(r["row_index"], int)
            assert isinstance(r["indent_level"], int)
            # 合计标记：两字段同义、必须一致（设计 §六.3 保留既有语义）
            assert isinstance(r["is_total"], bool) and isinstance(r["is_total_row"], bool)
            assert r["is_total"] == r["is_total_row"], f"is_total 与 is_total_row 不一致：{r['row_code']}"
            # 金额字段：str（到分）或 None（取不到数给原因，不伪造 0）
            assert r["current_period_amount"] is None or isinstance(r["current_period_amount"], str)
            assert r["prior_period_amount"] is None or isinstance(r["prior_period_amount"], str)
            # formula_used / source_accounts / blank_reason 允许 None
            assert r["formula_used"] is None or isinstance(r["formula_used"], str)
            assert r["source_accounts"] is None or isinstance(r["source_accounts"], list)
            assert r["blank_reason"] is None or isinstance(r["blank_reason"], str)
            # is_stale：读时计算恒 False（不是物化报表的过期标记）
            assert r["is_stale"] is False

    @pytest.mark.asyncio
    async def test_total_row_flag_matches_config(self, db, group, tree_root):
        """合计行标记来自 report config：BS-015 / IS-019 为合计行，其余非合计。"""
        bs = {r["row_code"]: r for r in (await _get(db, group["G"])).json()}
        assert bs["BS-015"]["is_total_row"] is True
        assert bs["BS-002"]["is_total_row"] is False
        income = {r["row_code"]: r for r in (await _get(db, group["G"], report_type="income_statement")).json()}
        assert income["IS-019"]["is_total_row"] is True
        assert income["IS-001"]["is_total_row"] is False


# ───────────────── 3. 节点金额与同节点 trial / breakdown 逐行对拍（P5/P8） ─────────────────


class TestReportTrialBreakdownAgree:
    @pytest.mark.asyncio
    async def test_report_amount_equals_trial_for_all_nodes_and_types(self, db, group, tree_root):
        """GET reports 每行本期金额 == 同节点 trial_view 合并数列，覆盖全部节点 × 全部报表类型（P5/P8）。"""
        ctx = await load_view_context(db, group["G"].id)
        from app.services.consol_calc_basis import node_measures

        all_nodes = sorted(node_measures(ctx.basis))
        assert "A:consol" in all_nodes and "A:parent" in all_nodes and "G:parent" in all_nodes
        for nk in all_nodes:
            for rt in ("balance_sheet", "income_statement"):
                resp = await _get(db, group["G"], node_key=nk, report_type=rt)
                assert resp.status_code == 200, (nk, rt, resp.text)
                rows = {r["row_code"]: r for r in resp.json()}
                trial = {r["row_code"]: r for r in (
                    await trial_view(ctx.basis, ctx.rows, report_type=rt, node_key=nk)
                )["rows"]}
                assert set(rows) == set(trial), (nk, rt)
                for code, row in rows.items():
                    assert row["current_period_amount"] == trial[code]["consolidated"], (nk, rt, code)

    @pytest.mark.asyncio
    async def test_report_amount_equals_breakdown_column_sum_for_aggregate_nodes(self, db, group, tree_root):
        """汇总节点（G:consol / A:consol）：GET reports 每行本期金额 == breakdown 各子列之和（P8）。"""
        ctx = await load_view_context(db, group["G"].id)
        for nk in ("G:consol", "A:consol"):
            for rt in ("balance_sheet", "income_statement"):
                resp = await _get(db, group["G"], node_key=nk, report_type=rt)
                assert resp.status_code == 200, (nk, rt, resp.text)
                rows = {r["row_code"]: r for r in resp.json()}
                bd = await breakdown_view(ctx.basis, ctx.rows, report_type=rt, node_key=nk)
                for brow in bd["rows"]:
                    code = brow["row_code"]
                    total = brow["total"]
                    # 报表本期金额 == 差额表合计
                    assert rows[code]["current_period_amount"] == total, (nk, rt, code)
                    # 线性行：各子列之和 == 合计
                    if total is not None:
                        assert sum(D(v) for v in brow["cells"].values()) == D(total), (nk, rt, code, brow)


# ───────────────── 4. 综合矩阵：缺省根 / 非法节点 / 上期缺失 / 非根不读根物化值 ─────────────────


class TestCollectorMatrix:
    @pytest.mark.asyncio
    async def test_default_root_equals_explicit_root(self, db, group, tree_root):
        """缺省（不传 node_key）== 显式传根 G:consol（设计 §六.1 兼容默认根）。"""
        omitted = {r["row_code"]: r for r in (await _get(db, group["G"])).json()}
        explicit = {r["row_code"]: r for r in (await _get(db, group["G"], node_key="G:consol")).json()}
        assert set(omitted) == set(explicit)
        for code in omitted:
            assert omitted[code]["current_period_amount"] == explicit[code]["current_period_amount"], code
            assert omitted[code]["prior_period_amount"] == explicit[code]["prior_period_amount"], code

    @pytest.mark.asyncio
    async def test_illegal_node_rejected_in_matrix(self, db, group, tree_root):
        """非法节点键 ⇒ 400（不降级成根、不冒充 company_code）。"""
        resp = await _get(db, group["G"], node_key="XX:consol")
        assert resp.status_code == 400
        assert "XX:consol" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_prior_unavailable_reason_for_nonroot(self, db, group, tree_root):
        """非根节点 A:consol 上期整体不可用（上年树无此节点）⇒ 全行 prior=null（有原因，不冒充）。"""
        rows = (await _get(db, group["G"], node_key="A:consol")).json()
        assert all(r["prior_period_amount"] is None for r in rows), "非根节点上期不可用 ⇒ 全 null"

    @pytest.mark.asyncio
    async def test_nonroot_does_not_read_root_materialized_value(self, db, group, tree_root):
        """非根不读根物化值（收口反证）：投毒根物化 FinancialReport 后，非根 A:parent 的值不受影响。

        步骤：先取 A:parent 本期/上期基线 ⇒ 再向 G:consol 物化表 upsert 一行投毒值 ⇒ 重取 A:parent，
        值必须与基线逐行相同（读时计算只走 node_measures，绝不读项目级 FinancialReport 冒充非根）。
        """
        before = {r["row_code"]: r for r in (await _get(db, group["G"], node_key="A:parent")).json()}
        # 投毒：向 G:consol 本项目物化报表写一个显眼的假值（本期 99999.00）
        db.add(FinancialReport(
            project_id=group["G"].id, year=Y, report_type=FinancialReportType.balance_sheet,
            row_code="BS-006", row_name="应收账款", current_period_amount=D("99999.00"),
            prior_period_amount=D("77777.00"),
        ))
        await db.commit()
        after = {r["row_code"]: r for r in (await _get(db, group["G"], node_key="A:parent")).json()}
        # 非根节点 A:parent 的 BS-006 本应 0.00（只本部），绝不读到投毒的 99999.00
        assert after["BS-006"]["current_period_amount"] == "0.00"
        assert after["BS-006"]["current_period_amount"] != "99999.00"
        # 全行与投毒前基线逐行一致（本期 + 上期）
        for code in before:
            assert after[code]["current_period_amount"] == before[code]["current_period_amount"], code
            assert after[code]["prior_period_amount"] == before[code]["prior_period_amount"], code

    @pytest.mark.asyncio
    async def test_mutation_proof_poison_would_be_read_if_router_read_materialized(self, db, group, tree_root):
        """变异证明（证明上条非恒绿）：直接查物化表确认投毒行真写进去了、且其值 ≠ 节点读时计算值。

        若生产 get_consol_report 改回读物化 FinancialReport，上一条断言 after[BS-006]==0.00 必然打红
        （会读到 99999.00）。这里直接读库证明投毒锚点真实存在、与读时计算值不同 ⇒ 守卫可区分两种实现。
        """
        db.add(FinancialReport(
            project_id=group["G"].id, year=Y, report_type=FinancialReportType.balance_sheet,
            row_code="BS-006", row_name="应收账款", current_period_amount=D("99999.00"),
        ))
        await db.commit()
        poisoned = (await db.execute(sa.select(FinancialReport.current_period_amount).where(
            FinancialReport.project_id == group["G"].id,
            FinancialReport.year == Y,
            FinancialReport.report_type == FinancialReportType.balance_sheet,
            FinancialReport.row_code == "BS-006",
        ))).scalars().all()
        assert D("99999.00") in poisoned, "投毒行应真实落库（否则非根不读根物化值的反证失效）"
        # 读时计算的 A:parent BS-006 == 0.00，与物化投毒值 99999.00 判然不同
        after = {r["row_code"]: r for r in (await _get(db, group["G"], node_key="A:parent")).json()}
        assert after["BS-006"]["current_period_amount"] == "0.00"
