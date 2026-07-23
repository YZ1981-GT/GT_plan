"""D4 营业收入 Auto Data Resolvers.

3个resolver:
- d4_tb_unadjusted: trial_balance 科目6001+6051 本期/上期未审数
- d4_ledger_monthly: tb_ledger 科目6001 按月汇总
- d4_analysis_indicators: 多科目余额计算毛利率/周转率/应收占比

Usage:
    result = await resolve_auto_data_source(db, project_id, year, "d4_tb_unadjusted")
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver 1: d4_tb_unadjusted — 科目6001+6051未审数
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d4_tb_unadjusted")
async def _resolve_d4_tb_unadjusted(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 获取科目6001(主营)+6051(其他)的本期/上期未审数。

    Returns:
        {
            "summary": str,
            "main_revenue_6001": {"current_unadjusted": float, "prior_unadjusted": float},
            "other_revenue_6051": {"current_unadjusted": float, "prior_unadjusted": float},
        }
    """
    result_data: dict[str, Any] = {
        "main_revenue_6001": {"current_unadjusted": 0.0, "prior_unadjusted": 0.0},
        "other_revenue_6051": {"current_unadjusted": 0.0, "prior_unadjusted": 0.0},
    }

    # 本期
    current = await db.execute(
        sa.text("""
            SELECT standard_account_code,
                   COALESCE(SUM(unadjusted_amount), 0) AS unadj
            FROM trial_balance
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND standard_account_code = ANY(:codes)
            GROUP BY standard_account_code
        """),
        {"pid": str(project_id), "year": year, "codes": ["6001", "6051"]},
    )
    for row in current.fetchall():
        code = row.standard_account_code
        amt = float(row.unadj)
        if code == "6001":
            result_data["main_revenue_6001"]["current_unadjusted"] = amt
        elif code == "6051":
            result_data["other_revenue_6051"]["current_unadjusted"] = amt

    # 上期
    prior_year = year - 1
    prior = await db.execute(
        sa.text("""
            SELECT standard_account_code,
                   COALESCE(SUM(unadjusted_amount), 0) AS unadj
            FROM trial_balance
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND standard_account_code = ANY(:codes)
            GROUP BY standard_account_code
        """),
        {"pid": str(project_id), "year": prior_year, "codes": ["6001", "6051"]},
    )
    for row in prior.fetchall():
        code = row.standard_account_code
        amt = float(row.unadj)
        if code == "6001":
            result_data["main_revenue_6001"]["prior_unadjusted"] = amt
        elif code == "6051":
            result_data["other_revenue_6051"]["prior_unadjusted"] = amt

    main_cur = result_data["main_revenue_6001"]["current_unadjusted"]
    other_cur = result_data["other_revenue_6051"]["current_unadjusted"]
    summary = f"主营6001未审={main_cur:,.0f}；其他6051未审={other_cur:,.0f}"

    return {"summary": summary, **result_data}


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver 2: d4_ledger_monthly — 科目6001按月汇总
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d4_ledger_monthly")
async def _resolve_d4_ledger_monthly(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 tb_ledger 科目6001按月汇总发生额。

    Returns:
        {
            "summary": str,
            "monthly": [{"month": 1, "amount": float}, ...],  # 12个月
            "annual_total": float,
        }
    """
    monthly: list[dict[str, Any]] = [{"month": m, "amount": 0.0} for m in range(1, 13)]

    try:
        result = await db.execute(
            sa.text("""
                SELECT EXTRACT(MONTH FROM voucher_date)::int AS m,
                       COALESCE(SUM(credit_amount - debit_amount), 0) AS net_amount
                FROM tb_ledger
                WHERE project_id = :pid
                  AND EXTRACT(YEAR FROM voucher_date) = :year
                  AND is_deleted = false
                  AND account_code LIKE '6001%'
                GROUP BY m
                ORDER BY m
            """),
            {"pid": str(project_id), "year": year},
        )
        for row in result.fetchall():
            month_idx = int(row.m) - 1
            if 0 <= month_idx < 12:
                monthly[month_idx]["amount"] = float(row.net_amount)
    except Exception as e:
        logger.warning("d4_ledger_monthly 查询失败: %s", e)

    annual_total = sum(m["amount"] for m in monthly)
    summary = f"6001年度合计={annual_total:,.0f}"

    return {
        "summary": summary,
        "monthly": monthly,
        "annual_total": annual_total,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver 3: d4_analysis_indicators — 多科目余额计算指标
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d4_analysis_indicators")
async def _resolve_d4_analysis_indicators(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 取多科目余额计算分析指标。

    指标：毛利率 / 应收周转率 / 应收占收入比

    科目：
    - 6001 主营业务收入
    - 6051 其他业务收入
    - 6401 主营业务成本
    - 6402 其他业务成本
    - 1122 应收账款

    Returns:
        {
            "summary": str,
            "indicators": {
                "gross_margin_rate": float | None,
                "ar_turnover_rate": float | None,
                "ar_to_revenue_ratio": float | None,
            },
            "balances": {
                "revenue_6001": float,
                "revenue_6051": float,
                "cost_6401": float,
                "cost_6402": float,
                "ar_1122": float,
            },
        }
    """
    codes = ["6001", "6051", "6401", "6402", "1122"]
    balances: dict[str, float] = {c: 0.0 for c in codes}

    result = await db.execute(
        sa.text("""
            SELECT standard_account_code,
                   COALESCE(SUM(audited_amount), 0) AS amt
            FROM trial_balance
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND standard_account_code = ANY(:codes)
            GROUP BY standard_account_code
        """),
        {"pid": str(project_id), "year": year, "codes": codes},
    )
    for row in result.fetchall():
        code = row.standard_account_code
        if code in balances:
            balances[code] = float(row.amt)

    revenue = balances["6001"] + balances["6051"]
    cost = balances["6401"] + balances["6402"]
    ar = balances["1122"]

    # 毛利率 = (收入 - 成本) / 收入
    gross_margin_rate = (revenue - cost) / revenue if revenue != 0 else None

    # 应收周转率 = 收入 / 应收余额（简化版，未用平均余额）
    ar_turnover_rate = revenue / ar if ar != 0 else None

    # 应收占收入比 = 应收 / 收入
    ar_to_revenue_ratio = ar / revenue if revenue != 0 else None

    indicators = {
        "gross_margin_rate": round(gross_margin_rate, 4) if gross_margin_rate is not None else None,
        "ar_turnover_rate": round(ar_turnover_rate, 4) if ar_turnover_rate is not None else None,
        "ar_to_revenue_ratio": round(ar_to_revenue_ratio, 4) if ar_to_revenue_ratio is not None else None,
    }

    parts = []
    if indicators["gross_margin_rate"] is not None:
        parts.append(f"毛利率={indicators['gross_margin_rate']:.1%}")
    if indicators["ar_turnover_rate"] is not None:
        parts.append(f"应收周转={indicators['ar_turnover_rate']:.2f}次")
    if indicators["ar_to_revenue_ratio"] is not None:
        parts.append(f"应收占比={indicators['ar_to_revenue_ratio']:.1%}")
    summary = "；".join(parts) if parts else "试算表无数据"

    return {
        "summary": summary,
        "indicators": indicators,
        "balances": {
            "revenue_6001": balances["6001"],
            "revenue_6051": balances["6051"],
            "cost_6401": balances["6401"],
            "cost_6402": balances["6402"],
            "ar_1122": balances["1122"],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver 4: d4_ledger_monthly_by_product — 科目6001按产品(明细科目/科目名)×月汇总
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d4_ledger_monthly_by_product")
async def _resolve_d4_ledger_monthly_by_product(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 tb_ledger 科目6001 按产品(account_name，回退account_code)×月汇总贷方净额。

    产品维度：优先 account_name（如"主营业务收入-A产品"），空则回退 account_code
    （6001.01 等明细科目）。净额 = SUM(credit - debit)（损益类贷方科目：贷增借减）。

    供 D4-2 主营业务收入明细表「从序时账导入」按产品分月一键填充。

    Returns:
        {
            "summary": str,
            "rows": [{"product": str, "months": [12 floats], "annual": float}, ...],
        }
    """
    products: dict[str, list[float]] = {}

    try:
        result = await db.execute(
            sa.text("""
                SELECT COALESCE(NULLIF(TRIM(account_name), ''), account_code) AS product,
                       EXTRACT(MONTH FROM voucher_date)::int AS m,
                       COALESCE(SUM(credit_amount - debit_amount), 0) AS net_amount
                FROM tb_ledger
                WHERE project_id = :pid
                  AND EXTRACT(YEAR FROM voucher_date) = :year
                  AND is_deleted = false
                  AND account_code LIKE '6001%'
                GROUP BY product, m
                ORDER BY product, m
            """),
            {"pid": str(project_id), "year": year},
        )
        for row in result.fetchall():
            product = str(row.product or "未命名")
            month_idx = int(row.m) - 1
            if product not in products:
                products[product] = [0.0] * 12
            if 0 <= month_idx < 12:
                products[product][month_idx] = float(row.net_amount)
    except Exception as e:  # pragma: no cover
        logger.warning("d4_ledger_monthly_by_product 查询失败: %s", e)

    rows: list[dict[str, Any]] = []
    for product, months in products.items():
        rows.append({
            "product": product,
            "months": months,
            "annual": sum(months),
        })

    total = sum(r["annual"] for r in rows)
    summary = f"6001按产品导入 {len(rows)} 行，年度合计={total:,.0f}"

    return {"summary": summary, "rows": rows}
