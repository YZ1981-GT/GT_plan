"""D5 应收款项融资 Auto Data Resolvers.

1个resolver:
- d5_tb_unadjusted: trial_balance 科目1124 期初/期末未审数

Usage:
    result = await resolve_auto_data_source(db, project_id, year, "d5_tb_unadjusted")
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
# Resolver: d5_tb_unadjusted — 科目1124期初/期末未审数
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d5_tb_unadjusted")
async def _resolve_d5_tb_unadjusted(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 获取科目1124的本期/上期未审数。

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
              AND standard_account_code = '1124'
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
              AND standard_account_code = '1124'
        """),
        {"pid": str(project_id), "year": prior_year},
    )
    row = prior.fetchone()
    if row:
        result_data["prior_unadjusted"] = float(row.unadj)

    cur = result_data["current_unadjusted"]
    pri = result_data["prior_unadjusted"]
    summary = f"应收款项融资1124: 期末未审={cur:,.0f}，期初未审={pri:,.0f}"

    return {"summary": summary, **result_data}
