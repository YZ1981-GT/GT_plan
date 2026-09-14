"""H2 在建工程 — 利息资本化引擎端点

POST /api/workpapers/{wp_id}/h2/interest-cap/calculate → 2分支计算（无/有专门借款）
POST /api/workpapers/{wp_id}/h2/interest-cap/validate → 验证账面vs测算差异

纯函数实现（与前端 useH2InterestCapEngine.ts 对等逻辑）
CAS17借款费用准则：
- 无专门借款：资本化金额=累计支出加权平均数×加权资本化率
- 有专门借款：资本化金额=专门借款利息-闲置收益+一般借款补充资本化
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["h2-interest-cap"])


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：利息资本化计算引擎（与前端 useH2InterestCapEngine.ts 对等）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_weighted_cap_rate(loans: list[dict[str, float]]) -> float:
    """加权资本化率 = Σ(本金×利率×天数/365) / Σ(本金×天数/365).

    Args:
        loans: [{principal, rate, days}]
    Returns:
        加权资本化率（小数形式，如0.05表示5%）
    """
    numerator = 0.0
    denominator = 0.0
    for loan in loans:
        principal = loan.get("principal", 0.0)
        rate = loan.get("rate", 0.0)
        days = loan.get("days", 0.0)
        weight = principal * days / 365
        numerator += weight * rate
        denominator += weight
    if denominator == 0:
        return 0.0
    return numerator / denominator


def calc_weighted_expenditure(expenditures: list[dict[str, float]], total_days: int) -> float:
    """累计支出加权平均数 = Σ(支出金额×占用天数/总天数).

    Args:
        expenditures: [{amount, days}] — amount为支出金额，days为从支出日到期末的天数
        total_days: 资本化期间总天数
    Returns:
        累计支出加权平均数
    """
    if total_days <= 0:
        return 0.0
    total = 0.0
    for exp in expenditures:
        amount = exp.get("amount", 0.0)
        days = exp.get("days", 0.0)
        total += amount * days / total_days
    return total


def calc_cap_amount_no_borrow(weighted_exp: float, cap_rate: float) -> float:
    """无专门借款资本化金额 = 累计支出加权平均数 × 加权资本化率."""
    return weighted_exp * cap_rate


def calc_special_loan_cap(interest: float, idle_income: float) -> float:
    """专门借款资本化金额 = max(专门借款利息 - 闲置资金收益, 0)."""
    return max(0.0, interest - idle_income)


def calc_general_loan_supp(excess_weighted_exp: float, general_cap_rate: float) -> float:
    """一般借款补充资本化 = 超出专门借款的累计支出加权平均数 × 一般借款加权资本化率.

    excess_weighted_exp: 累计资产支出超过专门借款部分的加权平均数
    """
    if excess_weighted_exp <= 0 or general_cap_rate == 0:
        return 0.0
    return excess_weighted_exp * general_cap_rate


def calc_excess_weighted_exp(weighted_exp: float, special_loan_amount: float) -> float:
    """累计支出加权超过专门借款的部分（一般借款资本化基数）."""
    return max(0.0, weighted_exp - special_loan_amount)


def calc_cap_diff_rate(difference: float, total_cap: float) -> float | None:
    """差异率；分母为 0 时返回 None（避免 #DIV/0!）."""
    if abs(total_cap) < 1e-9:
        return None
    return difference / total_cap


def calc_total_cap_with_borrow(special_cap: float, general_supp: float) -> float:
    """有专门借款合计资本化金额 = 专门借款资本化 + 一般借款补充."""
    return special_cap + general_supp


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 模型
# ═══════════════════════════════════════════════════════════════════════════════


class LoanInput(BaseModel):
    loan_id: str = ""
    loan_name: str = ""
    principal: float = Field(ge=0)
    rate: float = Field(ge=0, le=1, description="年利率（小数形式如0.05）")
    days: int = Field(ge=0, le=366, description="资本化期间天数")


class ExpenditureInput(BaseModel):
    date: str = ""
    amount: float = Field(ge=0)
    days: int = Field(ge=0, le=366, description="从支出日到期末的天数")


class NoBorrowInput(BaseModel):
    """无专门借款分支输入."""
    loans: list[LoanInput] = Field(min_length=1, description="一般借款列表")
    expenditures: list[ExpenditureInput] = Field(min_length=1, description="资产支出列表")
    total_days: int = Field(ge=1, le=366, description="资本化期间总天数")
    book_capitalized: float = Field(default=0, description="账面资本化金额（用于差异验证）")


class WithBorrowInput(BaseModel):
    """有专门借款分支输入."""
    special_loans: list[LoanInput] = Field(min_length=1, description="专门借款列表")
    general_loans: list[LoanInput] = Field(default_factory=list, description="一般借款列表")
    special_interest: float = Field(ge=0, description="专门借款利息总额")
    idle_income: float = Field(ge=0, default=0, description="闲置资金收益")
    expenditures: list[ExpenditureInput] = Field(default_factory=list, description="资产支出列表")
    total_days: int = Field(ge=1, le=366, description="资本化期间总天数")
    special_loan_total: float = Field(ge=0, default=0, description="专门借款总额")
    book_capitalized: float = Field(default=0, description="账面资本化金额（用于差异验证）")


class CalculateRequest(BaseModel):
    branch: str = Field(description="no_borrow | with_borrow")
    no_borrow: NoBorrowInput | None = None
    with_borrow: WithBorrowInput | None = None


class CalculateResult(BaseModel):
    branch: str
    weighted_cap_rate: float = 0.0
    weighted_expenditure: float = 0.0
    special_loan_cap: float = 0.0
    general_loan_supp: float = 0.0
    total_capitalized: float = 0.0
    book_capitalized: float = 0.0
    difference: float = 0.0
    is_within_tolerance: bool = True
    details: dict[str, Any] = {}


class ValidateRequest(BaseModel):
    branch: str = Field(description="no_borrow | with_borrow")
    no_borrow: NoBorrowInput | None = None
    with_borrow: WithBorrowInput | None = None
    tolerance: float = Field(default=100.0, description="允许差异容忍度（元）")


class ValidateResponse(BaseModel):
    is_valid: bool
    total_difference: float
    summary: str
    result: CalculateResult


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


def _calculate_no_borrow(data: NoBorrowInput) -> CalculateResult:
    """计算无专门借款分支."""
    loans_dict = [{"principal": l.principal, "rate": l.rate, "days": l.days} for l in data.loans]
    exp_dict = [{"amount": e.amount, "days": e.days} for e in data.expenditures]

    cap_rate = calc_weighted_cap_rate(loans_dict)
    weighted_exp = calc_weighted_expenditure(exp_dict, data.total_days)
    total_cap = calc_cap_amount_no_borrow(weighted_exp, cap_rate)
    difference = data.book_capitalized - total_cap

    return CalculateResult(
        branch="no_borrow",
        weighted_cap_rate=round(cap_rate, 6),
        weighted_expenditure=round(weighted_exp, 2),
        total_capitalized=round(total_cap, 2),
        book_capitalized=data.book_capitalized,
        difference=round(difference, 2),
        is_within_tolerance=abs(difference) <= 100,
        details={
            "loan_count": len(data.loans),
            "expenditure_count": len(data.expenditures),
            "total_days": data.total_days,
        },
    )


def _calculate_with_borrow(data: WithBorrowInput) -> CalculateResult:
    """计算有专门借款分支."""
    # 专门借款资本化
    special_cap = calc_special_loan_cap(data.special_interest, data.idle_income)

    # 一般借款补充（如果支出超过专门借款总额）
    general_supp = 0.0
    general_cap_rate = 0.0
    weighted_exp = 0.0

    if data.general_loans and data.expenditures:
        exp_dict = [{"amount": e.amount, "days": e.days} for e in data.expenditures]
        weighted_exp = calc_weighted_expenditure(exp_dict, data.total_days)
        excess = calc_excess_weighted_exp(weighted_exp, data.special_loan_total)
        if excess > 0 and data.general_loans:
            general_loans_dict = [{"principal": l.principal, "rate": l.rate, "days": l.days} for l in data.general_loans]
            general_cap_rate = calc_weighted_cap_rate(general_loans_dict)
            general_supp = calc_general_loan_supp(excess, general_cap_rate)

    total_cap = calc_total_cap_with_borrow(special_cap, general_supp)
    difference = data.book_capitalized - total_cap

    return CalculateResult(
        branch="with_borrow",
        weighted_cap_rate=round(general_cap_rate, 6),
        weighted_expenditure=round(weighted_exp, 2),
        special_loan_cap=round(special_cap, 2),
        general_loan_supp=round(general_supp, 2),
        total_capitalized=round(total_cap, 2),
        book_capitalized=data.book_capitalized,
        difference=round(difference, 2),
        is_within_tolerance=abs(difference) <= 100,
        details={
            "special_interest": data.special_interest,
            "idle_income": data.idle_income,
            "special_loan_total": data.special_loan_total,
            "excess_expenditure": round(max(weighted_exp - data.special_loan_total, 0.0), 2),
        },
    )


@router.post("/api/workpapers/{wp_id}/h2/interest-cap/calculate", response_model=CalculateResult)
async def h2_interest_cap_calculate(
    wp_id: str,
    body: CalculateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalculateResult:
    """利息资本化计算（2分支：无/有专门借款）."""
    if body.branch == "no_borrow":
        if not body.no_borrow:
            raise HTTPException(400, "no_borrow 分支需提供 no_borrow 数据")
        return _calculate_no_borrow(body.no_borrow)
    elif body.branch == "with_borrow":
        if not body.with_borrow:
            raise HTTPException(400, "with_borrow 分支需提供 with_borrow 数据")
        return _calculate_with_borrow(body.with_borrow)
    else:
        raise HTTPException(400, f"不支持的 branch: {body.branch}。支持: no_borrow / with_borrow")


@router.post("/api/workpapers/{wp_id}/h2/interest-cap/validate", response_model=ValidateResponse)
async def h2_interest_cap_validate(
    wp_id: str,
    body: ValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidateResponse:
    """验证账面利息资本化金额与测算差异."""
    if body.branch == "no_borrow":
        if not body.no_borrow:
            raise HTTPException(400, "no_borrow 分支需提供 no_borrow 数据")
        result = _calculate_no_borrow(body.no_borrow)
    elif body.branch == "with_borrow":
        if not body.with_borrow:
            raise HTTPException(400, "with_borrow 分支需提供 with_borrow 数据")
        result = _calculate_with_borrow(body.with_borrow)
    else:
        raise HTTPException(400, f"不支持的 branch: {body.branch}。支持: no_borrow / with_borrow")

    is_valid = abs(result.difference) <= body.tolerance
    result.is_within_tolerance = is_valid

    branch_label = "无专门借款" if body.branch == "no_borrow" else "有专门借款"
    summary = (
        f"利息资本化验证（{branch_label}）：\n"
        f"测算资本化金额={result.total_capitalized:,.2f}元，"
        f"账面资本化金额={result.book_capitalized:,.2f}元，"
        f"差异={result.difference:,.2f}元，"
        f"容忍度={body.tolerance:,.2f}元，"
        f"结果：{'通过' if is_valid else '差异超容忍度'}"
    )

    return ValidateResponse(
        is_valid=is_valid,
        total_difference=result.difference,
        summary=summary,
        result=result,
    )
