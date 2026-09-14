"""S 类交易型底稿 Auto Data Resolvers — S4/S5/S6/S8/S9/S10 审定表自动取数.

从 trial_balance 读取各底稿相关科目的未审数/审定数，
供审定表组件自动填充、用户可 field_overrides 覆盖。

数据来源: trial_balance 表（v2 正数口径）
Requirements: 9.2

科目映射：
- S4 非货币性资产交换: 1601固定资产/1701无形资产/1403原材料
- S5 债务重组: 1122应收/2202应付/2501短借/2601长借
- S6 关联方资金占用: 1221其他应收/1123预付/1231应收股利
- S8 租赁: 1901使用权资产/2802租赁负债
- S9 电子商务: 6001主营收入/1122应收
- S10 环境事项: 2801预计负债/6601管理费用
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
# S4 非货币性资产交换
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("s4_nonmonetary_exchange_data")
async def _resolve_s4_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """S4 非货币性资产交换审定表：读取相关非货币性资产科目.

    数据来源: trial_balance（1601固定资产/1701无形资产/1403原材料等）
    返回结构: {"summary": str, "accounts": dict, ...}
    """
    # 非货币性资产相关科目
    codes = ("1601", "1701", "1403", "1404", "1801")
    placeholders = ", ".join(f":a{i}" for i in range(len(codes)))
    params: dict[str, Any] = {
        "pid": str(project_id),
        "year": year,
        **{f"a{i}": c for i, c in enumerate(codes)},
    }

    result = await db.execute(
        sa.text(f"""
            SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
            FROM trial_balance
            WHERE project_id = :pid AND year = :year
                  AND standard_account_code IN ({placeholders})
                  AND (is_deleted = false OR is_deleted IS NULL)
        """),
        params,
    )
    rows = result.fetchall()

    accounts: dict[str, dict[str, float]] = {}
    for row in rows:
        accounts[row[0]] = {
            "unadjusted": float(row[1] or 0),
            "aje_adjustment": float(row[2] or 0),
            "audited": float(row[3] or 0),
        }

    total_audited = sum(v["audited"] for v in accounts.values())
    summary = f"S4非货币性资产: {len(accounts)}个科目, 审定合计={total_audited:,.2f}"

    return {
        "summary": summary,
        "accounts": accounts,
        "total_audited": total_audited,
        "account_codes": list(codes),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# S5 债务重组
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("s5_debt_restructuring_data")
async def _resolve_s5_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """S5 债务重组审定表：读取债权/债务相关科目.

    数据来源: trial_balance（1122应收/2202应付/2501短借/2601长借等）
    返回结构: {"summary": str, "creditor_accounts": dict, "debtor_accounts": dict, ...}
    """
    # 债权人视角科目
    creditor_codes = ("1122", "1123", "1131", "1221")
    # 债务人视角科目
    debtor_codes = ("2202", "2501", "2601", "2701")

    all_codes = creditor_codes + debtor_codes
    placeholders = ", ".join(f":a{i}" for i in range(len(all_codes)))
    params: dict[str, Any] = {
        "pid": str(project_id),
        "year": year,
        **{f"a{i}": c for i, c in enumerate(all_codes)},
    }

    result = await db.execute(
        sa.text(f"""
            SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
            FROM trial_balance
            WHERE project_id = :pid AND year = :year
                  AND standard_account_code IN ({placeholders})
                  AND (is_deleted = false OR is_deleted IS NULL)
        """),
        params,
    )
    rows = result.fetchall()

    creditor_accounts: dict[str, dict[str, float]] = {}
    debtor_accounts: dict[str, dict[str, float]] = {}

    for row in rows:
        entry = {
            "unadjusted": float(row[1] or 0),
            "aje_adjustment": float(row[2] or 0),
            "audited": float(row[3] or 0),
        }
        if row[0] in creditor_codes:
            creditor_accounts[row[0]] = entry
        else:
            debtor_accounts[row[0]] = entry

    creditor_total = sum(v["audited"] for v in creditor_accounts.values())
    debtor_total = sum(v["audited"] for v in debtor_accounts.values())
    summary = (
        f"S5债务重组: 债权人科目{len(creditor_accounts)}个 审定={creditor_total:,.2f}, "
        f"债务人科目{len(debtor_accounts)}个 审定={debtor_total:,.2f}"
    )

    return {
        "summary": summary,
        "creditor_accounts": creditor_accounts,
        "debtor_accounts": debtor_accounts,
        "creditor_total": creditor_total,
        "debtor_total": debtor_total,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# S6 大股东及关联方资金占用
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("s6_fund_occupation_data")
async def _resolve_s6_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """S6 大股东及关联方资金占用审定表：读取其他应收/预付相关科目.

    数据来源: trial_balance（1221其他应收/1123预付/1231应收股利等）
    返回结构: {"summary": str, "accounts": dict, "occupation_total": float}
    """
    codes = ("1221", "1123", "1231", "2241")  # 其他应收/预付/应收股利/其他应付
    placeholders = ", ".join(f":a{i}" for i in range(len(codes)))
    params: dict[str, Any] = {
        "pid": str(project_id),
        "year": year,
        **{f"a{i}": c for i, c in enumerate(codes)},
    }

    result = await db.execute(
        sa.text(f"""
            SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
            FROM trial_balance
            WHERE project_id = :pid AND year = :year
                  AND standard_account_code IN ({placeholders})
                  AND (is_deleted = false OR is_deleted IS NULL)
        """),
        params,
    )
    rows = result.fetchall()

    accounts: dict[str, dict[str, float]] = {}
    for row in rows:
        accounts[row[0]] = {
            "unadjusted": float(row[1] or 0),
            "aje_adjustment": float(row[2] or 0),
            "audited": float(row[3] or 0),
        }

    occupation_total = sum(v["audited"] for v in accounts.values())
    summary = f"S6资金占用: {len(accounts)}个科目, 合计={occupation_total:,.2f}"

    return {
        "summary": summary,
        "accounts": accounts,
        "occupation_total": occupation_total,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# S8 租赁
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("s8_lease_data")
async def _resolve_s8_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """S8 租赁审定表：读取使用权资产/租赁负债科目.

    数据来源: trial_balance（1901使用权资产/2802租赁负债）
    返回结构: {"summary": str, "rou_asset": dict, "lease_liability": dict}
    """
    codes = ("1901", "2802")
    placeholders = ", ".join(f":a{i}" for i in range(len(codes)))
    params: dict[str, Any] = {
        "pid": str(project_id),
        "year": year,
        **{f"a{i}": c for i, c in enumerate(codes)},
    }

    result = await db.execute(
        sa.text(f"""
            SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
            FROM trial_balance
            WHERE project_id = :pid AND year = :year
                  AND standard_account_code IN ({placeholders})
                  AND (is_deleted = false OR is_deleted IS NULL)
        """),
        params,
    )
    rows = result.fetchall()

    rou_asset: dict[str, float] = {"unadjusted": 0, "audited": 0}
    lease_liability: dict[str, float] = {"unadjusted": 0, "audited": 0}

    for row in rows:
        entry = {"unadjusted": float(row[1] or 0), "audited": float(row[3] or 0)}
        if row[0] == "1901":
            rou_asset = entry
        elif row[0] == "2802":
            lease_liability = entry

    summary = (
        f"S8租赁: 使用权资产审定={rou_asset['audited']:,.2f}, "
        f"租赁负债审定={lease_liability['audited']:,.2f}"
    )

    return {
        "summary": summary,
        "rou_asset": rou_asset,
        "lease_liability": lease_liability,
        "account_codes": list(codes),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# S9 对电子商务的考虑
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("s9_ecommerce_data")
async def _resolve_s9_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """S9 电子商务审定表：读取电商收入/应收相关科目.

    数据来源: trial_balance（6001主营收入/1122应收账款）
    返回结构: {"summary": str, "revenue": dict, "receivables": dict}
    """
    codes = ("6001", "1122")
    placeholders = ", ".join(f":a{i}" for i in range(len(codes)))
    params: dict[str, Any] = {
        "pid": str(project_id),
        "year": year,
        **{f"a{i}": c for i, c in enumerate(codes)},
    }

    result = await db.execute(
        sa.text(f"""
            SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
            FROM trial_balance
            WHERE project_id = :pid AND year = :year
                  AND standard_account_code IN ({placeholders})
                  AND (is_deleted = false OR is_deleted IS NULL)
        """),
        params,
    )
    rows = result.fetchall()

    revenue: dict[str, float] = {"unadjusted": 0, "audited": 0}
    receivables: dict[str, float] = {"unadjusted": 0, "audited": 0}

    for row in rows:
        entry = {"unadjusted": float(row[1] or 0), "audited": float(row[3] or 0)}
        if row[0] == "6001":
            revenue = entry
        elif row[0] == "1122":
            receivables = entry

    summary = f"S9电商: 收入审定={revenue['audited']:,.2f}, 应收审定={receivables['audited']:,.2f}"

    return {
        "summary": summary,
        "revenue": revenue,
        "receivables": receivables,
        "account_codes": list(codes),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# S10 对环境事项的考虑
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("s10_environment_data")
async def _resolve_s10_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """S10 环境事项审定表：读取环境相关负债/费用科目.

    数据来源: trial_balance（2801预计负债/6601管理费用）
    返回结构: {"summary": str, "provisions": dict, "expenses": dict}
    """
    codes = ("2801", "6601")
    placeholders = ", ".join(f":a{i}" for i in range(len(codes)))
    params: dict[str, Any] = {
        "pid": str(project_id),
        "year": year,
        **{f"a{i}": c for i, c in enumerate(codes)},
    }

    result = await db.execute(
        sa.text(f"""
            SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
            FROM trial_balance
            WHERE project_id = :pid AND year = :year
                  AND standard_account_code IN ({placeholders})
                  AND (is_deleted = false OR is_deleted IS NULL)
        """),
        params,
    )
    rows = result.fetchall()

    provisions: dict[str, float] = {"unadjusted": 0, "audited": 0}
    expenses: dict[str, float] = {"unadjusted": 0, "audited": 0}

    for row in rows:
        entry = {"unadjusted": float(row[1] or 0), "audited": float(row[3] or 0)}
        if row[0] == "2801":
            provisions = entry
        elif row[0] == "6601":
            expenses = entry

    summary = (
        f"S10环境: 预计负债审定={provisions['audited']:,.2f}, "
        f"管理费用审定={expenses['audited']:,.2f}"
    )

    return {
        "summary": summary,
        "provisions": provisions,
        "expenses": expenses,
        "account_codes": list(codes),
    }
