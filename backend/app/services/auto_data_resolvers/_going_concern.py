"""A15 持续经营财务指标 Resolver.

从 trial_balance 按 account_category 聚合审定额，
计算流动比率/速动比率/资产负债率/净资产/累计未分配利润等关键指标。

Usage:
    result = await resolve_auto_data_source(db, project_id, year, "a15_financial_ratios")
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.services.auto_data_resolvers import auto_resolver

# ═══════════════════════════════════════════════════════════════════════════════
# 科目编码范围（中国企业会计准则）
# ═══════════════════════════════════════════════════════════════════════════════

# 流动资产: 1001~1499 (货币资金/应收/预付/存货等)
_CURRENT_ASSET_RANGE = ("1001", "1499")
# 非流动资产: 1501~1899
_NON_CURRENT_ASSET_RANGE = ("1501", "1899")
# 流动负债: 2001~2299
_CURRENT_LIABILITY_RANGE = ("2001", "2299")
# 非流动负债: 2301~2699
_NON_CURRENT_LIABILITY_RANGE = ("2301", "2699")
# 速动资产排除：存货 1401~1499
_INVENTORY_RANGE = ("1401", "1499")
# 未分配利润: 4104
_RETAINED_EARNINGS_CODE = "4104"


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：指标计算
# ═══════════════════════════════════════════════════════════════════════════════


def compute_ratios(
    current_assets: Decimal,
    current_liabilities: Decimal,
    inventory: Decimal,
    total_assets: Decimal,
    total_liabilities: Decimal,
    retained_earnings: Decimal,
) -> dict[str, Any]:
    """计算财务指标（纯函数，便于测试）。"""
    net_assets = total_assets - total_liabilities

    # 流动比率 = 流动资产 / 流动负债
    current_ratio = (
        float(current_assets / current_liabilities)
        if current_liabilities != 0
        else None
    )

    # 速动比率 = (流动资产 - 存货) / 流动负债
    quick_ratio = (
        float((current_assets - inventory) / current_liabilities)
        if current_liabilities != 0
        else None
    )

    # 资产负债率 = 总负债 / 总资产
    debt_ratio = (
        float(total_liabilities / total_assets)
        if total_assets != 0
        else None
    )

    return {
        "current_ratio": round(current_ratio, 4) if current_ratio is not None else None,
        "quick_ratio": round(quick_ratio, 4) if quick_ratio is not None else None,
        "debt_ratio": round(debt_ratio, 4) if debt_ratio is not None else None,
        "net_assets": float(net_assets),
        "retained_earnings": float(retained_earnings),
        "current_assets": float(current_assets),
        "current_liabilities": float(current_liabilities),
        "total_assets": float(total_assets),
        "total_liabilities": float(total_liabilities),
    }


def assess_going_concern_risk(ratios: dict[str, Any]) -> str:
    """根据指标给出风险等级提示。

    Returns:
        "low" / "medium" / "high" / "undetermined"
    """
    cr = ratios.get("current_ratio")
    dr = ratios.get("debt_ratio")
    na = ratios.get("net_assets", 0)
    re = ratios.get("retained_earnings", 0)

    if cr is None or dr is None:
        return "undetermined"

    # 高风险: 流动比率<0.5 或 资不抵债 或 累计未分配利润严重为负
    if cr < 0.5 or na < 0 or re < -abs(na) * 0.5:
        return "high"
    # 中风险: 流动比率<1 或 资产负债率>80%
    if cr < 1.0 or dr > 0.8:
        return "medium"
    return "low"


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver 注册
# ═══════════════════════════════════════════════════════════════════════════════


async def _sum_range(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    start_code: str,
    end_code: str,
) -> Decimal:
    """按科目编码范围汇总 audited_amount（正数口径）。"""
    result = await db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(TrialBalance.audited_amount), 0)).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
            TrialBalance.standard_account_code >= start_code,
            TrialBalance.standard_account_code <= end_code,
        )
    )
    return Decimal(str(result.scalar_one()))


async def _sum_code(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    code: str,
) -> Decimal:
    """按精确科目编码汇总 audited_amount。"""
    result = await db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(TrialBalance.audited_amount), 0)).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
            TrialBalance.standard_account_code == code,
        )
    )
    return Decimal(str(result.scalar_one()))


@auto_resolver("a15_financial_ratios")
async def _resolve_a15_financial_ratios(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 计算 A15 持续经营财务指标。

    Returns:
        {
            "summary": str,
            "ratios": {current_ratio, quick_ratio, debt_ratio, net_assets, retained_earnings, ...},
            "risk_level": "low" | "medium" | "high" | "undetermined",
        }
    """
    current_assets = await _sum_range(db, project_id, year, *_CURRENT_ASSET_RANGE)
    inventory = await _sum_range(db, project_id, year, *_INVENTORY_RANGE)
    current_liabilities = await _sum_range(db, project_id, year, *_CURRENT_LIABILITY_RANGE)
    non_current_liabilities = await _sum_range(db, project_id, year, *_NON_CURRENT_LIABILITY_RANGE)
    non_current_assets = await _sum_range(db, project_id, year, *_NON_CURRENT_ASSET_RANGE)
    retained_earnings = await _sum_code(db, project_id, year, _RETAINED_EARNINGS_CODE)

    total_assets = current_assets + non_current_assets
    total_liabilities = current_liabilities + non_current_liabilities

    ratios = compute_ratios(
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        inventory=inventory,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        retained_earnings=retained_earnings,
    )

    risk_level = assess_going_concern_risk(ratios)

    # 构建摘要
    parts = []
    if ratios["current_ratio"] is not None:
        parts.append(f"流动比率={ratios['current_ratio']:.2f}")
    if ratios["debt_ratio"] is not None:
        parts.append(f"资产负债率={ratios['debt_ratio']:.1%}")
    if ratios["net_assets"] is not None:
        parts.append(f"净资产={ratios['net_assets']:,.0f}")
    summary = "；".join(parts) if parts else "试算表无数据"

    return {
        "summary": summary,
        "ratios": ratios,
        "risk_level": risk_level,
    }
