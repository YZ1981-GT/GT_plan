"""D4 营业收入 Auto Data Resolvers.

4 个 resolver（改造后口径，spec Task 1.4）:
- d4_tb_unadjusted: trial_balance 科目6001+6051 本期/上期未审数
- d4_ledger_monthly: tb_ledger 收入科目 按月汇总（单侧贷方发生额）
- d4_ledger_monthly_by_product: tb_ledger 收入科目 按产品×月汇总（单侧贷方发生额）
- d4_analysis_indicators: resolve_d4_accounts 动态定位 + normalize_trial_balance_pl 符号归一

改造依据（推翻旧口径）：
- SUM(credit_amount - debit_amount) 在 10 项目中 8 个返回 NULL → 恒 0（Req 1.1）
- 7/10 项目结转损益导致 SUM(credit)==SUM(debit) → 净额结构性恒 0（Req 1.3）
- 裸 is_deleted=false 在 0ec33ac9 产生 2.01× 双算（Req 1.4）
- trial_balance 的 df5b8403 存 -38,258,743.63 负值（Req 1.5）
- 上期缺失不得塌成 0（Req 1.6）

Usage:
    result = await resolve_auto_data_source(db, project_id, year, "d4_tb_unadjusted")
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger, TrialBalance
from app.services.auto_data_resolvers import auto_resolver
from app.services.dataset_query import get_active_filter
from app.services.d4_extraction import (
    REVENUE_SIDE,
    ledger_occurrence_sql,
    normalize_trial_balance_pl,
    resolve_d4_accounts,
)

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

    🔴 改造点：
    - 使用 get_active_filter 替代裸 is_deleted=false（Req 1.4 数据集隔离）
    - 上期无数据返回 None 而非 0（Req 1.6）

    Returns:
        {
            "summary": str,
            "main_revenue_6001": {"current_unadjusted": float|None, "prior_unadjusted": float|None},
            "other_revenue_6051": {"current_unadjusted": float|None, "prior_unadjusted": float|None},
        }
    """
    result_data: dict[str, Any] = {
        "main_revenue_6001": {"current_unadjusted": None, "prior_unadjusted": None},
        "other_revenue_6051": {"current_unadjusted": None, "prior_unadjusted": None},
    }

    try:
        # 本期 —— get_active_filter 确保数据集隔离
        tb_table = TrialBalance.__table__
        active_filter = await get_active_filter(db, tb_table, project_id, year)
        current = await db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                sa.func.coalesce(sa.func.sum(TrialBalance.unadjusted_amount), 0).label("unadj"),
            ).where(
                active_filter,
                TrialBalance.standard_account_code.in_(["6001", "6051"]),
            ).group_by(TrialBalance.standard_account_code)
        )
        for row in current.fetchall():
            code = row.standard_account_code
            amt = float(row.unadj)
            if code == "6001":
                result_data["main_revenue_6001"]["current_unadjusted"] = amt
            elif code == "6051":
                result_data["other_revenue_6051"]["current_unadjusted"] = amt

        # 上期 —— 单独的 get_active_filter 调用（year-1）
        prior_year = year - 1
        prior_filter = await get_active_filter(db, tb_table, project_id, prior_year)
        prior = await db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                sa.func.coalesce(sa.func.sum(TrialBalance.unadjusted_amount), 0).label("unadj"),
            ).where(
                prior_filter,
                TrialBalance.standard_account_code.in_(["6001", "6051"]),
            ).group_by(TrialBalance.standard_account_code)
        )
        prior_rows = prior.fetchall()
        if not prior_rows:
            # 上期无数据 → None（Req 1.6：不得伪装成 0）
            pass
        else:
            for row in prior_rows:
                code = row.standard_account_code
                amt = float(row.unadj)
                if code == "6001":
                    result_data["main_revenue_6001"]["prior_unadjusted"] = amt
                elif code == "6051":
                    result_data["other_revenue_6051"]["prior_unadjusted"] = amt
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("d4_tb_unadjusted 查询失败: %s", e)

    main_cur = result_data["main_revenue_6001"]["current_unadjusted"]
    other_cur = result_data["other_revenue_6051"]["current_unadjusted"]
    summary = f"主营6001未审={main_cur or 0:,.0f}；其他6051未审={other_cur or 0:,.0f}"

    return {"summary": summary, **result_data}


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver 2: d4_ledger_monthly — 收入科目按月汇总（单侧贷方发生额）
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d4_ledger_monthly")
async def _resolve_d4_ledger_monthly(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 tb_ledger 收入科目 6001 按月汇总**贷方**发生额。

    🔴 改造点（Req 1.1, 1.2, 1.3, 1.4）：
    - 使用 get_active_filter 替代裸 is_deleted=false（数据集隔离）
    - 使用 COALESCE(credit_amount, 0) 单侧发生额替代 credit - debit 净额
      （净额口径因 NULL 传播 + 结转损益导致恒为 0）

    Returns:
        {
            "summary": str,
            "monthly": [{"month": 1, "amount": float}, ...],  # 12个月
            "annual_total": float,
        }
    """
    monthly: list[dict[str, Any]] = [{"month": m, "amount": 0.0} for m in range(1, 13)]

    try:
        active_filter = await get_active_filter(db, TbLedger.__table__, project_id, year)
        # 单侧贷方发生额 —— 收入类取贷方（REVENUE_SIDE = "credit"）
        occurrence_col = ledger_occurrence_sql(REVENUE_SIDE)
        month_expr = sa.cast(sa.extract("month", TbLedger.voucher_date), sa.Integer)
        result = await db.execute(
            sa.select(
                month_expr.label("m"),
                sa.func.coalesce(
                    sa.func.sum(sa.text(occurrence_col)), 0
                ).label("occurrence"),
            ).where(
                active_filter,
                sa.extract("year", TbLedger.voucher_date) == year,
                TbLedger.account_code.like("6001%"),
            ).group_by(month_expr).order_by(month_expr)
        )
        for row in result.fetchall():
            month_idx = int(row.m) - 1
            if 0 <= month_idx < 12:
                monthly[month_idx]["amount"] = float(row.occurrence)
    except Exception as e:  # noqa: BLE001
        logger.warning("d4_ledger_monthly 查询失败: %s", e)

    annual_total = sum(m["amount"] for m in monthly)
    summary = f"6001年度贷方合计={annual_total:,.0f}"

    return {
        "summary": summary,
        "monthly": monthly,
        "annual_total": annual_total,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver 3: d4_analysis_indicators — 动态科目定位 + 符号归一
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d4_analysis_indicators")
async def _resolve_d4_analysis_indicators(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """使用 resolve_d4_accounts 动态定位科目 + normalize_trial_balance_pl 符号归一。

    🔴 改造点（Req 1.4, 1.5, 1.6, 2.1）：
    - 不再硬编码 ["6001","6051","6401","6402","1122"]，改走 resolve_d4_accounts
      获取报表行驱动的动态科目集（区间码展开 + 逐项目反解）
    - 使用 normalize_trial_balance_pl 对取数做符号归一（解决负数存储贷方性质）
    - 使用 get_active_filter（数据集隔离）
    - 上期无数据返回 None 而非 0

    指标：毛利率 / 应收周转率 / 应收占收入比

    Returns:
        {
            "summary": str,
            "indicators": {
                "gross_margin_rate": float | None,
                "ar_turnover_rate": float | None,
                "ar_to_revenue_ratio": float | None,
            },
            "balances": {
                "revenue": float | None,
                "cost": float | None,
                "ar_1122": float,
            },
            "scope": dict,  # D4AccountScope.as_dict()
        }
    """
    # 构造最小上下文给 resolve_d4_accounts
    ctx = SimpleNamespace(db=db, project_id=project_id, year=year)

    revenue_amount: float | None = None
    cost_amount: float | None = None
    ar_amount: float = 0.0
    scope_dict: dict = {}

    try:
        # 动态科目定位（报表行驱动，不再硬编码）
        scope = await resolve_d4_accounts(ctx)
        scope_dict = scope.as_dict()

        # 从 trial_balance 取收入 + 成本（使用展开后的标准码）
        tb_table = TrialBalance.__table__
        active_filter = await get_active_filter(db, tb_table, project_id, year)

        # 收入科目
        rev_codes = list(scope.revenue_standard_expanded) or ["6001", "6051"]
        rev_result = await db.execute(
            sa.select(
                sa.func.sum(TrialBalance.audited_amount).label("amt"),
            ).where(
                active_filter,
                TrialBalance.standard_account_code.in_(rev_codes),
            )
        )
        rev_row = rev_result.fetchone()
        if rev_row and rev_row.amt is not None:
            revenue_amount = normalize_trial_balance_pl(rev_row.amt)

        # 成本科目
        cost_codes = list(scope.cost_standard_expanded) or ["6401", "6402"]
        cost_result = await db.execute(
            sa.select(
                sa.func.sum(TrialBalance.audited_amount).label("amt"),
            ).where(
                active_filter,
                TrialBalance.standard_account_code.in_(cost_codes),
            )
        )
        cost_row = cost_result.fetchone()
        if cost_row and cost_row.amt is not None:
            cost_amount = normalize_trial_balance_pl(cost_row.amt)

        # 应收账款（1122，用于周转率 / 占比计算）
        ar_result = await db.execute(
            sa.select(
                sa.func.coalesce(sa.func.sum(TrialBalance.audited_amount), 0).label("amt"),
            ).where(
                active_filter,
                TrialBalance.standard_account_code == "1122",
            )
        )
        ar_row = ar_result.fetchone()
        if ar_row:
            ar_amount = float(ar_row.amt)

    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("d4_analysis_indicators 查询失败: %s", e)

    # 计算指标（None 表示不可计算，不塌成 0）
    gross_margin_rate: float | None = None
    ar_turnover_rate: float | None = None
    ar_to_revenue_ratio: float | None = None

    if revenue_amount is not None and revenue_amount != 0:
        if cost_amount is not None:
            gross_margin_rate = (revenue_amount - cost_amount) / revenue_amount
        ar_to_revenue_ratio = ar_amount / revenue_amount if ar_amount != 0 else 0.0
        ar_turnover_rate = revenue_amount / ar_amount if ar_amount != 0 else None

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
            "revenue": revenue_amount,
            "cost": cost_amount,
            "ar_1122": ar_amount,
        },
        "scope": scope_dict,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver 4: d4_ledger_monthly_by_product — 收入科目按产品×月汇总（单侧贷方发生额）
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d4_ledger_monthly_by_product")
async def _resolve_d4_ledger_monthly_by_product(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 tb_ledger 收入科目 6001 按产品(account_name/account_code)×月汇总**贷方**发生额。

    🔴 改造点（Req 1.1, 1.2, 1.3, 1.4）：
    - 使用 get_active_filter 替代裸 is_deleted=false（数据集隔离）
    - 使用 COALESCE(credit_amount, 0) 单侧发生额替代 credit - debit 净额
      （净额口径因 NULL 传播 + 结转损益导致恒为 0）

    产品维度：优先 account_name（如"主营业务收入-A产品"），空则回退 account_code。
    供 D4-2 主营业务收入明细表「从序时账导入」按产品分月一键填充。

    Returns:
        {
            "summary": str,
            "rows": [{"product": str, "months": [12 floats], "annual": float}, ...],
        }
    """
    products: dict[str, list[float]] = {}

    try:
        active_filter = await get_active_filter(db, TbLedger.__table__, project_id, year)
        # 单侧贷方发生额 —— 收入类取贷方（REVENUE_SIDE = "credit"）
        occurrence_col = ledger_occurrence_sql(REVENUE_SIDE)
        product_expr = sa.func.coalesce(
            sa.func.nullif(sa.func.trim(TbLedger.account_name), sa.literal("")),
            TbLedger.account_code,
        )
        month_expr = sa.cast(sa.extract("month", TbLedger.voucher_date), sa.Integer)
        result = await db.execute(
            sa.select(
                product_expr.label("product"),
                month_expr.label("m"),
                sa.func.coalesce(
                    sa.func.sum(sa.text(occurrence_col)), 0
                ).label("occurrence"),
            ).where(
                active_filter,
                sa.extract("year", TbLedger.voucher_date) == year,
                TbLedger.account_code.like("6001%"),
            ).group_by(product_expr, month_expr).order_by(product_expr, month_expr)
        )
        for row in result.fetchall():
            product = str(row.product or "未命名")
            month_idx = int(row.m) - 1
            if product not in products:
                products[product] = [0.0] * 12
            if 0 <= month_idx < 12:
                products[product][month_idx] = float(row.occurrence)
    except Exception as e:  # noqa: BLE001
        logger.warning("d4_ledger_monthly_by_product 查询失败: %s", e)

    rows: list[dict[str, Any]] = []
    for product, months in products.items():
        rows.append({
            "product": product,
            "months": months,
            "annual": sum(months),
        })

    total = sum(r["annual"] for r in rows)
    summary = f"6001按产品贷方导入 {len(rows)} 行，年度合计={total:,.0f}"

    return {"summary": summary, "rows": rows}
