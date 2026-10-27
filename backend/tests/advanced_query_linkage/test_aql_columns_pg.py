"""列补齐真 PG 回归（advanced-query-linkage-closure 任务 22；R5.7、R5.8；design §3.1；变异 B5-d、B5-m）。

改造前（AQ-26 / AQ-33）：试算表结果没有重分类调整列（审定 = 未审 + 重分类 + 审计调整，少一列就对不上）；科目余额
不带期初 / 期末方向（余额的正负因科目方向而异，没有方向读不出借贷）。

现在：试算表返回期初、未审、重分类调整、审计调整、审定五列；科目余额与辅助余额带期初 / 期末方向列（现库只有辽宁卫生
服务的方向列有值，其余项目为空、结构照常返回）。华氏试算表 Σ审定继续等于金标准（R5.8）。
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests.advanced_query_linkage.gold import AUDIT_YEAR, HS, LN, active_sql

pytestmark = pytest.mark.pg_only


def _money(value) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


async def test_trial_balance_returns_five_amount_columns(business, gold) -> None:
    count, opening, unadjusted, rje, aje, audited = (await gold.rows(
        "SELECT count(*), coalesce(sum(opening_balance), 0), coalesce(sum(unadjusted_amount), 0), "
        "coalesce(sum(rje_adjustment), 0), coalesce(sum(aje_adjustment), 0), coalesce(sum(audited_amount), 0) "
        "FROM trial_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted", pid=HS, year=AUDIT_YEAR))[0]
    data, rows = await business.all_rows(HS, "tb_detail")
    assert data["columns"] == ["standard_account_code", "account_name", "opening_balance", "unadjusted_amount",
                               "rje_adjustment", "aje_adjustment", "audited_amount"]
    assert data["total"] == len(rows) == count
    sums = {key: sum(_money(r[key]) for r in rows) for key in
            ("opening_balance", "unadjusted_amount", "rje_adjustment", "aje_adjustment", "audited_amount")}
    expected = {"opening_balance": opening, "unadjusted_amount": unadjusted, "rje_adjustment": rje,
                "aje_adjustment": aje, "audited_amount": audited}
    assert all(abs(sums[k] - expected[k]) < Decimal("0.01") for k in expected), (sums, expected)


async def test_account_balance_carries_direction_columns(business, gold) -> None:
    count, opening_dir, closing_dir = (await gold.rows(
        f"SELECT count(*), count(opening_direction), count(closing_direction) FROM tb_balance t WHERE {active_sql('t')}",
        pid=LN, year=AUDIT_YEAR))[0]
    assert closing_dir > 0, "前置：辽宁卫生服务的余额表方向列有值"
    data, rows = await business.all_rows(LN, "account_balance")
    assert data["total"] == len(rows) == count
    assert data["columns"] == ["account_code", "account_name", "opening_direction", "opening_balance", "debit_amount",
                               "credit_amount", "closing_direction", "closing_balance", "currency_code"]
    assert sum(1 for r in rows if r["opening_direction"] is not None) == opening_dir
    assert sum(1 for r in rows if r["closing_direction"] is not None) == closing_dir
    directions = {r["closing_direction"] for r in rows if r["closing_direction"] is not None}
    gold_dirs = {r[0] for r in await gold.rows(
        f"SELECT DISTINCT closing_direction FROM tb_balance t WHERE {active_sql('t')} AND closing_direction IS NOT NULL",
        pid=LN, year=AUDIT_YEAR)}
    assert directions == gold_dirs


async def test_aux_balance_direction_columns_and_condition(business, gold) -> None:
    closing_dir = await gold.scalar(
        f"SELECT count(*) FROM tb_aux_balance t WHERE {active_sql('t')} AND closing_direction IS NOT NULL",
        pid=LN, year=AUDIT_YEAR)
    assert closing_dir > 0, "前置：辽宁卫生服务的辅助余额方向列有值"
    data = await business.ok(LN, "aux_balance", limit=5,
                             conditions=[{"field": "closing_direction", "op": "is_not_null"}])
    assert data["total"] == closing_dir
    assert {"opening_direction", "closing_direction"} <= set(data["columns"])
    assert all(r["closing_direction"] is not None for r in data["rows"])
