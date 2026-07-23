"""F5 营业成本 — auto_data_source resolvers.

Resolver 1: f5_ledger_monthly_by_product
    从 tb_ledger 科目 6401 按产品(明细科目名/科目码)×月汇总借方净额，
    供 F5-2 月度明细表「从序时账导入」一键填充。

    产品维度：优先 account_name（如"主营业务成本-A产品"），空则回退 account_code。
    净额 = SUM(debit - credit)（损益借方科目：借增贷减）。
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from . import auto_resolver

logger = logging.getLogger(__name__)


@auto_resolver("f5_ledger_monthly_by_product")
async def _resolve_f5_ledger_monthly_by_product(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 tb_ledger 科目6401 按产品(account_name，回退account_code)×月汇总借方净额。

    产品维度：优先 account_name（如"主营业务成本_批发"），空则回退 account_code
    （6401.01 等明细科目）。净额 = SUM(debit - credit)（损益借方科目：借增贷减）。

    供 F5-2 主营业务成本明细表「从序时账导入」按产品分月一键填充。

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
                       COALESCE(SUM(debit_amount - credit_amount), 0) AS net_amount
                FROM tb_ledger
                WHERE project_id = :pid
                  AND EXTRACT(YEAR FROM voucher_date) = :year
                  AND is_deleted = false
                  AND account_code LIKE '6401%'
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
        logger.warning("f5_ledger_monthly_by_product 查询失败: %s", e)

    rows: list[dict[str, Any]] = []
    for product, months in products.items():
        rows.append({
            "product": product,
            "months": months,
            "annual": sum(months),
        })

    total = sum(r["annual"] for r in rows)
    summary = f"6401按产品导入 {len(rows)} 行，年度合计={total:,.0f}"

    return {"summary": summary, "rows": rows}
