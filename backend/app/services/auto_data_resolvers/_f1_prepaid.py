"""F1 预付账款 Auto Data Resolvers — 科目1123."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver

logger = logging.getLogger(__name__)


@auto_resolver("f1_tb_unadjusted")
async def _resolve_f1_tb_unadjusted(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 获取科目1123期初/期末未审数."""
    result_data: dict[str, Any] = {
        "prior_unadjusted": 0.0,
        "current_unadjusted": 0.0,
    }

    current = await db.execute(
        sa.text("""
            SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadj
            FROM trial_balance
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND standard_account_code = '1123'
        """),
        {"pid": str(project_id), "year": year},
    )
    row = current.fetchone()
    if row:
        result_data["current_unadjusted"] = float(row.unadj)

    prior = await db.execute(
        sa.text("""
            SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadj
            FROM trial_balance
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND standard_account_code = '1123'
        """),
        {"pid": str(project_id), "year": year - 1},
    )
    row = prior.fetchone()
    if row:
        result_data["prior_unadjusted"] = float(row.unadj)

    cur = result_data["current_unadjusted"]
    pri = result_data["prior_unadjusted"]
    summary = f"预付账款1123: 期末未审={cur:,.0f}，期初未审={pri:,.0f}"
    return {"summary": summary, **result_data}


@auto_resolver("f1_ledger_analysis")
async def _resolve_f1_ledger_analysis(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 tb_ledger 科目1123取借方/贷方发生额."""
    debit_total = 0.0
    credit_total = 0.0
    try:
        debit_result = await db.execute(
            sa.text("""
                SELECT COALESCE(SUM(debit_amount), 0) AS amount
                FROM tb_ledger
                WHERE project_id = :pid
                  AND EXTRACT(YEAR FROM voucher_date) = :year
                  AND is_deleted = false
                  AND account_code LIKE '1123%'
            """),
            {"pid": str(project_id), "year": year},
        )
        row = debit_result.fetchone()
        if row:
            debit_total = float(row.amount)

        credit_result = await db.execute(
            sa.text("""
                SELECT COALESCE(SUM(credit_amount), 0) AS amount
                FROM tb_ledger
                WHERE project_id = :pid
                  AND EXTRACT(YEAR FROM voucher_date) = :year
                  AND is_deleted = false
                  AND account_code LIKE '1123%'
            """),
            {"pid": str(project_id), "year": year},
        )
        row = credit_result.fetchone()
        if row:
            credit_total = float(row.amount)
    except Exception as e:
        logger.warning("f1_ledger_analysis 查询失败: %s", e)

    summary = f"预付1123: 借方合计={debit_total:,.0f}，贷方合计={credit_total:,.0f}"
    return {
        "summary": summary,
        "debit_total": debit_total,
        "credit_total": credit_total,
    }
