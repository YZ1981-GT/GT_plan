"""构建器作用域真 PG 回归（advanced-query-linkage-closure 任务 9；R1.2、R3.1~R3.3、R3.5 后端；ADR-AQL-09；
变异 #2、#5、#16、B3-a、B3-b）。

请求经生产注册的 query_builder router 真发（夹具 ``builder``：真库回滚事务会话，见 ``builder_client``）；金标准一律在
测试内用独立 SQL 现算（``gold``），数值随真库变化，不写死。写入只在回滚事务里、只写【UAT】项目；报表配置副本行的用例在
真 PG 临时 schema（``pg_world``）里造身份与数据。

本批（B3，合入远端之前）e2e_manager 的金标准按「OwnershipGuard 可访问 − 已删项目」；循环受限项目的排除在任务 23
（B6）加上后，本例改为 design §10.2 的金标准（0 行 + 排除提示）。
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal

import pytest

from app.models.audit_platform_models import AccountCategory, TbBalance, TrialBalance
from app.models.report_models import ReportConfig
from app.routers import query_builder
from tests.advanced_query_linkage.gold import AUDIT_YEAR, HS, UA, YB, active_sql
from tests.authz_world import OTHER_PROJECT_ID, TARGET_PROJECT_ID, pg_world

pytestmark = pytest.mark.pg_only

ACCESSIBLE_LIVE_SQL = """
SELECT a.pid::text FROM (
  SELECT pu.project_id AS pid FROM project_users pu WHERE pu.user_id = :uid AND NOT pu.is_deleted
  UNION
  SELECT pa.project_id FROM project_assignments pa JOIN staff_members s ON s.id = pa.staff_id
   WHERE s.user_id = :uid AND NOT pa.is_deleted AND NOT s.is_deleted) a
JOIN projects p ON p.id = a.pid AND NOT p.is_deleted
"""
_PROJECTS = {"table": "projects", "fields": ["id", "name"], "limit": 1000}


def _ids(data: dict, column: str = "id") -> set[str]:
    return {str(row[column]) for row in data["rows"]}


# ─── projects 与人员表（AQ-06；变异 #5、B3-a）──────────────────────────────────


async def test_admin_projects_are_all_live_projects(builder, gold) -> None:
    live = {r[0] for r in await gold.rows("SELECT id::text FROM projects WHERE NOT is_deleted")}
    deleted = await gold.scalar("SELECT count(*) FROM projects WHERE is_deleted")
    assert live and deleted > 0, "前置：库里同时有未删与已删项目，用例才证明得了「排除已删」"
    data = await builder.ok(builder.admin, _PROJECTS)
    assert data["total"] == len(live) and _ids(data) == live


async def test_admin_rows_exclude_deleted_projects(builder, gold) -> None:
    """不限项目的身份（admin / partner）也只查未删项目的行：现库已删项目上仍挂着未删的试算 / 序时账行。"""
    sql = ("SELECT count(*) FROM trial_balance t JOIN projects p ON p.id = t.project_id AND {deleted} p.is_deleted "
           "WHERE NOT t.is_deleted")
    live, on_deleted = await gold.scalar(sql.format(deleted="NOT")), await gold.scalar(sql.format(deleted=""))
    assert live > 0 and on_deleted > 0, "前置：已删项目上有未删的试算行（否则「排除已删项目」无从验证）"
    data = await builder.ok(builder.admin, {"table": "trial_balance",
                                            "aggregates": [{"func": "count", "field": "*", "alias": "n"}]})
    assert data["rows"][0]["n"] == live, f"应只数未删项目的 {live} 行（含已删项目为 {live + on_deleted}）"


@pytest.mark.parametrize("username", ["e2e_manager", "u_011abb97dd2d4101"])
async def test_scoped_identity_sees_only_accessible_live_projects(builder, gold, username: str) -> None:
    """e2e_manager（系统经理，只经委派访问一个项目）与 u_011abb97dd2d4101（系统 auditor、项目经理）只见自己的项目。"""
    user = await builder.real_user(username)
    expected = {r[0] for r in await gold.rows(ACCESSIBLE_LIVE_SQL, uid=user.id)}
    assert expected, f"前置：{username} 至少能访问一个未删项目（否则「只含 X」对空集恒真）"
    data = await builder.ok(user, _PROJECTS)
    assert _ids(data) == expected and data["total"] == len(expected)
    assert data["scope"] == {"all_projects": False, "project_count": len(expected), "unscoped_tables": [],
                             "requested_project_id": None}


@pytest.mark.parametrize("body", [
    {"table": "staff_members", "fields": ["id", "name"]},
    {"table": "work_hours", "joins": [{"table": "staff_members", "type": "left"}],
     "fields": ["work_hours.hours", "staff_members.name"]},
], ids=["base", "join-target"])
async def test_manager_cannot_read_staff_members(builder, body: dict) -> None:
    response = await builder.execute(await builder.real_user("e2e_manager"), body)
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["error_code"] == "TABLE_ROLE_FORBIDDEN"


# ─── 指定项目（AQ-18）──────────────────────────────────────────────────────────


async def test_explicit_project_limits_scope(builder, gold) -> None:
    expected = await gold.scalar(
        "SELECT count(*) FROM trial_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted",
        pid=HS, year=AUDIT_YEAR)
    data = await builder.ok(builder.admin, {"table": "trial_balance", "fields": ["project_id", "standard_account_code"],
                                            "project_id": str(HS), "year": AUDIT_YEAR, "limit": 1000})
    assert expected > 0 and data["total"] == expected and _ids(data, "project_id") == {str(HS)}
    assert data["scope"]["requested_project_id"] == str(HS) and data["scope"]["project_count"] == 1


async def test_inaccessible_or_deleted_project_is_403_and_not_executed(builder, gold, monkeypatch) -> None:
    entered: list[int] = []
    real = query_builder.cancellable_query

    def _spy(db, timeout_ms):  # 执行的下一层：进入即记一次（被测的作用域解析不替换）
        entered.append(timeout_ms)
        return real(db, timeout_ms)

    monkeypatch.setattr(query_builder, "cancellable_query", _spy)
    manager = await builder.real_user("e2e_manager")
    accessible = {r[0] for r in await gold.rows(ACCESSIBLE_LIVE_SQL, uid=manager.id)}
    assert str(HS) not in accessible, "前置：e2e_manager 不能访问华氏"
    deleted = (await gold.rows("SELECT id::text FROM projects WHERE is_deleted ORDER BY created_at LIMIT 1"))[0][0]
    for user, project in ((manager, str(HS)), (builder.admin, deleted)):
        response = await builder.execute(user, {"table": "trial_balance", "fields": ["id"], "project_id": project})
        assert response.status_code == 403, response.text
        assert response.json()["detail"]["error_code"] == "FORBIDDEN_PROJECT"
    assert entered == [], "403 之前不得执行任何查询"
    await builder.ok(manager, {"table": "trial_balance", "fields": ["id"]})
    assert len(entered) == 1, "反向对照：放行的请求确实经过执行这一层"


# ─── 数据集口径与已删行（AQ-02；变异 #2）──────────────────────────────────────


async def test_tb_balance_uses_the_active_dataset(builder, gold) -> None:
    count, closing = (await gold.rows(
        f"SELECT count(*), coalesce(sum(closing_balance), 0) FROM tb_balance t WHERE {active_sql('t')}",
        pid=YB, year=AUDIT_YEAR))[0]
    undeleted = await gold.scalar(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted",
        pid=YB, year=AUDIT_YEAR)
    assert 0 < count < undeleted, "前置：宜宾临港店有非生效数据集的行"
    data = await builder.ok(builder.admin, {
        "table": "tb_balance", "project_id": str(YB), "year": AUDIT_YEAR,
        "aggregates": [{"func": "count", "field": "*", "alias": "n"}, {"func": "sum", "field": "closing_balance",
                                                                        "alias": "s"}]})
    (row,) = data["rows"]
    assert row["n"] == count
    assert abs(Decimal(str(row["s"])) - closing) < Decimal("0.01")


async def test_deleted_rows_are_invisible(builder, gold) -> None:
    active = await gold.rows("SELECT id FROM ledger_datasets WHERE project_id = :pid AND year = :year "
                             "AND status = 'active' ORDER BY activated_at DESC NULLS LAST, created_at DESC LIMIT 1",
                             pid=UA, year=AUDIT_YEAR)
    dataset_id = active[0][0] if active else None
    for code, deleted in (("AQLB3-LIVE", False), ("AQLB3-DELETED", True)):
        builder.session.add(TbBalance(project_id=UA, year=AUDIT_YEAR, company_code="001", account_code=code,
                                      account_name="【UAT】B3 回滚事务造行", dataset_id=dataset_id, is_deleted=deleted))
    await builder.session.flush()
    data = await builder.ok(builder.admin, {
        "table": "tb_balance", "fields": ["account_code"], "project_id": str(UA), "year": AUDIT_YEAR,
        "filters": [{"field": "account_code", "op": "like", "value": "AQLB3-"}]})
    assert [r["account_code"] for r in data["rows"]] == ["AQLB3-LIVE"] and data["total"] == 1


# ─── JOIN 目标的作用域在 ON（变异 #16）──────────────────────────────────────────


async def test_left_join_without_match_keeps_the_base_row(builder) -> None:
    builder.session.add(TrialBalance(
        project_id=UA, year=AUDIT_YEAR, company_code="001", standard_account_code="AQLB3-NOMATCH",
        account_name="【UAT】B3 无对应标准科目", account_category=AccountCategory.asset, audited_amount=Decimal("1.00")))
    await builder.session.flush()
    base = {"table": "trial_balance", "project_id": str(UA), "year": AUDIT_YEAR, "limit": 1000}
    plain = await builder.ok(builder.admin, {**base, "fields": ["trial_balance.standard_account_code"]})
    joined = await builder.ok(builder.admin, {**base, "joins": [{"table": "account_chart", "type": "left"}],
                                              "fields": ["trial_balance.standard_account_code",
                                                         "account_chart.account_name"]})
    assert plain["total"] > 1 and joined["total"] == plain["total"]
    (row,) = [r for r in joined["rows"] if r["trial_balance.standard_account_code"] == "AQLB3-NOMATCH"]
    assert row["account_chart.account_name"] is None


# ─── 报表配置的项目副本行（变异 B3-b）────────────────────────────────────────────


@asynccontextmanager
async def _report_config_world(monkeypatch):
    async with pg_world(monkeypatch, extra_tables=(ReportConfig.__table__,)) as world:
        await world.other_project()
        for number, standard in enumerate(("soe_standalone", f"project:{TARGET_PROJECT_ID}",
                                           f"project:{OTHER_PROJECT_ID}"), start=1):
            world.db.add(ReportConfig(report_type="balance_sheet", row_number=number, row_code=f"BS-{number:03d}",
                                      row_name="【测试】副本行可见性", applicable_standard=standard))
        await world.db.flush()
        yield world


async def test_report_config_project_copies_only_for_accessible_projects(monkeypatch) -> None:
    async with _report_config_world(monkeypatch) as world:
        pm = (await world.edit_member()).user  # X 上（manager, edit），系统 auditor
        sm = (await world.non_member_with_other_project(global_role="manager")).user  # 只在 Y 有成员行
        admin = (await world.admin_non_member()).user
        seen = {}
        for key, user in (("PM", pm), ("SM", sm), ("AD", admin)):
            async with world.client(query_builder.router, user=user) as client:
                response = await client.post("/api/query/execute", json={
                    "table": "report_config", "fields": ["applicable_standard"], "limit": 100})
            assert response.status_code == 200, response.text
            seen[key] = {r["applicable_standard"] for r in response.json()["rows"]}
    assert seen["PM"] == {"soe_standalone", f"project:{TARGET_PROJECT_ID}"}
    assert seen["SM"] == {"soe_standalone", f"project:{OTHER_PROJECT_ID}"}
    assert seen["AD"] == {"soe_standalone", f"project:{TARGET_PROJECT_ID}", f"project:{OTHER_PROJECT_ID}"}
