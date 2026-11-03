"""JOIN 基数守卫真 PG（advanced-query-linkage-closure 任务 10；R3.4；ADR-AQL-09；变异 #6、B3-g）。

逐条覆盖保留的 11 条登记（参数取自 ``JOIN_WHITELIST`` 本身，新增登记自动进入本守卫）：

- 多对一：在全部未删项目上，``基表 LEFT JOIN 目标`` 的行数 = 基表行数，且确有匹配行（防「从来没匹配上」的空转）；
- 一对多：结果 warnings 带「该关联为一对多，结果行数可能多于基表行数」，schema 下发 ``one_to_many``；
- 已删除的「报表行次映射 → 报表配置」登记 ⇒ 400 ``JOIN_NOT_REGISTERED``；
- 华氏 ``trial_balance LEFT JOIN account_chart`` = 试算表行数（只按科目码关联时为两倍：科目表 standard / client 各一套）。

请求经生产注册的 query_builder router（夹具 ``builder``，真库回滚事务会话、系统管理员）；金标准用独立 SQL 现算。现库
工时表没有行、调整分录只有 2 行且对不上试算表：在回滚事务里给【UAT】子公司A 造工时两行与一条调整分录（另造同科目的
上年试算行与另一公司代码的试算行——调整分录 → 试算表的 ON 若漏了年度 / 公司代码，这一条会匹配三行）。
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.audit_platform_models import AccountCategory, Adjustment, AdjustmentType, TrialBalance
from app.models.core import User
from app.models.staff_models import StaffMember, WorkHour
from app.services.custom_query.table_whitelist import JOIN_WHITELIST, ONE_TO_MANY_WARNING
from tests.advanced_query_linkage.gold import AUDIT_YEAR, HS, UA

pytestmark = pytest.mark.pg_only

M2O = sorted((base, target) for base, targets in JOIN_WHITELIST.items()
             for target, spec in targets.items() if spec["cardinality"] == "many_to_one")
O2M = sorted((base, target) for base, targets in JOIN_WHITELIST.items()
             for target, spec in targets.items() if spec["cardinality"] == "one_to_many")
UA_COMPANY = "UAT_SUB_A"


def test_every_registration_is_covered() -> None:
    assert len(M2O) + len(O2M) == 11 and len(O2M) == 3, (M2O, O2M)


async def _seed_ua(builder) -> None:
    """回滚事务里给【UAT】子公司A 造工时两行、一条调整分录，及同科目的上年 / 另一公司代码试算行。"""
    session = builder.session
    creator = (await session.execute(select(User.id).where(User.username == "admin"))).scalar_one()
    staff = StaffMember(name="【测试】B3 基数守卫人员")
    session.add(staff)
    await session.flush()
    for day in (1, 2):
        session.add(WorkHour(staff_id=staff.id, project_id=UA, work_date=date(AUDIT_YEAR, 6, day), hours=Decimal("1.5"),
                             description="【UAT】B3 回滚事务造行"))
    for year, company in ((AUDIT_YEAR - 1, UA_COMPANY), (AUDIT_YEAR, "AQLB3-OTHER-CO")):
        session.add(TrialBalance(project_id=UA, year=year, company_code=company, standard_account_code="1001",
                                 account_name="库存现金", account_category=AccountCategory.asset))
    session.add(Adjustment(project_id=UA, year=AUDIT_YEAR, company_code=UA_COMPANY, adjustment_no="AQLB3-AJE-1",
                           adjustment_type=AdjustmentType.aje, account_code="1001", account_name="库存现金",
                           debit_amount=Decimal("1.00"), credit_amount=Decimal("0"), entry_group_id=uuid.uuid4(),
                           created_by=creator))
    await session.flush()


def _count_body(base: str, target: str | None = None) -> dict:
    body: dict = {"table": base, "aggregates": [{"func": "count", "field": "*", "alias": "n"}]}
    if target is not None:
        body["joins"] = [{"table": target, "type": "left"}]
        body["aggregates"].append({"func": "count", "field": f"{target}.id", "alias": "matched"})
    return body


@pytest.mark.parametrize(("base", "target"), M2O, ids=[f"{b}->{t}" for b, t in M2O])
async def test_many_to_one_left_join_keeps_the_base_row_count(builder, base: str, target: str) -> None:
    await _seed_ua(builder)
    (plain,) = (await builder.ok(builder.admin, _count_body(base)))["rows"]
    joined_data = await builder.ok(builder.admin, _count_body(base, target))
    (joined,) = joined_data["rows"]
    assert plain["n"] > 0, f"{base} 在未删项目上没有行，守卫空转"
    assert joined["n"] == plain["n"], f"{base} LEFT JOIN {target}：{joined['n']} 行 ≠ 基表 {plain['n']} 行（多对一被放大）"
    assert joined["matched"] > 0, f"{base} LEFT JOIN {target} 一行都没匹配上，守卫空转"
    assert not any(ONE_TO_MANY_WARNING in w for w in joined_data["warnings"]), joined_data["warnings"]


@pytest.mark.parametrize(("base", "target"), O2M, ids=[f"{b}->{t}" for b, t in O2M])
async def test_one_to_many_join_is_flagged_in_schema_and_results(builder, base: str, target: str) -> None:
    await _seed_ua(builder)
    data = await builder.ok(builder.admin, _count_body(base, target))
    assert any(ONE_TO_MANY_WARNING in w for w in data["warnings"]), data["warnings"]
    schema = await builder.request(builder.admin, "GET", "/schema")
    assert schema.status_code == 200, schema.text
    (table,) = [t for t in schema.json()["tables"] if t["name"] == base]
    assert {j["target_table"]: j["cardinality"] for j in table["joins"]}[target] == "one_to_many"


async def test_removed_registration_is_rejected(builder) -> None:
    response = await builder.execute(builder.admin, {
        "table": "report_line_mapping", "joins": [{"table": "report_config", "type": "left"}],
        "fields": ["report_line_mapping.report_line_code"]})
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["error_code"] == "JOIN_NOT_REGISTERED"


async def test_hs_trial_balance_left_join_account_chart_keeps_100_rows(builder, gold) -> None:
    """华氏：只按科目码关联时一行试算命中 standard / client 两行科目（金标准两倍）；登记的目标条件只认标准科目。"""
    base_sql = "FROM trial_balance t {join} WHERE t.project_id = :pid AND t.year = :year AND NOT t.is_deleted"
    on = "LEFT JOIN account_chart c ON c.project_id = t.project_id AND c.account_code = t.standard_account_code"
    expected = await gold.scalar("SELECT count(*) " + base_sql.format(join=""), pid=HS, year=AUDIT_YEAR)
    any_source = await gold.scalar("SELECT count(*) " + base_sql.format(join=on), pid=HS, year=AUDIT_YEAR)
    assert any_source > expected > 0, "前置：华氏科目表两套行，只按科目码关联会放大"
    data = await builder.ok(builder.admin, {
        "table": "trial_balance", "joins": [{"table": "account_chart", "type": "left"}], "project_id": str(HS),
        "year": AUDIT_YEAR, "fields": ["trial_balance.standard_account_code", "account_chart.account_name"],
        "limit": 1000})
    assert data["total"] == len(data["rows"]) == expected
    matched = await gold.scalar(
        "SELECT count(c.id) " + base_sql.format(join=on + " AND c.source = 'standard' AND NOT c.is_deleted"),
        pid=HS, year=AUDIT_YEAR)
    assert matched > 0 and sum(1 for r in data["rows"] if r["account_chart.account_name"] is not None) == matched
