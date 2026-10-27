"""报表源与报表行次真 PG 回归（advanced-query-linkage-closure 任务 17；R5.1、R5.3、R5.8；design §3.1、§10.2；
变异 #8、#20、B5-a）。

改造前（AQ-01 / AQ-08）：报表源的结构按 ``template_type`` 拼准则（国企合并项目拿到单体结构），金额取自全库 0 行的
``report_snapshot``——华氏资产负债表 129 行本期 / 上期金额全为空；报表行次源按不存在的 ``sort_order`` 排序，恒 500。

现在：结构 = 项目适用准则的行 ∪ 本项目独有的 ``project:{项目}`` 行（准则取报表生成用的
``ReportConfigService.resolve_applicable_standard``，覆盖行的结构仍取准则行），金额 LEFT JOIN 项目已生成的
``financial_report``；未生成 / 有过期行时写 warnings。报表行次只含准则行与本项目副本行，按准则、报表类型、行号排序。

请求经生产注册的 custom_query router（夹具 ``business``，系统管理员、真库回滚事务会话）；金标准用独立 SQL 现算。
需要「项目独有行 / 覆盖行」形态时在回滚事务里新建【测试】项目，复制华氏的 financial_report 行（华氏只读）。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.base import ProjectStatus
from app.models.core import Project
from app.models.report_models import FinancialReportType, ReportConfig
from app.services.formula_settings.effective_report import load_effective_report_configs
from app.services.report_config_service import ReportConfigService
from tests.advanced_query_linkage.gold import AUDIT_YEAR, HS, UA, UB

pytestmark = pytest.mark.pg_only

REPORT_TYPES = [t.value for t in FinancialReportType]
NOT_GENERATED = "该项目尚未生成此报表"
STALE = "报表数据已过期"
_STANDARD_SQL = ("SELECT coalesce(template_type, 'soe') || '_' || coalesce(report_scope, 'standalone') "
                 "FROM projects WHERE id = :pid")
_STRUCTURE_SQL = ("SELECT rc.row_code, fr.current_period_amount, fr.prior_period_amount FROM report_config rc "
                  "LEFT JOIN financial_report fr ON fr.project_id = :pid AND fr.year = :year "
                  "AND fr.report_type = rc.report_type AND fr.row_code = rc.row_code AND NOT fr.is_deleted "
                  "WHERE rc.applicable_standard = :std AND rc.report_type::text = :rt AND NOT rc.is_deleted")


def _money(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _has(warnings: list[str], text: str) -> bool:
    return any(text in w for w in warnings)


async def test_hs_balance_sheet_amounts_come_from_financial_report(business, gold) -> None:
    std = await gold.scalar(_STANDARD_SQL, pid=HS)
    expected = {code: (cur, pri) for code, cur, pri in await gold.rows(
        _STRUCTURE_SQL, pid=HS, year=AUDIT_YEAR, std=std, rt="balance_sheet")}
    cash = await gold.scalar(
        "SELECT current_period_amount FROM financial_report WHERE project_id = :pid AND year = :year "
        "AND report_type::text = 'balance_sheet' AND row_code = 'BS-002' AND NOT is_deleted", pid=HS, year=AUDIT_YEAR)
    assert cash is not None and len(expected) > 100, "前置：华氏已生成资产负债表"
    data, rows = await business.all_rows(HS, "report_balance_sheet", filters={"report_type": "balance_sheet"})
    by_code = {r["row_code"]: r for r in rows}
    assert data["total"] == len(rows) == len(expected) and by_code.keys() == expected.keys()
    assert _money(by_code["BS-002"]["current_period_amount"]) == cash, "货币资金本期 = financial_report 值"
    for code, (cur, pri) in expected.items():
        got = by_code[code]
        assert (_money(got["current_period_amount"]), _money(got["prior_period_amount"])) == (cur, pri), code
    assert data["columns"][:4] == ["row_code", "row_name", "current_period_amount", "prior_period_amount"]
    numbers = [r["row_number"] for r in rows]
    assert numbers == sorted(numbers), "按行号排序"
    assert data["meta"]["ref_context"] == {"template_type": "soe", "year": AUDIT_YEAR}


@pytest.mark.parametrize("report_type", REPORT_TYPES)
async def test_each_report_type_follows_the_source_key(business, gold, report_type: str) -> None:
    std = await gold.scalar(_STANDARD_SQL, pid=HS)
    expected = await gold.rows(_STRUCTURE_SQL, pid=HS, year=AUDIT_YEAR, std=std, rt=report_type)
    with_amount = sum(1 for _code, cur, _pri in expected if cur is not None)
    data, rows = await business.all_rows(HS, f"report_{report_type}")
    assert data["total"] == len(rows) == len(expected), report_type
    assert sum(1 for r in rows if r["current_period_amount"] is not None) == with_amount, report_type


async def test_warnings_follow_generation_and_staleness(business, gold) -> None:
    generated = {r[0] for r in await gold.rows(
        "SELECT DISTINCT report_type::text FROM financial_report WHERE project_id = :pid AND year = :year "
        "AND NOT is_deleted", pid=HS, year=AUDIT_YEAR)}
    stale = {r[0] for r in await gold.rows(
        "SELECT DISTINCT report_type::text FROM financial_report WHERE project_id = :pid AND year = :year "
        "AND is_stale AND NOT is_deleted", pid=HS, year=AUDIT_YEAR)}
    assert stale and generated - stale, "前置：华氏既有带过期行的报表、也有不带的"
    for report_type in REPORT_TYPES:
        data = await business.ok(HS, f"report_{report_type}", limit=1)
        assert _has(data["warnings"], STALE) == (report_type in stale), (report_type, data["warnings"])
        assert _has(data["warnings"], NOT_GENERATED) == (report_type not in generated), (report_type, data["warnings"])


async def test_project_without_report_returns_structure_with_empty_amounts(business, gold) -> None:
    assert await gold.scalar("SELECT count(*) FROM financial_report WHERE project_id = :pid AND NOT is_deleted",
                             pid=UA) == 0, "前置：【UAT】子公司A 没有生成报表"
    std = await gold.scalar(_STANDARD_SQL, pid=UA)
    expected = await gold.scalar("SELECT count(*) FROM report_config WHERE applicable_standard = :std "
                                 "AND report_type::text = 'balance_sheet' AND NOT is_deleted", std=std)
    data, rows = await business.all_rows(UA, "report_balance_sheet")
    assert data["total"] == len(rows) == expected > 0
    assert all(r["current_period_amount"] is None and r["prior_period_amount"] is None for r in rows)
    assert _has(data["warnings"], NOT_GENERATED), data["warnings"]


async def test_project_rows_join_the_standard_structure(business, gold) -> None:
    """回滚事务：【测试】项目复制华氏报表结果，再加一条覆盖行与一条独有行（R5.1；变异 #20）。"""
    session = business.session
    test_pid = uuid.uuid4()
    hs = await session.get(Project, HS)
    session.add(Project(id=test_pid, name="【测试】AQL-B5 报表源结构", client_name="【测试】AQL-B5",
                        status=ProjectStatus.created, template_type=hs.template_type, report_scope=hs.report_scope))
    await session.flush()
    await session.execute(sa.text(
        "INSERT INTO financial_report (id, project_id, year, report_type, row_code, row_name, current_period_amount, "
        "prior_period_amount, indent_level, is_total_row, is_stale, blank_reason, is_deleted) "
        "SELECT gen_random_uuid(), :tp, year, report_type, row_code, row_name, current_period_amount, "
        "prior_period_amount, indent_level, is_total_row, is_stale, blank_reason, is_deleted "
        "FROM financial_report WHERE project_id = :hs AND year = :year AND NOT is_deleted"),
        {"tp": test_pid, "hs": HS, "year": AUDIT_YEAR})
    own = f"project:{test_pid}"
    session.add(ReportConfig(report_type=FinancialReportType.balance_sheet, row_number=2, row_code="BS-002",
                             row_name="【测试】覆盖行（结构仍取准则行）", applicable_standard=own,
                             formula="TB('1001','期末余额')"))
    session.add(ReportConfig(report_type=FinancialReportType.balance_sheet, row_number=9999, row_code="BS-AQLB5",
                             row_name="【测试】本项目独有行", applicable_standard=own))
    await session.flush()

    std = await ReportConfigService.resolve_applicable_standard(session, test_pid)
    effective = await load_effective_report_configs(session, standard=std, project_id=test_pid,
                                                    report_type=FinancialReportType.balance_sheet)
    data, rows = await business.all_rows(test_pid, "report_balance_sheet")
    assert [r["row_code"] for r in rows] == [c.row_code for c in effective], "结构与报表生成同口径（含顺序）"
    by_code = {r["row_code"]: r for r in rows}
    own_row = by_code["BS-AQLB5"]
    assert own_row["row_name"] == "【测试】本项目独有行"
    assert own_row["current_period_amount"] is None and own_row["prior_period_amount"] is None, "独有行没有生成结果"
    standard_name = await gold.scalar("SELECT row_name FROM report_config WHERE applicable_standard = :std "
                                      "AND report_type::text = 'balance_sheet' AND row_code = 'BS-002'", std=std)
    hs_cash = await gold.scalar(
        "SELECT current_period_amount FROM financial_report WHERE project_id = :pid AND year = :year "
        "AND report_type::text = 'balance_sheet' AND row_code = 'BS-002' AND NOT is_deleted", pid=HS, year=AUDIT_YEAR)
    assert by_code["BS-002"]["row_name"] == standard_name, "覆盖行的结构取准则行"
    assert _money(by_code["BS-002"]["current_period_amount"]) == hs_cash
    assert data["total"] == len(rows) == len(effective)


async def test_live_projects_structure_equals_effective_configs(business) -> None:
    """各真实活项目（只读）：报表源 (报表类型, 行次码) 集合 == ``load_effective_report_configs``（含合并项目）。"""
    session = business.session
    live = list((await session.execute(sa.select(Project.id).where(Project.is_deleted.is_(False)))).scalars())
    assert len(live) > 10
    mismatches: list[str] = []
    for pid in live:
        std = await ReportConfigService.resolve_applicable_standard(session, pid)
        expected = {(c.report_type.value, c.row_code, c.row_name)
                    for c in await load_effective_report_configs(session, standard=std, project_id=pid)}
        got: set[tuple[str, str, str]] = set()
        for report_type in REPORT_TYPES:
            data = await business.ok(pid, f"report_{report_type}", limit=2000)
            assert data["total"] == len(data["rows"]), (pid, report_type)
            got |= {(report_type, r["row_code"], r["row_name"]) for r in data["rows"]}
        if got != expected:
            mismatches.append(f"{pid} 准则 {std}：多 {len(got - expected)} 行、少 {len(expected - got)} 行")
    assert not mismatches, mismatches[:5]


async def test_standard_follows_project_type_and_scope(business, gold) -> None:
    """准则 = 报表生成同一函数（模板类型 + 报表范围）；回滚事务里新建上市合并的【测试】项目（变异 B5-e）。

    现库活项目只有国企单体与一个国企合并，两套国企结构逐行相同，取错准则看不出来；上市单体 / 合并的权益变动表行数不同。
    """
    consolidated = await gold.scalar("SELECT count(*) FROM report_config WHERE applicable_standard = 'listed_consolidated' "
                                     "AND report_type::text = 'equity_statement' AND NOT is_deleted")
    standalone = await gold.scalar("SELECT count(*) FROM report_config WHERE applicable_standard = 'listed_standalone' "
                                   "AND report_type::text = 'equity_statement' AND NOT is_deleted")
    assert consolidated != standalone, "前置：上市单体 / 合并的权益变动表行数不同"
    test_pid = uuid.uuid4()
    business.session.add(Project(id=test_pid, name="【测试】AQL-B5 上市合并准则", client_name="【测试】AQL-B5",
                                 status=ProjectStatus.created, template_type="listed", report_scope="consolidated"))
    await business.session.flush()
    data = await business.ok(test_pid, "report_equity_statement", limit=1)
    assert data["total"] == consolidated, "上市合并项目取上市合并结构"
    assert data["meta"]["ref_context"]["template_type"] == "listed"


async def test_report_conditions_are_evaluated_in_database(business, gold) -> None:
    expected = await gold.scalar(
        "SELECT count(*) FROM financial_report WHERE project_id = :pid AND year = :year "
        "AND report_type::text = 'balance_sheet' AND NOT is_deleted AND current_period_amount > 100000000",
        pid=HS, year=AUDIT_YEAR)
    assert expected > 0
    data = await business.ok(HS, "report_balance_sheet", limit=2000,
                             conditions=[{"field": "current_period_amount", "op": "gt", "value": 100000000}])
    assert data["total"] == len(data["rows"]) == expected
    assert all(_money(r["current_period_amount"]) > 100000000 for r in data["rows"])


async def test_generic_report_source_defaults_to_balance_sheet(business, gold) -> None:
    std = await gold.scalar(_STANDARD_SQL, pid=HS)
    bs = await gold.scalar("SELECT count(*) FROM report_config WHERE applicable_standard = :std "
                           "AND report_type::text = 'balance_sheet' AND NOT is_deleted", std=std)
    income = await gold.scalar("SELECT count(*) FROM report_config WHERE applicable_standard = :std "
                               "AND report_type::text = 'income_statement' AND NOT is_deleted", std=std)
    assert (await business.ok(HS, "report", limit=1))["total"] == bs
    generic = await business.ok(HS, "report", limit=1, filters={"report_type": "income_statement"})
    assert generic["total"] == income


@pytest.mark.parametrize(("source", "filters", "code"), [
    ("report", {"report_type": "nope"}, "INVALID_FILTER_VALUE"),
    ("report_balance_sheet", {"standard": f"project:{UB}"}, "INVALID_FILTER_VALUE"),
    ("report_nope", {}, "UNKNOWN_SOURCE"),
    ("report_balance_sheet", {"row_code": "BS-002"}, "UNKNOWN_FILTER_KEY"),
], ids=["bad-type", "other-project-standard", "bad-key", "unknown-filter"])
async def test_report_inputs_are_validated(business, source: str, filters: dict, code: str) -> None:
    detail = await business.error(HS, source, 400, filters=filters)
    assert detail["error_code"] == code and detail["message"], detail


# ─── 报表行次（R5.3；变异 B5-a）──────────────────────────────────────────────


async def test_report_lines_are_standard_rows_in_row_order(business, gold) -> None:
    expected = [str(r[0]) for r in await gold.rows(
        "SELECT id FROM report_config WHERE NOT is_deleted AND (applicable_standard NOT LIKE 'project:%' "
        "OR applicable_standard = 'project:' || :pid) ORDER BY applicable_standard, report_type, row_number, id",
        pid=str(HS))]
    assert len(expected) > 1000
    data, rows = await business.all_rows(HS, "report_lines")
    assert [r["id"] for r in rows] == expected, "只含准则行与本项目副本行，按准则、报表类型、行号排序"
    assert data["total"] == len(expected)
    assert "row_number" in data["columns"] and "sort_order" not in data["columns"]


async def test_report_lines_show_only_own_project_copies(business, gold) -> None:
    session = business.session
    for pid, code in ((UA, "BS-AQLB5-A"), (UB, "BS-AQLB5-B")):
        session.add(ReportConfig(report_type=FinancialReportType.balance_sheet, row_number=9998, row_code=code,
                                 row_name="【测试】报表行次副本行", applicable_standard=f"project:{pid}"))
    await session.flush()
    base = await gold.scalar("SELECT count(*) FROM report_config WHERE NOT is_deleted "
                             "AND applicable_standard NOT LIKE 'project:%'")
    data, rows = await business.all_rows(UA, "report_lines", filters={"report_type": "balance_sheet"})
    codes = {r["row_code"] for r in rows}
    assert "BS-AQLB5-A" in codes and "BS-AQLB5-B" not in codes, "他项目副本行不可见"
    filtered = await business.ok(UA, "report_lines", limit=1, filters={"applicable_standard": f"project:{UA}"})
    assert filtered["total"] == 1
    whole = await business.ok(UA, "report_lines", limit=1)
    assert whole["total"] == base + 1
