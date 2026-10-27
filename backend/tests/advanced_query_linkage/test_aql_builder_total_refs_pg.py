"""构建器 total、空值排序与公式引用真 PG（advanced-query-linkage-closure 任务 11；R2.2、R2.6 后端、R3.7；ADR-AQL-18；
变异 B3-d、B3-e、B3-f）。

- total = 同一查询的全量行数（分组时为组数），翻页不变：改造前是本页行数（和平药房序时账 offset 1,000 时 total 1,000）；
- 按可空列排序时空值排在最后：改造前和平药房序时账按借方降序，首行是借方为空的行（PG 降序默认 NULL 在前）；
- 公式引用只给试算表行，且每条都能通过地址库校验（``address_registry.validate_formula_refs``，与公式编辑器同一函数）；
  科目余额表行不再生成。「审定数有效、期末无效」从写法闭包测试（``test_query_builder_formula_ref_grammar_v1.py``）移到
  这里：那边只验「能解析成 URI」，``#cell`` 段原样透传、恒成立。

请求经生产注册的 query_builder router（夹具 ``builder``，系统管理员、真库回滚事务会话）；金标准用独立 SQL 现算。
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.address_registry import address_registry
from tests.advanced_query_linkage.gold import AUDIT_YEAR, HP, HS, YB, active_sql

pytestmark = pytest.mark.pg_only

_HP_LEDGER = {"table": "tb_ledger", "project_id": str(HP), "year": AUDIT_YEAR,
              "fields": ["voucher_date", "voucher_no", "account_code", "debit_amount"]}


async def test_total_is_the_full_count_and_does_not_change_with_paging(builder, gold) -> None:
    expected = await gold.scalar(f"SELECT count(*) FROM tb_ledger t WHERE {active_sql('t')}", pid=HP, year=AUDIT_YEAR)
    assert expected > 1000
    first = await builder.ok(builder.admin, {**_HP_LEDGER, "limit": 100})
    deep = await builder.ok(builder.admin, {**_HP_LEDGER, "limit": 100, "offset": 1000})
    assert first["total"] == deep["total"] == expected
    assert len(first["rows"]) == len(deep["rows"]) == 100


async def test_grouped_total_is_the_number_of_groups(builder, gold) -> None:
    groups = await gold.scalar("SELECT count(DISTINCT account_category) FROM trial_balance "
                               "WHERE project_id = :pid AND year = :year AND NOT is_deleted", pid=HS, year=AUDIT_YEAR)
    data = await builder.ok(builder.admin, {
        "table": "trial_balance", "project_id": str(HS), "year": AUDIT_YEAR, "fields": ["account_category"],
        "group_by": ["account_category"], "aggregates": [{"func": "count", "field": "*", "alias": "n"}], "limit": 2})
    assert groups > 2 and data["total"] == groups and len(data["rows"]) == 2


async def test_descending_sort_puts_nulls_last(builder, gold) -> None:
    nulls = await gold.scalar(f"SELECT count(*) FROM tb_ledger t WHERE {active_sql('t')} AND t.debit_amount IS NULL",
                              pid=HP, year=AUDIT_YEAR)
    top = await gold.scalar(f"SELECT max(debit_amount) FROM tb_ledger t WHERE {active_sql('t')}", pid=HP, year=AUDIT_YEAR)
    assert nulls > 0, "前置：和平药房序时账有借方为空的行（否则空值位置无从验证）"
    data = await builder.ok(builder.admin, {**_HP_LEDGER, "limit": 2,
                                            "order_by": [{"field": "debit_amount", "direction": "desc"}]})
    debits = [r["debit_amount"] for r in data["rows"]]
    assert debits[0] is not None and Decimal(str(debits[0])) == top, debits
    assert debits[1] is not None and debits[1] <= debits[0], debits


@pytest.mark.parametrize(("table", "project", "expect_refs"), [
    ("trial_balance", HS, True), ("tb_balance", YB, False)], ids=["trial_balance", "tb_balance"])
async def test_formula_refs_pass_the_address_registry(builder, table: str, project, expect_refs: bool) -> None:
    data = await builder.ok(builder.admin, {"table": table, "project_id": str(project), "year": AUDIT_YEAR,
                                            "limit": 1000})
    refs = [ref for ref in data["formula_refs"] if ref is not None]
    assert len(data["formula_refs"]) == len(data["rows"]) > 0
    if not expect_refs:
        assert refs == [], f"{table} 行不应生成公式引用：{refs[:3]}"
        return
    assert len(refs) == len(data["rows"]), "试算表每行都有标准科目码，都应生成引用"
    issues = await address_registry.validate_formula_refs(builder.session, str(project), AUDIT_YEAR, "+".join(refs))
    assert issues == [], issues[:3]


async def test_only_trial_balance_column_names_are_valid_tb_refs(builder) -> None:
    """``TB('1001','审定数')`` 有效；原先给科目余额表行生成的 ``TB('1001','期末')`` 无效（「期末」不是试算表列名）。"""
    assert await address_registry.validate_formula_refs(builder.session, str(HS), AUDIT_YEAR, "TB('1001','审定数')") == []
    issues = await address_registry.validate_formula_refs(builder.session, str(HS), AUDIT_YEAR, "TB('1001','期末')")
    assert [i["ref"] for i in issues] == ["TB('1001','期末')"] and "期末" in issues[0]["message"], issues
