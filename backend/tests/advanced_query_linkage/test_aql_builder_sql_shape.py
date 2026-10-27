"""构建器 SQL 形态、JOIN 登记不变式与人员表角色门（advanced-query-linkage-closure 任务 9~11；ADR-AQL-09 / 18；
R1.2、R2.2、R2.6、R3.2~R3.4；变异 #16、B3-a、B3-b、B3-c、B3-e）。

只编译、不连库（total 与人员表审计两例在 SQLite 权限世界里真发请求）：作用域谓词落在哪个子句（基表在 WHERE、JOIN 目标
在 ON——放进 WHERE 会把左连接变成内连接）、不限项目时排除已删项目的子查询不被外层的 ``projects`` 自动关联、报表配置的
项目副本行谓词、空值排序与唯一键、计数语句、一对多提示。口径与行数的真库金标准见同目录 ``*_pg.py``。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import UserRole
from app.models.staff_models import WorkHour
from app.routers import query_builder
from app.services.custom_query import audit_helper
from app.services.custom_query import table_whitelist as tw
from app.services.custom_query.builder_dsl import QueryDSL, _build_select, build_count
from app.services.custom_query.builder_scope import BuilderScope, resolve_builder_scope
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

P1 = uuid.UUID("11111111-1111-4111-8111-111111111111")
SCOPED = BuilderScope(project_ids=frozenset({P1}))
ALL = BuilderScope(project_ids=None)


def _pg(clause) -> str:
    return str(clause.compile(dialect=postgresql.dialect()))


def _join_and_where(dsl: QueryDSL, scope: BuilderScope) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    stmt, _ = _build_select(dsl, scope=scope, warnings=warnings)
    (join,) = stmt.get_final_froms()
    return _pg(join.onclause), _pg(stmt.whereclause), warnings


# ─── 作用域谓词的位置（变异 #16）────────────────────────────────────────────────


def test_join_target_scope_goes_into_on_and_base_scope_into_where() -> None:
    dsl = QueryDSL(table="trial_balance", joins=[{"table": "account_chart", "type": "left"}], year=2025,
                   fields=["trial_balance.standard_account_code", "account_chart.account_name"])
    on_sql, where_sql, _ = _join_and_where(dsl, SCOPED)
    # 目标表：登记的目标条件 + 项目 + 未删，全在 ON（左连接没有匹配行时目标列为空、基表行保留）
    for fragment in ("account_chart.source = ", "account_chart.project_id IN", "account_chart.is_deleted = false"):
        assert fragment in on_sql, (fragment, on_sql)
    assert "account_chart" not in where_sql, where_sql
    # 基表：项目、未删、年度在 WHERE 的最后一步（用户 DSL 无法放宽）
    for fragment in ("trial_balance.project_id IN", "trial_balance.is_deleted = false", "trial_balance.year = "):
        assert fragment in where_sql, (fragment, where_sql)
    assert str(P1) not in on_sql + where_sql, "项目 id 只能在绑定参数里"


def test_all_projects_scope_excludes_deleted_projects_without_correlating() -> None:
    """不限项目（admin / partner）时排除已删项目：子查询自带 FROM，不被外层 JOIN 的 projects 自动关联。"""
    dsl = QueryDSL(table="work_hours", joins=[{"table": "projects", "type": "left"}],
                   fields=["work_hours.hours", "projects.name"])
    on_sql, where_sql, _ = _join_and_where(dsl, ALL)
    assert "work_hours.project_id IN (SELECT projects.id \nFROM projects \nWHERE projects.is_deleted = false)" in where_sql
    assert "projects.is_deleted = false" in on_sql and "projects.id IN" not in on_sql, on_sql


def test_projects_table_is_scoped_by_id() -> None:
    stmt, _ = _build_select(QueryDSL(table="projects", fields=["id", "name"]), scope=SCOPED)
    where_sql = _pg(stmt.whereclause)
    assert "projects.id IN" in where_sql and "projects.is_deleted = false" in where_sql, where_sql
    stmt, _ = _build_select(QueryDSL(table="projects", fields=["id", "name"]), scope=ALL)
    assert _pg(stmt.whereclause) == "projects.is_deleted = false"


def test_report_config_project_copy_rows_only_for_accessible_projects() -> None:
    """报表配置的项目副本行（``project:{项目}``）只对能访问该项目的身份可见；不限项目时不加（变异 B3-b）。"""
    stmt, _ = _build_select(QueryDSL(table="report_config", fields=["row_code"]), scope=SCOPED)
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert "report_config.applicable_standard NOT LIKE" in str(compiled), str(compiled)
    assert [f"project:{P1}"] in list(compiled.params.values()), compiled.params
    stmt, _ = _build_select(QueryDSL(table="report_config", fields=["row_code"]), scope=ALL)
    assert "applicable_standard" not in _pg(stmt.whereclause)


# ─── 排序、计数与一对多提示 ──────────────────────────────────────────────────────


def test_order_by_puts_nulls_last_only_on_nullable_columns_then_unique_keys() -> None:
    dsl = QueryDSL(table="tb_ledger", fields=["voucher_date", "debit_amount"],
                   order_by=[{"field": "debit_amount", "direction": "desc"}, {"field": "voucher_date"}])
    stmt, _ = _build_select(dsl)
    order = _pg(stmt).split("ORDER BY", 1)[1]
    assert order.strip().startswith(
        "tb_ledger.debit_amount DESC NULLS LAST, tb_ledger.voucher_date ASC, tb_ledger.id ASC"), order
    # JOIN 时末尾再追加目标表主键；分组 / 聚合时不追加
    stmt, _ = _build_select(QueryDSL(table="working_paper", joins=[{"table": "wp_index", "type": "left"}],
                                     fields=["working_paper.status"]))
    assert _pg(stmt).split("ORDER BY", 1)[1].strip().startswith("working_paper.id ASC, wp_index.id ASC")
    stmt, _ = _build_select(QueryDSL(table="trial_balance", fields=["account_category"], group_by=["account_category"],
                                     aggregates=[{"func": "count", "field": "*", "alias": "n"}]))
    assert "ORDER BY" not in _pg(stmt)


def test_build_count_counts_the_same_statement_without_paging() -> None:
    dsl = QueryDSL(table="trial_balance", fields=["standard_account_code"], limit=10, offset=20,
                   order_by=[{"field": "audited_amount", "direction": "desc"}])
    stmt, _ = _build_select(dsl, scope=SCOPED)
    count_sql = _pg(build_count(stmt))
    assert count_sql.startswith("SELECT count(*) AS count_1 \nFROM (SELECT"), count_sql
    for word in ("LIMIT", "OFFSET", "ORDER BY"):
        assert word not in count_sql, count_sql
    assert "trial_balance.project_id IN" in count_sql, "计数必须带同一作用域"


def test_aggregate_only_select_keeps_the_base_table_as_from() -> None:
    """只选聚合时基表仍是 FROM 的左侧：此前「count(目标表.id) + JOIN」报 Don't know how to join（500 级的「查询执行失败」），
    只选 count(*) 时语句不带 FROM。"""
    stmt, _ = _build_select(QueryDSL(table="adjustments", joins=[{"table": "trial_balance", "type": "left"}],
                                     aggregates=[{"func": "count", "field": "*", "alias": "n"},
                                                 {"func": "count", "field": "trial_balance.id", "alias": "m"}]))
    assert "FROM adjustments LEFT OUTER JOIN trial_balance ON" in _pg(stmt), _pg(stmt)
    stmt, _ = _build_select(QueryDSL(table="tb_balance", aggregates=[{"func": "count", "field": "*", "alias": "n"}]))
    assert "FROM tb_balance" in _pg(stmt), _pg(stmt)


async def test_total_is_rows_or_groups_and_one_for_ungrouped_aggregates(monkeypatch: pytest.MonkeyPatch) -> None:
    """total = 全量行数（分组时为组数），与 limit / offset 无关；不分组的聚合恒为一行（变异 B3-d）。"""
    async with sqlite_world(monkeypatch, extra_tables=(TrialBalance.__table__,)) as world:
        for code, category in (("1001", AccountCategory.asset), ("1002", AccountCategory.asset),
                               ("2001", AccountCategory.liability)):
            world.db.add(TrialBalance(project_id=TARGET_PROJECT_ID, year=2025, company_code="001",
                                      standard_account_code=code, account_category=category))
        await world.db.flush()
        admin = (await world.admin_non_member()).user
        count = [{"func": "count", "field": "*", "alias": "n"}]
        bodies = {
            "plain": {"table": "trial_balance", "fields": ["standard_account_code"], "limit": 1, "offset": 1},
            "grouped": {"table": "trial_balance", "fields": ["account_category"], "group_by": ["account_category"],
                        "aggregates": count, "limit": 1},
            "ungrouped": {"table": "trial_balance", "aggregates": count, "offset": 5},
        }
        got = {}
        async with world.client(query_builder.router, user=admin) as client:
            for name, body in bodies.items():
                response = await client.post("/api/query/execute", json=body)
                assert response.status_code == 200, response.text
                got[name] = (response.json()["total"], len(response.json()["rows"]))
    assert got == {"plain": (3, 1), "grouped": (2, 1), "ungrouped": (1, 0)}, got


def test_one_to_many_join_warns_and_many_to_one_does_not() -> None:
    _, _, warnings = _join_and_where(
        QueryDSL(table="trial_balance", joins=[{"table": "report_line_mapping", "type": "left"}],
                 fields=["trial_balance.standard_account_code"]), SCOPED)
    assert any(tw.ONE_TO_MANY_WARNING in w for w in warnings), warnings
    _, _, warnings = _join_and_where(
        QueryDSL(table="trial_balance", joins=[{"table": "account_chart", "type": "left"}],
                 fields=["trial_balance.standard_account_code"]), SCOPED)
    assert not any(tw.ONE_TO_MANY_WARNING in w for w in warnings), warnings


# ─── JOIN 登记（变异 B3-c）──────────────────────────────────────────────────────


def test_join_registry_declares_cardinality_for_the_eleven_kept_joins() -> None:
    registered = {(base, target): spec["cardinality"] for base, targets in tw.JOIN_WHITELIST.items()
                  for target, spec in targets.items()}
    assert len(registered) == 11, sorted(registered)
    assert {pair for pair, card in registered.items() if card == "one_to_many"} == {
        ("trial_balance", "report_line_mapping"), ("wp_index", "working_paper"), ("staff_members", "work_hours")}
    assert ("report_line_mapping", "report_config") not in registered
    assert tw.JOIN_WHITELIST["trial_balance"]["account_chart"]["target_where"] == (("source", "standard"),)
    for base in ("tb_balance", "tb_ledger"):
        assert tw.JOIN_WHITELIST[base]["account_chart"]["target_where"] == (("source", "client"),)


def test_cardinality_invariant_names_a_missing_or_bad_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = tw.JOIN_WHITELIST["trial_balance"]["account_chart"]
    monkeypatch.setitem(tw.JOIN_WHITELIST["trial_balance"], "account_chart", {**spec, "cardinality": None})
    with pytest.raises(RuntimeError, match="trial_balance -> account_chart：基数 None"):
        tw._assert_all_joins_declare_cardinality()
    monkeypatch.setitem(tw.JOIN_WHITELIST["trial_balance"], "account_chart",
                        {**spec, "target_where": (("no_such_column", 1),)})
    with pytest.raises(RuntimeError, match="目标条件列 'no_such_column'"):
        tw._assert_all_joins_declare_cardinality()
    monkeypatch.setitem(tw.JOIN_WHITELIST["trial_balance"], "account_chart", spec)
    tw._assert_all_joins_declare_cardinality()


# ─── 人员表角色门（R3.2；变异 B3-a）─────────────────────────────────────────────


@pytest.mark.parametrize("tables", [["staff_members"], ["work_hours", "staff_members"]], ids=["base", "join-target"])
async def test_staff_members_role_gate_runs_before_any_data_access(tables: list[str]) -> None:
    def user(role: str) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), role=SimpleNamespace(value=role))

    # db=None：门禁先于一切取数（不可访问时不触达数据层）
    with pytest.raises(HTTPException) as exc:
        await resolve_builder_scope(user=user("manager"), dsl_tables=tables, db=None)
    assert exc.value.status_code == 403
    assert exc.value.detail["error_code"] == "TABLE_ROLE_FORBIDDEN"
    assert exc.value.detail["message"] == "表「人员」仅对管理员、合伙人开放"
    for role in ("admin", "partner"):  # 不限项目的角色：门禁放行、作用域不查库
        scope = await resolve_builder_scope(user=user(role), dsl_tables=tables, db=None)
        assert scope.is_all_projects


async def test_staff_members_rejection_is_audited_as_pii_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[str] = []

    async def _record(**kwargs):  # 审计的下一层：被测的 record_query_rejected 与路由接线都不替换
        recorded.append(kwargs["action"])
        return True

    assert audit_helper.resolve_rejection_action("TABLE_ROLE_FORBIDDEN") == audit_helper.ACTION_PII_DENIED
    monkeypatch.setattr(audit_helper, "_log_unthrottled", _record)
    async with sqlite_world(monkeypatch, extra_tables=(WorkHour.__table__,)) as world:
        manager = await world.user(UserRole.manager)
        async with world.client(query_builder.router, user=manager) as client:
            response = await client.post("/api/query/execute", json={
                "table": "work_hours", "joins": [{"table": "staff_members", "type": "left"}],
                "fields": ["work_hours.hours", "staff_members.name"]})
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["error_code"] == "TABLE_ROLE_FORBIDDEN"
    assert recorded == [audit_helper.ACTION_PII_DENIED]
