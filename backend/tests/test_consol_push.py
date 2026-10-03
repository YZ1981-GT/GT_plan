"""合并推送 + 读时计算视图（spec consol-elimination-single-source-push 任务 3~5，design §四~§八 / §十二）。

真 SQLite + 真 ORM 行 + 真 service；端点真发请求（ASGITransport），鉴权走真实实现（只替换当前用户与会话）。

- 任务 3：合并报表生成 —— 全部报表类型、按项目口径（上市 / 国企）、留空行写原因、上期取上年合并项目；
- P1：推送写入的合并报表 == 读时计算（``report-trial`` 合并审定数列）逐行同值；
- P4：报表差额表各列之和 == 合计列；根节点合计 == 合并报表值；
- P8：撤销审批后推送 ⇒ 合并数回到审批前；锁定时撤销审批 423；
- 上层联动：下级合并项目的分录审批 ⇒ 下级与上级合并项目都推送；
- 失败留痕：关键步失败 ⇒ 该项目后续跳过、运行记录 partial / failed 并给原因，不静默；
- 穿透：``drill/entries`` 只计已审批、贡献之和 == 该行该列；``drill/individual`` 列出各数据节点；
- 端点鉴权：非成员 403；只读成员可读、不能推送（403）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base, PermissionLevel, ProjectStatus, UserRole
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_push_models import ConsolPushRun
from app.models.consolidation_models import EliminationEntry, EliminationEntryType, ReviewStatusEnum
from app.models.core import Project, ProjectUser, User
from app.models.report_models import FinancialReport, FinancialReportType, ReportConfig

Y = 2025
D = Decimal

# 最小合并口径报表配置（两套口径各一份，行次覆盖取数、合计、跨表 ROW、留空）
_CONFIG = [
    ("balance_sheet", "BS-001", "流动资产：", 1, None),
    ("balance_sheet", "BS-002", "货币资金", 2, "TB('1001','期末余额')"),
    ("balance_sheet", "BS-006", "应收账款", 3, "TB('1122','期末余额')"),
    ("balance_sheet", "BS-015", "流动资产合计", 4, "ROW('BS-002') + ROW('BS-006')"),
    ("balance_sheet", "BS-045", "应付账款", 5, "TB('2202','期末余额')"),
    ("balance_sheet", "BS-081", "实收资本", 6, "TB('4001','期末余额')"),
    ("balance_sheet", "BS-090", "少数股东权益", 7, None),
    ("income_statement", "IS-001", "一、营业收入", 1, "SUM_TB('6001~6099','本期发生额')"),
    ("income_statement", "IS-002", "减：营业成本", 2, "SUM_TB('6401~6499','本期发生额')"),
    ("income_statement", "IS-019", "二、营业利润", 3, "ROW('IS-001') - ROW('IS-002')"),
    ("income_statement", "IS-030", "其他综合收益的税后净额", 4, "TB('4003','本期发生额')"),
    ("cash_flow_supplement", "CFSS-002", "净利润", 1, "ROW('IS-019')"),
    ("cash_flow_supplement", "CFSS-007", "无形资产摊销", 2, "TB('1702','期末余额')-TB('1702','年初余额')"),
]

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def factory():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(factory) -> AsyncSession:
    async with factory() as session:
        yield session


def _p(code, name, scope, *, parent=None, relation=None, template=None, year=Y):
    return Project(
        id=uuid.uuid4(), name=f"{name}_{year}", client_name=name, company_code=code, report_scope=scope,
        audit_year=year, parent_company_code=parent, relation_to_parent=relation, ultimate_company_code="G",
        template_type=template, status=ProjectStatus.execution,
    )


def _tb(project, code, name, category, amount, year=Y):
    return TrialBalance(
        id=uuid.uuid4(), project_id=project.id, year=year, company_code="001", standard_account_code=code,
        account_name=name, account_category=category, audited_amount=D(amount),
    )


def _entry(project, no, entry_type, lines, *, status=ReviewStatusEnum.approved, branch=None, year=Y):
    return EliminationEntry(
        id=uuid.uuid4(), project_id=project.id, year=year, entry_no=no, entry_type=entry_type,
        account_code=lines[0][0], entry_group_id=uuid.uuid4(),
        lines=[{"account_code": c, "account_name": n, "debit_amount": dr, "credit_amount": cr}
               for c, n, dr, cr in lines],
        debit_amount=sum((D(ln[2]) for ln in lines), D(0)), credit_amount=sum((D(ln[3]) for ln in lines), D(0)),
        branch_entity_code=branch, review_status=status,
    )


def _configs():
    out = []
    for standard in ("soe_consolidated", "listed_consolidated"):
        for rt, code, name, n, formula in _CONFIG:
            if standard == "listed_consolidated" and code == "BS-090":
                name = "少数股东权益（上市）"
            out.append(ReportConfig(
                id=uuid.uuid4(), report_type=FinancialReportType(rt), row_number=n, row_code=code, row_name=name,
                formula=formula, applicable_standard=standard, is_total_row=code in ("BS-015", "IS-019"),
                indent_level=0 if code in ("BS-001", "BS-015") else 1,
            ))
    return out


@pytest_asyncio.fixture
async def group(db: AsyncSession) -> dict[str, Project]:
    """G（合并+单户）⊃ 子公司 A（合并+单户）⊃ 子公司 A1（单户）；G ⊃ 子公司 B（单户）。另有上年 G 合并项目。"""
    g = {
        "G": _p("G", "某集团", "consolidated"),
        "G_s": _p("G", "某集团", "standalone"),
        "A": _p("A", "甲公司", "consolidated", parent="G", relation="subsidiary"),
        "A_s": _p("A", "甲公司", "standalone", parent="G", relation="subsidiary"),
        "A1": _p("A1", "甲一公司", "standalone", parent="A", relation="subsidiary"),
        "B": _p("B", "乙公司", "standalone", parent="G", relation="subsidiary"),
        "G24": _p("G", "某集团", "consolidated", year=Y - 1),
    }
    db.add_all(g.values())
    db.add_all(_configs())
    db.add_all([
        _tb(g["G_s"], "1001", "货币资金", AccountCategory.asset, "1000"),
        _tb(g["G_s"], "1122", "应收账款", AccountCategory.asset, "300"),
        _tb(g["G_s"], "112201", "应收账款-甲", AccountCategory.asset, "20"),
        _tb(g["G_s"], "4001", "实收资本", AccountCategory.equity, "5000"),
        _tb(g["G_s"], "1702", "累计摊销", AccountCategory.asset, "30"),
        _tb(g["A_s"], "1001", "货币资金", AccountCategory.asset, "400"),
        _tb(g["A_s"], "2202", "应付账款", AccountCategory.liability, "250"),
        _tb(g["A_s"], "6001", "主营业务收入", AccountCategory.revenue, "900"),
        _tb(g["A1"], "1122", "应收账款", AccountCategory.asset, "80"),
        _tb(g["A1"], "6401", "主营业务成本", AccountCategory.expense, "500"),
        _tb(g["B"], "2202", "应付账款", AccountCategory.liability, "60"),
        _tb(g["B"], "609901", "其他收入", AccountCategory.revenue, "7"),
        _tb(g["B"], "4003", "其他综合收益", AccountCategory.equity, "11"),
    ])
    # 上年合并报表已生成（本年上期值来源）
    db.add(FinancialReport(project_id=g["G24"].id, year=Y - 1, report_type=FinancialReportType.balance_sheet,
                           row_code="BS-002", row_name="货币资金", current_period_amount=D("888.00")))
    await db.flush()
    from app.services.group_links import sync_group_links

    for year in (Y - 1, Y):
        await sync_group_links(db, year)
    await db.commit()
    return g


async def _report(db, project, rt="balance_sheet") -> dict[str, FinancialReport]:
    rows = (await db.execute(sa.select(FinancialReport).where(
        FinancialReport.project_id == project.id, FinancialReport.year == Y,
        FinancialReport.report_type == FinancialReportType(rt), FinancialReport.is_deleted == sa.false(),
    ))).scalars().all()
    return {r.row_code: r for r in rows}


# ─────────────────────────────── 任务 3：合并报表生成 ───────────────────────────────


class TestGenerateReports:
    @pytest.mark.asyncio
    async def test_all_types_prefix_blank_and_prior(self, db, group):
        from app.services.consol_report_service import generate_consol_reports_sync

        results = await generate_consol_reports_sync(db, group["G"].id, Y)
        await db.commit()
        assert set(results) == {"balance_sheet", "income_statement", "cash_flow_supplement"}
        bs = await _report(db, group["G"])
        # 个别数汇总：G_s + A_s + A1 + B（多级合并）；TB('1122') 前缀含 112201
        assert bs["BS-002"].current_period_amount == D("1400.00")
        assert bs["BS-006"].current_period_amount == D("400.00")
        assert bs["BS-015"].current_period_amount == D("1800.00")
        assert bs["BS-045"].current_period_amount == D("310.00")
        assert bs["BS-090"].current_period_amount == D("0.00") and bs["BS-090"].blank_reason is None
        assert bs["BS-002"].prior_period_amount == D("888.00"), "上期取上年同一企业合并项目的本期值"
        assert bs["BS-006"].prior_period_amount is None, "上年没有的行 ⇒ NULL，不臆造"
        assert bs["BS-015"].is_total_row is True and bs["BS-002"].indent_level == 1
        assert bs["BS-006"].source_accounts == ["1122"]
        income = await _report(db, group["G"], "income_statement")
        # SUM_TB 区间含终点子级 609901
        assert income["IS-001"].current_period_amount == D("907.00")
        assert income["IS-019"].current_period_amount == D("407.00")
        assert income["IS-030"].current_period_amount is None and "不是损益类" in income["IS-030"].blank_reason
        supplement = await _report(db, group["G"], "cash_flow_supplement")
        assert supplement["CFSS-002"].current_period_amount == D("407.00"), "跨表 ROW"
        assert supplement["CFSS-007"].current_period_amount is None and "年初余额" in supplement["CFSS-007"].blank_reason

    @pytest.mark.asyncio
    async def test_standard_by_template_and_stale_rows_soft_deleted(self, db, group):
        from app.services.consol_report_service import generate_consol_reports_sync

        await generate_consol_reports_sync(db, group["G"].id, Y, "CAS")  # 非合并口径 ⇒ 按项目解析（soe）
        await db.commit()
        assert (await _report(db, group["G"]))["BS-090"].row_name == "少数股东权益"
        project = await db.get(Project, group["G"].id)
        project.template_type = "listed"
        db.add(FinancialReport(project_id=project.id, year=Y, report_type=FinancialReportType.balance_sheet,
                               row_code="BS-999", row_name="旧口径多出的行", current_period_amount=D("1")))
        await db.commit()
        await generate_consol_reports_sync(db, group["G"].id, Y)
        await db.commit()
        bs = await _report(db, group["G"])
        assert bs["BS-090"].row_name == "少数股东权益（上市）"
        assert "BS-999" not in bs, "当前口径已没有的行次软删，不混入报表页"
        # 再生成一次：同键复用原行（唯一索引不带 is_deleted 谓词），不重复插入
        await generate_consol_reports_sync(db, group["G"].id, Y)
        await db.commit()
        count = (await db.execute(sa.select(sa.func.count()).select_from(FinancialReport).where(
            FinancialReport.project_id == group["G"].id, FinancialReport.year == Y))).scalar_one()
        assert count == len(_CONFIG) + 1

    @pytest.mark.asyncio
    async def test_eliminations_reach_report(self, db, group):
        from app.services.consol_report_service import generate_consol_reports_sync

        db.add(_entry(group["G"], "IA-1", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "50", "0"), ("1122", "应收账款", "0", "50")]))
        db.add(_entry(group["G"], "IA-2", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "9", "0"), ("1122", "应收账款", "0", "9")], status=ReviewStatusEnum.draft))
        await db.commit()
        await generate_consol_reports_sync(db, group["G"].id, Y)
        await db.commit()
        bs = await _report(db, group["G"])
        assert (bs["BS-006"].current_period_amount, bs["BS-045"].current_period_amount) == (D("350.00"), D("260.00")), \
            "只计已审批：应收 400−50、应付 310−50"


# ─────────────────────────────── 读时计算视图（任务 5）───────────────────────────────


class TestViews:
    @pytest.mark.asyncio
    async def test_p1_p4_trial_breakdown_and_report_agree(self, db, group):
        from app.services.consol_report_service import generate_consol_reports_sync
        from app.services.consol_report_view_service import breakdown_view, load_view_context, trial_view

        db.add(_entry(group["A"], "IT-1", EliminationEntryType.internal_trade,
                      [("6001", "主营业务收入", "120", "0"), ("6401", "主营业务成本", "0", "120")]))
        db.add(_entry(group["G"], "EQ-1", EliminationEntryType.equity,
                      [("4001", "实收资本", "300", "0"), ("1001", "货币资金", "0", "300")]))
        db.add(_entry(group["G"], "OT-1", EliminationEntryType.other,
                      [("1122", "应收账款", "15", "0"), ("2202", "应付账款", "0", "15")]))
        await db.commit()
        await generate_consol_reports_sync(db, group["G"].id, Y)
        await db.commit()
        ctx = await load_view_context(db, group["G"].id)
        for rt in ("balance_sheet", "income_statement", "cash_flow_supplement"):
            report = await _report(db, group["G"], rt)
            trial = await trial_view(ctx.basis, ctx.rows, report_type=rt)
            for row in trial["rows"]:
                stored = report[row["row_code"]].current_period_amount
                assert (None if stored is None else str(stored)) == row["consolidated"], (rt, row["row_code"])
                if row["consolidated"] is not None:
                    parts = sum(D(row[k]) for k in ("individual", "elim_equity", "elim_trade", "adjustment"))
                    assert parts == D(row["consolidated"]), row
            bd = await breakdown_view(ctx.basis, ctx.rows, report_type=rt)
            # 列 = 根的直接子节点，按树序（树构建器的展示顺序）
            assert [c["node_key"] for c in bd["columns"]] == [c.node_key for c in ctx.basis.tree.children]
            assert {c["node_key"] for c in bd["columns"]} == {"G:consol_elim", "G:parent", "A:consol", "B:subsidiary"}
            for row in bd["rows"]:
                assert row["total"] == trial["rows"][[r["row_code"] for r in trial["rows"]].index(row["row_code"])]["consolidated"]
                if row["total"] is not None:
                    assert sum(D(v) for v in row["cells"].values()) == D(row["total"]), (rt, row)
        bs_trial = await trial_view(ctx.basis, ctx.rows, report_type="balance_sheet")
        by = {r["row_code"]: r for r in bs_trial["rows"]}
        # 权益抵销：借实收资本 300（贷方性质 ⇒ −300）、贷货币资金 300（⇒ −300）；报表调整：应收 +15、应付 +15
        assert (by["BS-081"]["elim_equity"], by["BS-002"]["elim_equity"]) == ("-300.00", "-300.00")
        assert (by["BS-006"]["adjustment"], by["BS-045"]["adjustment"]) == ("15.00", "15.00")
        income = {r["row_code"]: r for r in (await trial_view(ctx.basis, ctx.rows, report_type="income_statement"))["rows"]}
        # 下级合并项目 A 的内部交易抵销也进了 G（多级合并）
        assert (income["IS-001"]["elim_trade"], income["IS-002"]["elim_trade"]) == ("-120.00", "-120.00")
        a_view = await breakdown_view(ctx.basis, ctx.rows, report_type="income_statement", node_key="A:consol")
        assert [c["kind"] for c in a_view["columns"]] == ["elim", "data", "data"]

    @pytest.mark.asyncio
    async def test_drill_entries_sum_equals_cell(self, db, group):
        from app.services.consol_report_view_service import load_entry_drill, load_view_context, trial_view

        db.add(_entry(group["G"], "IA-1", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "50", "0"), ("112201", "应收账款-甲", "0", "50")]))
        db.add(_entry(group["G"], "IA-9", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "9", "0"), ("1122", "应收账款", "0", "9")], status=ReviewStatusEnum.draft))
        db.add(_entry(group["A"], "IA-A", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "7", "0"), ("1122", "应收账款", "0", "7")]))
        await db.commit()
        ctx = await load_view_context(db, group["G"].id)
        trial = {r["row_code"]: r for r in (await trial_view(ctx.basis, ctx.rows, report_type="balance_sheet"))["rows"]}
        for code in ("BS-006", "BS-015", "BS-045"):
            drill = await load_entry_drill(db, ctx, row_code=code, measure="elim_trade", node_key=None)
            assert drill["decomposable"] and drill["total"] == trial[code]["elim_trade"], code
            assert {ln["entry_no"] for ln in drill["lines"]} <= {"IA-1", "IA-A"}, "草稿不进穿透"
        drill = await load_entry_drill(db, ctx, row_code="BS-006", measure="elim_trade", node_key="A:consol")
        assert [ln["entry_no"] for ln in drill["lines"]] == ["IA-A"] and drill["total"] == "-7.00"
        assert drill["lines"][0]["node_label"] == "甲公司（合并差额）"
        # 前缀取数：112201 的明细行计入 TB('1122') 行
        drill = await load_entry_drill(db, ctx, row_code="BS-006", measure="consolidated", node_key=None)
        assert {ln["account_code"] for ln in drill["lines"]} == {"112201", "1122"}


# ─────────────────────────────── 推送（任务 4）───────────────────────────────


async def _runs(factory, project_id: uuid.UUID) -> list[ConsolPushRun]:
    """独立会话读运行记录。传 id 不传 ORM 对象：推送里某步回滚会让测试会话里的对象过期，异步会话不能懒加载。"""
    async with factory() as s:
        return list((await s.execute(sa.select(ConsolPushRun).where(ConsolPushRun.project_id == project_id)
                                     .order_by(ConsolPushRun.started_at))).scalars().all())


class TestPush:
    @pytest.mark.asyncio
    async def test_upper_levels_pushed_bottom_up(self, db, group, factory):
        from app.services.consol_push_service import push, push_targets

        assert await push_targets(db, group["A"].id) == [group["A"].id, group["G"].id]
        assert await push_targets(db, group["G"].id) == [group["G"].id]
        db.add(ConsolNoteData(project_id=group["G"].id, year=Y, section_id="五-1", data={}))
        db.add(_entry(group["A"], "IA-A", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "7", "0"), ("1122", "应收账款", "0", "7")]))
        await db.commit()
        with patch("app.services.event_bus.event_bus.broadcast_raw") as sse:
            result = await push(db, group["A"].id, Y, trigger="elimination_approved")
        assert result.status == "succeeded", result.steps
        assert result.pushed_projects == [str(group["A"].id), str(group["G"].id)]
        assert [s["project_id"] for s in result.steps] == [str(group["A"].id)] * 4 + [str(group["G"].id)] * 4
        a_bs, g_bs = await _report(db, group["A"]), await _report(db, group["G"])
        assert a_bs["BS-006"].current_period_amount == D("73.00")   # A1 80 − 7
        assert g_bs["BS-006"].current_period_amount == D("393.00")  # 400 − 7（上层纳入下级抵销）
        note = (await db.execute(sa.select(ConsolNoteData))).scalar_one()
        await db.refresh(note)
        assert note.is_stale is True
        events = [(c.args[0], c.args[1]["project_id"]) for c in sse.call_args_list]
        assert events == [("consol.pushed", str(group["A"].id)), ("consol.pushed", str(group["G"].id))]
        (run,) = await _runs(factory, group["A"].id)
        assert (run.status, run.trigger_source) == ("succeeded", "elimination_approved") and run.finished_at

    @pytest.mark.asyncio
    async def test_critical_failure_skips_rest_and_is_recorded(self, db, group, factory):
        from app.services.consol_push_service import push
        from app.services.consol_trial_service import recalculate_trial as real

        a_id, g_id = group["A"].id, group["G"].id

        async def flaky(session, project_id, year):
            if project_id == a_id:
                raise RuntimeError("试算写入冲突")
            return await real(session, project_id, year)

        with patch("app.services.consol_trial_service.recalculate_trial", new=flaky), \
             patch("app.services.event_bus.event_bus.broadcast_raw") as sse:
            result = await push(db, a_id, Y, trigger="manual")
        assert result.status == "partial"
        a_steps = {s["step"]: s["status"] for s in result.steps if s["project_id"] == str(a_id)}
        assert a_steps == {"worksheet": "succeeded", "trial": "failed", "report": "skipped", "notes": "skipped"}
        assert all(s["status"] == "succeeded" for s in result.steps if s["project_id"] == str(g_id))
        assert any("甲公司" in w and "重算合并试算失败" in w for w in result.warnings)
        assert result.pushed_projects == [str(g_id)]
        (run,) = await _runs(factory, a_id)
        assert run.status == "partial" and any(s["detail"] and "试算写入冲突" in s["detail"] for s in run.steps)
        assert sse.call_args_list[0].args[0] == "consol.pushed"

    @pytest.mark.asyncio
    async def test_all_failed_broadcasts_failure(self, db, group, factory):
        from app.services.consol_push_service import push

        g_id = group["G"].id
        with patch("app.services.consol_worksheet_engine.recalc_full", new=AsyncMock(side_effect=RuntimeError("库不可写"))), \
             patch("app.services.event_bus.event_bus.broadcast_raw") as sse:
            result = await push(db, g_id, Y)
        assert result.status == "failed" and result.pushed_projects == []
        assert sse.call_args.args[0] == "consol.push_failed"
        (run,) = await _runs(factory, g_id)
        assert run.status == "failed" and "库不可写" in run.warnings[0]
        assert [s["status"] for s in run.steps] == ["failed", "skipped", "skipped", "skipped"]

    @pytest.mark.asyncio
    async def test_request_push_coalesces_queued(self, db, group, factory):
        from app.services import consol_push_service as svc

        g_id = group["G"].id
        with patch("app.core.database.async_session", factory), \
             patch("app.services.event_bus.event_bus.broadcast_raw"):
            first = svc.request_push(g_id, Y, trigger="manual")
            second = svc.request_push(g_id, Y, trigger="elimination_approved")
            assert first is not None and second is None, "排队未开始的同键推送合并为一次"
            await svc.wait_for_pushes()
        runs = await _runs(factory, g_id)
        assert [r.trigger_source for r in runs] == ["elimination_approved"], "以最后一次触发记账，只跑一次"
        with pytest.raises(ValueError):
            svc.request_push(g_id, Y, trigger="bogus")


# ─────────────────────────────── 端点（审批 → 推送 → 撤销审批回退；鉴权）───────────────────────────────


class _User:
    def __init__(self, role: UserRole):
        self.id = uuid.uuid4()
        self.username = f"u_{role.value}_{self.id.hex[:6]}"
        self.role = role
        self.is_active = True
        self.is_deleted = False


async def _persist(db, user: _User, memberships=()):
    db.add(User(id=user.id, username=user.username, email=f"{user.id.hex[:8]}@t.local",
                hashed_password="x", role=user.role))
    for project, level in memberships:
        db.add(ProjectUser(project_id=project.id, user_id=user.id, role="auditor", permission_level=level))
    await db.commit()
    return user


@pytest_asyncio.fixture
async def client_for(db):
    from app.routers.consol_push import router as push_router
    from app.routers.consol_report import router as report_router
    from app.routers.consol_worksheet import router as worksheet_router
    from app.routers.consolidation import router as elim_router

    app = FastAPI()
    for r in (push_router, report_router, worksheet_router, elim_router):
        app.include_router(r)

    async def _db():
        yield db

    def make(user):
        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return make


def _payload(project):
    return {
        "project_id": str(project.id), "year": Y, "entry_type": "internal_ar_ap", "description": "推送测试",
        "lines": [
            {"account_code": "2202", "account_name": "应付账款", "debit_amount": "50", "credit_amount": "0"},
            {"account_code": "1122", "account_name": "应收账款", "debit_amount": "0", "credit_amount": "50"},
        ],
    }


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_approve_push_revoke_roundtrip(self, db, group, client_for, factory):
        """P8：审批 → 推送（报表 −50）→ 撤销审批 → 推送（回到审批前）；审计日志两条；锁定时撤销 423。"""
        from app.models.audit_log_models import AuditLogEntry
        from app.services.consol_elimination_recalc_handler import (
            handle_elimination_approved,
            handle_elimination_revoked,
        )

        admin = _User(UserRole.admin)
        gid = str(group["G"].id)
        published = []

        async def capture(payload):
            published.append(payload)

        with patch("app.services.event_bus.event_bus.publish", new=capture), \
             patch("app.core.database.async_session", factory), \
             patch("app.services.event_bus.event_bus.broadcast_raw"):
            async with client_for(admin) as c:
                base = (await c.post("/api/consolidation/reports/generate", params={"project_id": gid},
                                     json={"project_id": gid, "year": Y, "applicable_standard": "CAS"})).json()
                assert base["applicable_standard"] == "soe_consolidated" and "不是合并口径" in base["standard_note"]
                assert base["blank_counts"] == {"income_statement": 1, "cash_flow_supplement": 1}
                before = (await c.get(f"/api/consolidation/reports/{gid}/{Y}",
                                      params={"report_type": "balance_sheet"})).json()
                before_ar = next(r for r in before if r["row_code"] == "BS-006")["current_period_amount"]
                eid = (await c.post(f"/api/consolidation/eliminations?project_id={gid}", json=_payload(group["G"]))).json()["id"]
                resp = await c.post(f"/api/consolidation/eliminations/{eid}/review?project_id={gid}", json={"action": "approve"})
                assert resp.status_code == 200 and resp.json()["review_status"] == "approved"
                await handle_elimination_approved(published[-1])
                after = (await c.get(f"/api/consolidation/reports/{gid}/{Y}", params={"report_type": "balance_sheet"})).json()
                assert D(next(r for r in after if r["row_code"] == "BS-006")["current_period_amount"]) == D(before_ar) - 50

                project = await db.get(Project, group["G"].id)
                project.consol_lock = True
                await db.commit()
                locked = await c.post(f"/api/consolidation/eliminations/{eid}/review?project_id={gid}", json={"action": "revoke"})
                assert locked.status_code == 423 and "已合并锁定" in locked.json()["detail"]
                project.consol_lock = False
                await db.commit()

                revoked = await c.post(f"/api/consolidation/eliminations/{eid}/review?project_id={gid}", json={"action": "revoke"})
                assert revoked.status_code == 200 and revoked.json()["review_status"] == "draft"
                assert published[-1].event_type.value == "elimination.revoked"
                await handle_elimination_revoked(published[-1])
                back = (await c.get(f"/api/consolidation/reports/{gid}/{Y}", params={"report_type": "balance_sheet"})).json()
                assert next(r for r in back if r["row_code"] == "BS-006")["current_period_amount"] == before_ar
                again = await c.post(f"/api/consolidation/eliminations/{eid}/review?project_id={gid}", json={"action": "revoke"})
                assert again.status_code == 400 and "只有已审批" in again.json()["detail"]

                runs = (await c.get(f"/api/consolidation/{gid}/{Y}/push-runs")).json()["runs"]
                assert [r["trigger_source"] for r in runs] == ["elimination_revoked", "elimination_approved"]
                assert runs[0]["trigger_label"] == "撤销审批" and runs[0]["status"] == "succeeded"
        actions = (await db.execute(sa.select(AuditLogEntry.action_type).where(
            AuditLogEntry.object_id == uuid.UUID(eid)))).scalars().all()
        assert sorted(actions) == ["consol.elimination.approve", "consol.elimination.revoke"]

    @pytest.mark.asyncio
    async def test_view_endpoints_and_manual_push(self, db, group, client_for, factory):
        admin = _User(UserRole.admin)
        gid = str(group["G"].id)
        db.add(_entry(group["G"], "IA-1", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "50", "0"), ("1122", "应收账款", "0", "50")]))
        await db.commit()
        with patch("app.core.database.async_session", factory), \
             patch("app.services.event_bus.event_bus.broadcast_raw"):
            async with client_for(admin) as c:
                trial = await c.get("/api/consolidation/worksheet/report-trial",
                                    params={"project_id": gid, "report_type": "balance_sheet"})
                assert trial.status_code == 200, trial.text
                body = trial.json()
                assert [(col["key"], col["label"]) for col in body["columns"]] == [
                    ("individual", "审定汇总"), ("elim_equity", "权益抵销"), ("elim_trade", "往来交易抵销"),
                    ("adjustment", "报表调整"), ("consolidated", "合并审定数"),
                ], "列键与列名一一对应（前端按键取值、按名显示）"
                row = next(r for r in body["rows"] if r["row_code"] == "BS-006")
                assert (row["individual"], row["elim_trade"], row["consolidated"]) == ("400.00", "-50.00", "350.00")
                bd = (await c.get("/api/consolidation/worksheet/report-breakdown",
                                  params={"project_id": gid, "report_type": "balance_sheet"})).json()
                assert [n["node_key"] for n in bd["aggregate_nodes"]] == ["G:consol", "A:consol"]
                assert next(r for r in bd["rows"] if r["row_code"] == "BS-006")["cells"]["G:consol_elim"] == "-50.00"
                bad = await c.get("/api/consolidation/worksheet/report-breakdown",
                                  params={"project_id": gid, "node_key": "B:subsidiary"})
                assert bad.status_code == 400 and "不是汇总节点" in bad.json()["detail"]
                missing = await c.get("/api/consolidation/worksheet/report-trial",
                                      params={"project_id": gid, "node_key": "NOPE:consol"})
                assert missing.status_code == 404
                drill = (await c.get("/api/consolidation/worksheet/drill/entries",
                                     params={"project_id": gid, "row_code": "BS-006", "measure": "elim_trade"})).json()
                assert drill["total"] == "-50.00" and [ln["entry_no"] for ln in drill["lines"]] == ["IA-1"]
                wrong = await c.get("/api/consolidation/worksheet/drill/entries",
                                    params={"project_id": gid, "row_code": "BS-006", "measure": "individual"})
                assert wrong.status_code == 400
                ind = (await c.get("/api/consolidation/worksheet/drill/individual",
                                   params={"project_id": gid, "row_code": "BS-006"})).json()
                assert {r["node_key"]: r["amount"] for r in ind["rows"]} == {
                    "G:parent": "320.00", "A:parent": "0.00", "A1:subsidiary": "80.00", "B:subsidiary": "0.00",
                }
                pushed = await c.post(f"/api/consolidation/{gid}/{Y}/push", json={"trigger": "manual"})
                assert pushed.status_code == 200 and pushed.json()["queued"] is True
                from app.services.consol_push_service import wait_for_pushes

                await wait_for_pushes()
                status = (await c.get(f"/api/consolidation/{gid}/{Y}/push-status")).json()
                assert status["last_run"]["status"] == "succeeded" and status["is_stale"] is False
                not_consol = await c.post(f"/api/consolidation/{group['B'].id}/{Y}/push")
                assert not_consol.status_code == 400
                bogus = await c.post(f"/api/consolidation/{gid}/{Y}/push", json={"trigger": "elimination_approved"})
                assert bogus.status_code == 400

    @pytest.mark.asyncio
    async def test_auth(self, db, group, client_for):
        outsider = await _persist(db, _User(UserRole.auditor))
        reader = await _persist(db, _User(UserRole.auditor), [(group["G"], PermissionLevel.readonly)])
        gid = str(group["G"].id)
        reads = [
            ("GET", "/api/consolidation/worksheet/report-trial", {"project_id": gid}),
            ("GET", "/api/consolidation/worksheet/report-breakdown", {"project_id": gid}),
            ("GET", "/api/consolidation/worksheet/drill/entries", {"project_id": gid, "row_code": "BS-006", "measure": "elim_trade"}),
            ("GET", "/api/consolidation/worksheet/drill/individual", {"project_id": gid, "row_code": "BS-006"}),
            ("GET", f"/api/consolidation/{gid}/{Y}/push-runs", {}),
            ("GET", f"/api/consolidation/{gid}/{Y}/push-status", {}),
        ]
        async with client_for(outsider) as c:
            for method, url, params in reads:
                assert (await c.request(method, url, params=params)).status_code == 403, url
            assert (await c.post(f"/api/consolidation/{gid}/{Y}/push")).status_code == 403
        async with client_for(reader) as c:
            for method, url, params in reads:
                assert (await c.request(method, url, params=params)).status_code == 200, url
            assert (await c.post(f"/api/consolidation/{gid}/{Y}/push")).status_code == 403, "只读成员不能推送"
            gen = await c.post("/api/consolidation/reports/generate", params={"project_id": gid},
                               json={"project_id": gid, "year": Y})
            assert gen.status_code == 403
