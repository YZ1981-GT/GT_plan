"""L3 长期借款 — 业务逻辑服务

纯函数计算引擎（无DB依赖，可单独测试）+ 业务校验逻辑。

提供功能：
- 利息测算（365天制：本金×年利率/365×天数）
- 征信核对（差异=征信余额-账面余额）
- 逾期检查（逾期天数=报告日-到期日）
- 担保比例（担保借款/资产账面价值×100）
- 一年内到期重分类（判定+生成RJE）
- 负债类余额校验（期末=期初+贷方-借方）

科目2501长期借款（贷方/负债类）：期末=期初+贷方-借方
与L1短期借款的区别：增加一年内到期重分类逻辑（RJE借2501/贷2801）

Requirements: 4.2, 5.1, 6.2, 7.2, 10.1-10.4
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from dateutil.relativedelta import relativedelta


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

    Requirements: 10.1
    """
    if days == 0 or annual_rate == 0 or principal == 0:
        return 0.0
    return principal * annual_rate * days / 365


def calc_interest_diff(estimated: float, booked: float) -> float:
    """计算利息差异 = 测算利息 - 账载利息

    正数表示少计利息（账面偏低），负数表示多计利息（账面偏高）。

    Requirements: 4.2
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
# 逾期检查
# ═══════════════════════════════════════════════════════════════════════════════


def calc_overdue_days(due_date: date, report_date: date) -> int:
    """逾期天数 = 报告日 - 到期日

    >0 表示逾期，≤0 表示未到期。
    允许为负（表示距到期尚有天数）。

    Requirements: 7.2, 10.2
    """
    return (report_date - due_date).days


def calc_overdue_interest(
    principal: float, annual_rate: float, overdue_days: int, penalty_multiplier: float = 1.5
) -> float:
    """逾期利息 = 本金 × 年利率 × 罚息倍数 × 逾期天数 / 365

    长期借款逾期罚息通常为正常利率的 1.5 倍（央行规定上浮 50%）。
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
# 征信核对
# ═══════════════════════════════════════════════════════════════════════════════


def calc_credit_diff(credit_balance: float, book_balance: float) -> float:
    """征信差异 = 征信借款余额 - 账面借款余额

    正数表示账面可能少计（有表外借款遗漏风险）。
    负数表示征信偏低（可能征信未及时更新）。

    Requirements: 6.2
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
# 担保比例
# ═══════════════════════════════════════════════════════════════════════════════


def calc_pledge_ratio(guaranteed_loan: float, book_value: float) -> float:
    """担保比例 = 担保借款金额 / 资产账面价值 × 100

    表示抵质押资产对借款的覆盖程度。
    >100% 表示资不抵债（担保不足）。
    <100% 表示资产覆盖充足。

    当 book_value=0 时返回 0.0（避免除零错误，实际业务中需关注）。

    Requirements: 7.2
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
# 一年内到期重分类（L3特有！L1无此逻辑）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_current_portion(due_date: date, report_date: date, amount: float) -> float:
    """一年内到期金额判定

    规则：如果到期日 ≤ 报告日起一年内，则全额重分类为流动负债。
    如果到期日 > 报告日+1年，则不重分类（金额=0）。

    边界条件：
    - amount <= 0 → 返回0
    - due_date 已过期（到期日 <= 报告日） → 全额重分类
    - due_date 在一年内（报告日 < 到期日 <= 报告日+1年） → 全额重分类
    - due_date 超过一年（到期日 > 报告日+1年） → 不重分类=0

    Requirements: 5.1, 10.3
    """
    if amount <= 0:
        return 0.0
    one_year_later = report_date + relativedelta(years=1)
    if due_date <= one_year_later:
        return amount
    return 0.0


def build_reclass_entry(current_portion: float) -> dict[str, Any] | None:
    """生成一年内到期重分类分录

    借：2501 长期借款
    贷：2801 一年内到期的非流动负债

    当 current_portion <= 0 时返回 None（无需重分类）。

    Requirements: 5.1, 10.3
    """
    if current_portion <= 0:
        return None
    return {
        "type": "RJE",
        "description": "一年内到期的长期借款重分类",
        "debit": {
            "account": "2501",
            "account_name": "长期借款",
            "amount": current_portion,
        },
        "credit": {
            "account": "2801",
            "account_name": "一年内到期的非流动负债",
            "amount": current_portion,
        },
    }


def batch_reclass(
    loans: list[dict], report_date: date
) -> dict[str, Any]:
    """批量一年内到期重分类

    Args:
        loans: [{due_date: date, amount: float, contract_no: str}, ...]
        report_date: 报告日

    Returns:
        dict with keys:
        - details: 每笔判定结果
        - total_current_portion: 一年内到期合计
        - reclass_entry: 合并重分类分录（若有）
    """
    details: list[dict] = []
    total_current = 0.0

    for loan in loans:
        due = loan.get("due_date")
        amt = loan.get("amount", 0.0)
        contract_no = loan.get("contract_no", "")

        if isinstance(due, str):
            from datetime import datetime
            for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                try:
                    due = datetime.strptime(due, fmt).date()
                    break
                except ValueError:
                    continue

        if not isinstance(due, date):
            details.append({
                "contract_no": contract_no,
                "current_portion": 0.0,
                "reason": "无效到期日",
            })
            continue

        portion = calc_current_portion(due, report_date, amt)
        total_current += portion
        details.append({
            "contract_no": contract_no,
            "due_date": due.isoformat(),
            "amount": amt,
            "current_portion": portion,
            "is_current": portion > 0,
        })

    return {
        "details": details,
        "total_current_portion": total_current,
        "reclass_entry": build_reclass_entry(total_current),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 负债类公式验证
# ═══════════════════════════════════════════════════════════════════════════════


def validate_liability_balance(
    begin: float, credit: float, debit: float, reported_end: float | None = None, tolerance: float = 0.01
) -> dict:
    """校验负债类期末余额

    负债类公式：期末 = 期初 + 贷方发生额 - 借方发生额

    长期借款（贷方/负债类科目）：
    - 贷方增加（借入新贷款）
    - 借方减少（偿还本金）
    - 期末 = 期初 + 贷方 - 借方

    当 reported_end 提供时做差异校验。

    Requirements: 10.4

    Returns:
        dict with keys:
        - expected: 计算期末
        - reported: 报告期末（如提供）
        - difference: 差异（如提供reported_end）
        - is_valid: 是否在容差内（如提供reported_end）
    """
    expected = begin + credit - debit
    result: dict[str, Any] = {"expected": expected}

    if reported_end is not None:
        diff = reported_end - expected
        result["reported"] = reported_end
        result["difference"] = diff
        result["is_valid"] = abs(diff) <= tolerance

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 批量利息测算
# ═══════════════════════════════════════════════════════════════════════════════


def batch_calc_interest(loans: list[dict]) -> dict:
    """批量利息测算

    Args:
        loans: 每笔借款信息 [{principal, annual_rate, days, booked_interest, contract_no}, ...]

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
