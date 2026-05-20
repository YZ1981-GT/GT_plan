"""K 管理循环 — K-F7 销售/管理费用分析引擎

POST /api/projects/{project_id}/workpapers/{wp_id}/k8/expense-analysis

3 维度分析：
  - 同比 YoY: (current - prior) / prior
  - 预算差异 Budget Variance: (current - budget) / budget
  - 行业对比 Industry Comparison: current_rate vs industry_avg_rate

异常标记规则：
  - YoY 绝对变化率 > 20% → "yoy_change_anomaly_{category}"
  - 预算差异绝对率 > 10% → "budget_overrun_{category}" 或 "budget_underrun_{category}"
  - 行业对比偏离 > 10% → "industry_deviation_{category}"

写回模式：parsed_data.expense_analysis[sheet] = {wp_code, applied_at, data}
is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动。

对应 spec：workpaper-k-admin-cycle K-F7 / ADR-K4
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/k8",
    tags=["wp-k-expense-analysis"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class ExpenseAnalysisRequest(BaseModel):
    """费用分析请求"""

    wp_code: Literal["K8", "K9"] = Field(
        ..., description="底稿 wp_code（K8 销售费用 / K9 管理费用）"
    )
    current_year: dict[str, float] = Field(
        ..., description="本年费用 {费用类别: 金额}（如 {'职工薪酬': 1200000.00}）"
    )
    prior_year: dict[str, float] = Field(
        default_factory=dict, description="上年费用 {费用类别: 金额}"
    )
    budget: dict[str, float] | None = Field(
        None, description="预算金额 {费用类别: 预算金额}（可选）"
    )
    industry_avg_rates: dict[str, float] | None = Field(
        None, description="行业均值占收入比率 {费用类别: 比率}（可选）"
    )
    revenue: float | None = Field(
        None, ge=0, description="本年营业收入（用于行业占比计算）"
    )
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 parsed_data.expense_analysis[sheet]",
    )


class YoyChangeItem(BaseModel):
    amount_change: float
    rate_change: float
    flag: str  # 'normal' / 'increase_anomaly' / 'decrease_anomaly'


class BudgetVarianceItem(BaseModel):
    variance_amount: float
    variance_rate: float
    flag: str  # 'normal' / 'overrun' / 'underrun'


class IndustryComparisonItem(BaseModel):
    project_rate: float
    industry_avg_rate: float
    deviation: float  # 项目占比 - 行业占比
    flag: str  # 'normal' / 'above_industry' / 'below_industry'


class ExpenseAnalysisResponse(BaseModel):
    yoy_changes: dict[str, YoyChangeItem]
    budget_variances: dict[str, BudgetVarianceItem] | None
    industry_comparison: dict[str, IndustryComparisonItem] | None
    anomaly_flags: list[str]
    summary: str
    is_llm_stub: bool
    applied_to_sheet: str | None = None
    applied_at: str | None = None


# ─── Calculation Core ────────────────────────────────────────────────────────


YOY_CHANGE_THRESHOLD = 0.20  # |yoy_rate| > 20% → anomaly
BUDGET_VARIANCE_THRESHOLD = 0.10  # |budget_rate| > 10% → anomaly
INDUSTRY_DEVIATION_THRESHOLD = 0.10  # |industry_dev| > 10% → anomaly


def _quantize(value: float, places: int = 4) -> float:
    """保留指定小数位"""
    return round(value, places)


def _calc_yoy(
    current: dict[str, float], prior: dict[str, float]
) -> dict[str, dict[str, Any]]:
    """计算同比变化（按费用类别）

    Returns: {category: {amount_change, rate_change, flag}}
    """
    result: dict[str, dict[str, Any]] = {}
    for cat, cur in current.items():
        prior_val = prior.get(cat, 0.0)
        amount_change = _quantize(cur - prior_val, 2)
        if prior_val == 0:
            # 上年为 0，无法算变化率（视为新增）
            rate_change = 0.0 if cur == 0 else float("inf")
            flag = "new_category" if cur > 0 else "normal"
        else:
            rate_change = _quantize(amount_change / prior_val, 4)
            if rate_change > YOY_CHANGE_THRESHOLD:
                flag = "increase_anomaly"
            elif rate_change < -YOY_CHANGE_THRESHOLD:
                flag = "decrease_anomaly"
            else:
                flag = "normal"
        result[cat] = {
            "amount_change": amount_change,
            "rate_change": rate_change if rate_change != float("inf") else 999.0,
            "flag": flag,
        }
    return result


def _calc_budget_variance(
    current: dict[str, float], budget: dict[str, float]
) -> dict[str, dict[str, Any]]:
    """计算预算差异

    Returns: {category: {variance_amount, variance_rate, flag}}
    """
    result: dict[str, dict[str, Any]] = {}
    for cat, cur in current.items():
        bud_val = budget.get(cat, 0.0)
        variance_amount = _quantize(cur - bud_val, 2)
        if bud_val == 0:
            variance_rate = 0.0 if cur == 0 else 999.0
            flag = "no_budget" if cur > 0 else "normal"
        else:
            variance_rate = _quantize(variance_amount / bud_val, 4)
            if variance_rate > BUDGET_VARIANCE_THRESHOLD:
                flag = "overrun"
            elif variance_rate < -BUDGET_VARIANCE_THRESHOLD:
                flag = "underrun"
            else:
                flag = "normal"
        result[cat] = {
            "variance_amount": variance_amount,
            "variance_rate": variance_rate,
            "flag": flag,
        }
    return result


def _calc_industry_comparison(
    current: dict[str, float],
    industry_avg_rates: dict[str, float],
    revenue: float,
) -> dict[str, dict[str, Any]]:
    """计算行业对比（费用占收入比 vs 行业均值）

    Returns: {category: {project_rate, industry_avg_rate, deviation, flag}}
    """
    if revenue <= 0:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for cat, cur in current.items():
        if cat not in industry_avg_rates:
            continue
        project_rate = _quantize(cur / revenue, 4)
        industry_rate = industry_avg_rates[cat]
        deviation = _quantize(project_rate - industry_rate, 4)
        if abs(deviation) > INDUSTRY_DEVIATION_THRESHOLD:
            flag = "above_industry" if deviation > 0 else "below_industry"
        else:
            flag = "normal"
        result[cat] = {
            "project_rate": project_rate,
            "industry_avg_rate": industry_rate,
            "deviation": deviation,
            "flag": flag,
        }
    return result


def _build_anomaly_flags(
    yoy: dict[str, dict[str, Any]],
    budget: dict[str, dict[str, Any]] | None,
    industry: dict[str, dict[str, Any]] | None,
) -> list[str]:
    """汇总所有异常标记（用于审计师快速定位）"""
    flags: list[str] = []
    for cat, info in yoy.items():
        if info["flag"] in ("increase_anomaly", "decrease_anomaly"):
            flags.append(f"yoy_{info['flag']}_{cat}")
    if budget:
        for cat, info in budget.items():
            if info["flag"] in ("overrun", "underrun"):
                flags.append(f"budget_{info['flag']}_{cat}")
    if industry:
        for cat, info in industry.items():
            if info["flag"] in ("above_industry", "below_industry"):
                flags.append(f"industry_{info['flag']}_{cat}")
    return flags


def _build_summary(
    wp_code: str,
    yoy: dict[str, dict[str, Any]],
    anomaly_count: int,
    is_llm_stub: bool,
) -> str:
    """生成审计师友好的简要分析（非 LLM 版）"""
    name_map = {"K8": "销售费用", "K9": "管理费用"}
    name = name_map.get(wp_code, wp_code)
    total_categories = len(yoy)
    if total_categories == 0:
        return f"{name}分析未提供数据。"
    avg_change = sum(v["rate_change"] for v in yoy.values() if v["rate_change"] < 999) / max(
        1, sum(1 for v in yoy.values() if v["rate_change"] < 999)
    )
    suffix = "（待 wp_ai_service 真实接入）" if is_llm_stub else ""
    return (
        f"{name}分析：共 {total_categories} 个费用类别，"
        f"同比平均变化率 {avg_change:.1%}，发现 {anomaly_count} 项异常{suffix}。"
    )


# ─── Validation ───────────────────────────────────────────────────────────────


def _validate_request(payload: ExpenseAnalysisRequest) -> None:
    if not payload.current_year:
        raise HTTPException(400, "当年费用数据不能为空")
    for cat, val in payload.current_year.items():
        if val < 0:
            raise HTTPException(
                400, f"费用金额不能为负：{cat}={val}"
            )


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/expense-analysis", response_model=ExpenseAnalysisResponse)
async def k_expense_analysis(
    project_id: str,
    wp_id: str,
    payload: ExpenseAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> ExpenseAnalysisResponse:
    """K-F7 销售/管理费用 3 维度分析

    业务约束：
    - current_year 不为空（否则 400）
    - 费用金额非负（否则 400）
    - is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动
    - 支持 apply_to_sheet 写回
    """
    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    _validate_request(payload)

    yoy = _calc_yoy(payload.current_year, payload.prior_year)
    budget = (
        _calc_budget_variance(payload.current_year, payload.budget)
        if payload.budget
        else None
    )
    industry = (
        _calc_industry_comparison(
            payload.current_year, payload.industry_avg_rates, payload.revenue or 0.0
        )
        if (payload.industry_avg_rates and (payload.revenue or 0) > 0)
        else None
    )
    flags = _build_anomaly_flags(yoy, budget, industry)

    is_llm_stub = not getattr(settings, "WP_AI_SERVICE_ENABLED", False)

    summary = _build_summary(payload.wp_code, yoy, len(flags), is_llm_stub)

    # 写回
    applied_to_sheet = None
    applied_at = None
    if payload.apply_to_sheet:
        result_data = {
            "wp_code": payload.wp_code,
            "yoy_changes": yoy,
            "budget_variances": budget,
            "industry_comparison": industry,
            "anomaly_flags": flags,
            "summary": summary,
        }
        applied_to_sheet = await _maybe_apply_analysis_to_workpaper(
            db, wp_id, payload.apply_to_sheet, payload.wp_code, result_data
        )
        if applied_to_sheet:
            applied_at = datetime.now(timezone.utc).isoformat()

    return ExpenseAnalysisResponse(
        yoy_changes={k: YoyChangeItem(**v) for k, v in yoy.items()},
        budget_variances=(
            {k: BudgetVarianceItem(**v) for k, v in budget.items()} if budget else None
        ),
        industry_comparison=(
            {k: IndustryComparisonItem(**v) for k, v in industry.items()}
            if industry
            else None
        ),
        anomaly_flags=flags,
        summary=summary,
        is_llm_stub=is_llm_stub,
        applied_to_sheet=applied_to_sheet,
        applied_at=applied_at,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_analysis_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    sheet: str,
    wp_code: str,
    data: dict[str, Any],
) -> str | None:
    """把费用分析结果写回 working_paper.parsed_data.expense_analysis[sheet]

    数据结构：
      parsed_data.expense_analysis[sheet] = {
        "wp_code": "K8" or "K9",
        "applied_at": ISO8601,
        "data": {
          "yoy_changes": {...},
          "budget_variances": {...},
          "industry_comparison": {...},
          "anomaly_flags": [...],
          "summary": "..."
        }
      }
    """
    from app.models.workpaper_models import WorkingPaper

    try:
        wp_uuid = UUID(wp_id)
    except Exception:
        return None

    res = await db.execute(sa.select(WorkingPaper).where(WorkingPaper.id == wp_uuid))
    wp = res.scalar_one_or_none()
    if wp is None:
        return None

    pd = wp.parsed_data or {}
    if not isinstance(pd, dict):
        pd = {}
    pd.setdefault("expense_analysis", {})
    pd["expense_analysis"][sheet] = {
        "wp_code": wp_code,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return sheet
