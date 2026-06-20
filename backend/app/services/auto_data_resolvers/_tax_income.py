"""损益汇总 / 税费 / S 类专项（收入/EPS/非经常性损益）域 resolvers。"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver


@auto_resolver("ledger_detail_for_account")
async def _resolve_ledger_detail(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """从 tb_ledger 获取指定科目的明细发生额（K8/K9 费用类科目用）。

    数据来源: tb_ledger 表（按 account_code LIKE '{prefix}%' 分组汇总）
    返回结构: {"summary": str, "items": list[dict], "total_debit": float, "total_credit": float, "account_prefix": str}
    参数: kw['account_prefix'] 或自动从 kw['wp_code'] 推导（K8→6601, K9→6602）。
    """
    from sqlalchemy import text as sa_text

    account_prefix = kw.get("account_prefix", "")
    if not account_prefix:
        # 从 wp_code 推导：K8→6601(销售费用), K9→6602(管理费用)
        wp_code = kw.get("wp_code", "")
        if "K8" in wp_code:
            account_prefix = "6601"
        elif "K9" in wp_code:
            account_prefix = "6602"
        else:
            return {"summary": "费用明细取数：未指定科目前缀", "items": []}

    sql = sa_text("""
        SELECT account_code, account_name,
               SUM(debit_amount) as total_debit,
               SUM(credit_amount) as total_credit
        FROM tb_ledger
        WHERE project_id = :pid AND year = :year
              AND account_code LIKE :prefix
              AND (is_deleted = false OR is_deleted IS NULL)
        GROUP BY account_code, account_name
        ORDER BY account_code
    """)
    result = await db.execute(
        sql,
        {"pid": str(project_id), "year": year, "prefix": f"{account_prefix}%"},
    )
    rows = result.fetchall()

    if not rows:
        return {
            "summary": f"费用明细取数：序时账无 {account_prefix} 开头科目数据",
            "items": [],
            "total_debit": 0,
            "total_credit": 0,
        }

    items = []
    total_debit = 0
    total_credit = 0
    for row in rows:
        items.append({
            "account_code": row.account_code,
            "account_name": row.account_name or "",
            "debit_amount": float(row.total_debit or 0),
            "credit_amount": float(row.total_credit or 0),
        })
        total_debit += float(row.total_debit or 0)
        total_credit += float(row.total_credit or 0)

    return {
        "summary": f"费用明细取数：{len(items)} 个明细科目，借方合计 {total_debit:,.2f}",
        "items": items,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "account_prefix": account_prefix,
    }


@auto_resolver("income_statement_total")
async def _resolve_income_total(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """汇总 D~N 损益类科目 audited_amount 得到本年净利润。

    数据来源: trial_balance 表（audited_amount，收入类 6xxx - 费用类 5xxx/64xx/66xx/67xx）
    返回结构: {"summary": str, "net_income": float, "total_revenue": float, "total_expense": float, "coverage_percent": float, ...}
    """
    from sqlalchemy import text as sa_text

    # 收入类科目（6xxx，但排除 6401/6402 营业成本、6403 税金及附加、660x 费用）
    # 简化方式：6xxx 中 audited_amount 取贷方方向为正的科目
    # 按会计准则：收入 = 6001/6051/6111/6115/6117/6301/6401负(已对冲)/...
    # 最精确方式：取 trial_balance 全部 5xxx+6xxx 科目 audited_amount
    sql_income = sa_text("""
        SELECT COALESCE(SUM(audited_amount), 0) as total
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '6001%'
                   OR standard_account_code LIKE '6051%'
                   OR standard_account_code LIKE '6111%'
                   OR standard_account_code LIKE '6115%'
                   OR standard_account_code LIKE '6117%'
                   OR standard_account_code LIKE '6301%')
              AND (is_deleted = false OR is_deleted IS NULL)
    """)

    sql_expense = sa_text("""
        SELECT COALESCE(SUM(audited_amount), 0) as total
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '5%'
                   OR standard_account_code LIKE '6401%'
                   OR standard_account_code LIKE '6402%'
                   OR standard_account_code LIKE '6403%'
                   OR standard_account_code LIKE '6601%'
                   OR standard_account_code LIKE '6602%'
                   OR standard_account_code LIKE '6603%'
                   OR standard_account_code LIKE '6604%'
                   OR standard_account_code LIKE '6701%'
                   OR standard_account_code LIKE '6702%'
                   OR standard_account_code LIKE '6711%'
                   OR standard_account_code LIKE '6801%')
              AND (is_deleted = false OR is_deleted IS NULL)
    """)

    params = {"pid": str(project_id), "year": year}

    income_result = await db.execute(sql_income, params)
    total_revenue = float(income_result.scalar() or 0)

    expense_result = await db.execute(sql_expense, params)
    total_expense = float(expense_result.scalar() or 0)

    net_income = total_revenue - total_expense

    # 统计已审定科目覆盖率
    sql_count = sa_text("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN audited_amount IS NOT NULL AND audited_amount != 0 THEN 1 END) as audited
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '5%' OR standard_account_code LIKE '6%')
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    count_result = await db.execute(sql_count, params)
    count_row = count_result.fetchone()
    total_accounts = int(count_row.total) if count_row else 0
    audited_accounts = int(count_row.audited) if count_row else 0

    coverage_pct = (audited_accounts / total_accounts * 100) if total_accounts > 0 else 0
    incomplete_warning = ""
    if coverage_pct < 100 and total_accounts > 0:
        incomplete_warning = f"（⚠️ 部分损益科目审定未完成：{audited_accounts}/{total_accounts}）"

    return {
        "summary": f"本年净利润（D~N 损益审定额合计）：{net_income:,.2f}{incomplete_warning}",
        "net_income": net_income,
        "total_revenue": total_revenue,
        "total_expense": total_expense,
        "total_income_accounts": total_accounts,
        "audited_income_accounts": audited_accounts,
        "coverage_percent": round(coverage_pct, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# N 类 — 税费循环 resolvers
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("temporary_differences_summary")
async def _resolve_temp_diff(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """暂时性差异汇总（N1-3/N3-3 递延所得税程序表用）。

    数据来源: trial_balance 表（1xxx~4xxx 资产负债类科目 audited_amount）
    返回结构: {"summary": str, "account_count": int, "total_audited_amount": float, "deductible_differences": list, "taxable_differences": list, "total_dta": float, "total_dtl": float, "note": str}
    """
    from sqlalchemy import text as sa_text

    # 查询资产负债类科目（1xxx~4xxx）的 audited_amount
    sql = sa_text("""
        SELECT standard_account_code, audited_amount
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '1%'
                   OR standard_account_code LIKE '2%'
                   OR standard_account_code LIKE '3%'
                   OR standard_account_code LIKE '4%')
              AND audited_amount IS NOT NULL
              AND audited_amount != 0
              AND (is_deleted = false OR is_deleted IS NULL)
        ORDER BY standard_account_code
    """)

    result = await db.execute(sql, {"pid": str(project_id), "year": year})
    rows = result.fetchall()

    # 框架数据：暂时性差异需要计税基础（由用户在底稿中手动填写）
    # 此处仅提供科目清单和审定额作为起始数据
    account_count = len(rows)
    total_audited = sum(float(r.audited_amount or 0) for r in rows)

    return {
        "summary": f"已审定资产负债科目 {account_count} 个，合计审定额 {total_audited:,.2f}（暂时性差异需在底稿中逐科目填写计税基础）",
        "account_count": account_count,
        "total_audited_amount": total_audited,
        "deductible_differences": [],
        "taxable_differences": [],
        "total_dta": 0,
        "total_dtl": 0,
        "note": "计税基础需手动维护，DTA/DTL 由底稿公式自动计算",
    }


@auto_resolver("income_tax_calculation")
async def _resolve_income_tax(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """所得税计算基础数据：利润总额 + 已知调增调减项（N5-3 程序表用）。

    数据来源: trial_balance 表（5xxx/6xxx 损益科目 audited_amount 汇总）
    返回结构: {"summary": str, "profit_before_tax": float, "tax_rate": float, "known_adjustments": list, "note": str}
    """
    from sqlalchemy import text as sa_text

    # 利润总额 = 营业利润 + 营业外收支（简化：收入-费用-所得税费用前）
    sql_profit = sa_text("""
        SELECT COALESCE(SUM(CASE
            WHEN standard_account_code LIKE '6001%'
                 OR standard_account_code LIKE '6051%'
                 OR standard_account_code LIKE '6111%'
                 OR standard_account_code LIKE '6115%'
                 OR standard_account_code LIKE '6117%'
                 OR standard_account_code LIKE '6301%'
                 OR standard_account_code LIKE '6711%'
            THEN audited_amount ELSE 0 END) -
        SUM(CASE
            WHEN standard_account_code LIKE '5%'
                 OR standard_account_code LIKE '6401%'
                 OR standard_account_code LIKE '6402%'
                 OR standard_account_code LIKE '6403%'
                 OR standard_account_code LIKE '6601%'
                 OR standard_account_code LIKE '6602%'
                 OR standard_account_code LIKE '6603%'
                 OR standard_account_code LIKE '6604%'
                 OR standard_account_code LIKE '6701%'
                 OR standard_account_code LIKE '6702%'
            THEN audited_amount ELSE 0 END), 0 as profit_before_tax
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '5%' OR standard_account_code LIKE '6%')
              AND (is_deleted = false OR is_deleted IS NULL)
    """)

    result = await db.execute(sql_profit, {"pid": str(project_id), "year": year})
    profit_before_tax = float(result.scalar() or 0)

    tax_rate = 0.25  # 默认企业所得税率 25%

    return {
        "summary": f"利润总额 {profit_before_tax:,.2f}，适用税率 {tax_rate*100:.0f}%（纳税调整项需手动填写）",
        "profit_before_tax": profit_before_tax,
        "tax_rate": tax_rate,
        "known_adjustments": [],
        "note": "调增调减明细需在 N5-4 底稿中逐项填写",
    }

# ═══════════════════════════════════════════════════════════════════════════════
# S 类 — 专项循环 resolvers（纯数据消费者，从 D~N/trial_balance 读取）
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("revenue_audited_for_s20")
async def _resolve_revenue_for_s20(db: AsyncSession, project_id: UUID, year: int, **kw):
    """S20 营业收入扣除情况核查：读取营业收入审定金额。

    数据来源: trial_balance 表（6001 主营业务收入 + 6051 其他业务收入）
    返回结构: {"summary": str, "main_revenue": float, "other_revenue": float, "total_revenue": float}
    """
    sql = sa.text("""
        SELECT standard_account_code, audited_amount
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND standard_account_code LIKE '6001%'
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    result = await db.execute(sql, {"pid": str(project_id), "year": year})
    rows = result.fetchall()

    total_revenue = sum(float(r[1] or 0) for r in rows)

    # 其他业务收入
    sql_other = sa.text("""
        SELECT COALESCE(SUM(audited_amount), 0)
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND standard_account_code LIKE '6051%'
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    result_other = await db.execute(sql_other, {"pid": str(project_id), "year": year})
    other_revenue = float(result_other.scalar() or 0)

    return {
        "summary": f"主营业务收入 {total_revenue:,.2f}，其他业务收入 {other_revenue:,.2f}",
        "main_revenue": total_revenue,
        "other_revenue": other_revenue,
        "total_revenue": total_revenue + other_revenue,
    }


@auto_resolver("eps_data_from_tb")
async def _resolve_eps_data(db: AsyncSession, project_id: UUID, year: int, **kw):
    """S15 每股收益：读取净利润和股本数据。

    数据来源: trial_balance 表（5xxx/6xxx 损益科目 + 4001 实收资本）
    返回结构: {"summary": str, "net_profit": float, "shares_outstanding": float, "weighted_avg_shares": float}
    """
    # 净利润 = 损益类汇总
    sql_profit = sa.text("""
        SELECT COALESCE(SUM(CASE
            WHEN standard_account_code LIKE '6%' THEN audited_amount
            WHEN standard_account_code LIKE '5%' THEN -audited_amount
            ELSE 0
        END), 0)
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '5%' OR standard_account_code LIKE '6%')
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    result = await db.execute(sql_profit, {"pid": str(project_id), "year": year})
    net_profit = float(result.scalar() or 0)

    # 股本 = 4001 实收资本
    sql_shares = sa.text("""
        SELECT COALESCE(audited_amount, 0)
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND standard_account_code = '4001'
              AND (is_deleted = false OR is_deleted IS NULL)
        LIMIT 1
    """)
    result_shares = await db.execute(sql_shares, {"pid": str(project_id), "year": year})
    shares_outstanding = float(result_shares.scalar() or 0)

    return {
        "summary": f"净利润 {net_profit:,.2f}，股本 {shares_outstanding:,.0f}",
        "net_profit": net_profit,
        "shares_outstanding": shares_outstanding,
        "weighted_avg_shares": shares_outstanding,  # 简化：全年加权平均=期末
    }


@auto_resolver("non_recurring_items_from_tb")
async def _resolve_non_recurring_items(db: AsyncSession, project_id: UUID, year: int, **kw):
    """S17 非经常性损益：读取营业外收支科目审定金额。

    数据来源: trial_balance 表（6301 营业外收入 / 6711 营业外支出）
    返回结构: {"summary": str, "non_recurring_total": float, "extra_income": float, "extra_expense": float, "items": list}
    """
    # 营业外收入
    sql_extra_income = sa.text("""
        SELECT COALESCE(SUM(audited_amount), 0)
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND standard_account_code LIKE '6301%'
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    result = await db.execute(sql_extra_income, {"pid": str(project_id), "year": year})
    extra_income = float(result.scalar() or 0)

    # 营业外支出
    sql_extra_expense = sa.text("""
        SELECT COALESCE(SUM(audited_amount), 0)
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND standard_account_code LIKE '6711%'
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    result = await db.execute(sql_extra_expense, {"pid": str(project_id), "year": year})
    extra_expense = float(result.scalar() or 0)

    non_recurring_total = extra_income - extra_expense

    return {
        "summary": f"非经常性损益合计 {non_recurring_total:,.2f}（营业外收入 {extra_income:,.2f} - 营业外支出 {extra_expense:,.2f}）",
        "non_recurring_total": non_recurring_total,
        "extra_income": extra_income,
        "extra_expense": extra_expense,
        "items": [],  # 明细需在 S17 底稿中逐项填写
    }
