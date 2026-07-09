"""H5 油气资产 — 业务逻辑服务层

功能：
- 行业适用性检查（oil_gas / mining）
- 折耗公式后端验证
- 跨sheet勾稽校验
- 导入导出辅助方法

Requirements: 9.1-9.5, 12.1-12.3
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 行业适用性
# ═══════════════════════════════════════════════════════════════════════════════

_APPLICABLE_INDUSTRIES = {"oil_gas", "mining"}


async def check_industry_applicability(
    db: AsyncSession,
    project_id: str,
) -> dict[str, Any]:
    """
    检查项目行业是否适用H5油气资产底稿。

    Returns:
        {
            "is_applicable": bool,
            "industry": str | None,
            "message": str,
        }
    """
    result = await db.execute(
        sa.text("""
            SELECT industry FROM projects WHERE id = :pid LIMIT 1
        """),
        {"pid": project_id},
    )
    row = result.first()
    if not row:
        return {
            "is_applicable": False,
            "industry": None,
            "message": "项目不存在",
        }

    industry = (row[0] or "").strip().lower()
    is_applicable = industry in _APPLICABLE_INDUSTRIES

    if is_applicable:
        return {
            "is_applicable": True,
            "industry": industry,
            "message": f"项目行业 [{industry}] 适用H5油气资产底稿",
        }
    else:
        return {
            "is_applicable": False,
            "industry": industry,
            "message": f"本底稿仅适用于石油天然气/采矿行业项目（当前行业: {industry or '未设置'}）",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 折耗公式后端验证
# ═══════════════════════════════════════════════════════════════════════════════


def calc_unit_depletion(
    cost: float,
    salvage: float,
    production: float,
    reserves: float,
) -> float:
    """
    单位产量法折耗计算。

    折耗 = (原值 - 残值) × 当期产量 ÷ 预计可采储量

    Args:
        cost: 原值
        salvage: 残值
        production: 当期产量
        reserves: 预计可采储量

    Returns:
        本期折耗金额，储量为0时返回0
    """
    if reserves <= 0:
        return 0.0
    depletable = cost - salvage
    if depletable <= 0:
        return 0.0
    return depletable * production / reserves


def calc_depletion_capped(
    cost: float,
    salvage: float,
    acc_depletion: float,
) -> float:
    """
    折耗封顶：最大可折耗金额 = 原值 - 残值 - 累计已提折耗

    当产量>储量导致公式折耗超限时，封顶到此值。
    """
    cap = cost - salvage - acc_depletion
    return max(0.0, cap)


def calc_depletion_after_impairment(
    net_value: float,
    salvage: float,
    production: float,
    remain_reserves: float,
) -> float:
    """
    含减值后折耗：基于净值计算。

    折耗 = (净值 - 残值) × 当期产量 ÷ 剩余可采储量
    """
    if remain_reserves <= 0:
        return 0.0
    depletable = net_value - salvage
    if depletable <= 0:
        return 0.0
    return depletable * production / remain_reserves


def calc_depletion_rate(acc_depletion: float, cost: float) -> float:
    """折耗率(%) = 累计折耗 / 原值 × 100"""
    if cost <= 0:
        return 0.0
    return (acc_depletion / cost) * 100.0


def calc_remaining_reserves(total_reserves: float, acc_production: float) -> float:
    """剩余可采储量 = 总储量 - 累计产量"""
    return max(0.0, total_reserves - acc_production)


# ═══════════════════════════════════════════════════════════════════════════════
# 跨sheet勾稽校验
# ═══════════════════════════════════════════════════════════════════════════════


def validate_cross_sheet_reconciliation(
    adjudication_cost_end: float,
    detail_cost_total: float,
    adjudication_depletion_end: float,
    detail_depletion_total: float,
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """
    验证H5-1审定表与H5-2明细表的跨sheet一致性。

    Returns:
        {
            "cost_diff": float,
            "depletion_diff": float,
            "is_cost_matched": bool,
            "is_depletion_matched": bool,
            "is_all_matched": bool,
        }
    """
    cost_diff = abs(adjudication_cost_end - detail_cost_total)
    depletion_diff = abs(adjudication_depletion_end - detail_depletion_total)

    return {
        "cost_diff": adjudication_cost_end - detail_cost_total,
        "depletion_diff": adjudication_depletion_end - detail_depletion_total,
        "is_cost_matched": cost_diff <= tolerance,
        "is_depletion_matched": depletion_diff <= tolerance,
        "is_all_matched": cost_diff <= tolerance and depletion_diff <= tolerance,
    }


def validate_depletion_vs_adjudication(
    depletion_total: float,
    adjudication_credit: float,
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """
    验证H5-12折耗测算本期计提 = H5-1审定表累计折耗本期贷方发生。

    Returns:
        {
            "diff": float,
            "is_matched": bool,
        }
    """
    diff = depletion_total - adjudication_credit
    return {
        "diff": diff,
        "is_matched": abs(diff) <= tolerance,
    }


def validate_addition_vs_adjudication(
    addition_total: float,
    adjudication_debit: float,
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """
    验证H5-7增加合计 = H5-1审定表原值本期借方发生。
    """
    diff = addition_total - adjudication_debit
    return {
        "diff": diff,
        "is_matched": abs(diff) <= tolerance,
    }


def validate_disposal_vs_adjudication(
    disposal_total: float,
    adjudication_credit: float,
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """
    验证H5-8减少合计 = H5-1审定表原值本期贷方发生。
    """
    diff = disposal_total - adjudication_credit
    return {
        "diff": diff,
        "is_matched": abs(diff) <= tolerance,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出辅助
# ═══════════════════════════════════════════════════════════════════════════════


def safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为float"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_bool(value: Any) -> bool:
    """安全转换为bool"""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("是", "true", "1", "yes")
