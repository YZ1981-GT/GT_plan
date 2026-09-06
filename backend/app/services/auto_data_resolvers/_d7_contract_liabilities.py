"""D7 合同负债 Auto Data Resolvers.

2个resolver:
- d7_tb_unadjusted: trial_balance 科目2205 期初/期末未审数
- d7_ledger_analysis: tb_ledger 科目2205 借方/贷方发生额 + 按对方科目分拆

Usage:
    result = await resolve_auto_data_source(db, project_id, year, "d7_tb_unadjusted")
    result = await resolve_auto_data_source(db, project_id, year, "d7_ledger_analysis")
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
# Resolver: d7_tb_unadjusted — 科目2205期初/期末未审数
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d7_tb_unadjusted")
async def _resolve_d7_tb_unadjusted(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 获取科目2205的本期/上期未审数。

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
              AND standard_account_code = '2205'
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
              AND standard_account_code = '2205'
        """),
        {"pid": str(project_id), "year": prior_year},
    )
    row = prior.fetchone()
    if row:
        result_data["prior_unadjusted"] = float(row.unadj)

    cur = result_data["current_unadjusted"]
    pri = result_data["prior_unadjusted"]
    summary = f"合同负债2205: 期末未审={cur:,.0f}，期初未审={pri:,.0f}"

    return {"summary": summary, **result_data}


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver: d7_ledger_analysis — 科目2205借方/贷方发生额+按对方科目分拆
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d7_ledger_analysis")
async def _resolve_d7_ledger_analysis(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 tb_ledger 获取科目2205的借方/贷方发生额，按对方科目分拆。

    Returns:
        {
            "summary": str,
            "debit_total": float,
            "credit_total": float,
            "debit_by_counter": [{"counter_account": str, "amount": float}],
            "credit_by_counter": [{"counter_account": str, "amount": float}],
        }
    """
    result_data: dict[str, Any] = {
        "debit_total": 0.0,
        "credit_total": 0.0,
        "debit_by_counter": [],
        "credit_by_counter": [],
    }

    # 借方发生额按对方科目分拆
    debit_result = await db.execute(
        sa.text("""
            SELECT COALESCE(counterpart_account, '未知') AS counter_acct,
                   COALESCE(SUM(debit_amount), 0) AS total
            FROM tb_ledger
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND account_code = '2205'
              AND debit_amount > 0
            GROUP BY counterpart_account
            ORDER BY total DESC
        """),
        {"pid": str(project_id), "year": year},
    )
    debit_rows = debit_result.fetchall()
    debit_total = 0.0
    debit_by_counter = []
    for r in debit_rows:
        amt = float(r.total)
        debit_total += amt
        debit_by_counter.append({"counter_account": r.counter_acct, "amount": amt})

    result_data["debit_total"] = debit_total
    result_data["debit_by_counter"] = debit_by_counter

    # 贷方发生额按对方科目分拆
    credit_result = await db.execute(
        sa.text("""
            SELECT COALESCE(counterpart_account, '未知') AS counter_acct,
                   COALESCE(SUM(credit_amount), 0) AS total
            FROM tb_ledger
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND account_code = '2205'
              AND credit_amount > 0
            GROUP BY counterpart_account
            ORDER BY total DESC
        """),
        {"pid": str(project_id), "year": year},
    )
    credit_rows = credit_result.fetchall()
    credit_total = 0.0
    credit_by_counter = []
    for r in credit_rows:
        amt = float(r.total)
        credit_total += amt
        credit_by_counter.append({"counter_account": r.counter_acct, "amount": amt})

    result_data["credit_total"] = credit_total
    result_data["credit_by_counter"] = credit_by_counter

    summary = f"合同负债2205: 借方发生={debit_total:,.0f}，贷方发生={credit_total:,.0f}"

    return {"summary": summary, **result_data}
