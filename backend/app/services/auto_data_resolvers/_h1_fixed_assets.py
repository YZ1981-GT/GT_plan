"""H1 固定资产 Auto Data Resolvers — 科目1601+1602 / 月度折旧发生额."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver

logger = logging.getLogger(__name__)

_H1_ACCOUNT_PREFIXES = ("1601", "1602")


@auto_resolver("h1_tb_unadjusted")
async def _resolve_h1_tb_unadjusted(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 取科目1601固定资产+1602累计折旧的未审数.

    1601: 资产类/借方 — unadjusted_amount 为正数（期末余额）
    1602: 备抵类/贷方 — unadjusted_amount 为正数（期末余额，贷方方向）
    """
    cost_unadjusted = 0.0
    dep_unadjusted = 0.0
    cost_audited = 0.0
    dep_audited = 0.0

    try:
        result = await db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND (standard_account_code LIKE '1601%' OR standard_account_code LIKE '1602%')
            """),
            {"pid": str(project_id), "year": year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            if code.startswith("1601"):
                cost_unadjusted += float(row.unadjusted_amount or 0)
                cost_audited += float(row.audited_amount or 0)
            elif code.startswith("1602"):
                dep_unadjusted += float(row.unadjusted_amount or 0)
                dep_audited += float(row.audited_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("h1_tb_unadjusted resolver failed: %s", e)
        return {"summary": "⚠️ 数据获取失败", "_error": True}

    net_unadjusted = cost_unadjusted - dep_unadjusted
    summary = (
        f"H1: 1601原值未审={cost_unadjusted:,.0f}，"
        f"1602折旧未审={dep_unadjusted:,.0f}，"
        f"净值未审={net_unadjusted:,.0f}"
    )
    return {
        "summary": summary,
        "cost_unadjusted": cost_unadjusted,
        "dep_unadjusted": dep_unadjusted,
        "cost_audited": cost_audited,
        "dep_audited": dep_audited,
        "net_unadjusted": net_unadjusted,
        "account_codes": list(_H1_ACCOUNT_PREFIXES),
    }


@auto_resolver("h1_depreciation_monthly")
async def _resolve_h1_depreciation_monthly(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 tb_ledger 取月度折旧发生额（科目1602贷方发生=折旧计提）.

    折旧计提在贷方：每月贷方发生额即为当月折旧。
    """
    monthly: dict[int, float] = {m: 0.0 for m in range(1, 13)}
    total = 0.0

    try:
        result = await db.execute(
            sa.text("""
                SELECT
                    EXTRACT(MONTH FROM occurrence_date)::int AS m,
                    COALESCE(SUM(credit_amount), 0) AS dep_amount
                FROM tb_ledger
                WHERE project_id = :pid
                  AND EXTRACT(YEAR FROM occurrence_date) = :year
                  AND is_deleted = false
                  AND account_code LIKE '1602%'
                GROUP BY EXTRACT(MONTH FROM occurrence_date)
                ORDER BY m
            """),
            {"pid": str(project_id), "year": year},
        )
        for row in result.fetchall():
            month_num = int(row.m)
            amt = float(row.dep_amount or 0)
            if 1 <= month_num <= 12:
                monthly[month_num] = amt
                total += amt
    except Exception as e:  # noqa: BLE001
        logger.warning("h1_depreciation_monthly resolver failed: %s", e)
        return {"summary": "⚠️ 数据获取失败", "_error": True}

    summary = f"H1折旧月度: 合计={total:,.0f}，月均={total / 12:,.0f}"
    return {
        "summary": summary,
        "monthly": monthly,
        "total": total,
        "monthly_avg": round(total / 12, 2),
    }
