"""列补齐真 PG 回归（advanced-query-linkage-closure 任务 22；R5.7、R5.8；design §3.1；变异 B5-d、B5-m）。

改造前（AQ-26 / AQ-33）：试算表结果没有重分类调整列（审定 = 未审 + 重分类 + 审计调整，少一列就对不上）；科目余额
不带期初 / 期末方向（余额的正负因科目方向而异，没有方向读不出借贷）。

现在：试算表返回期初、未审、重分类调整、审计调整、审定五列；科目余额与辅助余额带期初 / 期末方向列。

🔴 **2026-11-01 阶段 0 改造**：原先用 `gold.py` 里写死的 `HS`（华氏）/ `LN`（辽宁卫生服务）两个项目
UUID，而那两个 UUID 现算在 `projects` 表里**已经查不到行** —— 用例会拿 403 / 空集跟同样是空的金标准
互相印证而假绿（9 个固定 UUID 全失效，见 `closure.md` §16.3）。现在改为按**数据能力**动态解析：
试算表五列用 `tb_detail`、余额表方向列用 `balance_direction_columns`、辅助余额方向列用
`aux_balance_direction_columns`（判据与解析器见 `project_picks.py`，解析不到就当场失败并打印库内分布）。
年度也不再用常量 2025，而取所选项目自己的 `audit_year`。
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests.advanced_query_linkage.gold import active_sql

pytestmark = pytest.mark.pg_only


def _money(value) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


async def test_trial_balance_returns_five_amount_columns(business, gold, picks) -> None:
    pick = await picks.resolve("tb_detail")
    count, opening, unadjusted, rje, aje, audited = (await gold.rows(
        "SELECT count(*), coalesce(sum(opening_balance), 0), coalesce(sum(unadjusted_amount), 0), "
        "coalesce(sum(rje_adjustment), 0), coalesce(sum(aje_adjustment), 0), coalesce(sum(audited_amount), 0) "
        "FROM trial_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted",
        pid=pick.id, year=pick.audit_year))[0]
    assert count > 0, f"能力 tb_detail 选中 {pick} 却查不到试算表行 ⇒ 判据与金标准口径不一致"
    data, rows = await business.all_rows(pick, "tb_detail")
    assert data["columns"] == ["standard_account_code", "account_name", "opening_balance", "unadjusted_amount",
                               "rje_adjustment", "aje_adjustment", "audited_amount"]
    assert data["total"] == len(rows) == count
    sums = {key: sum(_money(r[key]) for r in rows) for key in
            ("opening_balance", "unadjusted_amount", "rje_adjustment", "aje_adjustment", "audited_amount")}
    expected = {"opening_balance": opening, "unadjusted_amount": unadjusted, "rje_adjustment": rje,
                "aje_adjustment": aje, "audited_amount": audited}
    assert all(abs(sums[k] - expected[k]) < Decimal("0.01") for k in expected), (pick, sums, expected)


async def test_account_balance_carries_direction_columns(business, gold, picks) -> None:
    pick = await picks.resolve("balance_direction_columns")
    count, opening_dir, closing_dir = (await gold.rows(
        f"SELECT count(*), count(opening_direction), count(closing_direction) FROM tb_balance t WHERE {active_sql('t')}",
        pid=pick.id, year=pick.audit_year))[0]
    assert closing_dir > 0, f"能力 balance_direction_columns 选中 {pick} 却没有期末方向列值 ⇒ 判据与金标准口径不一致"
    data, rows = await business.all_rows(pick, "account_balance")
    assert data["total"] == len(rows) == count
    assert data["columns"] == ["account_code", "account_name", "opening_direction", "opening_balance", "debit_amount",
                               "credit_amount", "closing_direction", "closing_balance", "currency_code"]
    assert sum(1 for r in rows if r["opening_direction"] is not None) == opening_dir
    assert sum(1 for r in rows if r["closing_direction"] is not None) == closing_dir
    directions = {r["closing_direction"] for r in rows if r["closing_direction"] is not None}
    gold_dirs = {r[0] for r in await gold.rows(
        f"SELECT DISTINCT closing_direction FROM tb_balance t WHERE {active_sql('t')} AND closing_direction IS NOT NULL",
        pid=pick.id, year=pick.audit_year)}
    assert directions == gold_dirs


async def test_aux_balance_direction_columns_and_condition(business, gold, picks) -> None:
    pick = await picks.resolve("aux_balance_direction_columns")
    closing_dir = await gold.scalar(
        f"SELECT count(*) FROM tb_aux_balance t WHERE {active_sql('t')} AND closing_direction IS NOT NULL",
        pid=pick.id, year=pick.audit_year)
    assert closing_dir > 0, f"能力 aux_balance_direction_columns 选中 {pick} 却没有期末方向列值 ⇒ 判据与金标准口径不一致"
    data = await business.ok(pick, "aux_balance", limit=5,
                             conditions=[{"field": "closing_direction", "op": "is_not_null"}])
    assert data["total"] == closing_dir
    assert {"opening_direction", "closing_direction"} <= set(data["columns"])
    assert all(r["closing_direction"] is not None for r in data["rows"])
