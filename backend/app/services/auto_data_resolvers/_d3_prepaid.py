"""D3 预收账款 Auto Data Resolvers.

2个resolver:
- d3_tb_unadjusted: trial_balance 科目2203 期初/期末未审数
- d3_ledger_analysis: tb_ledger 科目2203 借方/贷方发生额+按对方科目分拆

Usage:
    result = await resolve_auto_data_source(db, project_id, year, "d3_tb_unadjusted")
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver 1: d3_tb_unadjusted — 科目2203期初/期末未审数
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d3_tb_unadjusted")
async def _resolve_d3_tb_unadjusted(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 获取科目2203的本期/上期未审数。

    Returns:
        {
            "summary": str,
            "prior_unadjusted": float,
            "current_unadjusted": float,
        }
    """
    result_data: dict[str, Any] = {
        "prior_unadjusted": 0.0,
        "current_unadjusted": 0.0,
    }

    # 本期未审数
    current = await db.execute(
        sa.text("""
            SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadj
            FROM trial_balance
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND standard_account_code = '2203'
        """),
        {"pid": str(project_id), "year": year},
    )
    row = current.fetchone()
    if row:
        result_data["current_unadjusted"] = float(row.unadj)

    # 上期未审数
    prior_year = year - 1
    prior = await db.execute(
        sa.text("""
            SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadj
            FROM trial_balance
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND standard_account_code = '2203'
        """),
        {"pid": str(project_id), "year": prior_year},
    )
    row = prior.fetchone()
    if row:
        result_data["prior_unadjusted"] = float(row.unadj)

    cur = result_data["current_unadjusted"]
    pri = result_data["prior_unadjusted"]
    summary = f"预收账款2203: 期末未审={cur:,.0f}，期初未审={pri:,.0f}"

    return {"summary": summary, **result_data}


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver 2: d3_ledger_analysis — 科目2203借方/贷方发生额+对方科目分拆
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d3_ledger_analysis")
async def _resolve_d3_ledger_analysis(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 tb_ledger 科目2203取借方/贷方发生额+按对方科目分拆。

    Returns:
        {
            "summary": str,
            "debit_total": float,
            "credit_total": float,
            "debit_by_counter": [{"account": str, "amount": float}],
            "credit_by_counter": [{"account": str, "amount": float}],
        }
    """
    debit_total = 0.0
    credit_total = 0.0
    debit_by_counter: list[dict[str, Any]] = []
    credit_by_counter: list[dict[str, Any]] = []

    try:
        # 借方发生额按对方科目分拆
        #
        # 🔴 列名真名是 `counterpart_account`（原写 `counter_account_code` 不存在，
        #    该查询从未成功执行过，异常被下方 except 吞掉 ⇒ 表现为「本项目无数据」）。
        # 🔴 数据可用性警示：`tb_ledger.counterpart_account` 真库填充率仅 **0.2%**
        #    （2026-09-06 实测 15,162 / 6,954,511 行非空）。因此本查询修好后
        #    绝大多数行会落进 `COALESCE(..., '未知')` 那一档 —— 这是**数据侧缺口**
        #    而非 SQL 缺陷。消费方在展示「按对方科目分拆」时应能接受
        #    「未知」占绝对多数，不要据此判断取数逻辑有问题。
        debit_result = await db.execute(
            sa.text("""
                SELECT COALESCE(counterpart_account, '未知') AS counter,
                       COALESCE(SUM(debit_amount), 0) AS amount
                FROM tb_ledger
                WHERE project_id = :pid
                  AND EXTRACT(YEAR FROM voucher_date) = :year
                  AND is_deleted = false
                  AND account_code LIKE '2203%'
                  AND debit_amount > 0
                GROUP BY counterpart_account
                ORDER BY amount DESC
            """),
            {"pid": str(project_id), "year": year},
        )
        for row in debit_result.fetchall():
            amt = float(row.amount)
            debit_total += amt
            debit_by_counter.append({"account": row.counter, "amount": amt})

        # 贷方发生额按对方科目分拆
        credit_result = await db.execute(
            sa.text("""
                SELECT COALESCE(counterpart_account, '未知') AS counter,
                       COALESCE(SUM(credit_amount), 0) AS amount
                FROM tb_ledger
                WHERE project_id = :pid
                  AND EXTRACT(YEAR FROM voucher_date) = :year
                  AND is_deleted = false
                  AND account_code LIKE '2203%'
                  AND credit_amount > 0
                GROUP BY counterpart_account
                ORDER BY amount DESC
            """),
            {"pid": str(project_id), "year": year},
        )
        for row in credit_result.fetchall():
            amt = float(row.amount)
            credit_total += amt
            credit_by_counter.append({"account": row.counter, "amount": amt})

    except Exception as e:
        logger.warning("d3_ledger_analysis 查询失败: %s", e)

    summary = f"预收2203: 借方合计={debit_total:,.0f}，贷方合计={credit_total:,.0f}"

    return {
        "summary": summary,
        "debit_total": debit_total,
        "credit_total": credit_total,
        "debit_by_counter": debit_by_counter,
        "credit_by_counter": credit_by_counter,
    }
