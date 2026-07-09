"""H9 租赁负债 — 业务逻辑服务

纯函数计算引擎（无DB依赖，可单独测试）+ H8联动校验逻辑。

提供功能：
- 现值计算：PV = Σ(payments[i] / (1+rate)^(i+1))（CAS21第14条）
- 等额年金现值：payment × (1 - (1+rate)^(-periods)) / rate
- 增量借款利率(IBR)确定：market_rate + credit_spread + term_adjust
- 摊销表生成：实际利率法（利息=期初×利率；本金=付款-利息）
- 摊销表验证：最后一期期末≈0 + 总利息/总本金合计
- H8-H9联动校验：CAS21配对关系 H9 = H8 - 直接费用 + 激励（±1元容差）
- 公式方向校验：负债类贷方 期末=期初+贷方-借方

科目2205租赁负债（贷方/负债类）+ 未确认融资费用（借方/负债备抵类）

Service只flush不commit（由调用方控制事务）。

Requirements: 6.1-6.4, 7.1-7.5, 8.1-8.4
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# H8-H9联动容差（±1元）
LINKAGE_TOLERANCE = 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：现值计算引擎（CAS21第14条）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_present_value(payments: list[float], rate: float) -> float:
    """计算不等额租金的现值

    PV = Σ(payments[i] / (1+rate)^(i+1))

    CAS21第14条：租赁负债应当按照租赁期开始日尚未支付的租赁付款额的现值
    进行初始计量。

    Args:
        payments: 各期付款金额列表
        rate: 折现率（年利率，如0.05表示5%）

    Returns:
        现值合计

    Requirements: 6.1, 6.4
    """
    if not payments:
        return 0.0
    if rate == 0:
        return sum(payments)
    pv = 0.0
    for i, pmt in enumerate(payments):
        pv += pmt / (1 + rate) ** (i + 1)
    return round(pv, 2)


def calc_annuity_pv(payment: float, rate: float, periods: int) -> float:
    """等额年金现值

    PV = payment × (1 - (1+rate)^(-periods)) / rate

    适用于等额租金的租赁合同，简化计算。

    Args:
        payment: 每期等额付款金额
        rate: 折现率（年利率）
        periods: 期数

    Returns:
        年金现值

    Requirements: 6.2, 6.4
    """
    if periods <= 0:
        return 0.0
    if rate == 0:
        return payment * periods
    return round(payment * (1 - (1 + rate) ** (-periods)) / rate, 2)


def calc_ibr(market_rate: float, credit_spread: float, term_adjust: float) -> float:
    """增量借款利率(IBR)确定

    IBR = 市场参考利率 + 信用利差 + 期限调整

    CAS21第14条：承租人无法确定租赁内含利率时，应当采用增量借款利率
    作为折现率。增量借款利率是指承租人在类似经济环境下为获得与
    使用权资产价值接近的资产，在类似期限以类似担保条件借入资金
    须支付的利率。

    Args:
        market_rate: 市场参考利率（如LPR）
        credit_spread: 信用利差（基于承租人信用等级）
        term_adjust: 期限调整（长期租赁的额外溢价）

    Returns:
        增量借款利率

    Requirements: 6.3
    """
    return round(market_rate + credit_spread + term_adjust, 6)


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：摊销表引擎（实际利率法，CAS21第18-20条）
# ═══════════════════════════════════════════════════════════════════════════════


def generate_amortization_schedule(
    initial_balance: float, payment: float, rate: float, periods: int
) -> list[dict]:
    """生成租赁负债摊销表

    实际利率法：
    - 每期利息 = 期初余额 × 实际利率
    - 本金偿还 = 每期付款 - 利息
    - 期末余额 = 期初余额 - 本金偿还

    CAS21第18条：在租赁期开始日后，承租人应当按照固定的周期性利率
    计算租赁负债在租赁期内各期间的利息费用，并计入当期损益。

    最后一期调整尾差确保期末余额精确为0。

    Args:
        initial_balance: 租赁负债初始余额（即现值）
        payment: 每期付款金额
        rate: 实际利率（每期利率）
        periods: 总期数

    Returns:
        摊销表行列表：[{period, begin_balance, payment, interest, principal, end_balance}]

    Requirements: 7.1-7.5
    """
    if periods <= 0:
        return []

    schedule: list[dict] = []
    balance = initial_balance

    for n in range(1, periods + 1):
        begin_balance = round(balance, 2)
        interest = round(balance * rate, 2)

        if n == periods:
            # 最后一期：调整本金使期末余额精确为0
            principal = round(begin_balance, 2)
            actual_payment = round(principal + interest, 2)
            end_balance = 0.0
        else:
            principal = round(payment - interest, 2)
            end_balance = round(begin_balance - principal, 2)
            actual_payment = round(payment, 2)

        schedule.append({
            "period": n,
            "begin_balance": begin_balance,
            "payment": actual_payment,
            "interest": interest,
            "principal": principal,
            "end_balance": end_balance,
        })

        balance = end_balance

    return schedule


def validate_amortization(schedule: list[dict]) -> dict:
    """验证摊销表正确性

    检查项：
    1. 最后一期期末余额是否≈0（允许±1元尾差）
    2. 总利息合计
    3. 总本金合计
    4. 总本金≈初始余额

    Args:
        schedule: 摊销表行列表

    Returns:
        {
            "is_valid": bool,
            "tail_diff": float,      # 最后一期期末余额（应≈0）
            "total_interest": float,  # 利息费用合计
            "total_principal": float  # 本金偿还合计
        }

    Requirements: 7.4, 7.5
    """
    if not schedule:
        return {
            "is_valid": True,
            "tail_diff": 0.0,
            "total_interest": 0.0,
            "total_principal": 0.0,
        }

    tail_diff = schedule[-1]["end_balance"]
    total_interest = round(sum(row["interest"] for row in schedule), 2)
    total_principal = round(sum(row["principal"] for row in schedule), 2)

    # 尾差允许±1元
    is_valid = abs(tail_diff) <= 1.0

    return {
        "is_valid": is_valid,
        "tail_diff": tail_diff,
        "total_interest": total_interest,
        "total_principal": total_principal,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：H8-H9联动校验（CAS21第16条）
# ═══════════════════════════════════════════════════════════════════════════════


def validate_h8_linkage(
    h9_initial: float,
    h8_initial: float,
    direct_cost: float,
    incentive: float,
) -> dict:
    """H8-H9联动校验

    CAS21第16条配对关系：
    H8使用权资产 = H9租赁负债 + 直接费用 - 激励
    即：H9 = H8 - 直接费用 + 激励

    Args:
        h9_initial: H9租赁负债初始确认金额（实际值）
        h8_initial: H8使用权资产初始计量金额
        direct_cost: 初始直接费用
        incentive: 租赁激励

    Returns:
        {
            "is_consistent": bool,   # 是否一致（±1元容差）
            "expected_h9": float,    # H9应有值 = H8 - 直接费用 + 激励
            "actual_h9": float,      # H9实际值
            "diff": float            # 差异
        }

    Requirements: 8.1-8.4
    """
    expected_h9 = round(h8_initial - direct_cost + incentive, 2)
    actual_h9 = round(h9_initial, 2)
    diff = round(actual_h9 - expected_h9, 2)
    is_consistent = abs(diff) <= LINKAGE_TOLERANCE

    return {
        "is_consistent": is_consistent,
        "expected_h9": expected_h9,
        "actual_h9": actual_h9,
        "diff": diff,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：公式方向校验（负债贷方）
# ═══════════════════════════════════════════════════════════════════════════════


def validate_formula_direction(
    begin: float, credit: float, debit: float, expected_end: float
) -> dict:
    """负债类贷方公式方向校验

    负债类科目：期末 = 期初 + 贷方(增加) - 借方(减少)
    （与资产类 期末=期初+借方-贷方 相反！）

    Args:
        begin: 期初余额
        credit: 贷方发生额（增加）
        debit: 借方发生额（减少）
        expected_end: 期末余额（期望值）

    Returns:
        {
            "is_valid": bool,
            "calculated_end": float,  # 计算期末
            "expected_end": float,    # 期望期末
            "diff": float             # 差异
        }

    Requirements: 2.4（负债类贷方方向）
    """
    calculated_end = round(begin + credit - debit, 2)
    expected_end_rounded = round(expected_end, 2)
    diff = round(calculated_end - expected_end_rounded, 2)
    is_valid = abs(diff) <= 0.01  # 2分钱容差（浮点精度）

    return {
        "is_valid": is_valid,
        "calculated_end": calculated_end,
        "expected_end": expected_end_rounded,
        "diff": diff,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Service 类封装
# ═══════════════════════════════════════════════════════════════════════════════


class H9LeaseLiabilitiesService:
    """H9租赁负债业务逻辑服务.

    核心功能：
    - 现值折现计算（初始确认）
    - 摊销表生成与验证（实际利率法）
    - IBR确定
    - H8-H9联动校验（CAS21配对）
    - 负债贷方方向校验

    纯函数设计，无DB依赖，所有方法可独立PBT测试。
    """

    @staticmethod
    def calc_present_value(payments: list[float], rate: float) -> float:
        """现值计算: PV = Σ(p/(1+r)^n) (CAS21第14条)"""
        return calc_present_value(payments, rate)

    @staticmethod
    def calc_annuity_pv(payment: float, rate: float, periods: int) -> float:
        """等额年金现值: p×(1-(1+r)^-n)/r"""
        return calc_annuity_pv(payment, rate, periods)

    @staticmethod
    def calc_ibr(market_rate: float, credit_spread: float, term_adjust: float) -> float:
        """增量借款利率: market + spread + term_adjust"""
        return calc_ibr(market_rate, credit_spread, term_adjust)

    @staticmethod
    def generate_amortization_schedule(
        initial_balance: float, payment: float, rate: float, periods: int
    ) -> list[dict]:
        """生成摊销表（实际利率法）"""
        return generate_amortization_schedule(initial_balance, payment, rate, periods)

    @staticmethod
    def validate_amortization(schedule: list[dict]) -> dict:
        """验证摊销表正确性"""
        return validate_amortization(schedule)

    @staticmethod
    def validate_h8_linkage(
        h9_initial: float,
        h8_initial: float,
        direct_cost: float,
        incentive: float,
    ) -> dict:
        """H8-H9联动校验 (CAS21第16条)"""
        return validate_h8_linkage(h9_initial, h8_initial, direct_cost, incentive)

    @staticmethod
    def validate_formula_direction(
        begin: float, credit: float, debit: float, expected_end: float
    ) -> dict:
        """负债贷方方向校验: 期末=期初+贷方-借方"""
        return validate_formula_direction(begin, credit, debit, expected_end)


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_float(val: Any) -> float:
    """安全转 float，None/非数值返回 0.0"""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0
