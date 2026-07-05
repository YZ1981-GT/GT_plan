"""L1 短期借款 — 业务逻辑服务

纯函数计算引擎（无DB依赖，可单独测试）+ 业务校验逻辑。

提供功能：
- 利息测算（365天制：本金×年利率/365×天数）
- 征信核对（倒轧余额 + 差异计算）
- 逾期检查（逾期天数 + 逾期利息）
- 担保比例（担保借款/资产账面价值×100）

科目2001短期借款（贷方/负债类）：期末=期初+贷方-借方

Requirements: 4.2, 5.2, 6.2, 9.1-9.4
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP


# ═══════════════════════════════════════════════════════════════════════════════
# 利息测算（365天制）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_interest(principal: float, annual_rate: float, days: int) -> float:
    """计算利息 = 本金 × 年利率 × 计息天数 / 365

    365天制（致同2025修订版模板实际公式）。

    边界条件：
    - days=0 → 利息=0
    - annual_rate=0 → 利息=0
    - principal=0 → 利息=0

    Requirements: 9.1
    """
    if days == 0 or annual_rate == 0 or principal == 0:
        return 0.0
    return principal * annual_rate * days / 365


def calc_interest_diff(estimated: float, booked: float) -> float:
    """计算利息差异 = 测算利息 - 账载利息

    正数表示少计利息（账面偏低），负数表示多计利息（账面偏高）。
    """
    return estimated - booked


def calc_interest_decimal(
    principal: Decimal, annual_rate: Decimal, days: int
) -> Decimal:
    """高精度利息计算（Decimal版本，用于金额敏感场景）

    利息 = 本金 × 年利率 × 天数 / 365，四舍五入到2位小数。
    """
    if days == 0 or annual_rate == 0 or principal == 0:
        return Decimal("0.00")
    result = principal * annual_rate * Decimal(str(days)) / Decimal("365")
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ═══════════════════════════════════════════════════════════════════════════════
# 征信核对
# ═══════════════════════════════════════════════════════════════════════════════


def calc_credit_diff(credit_balance: float, book_balance: float) -> float:
    """征信差异 = 征信借款余额 - 账面借款余额

    正数表示账面可能少计（有表外借款遗漏风险）。
    负数表示征信偏低（可能征信未及时更新）。

    Requirements: 5.2
    """
    return credit_balance - book_balance


def check_credit_completeness(
    credit_balance: float, book_balance: float, threshold: float = 0.0
) -> dict:
    """征信完整性核对

    Returns:
        dict with keys:
        - difference: 差异金额
        - is_consistent: 差异是否在阈值内
        - risk_level: "normal" / "attention" / "warning"
    """
    diff = calc_credit_diff(credit_balance, book_balance)
    abs_diff = abs(diff)
    is_consistent = abs_diff <= threshold

    if abs_diff == 0:
        risk_level = "normal"
    elif abs_diff <= threshold:
        risk_level = "attention"
    else:
        risk_level = "warning"

    return {
        "difference": diff,
        "is_consistent": is_consistent,
        "risk_level": risk_level,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 逾期检查
# ═══════════════════════════════════════════════════════════════════════════════


def calc_overdue_days(due_date: date, report_date: date) -> int:
    """逾期天数 = 报告日 - 到期日

    >0 表示逾期，≤0 表示未到期。
    允许为负（表示距到期尚有天数）。

    Requirements: 9.2
    """
    return (report_date - due_date).days


def calc_overdue_interest(
    principal: float, annual_rate: float, overdue_days: int, penalty_multiplier: float = 1.5
) -> float:
    """逾期利息 = 本金 × 年利率 × 罚息倍数 × 逾期天数 / 365

    逾期罚息通常为正常利率的 1.5 倍（央行规定上浮 50%）。
    仅当 overdue_days > 0 时计算。
    """
    if overdue_days <= 0 or principal == 0 or annual_rate == 0:
        return 0.0
    return principal * annual_rate * penalty_multiplier * overdue_days / 365


def classify_overdue_risk(overdue_days: int) -> str:
    """逾期风险分级

    返回:
    - "normal": 未逾期 (days <= 0)
    - "attention": 轻度逾期 (1-30天)
    - "warning": 中度逾期 (31-90天)
    - "danger": 严重逾期 (>90天)
    """
    if overdue_days <= 0:
        return "normal"
    elif overdue_days <= 30:
        return "attention"
    elif overdue_days <= 90:
        return "warning"
    else:
        return "danger"


# ═══════════════════════════════════════════════════════════════════════════════
# 担保比例
# ═══════════════════════════════════════════════════════════════════════════════


def calc_pledge_ratio(guaranteed_loan: float, book_value: float) -> float:
    """担保比例 = 担保借款金额 / 资产账面价值 × 100

    表示抵质押资产对借款的覆盖程度。
    >100% 表示资不抵债（担保不足）。
    <100% 表示资产覆盖充足。

    当 book_value=0 时返回 0.0（避免除零错误，实际业务中需关注）。

    Requirements: 9.3
    """
    if book_value == 0:
        return 0.0
    return guaranteed_loan / book_value * 100


def check_pledge_adequacy(
    guaranteed_loan: float, book_value: float, threshold: float = 100.0
) -> dict:
    """担保充足性检查

    Returns:
        dict with keys:
        - ratio: 担保比例
        - is_adequate: 是否充足（ratio <= threshold）
        - risk_level: "normal" / "attention" / "warning"
    """
    ratio = calc_pledge_ratio(guaranteed_loan, book_value)

    if ratio == 0.0 and book_value == 0:
        # 无资产情况特殊处理
        return {
            "ratio": ratio,
            "is_adequate": False,
            "risk_level": "warning",
        }

    if ratio <= 70:
        risk_level = "normal"
    elif ratio <= threshold:
        risk_level = "attention"
    else:
        risk_level = "warning"

    return {
        "ratio": ratio,
        "is_adequate": ratio <= threshold,
        "risk_level": risk_level,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 负债类公式验证
# ═══════════════════════════════════════════════════════════════════════════════


def calc_liability_end_balance(begin: float, credit: float, debit: float) -> float:
    """负债类期末余额 = 期初 + 贷方发生额 - 借方发生额

    短期借款（贷方/负债类科目）：
    - 贷方增加（借入）
    - 借方减少（归还）
    - 期末 = 期初 + 贷方 - 借方

    注意：与资产类（期末=期初+借方-贷方）方向相反！
    """
    return begin + credit - debit


def validate_liability_balance(
    begin: float, credit: float, debit: float, reported_end: float, tolerance: float = 0.01
) -> dict:
    """校验负债类期末余额是否正确

    Returns:
        dict with keys:
        - expected: 计算期末
        - reported: 报告期末
        - difference: 差异
        - is_valid: 是否在容差内
    """
    expected = calc_liability_end_balance(begin, credit, debit)
    diff = reported_end - expected
    return {
        "expected": expected,
        "reported": reported_end,
        "difference": diff,
        "is_valid": abs(diff) <= tolerance,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 批量利息测算
# ═══════════════════════════════════════════════════════════════════════════════


def batch_calc_interest(loans: list[dict]) -> dict:
    """批量利息测算

    Args:
        loans: 每笔借款信息 [{principal, annual_rate, days, booked_interest}, ...]

    Returns:
        dict with keys:
        - details: 每笔测算结果列表
        - total_estimated: 测算利息合计
        - total_booked: 账载利息合计
        - total_difference: 总差异
    """
    details: list[dict] = []
    total_estimated = 0.0
    total_booked = 0.0

    for loan in loans:
        principal = loan.get("principal", 0.0)
        rate = loan.get("annual_rate", 0.0)
        days = loan.get("days", 0)
        booked = loan.get("booked_interest", 0.0)

        estimated = calc_interest(principal, rate, days)
        diff = calc_interest_diff(estimated, booked)

        details.append({
            "contract_no": loan.get("contract_no", ""),
            "principal": principal,
            "annual_rate": rate,
            "days": days,
            "estimated_interest": estimated,
            "booked_interest": booked,
            "difference": diff,
        })

        total_estimated += estimated
        total_booked += booked

    return {
        "details": details,
        "total_estimated": total_estimated,
        "total_booked": total_booked,
        "total_difference": total_estimated - total_booked,
    }
