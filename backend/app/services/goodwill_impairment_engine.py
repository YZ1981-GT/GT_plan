"""
商誉减值测试 WACC/DCF 计算引擎。

提供：
- CAPM 权益资本成本计算
- WACC 加权平均资本成本计算
- DCF 折现现金流估值（含永续价值）
- 减值损失判定

精度：4 位小数（round(x, 4)）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP


def _r4(value: float) -> float:
    """保留 4 位小数。"""
    return float(Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


@dataclass
class WaccParams:
    """WACC 计算参数。"""
    debt_total: float  # D - 债务总额
    equity_total: float  # E - 权益总额
    cost_of_debt: float  # Kd - 税前债务成本率
    risk_free_rate: float  # Rf - 无风险报酬率
    beta: float  # β系数
    market_return: float  # Rm - 市场平均收益率
    tax_rate: float  # T - 所得税率


@dataclass
class DcfParams:
    """DCF 计算参数。"""
    cash_flows: list[float]  # 预测期各年现金流（税前）
    terminal_growth_rate: float  # 永续增长率 g


@dataclass
class WaccResult:
    """WACC 计算结果。"""
    ke: float  # 权益资本成本
    wacc_pretax: float  # 税前 WACC
    wacc_posttax: float  # 税后 WACC
    market_risk_premium: float  # 市场风险溢价 (Rm - Rf)


@dataclass
class DcfResult:
    """DCF 计算结果。"""
    discount_factors: list[float]  # 各年折现系数
    present_values: list[float]  # 各年现值
    pv_sum: float  # 预测期现值合计
    terminal_value: float  # 永续价值
    pv_terminal: float  # 永续价值现值
    recoverable_amount: float  # 可收回金额（现金流现值法）


@dataclass
class ImpairmentResult:
    """减值判定结果。"""
    carrying_amount: float  # 账面价值
    recoverable_amount: float  # 可收回金额
    impairment_loss: float  # 减值损失（正数表示需计提）
    needs_impairment: bool  # 是否需要计提减值


def calculate_capm(rf: float, beta: float, rm: float) -> float:
    """CAPM: Ke = Rf + β × (Rm - Rf)"""
    return _r4(rf + beta * (rm - rf))


def calculate_wacc(params: WaccParams) -> WaccResult:
    """计算 WACC。

    WACC(税后) = [D × Kd × (1-T) + E × Ke] / (D + E)
    WACC(税前) = WACC(税后) / (1 - T)  近似
    """
    ke = calculate_capm(params.risk_free_rate, params.beta, params.market_return)
    total_capital = params.debt_total + params.equity_total

    if total_capital == 0:
        return WaccResult(ke=ke, wacc_pretax=0, wacc_posttax=0, market_risk_premium=0)

    wacc_posttax = _r4(
        (params.debt_total * params.cost_of_debt * (1 - params.tax_rate)
         + params.equity_total * ke)
        / total_capital
    )

    # 税前 WACC（用于折现税前现金流）
    wacc_pretax = _r4(wacc_posttax / (1 - params.tax_rate)) if params.tax_rate < 1 else wacc_posttax
    mrp = _r4(params.market_return - params.risk_free_rate)

    return WaccResult(ke=ke, wacc_pretax=wacc_pretax, wacc_posttax=wacc_posttax, market_risk_premium=mrp)


def calculate_dcf(dcf_params: DcfParams, wacc: float) -> DcfResult:
    """DCF 折现现金流估值。

    V = Σ(CF_t / (1+WACC)^t) + TV / (1+WACC)^n
    TV = CF_n × (1+g) / (WACC - g)
    """
    n = len(dcf_params.cash_flows)
    if n == 0 or wacc <= dcf_params.terminal_growth_rate:
        return DcfResult(
            discount_factors=[], present_values=[], pv_sum=0,
            terminal_value=0, pv_terminal=0, recoverable_amount=0,
        )

    discount_factors = [_r4(1 / (1 + wacc) ** t) for t in range(1, n + 1)]
    present_values = [_r4(cf * df) for cf, df in zip(dcf_params.cash_flows, discount_factors)]
    pv_sum = _r4(sum(present_values))

    # 永续价值
    last_cf = dcf_params.cash_flows[-1]
    g = dcf_params.terminal_growth_rate
    terminal_value = _r4(last_cf * (1 + g) / (wacc - g))
    pv_terminal = _r4(terminal_value * discount_factors[-1])

    recoverable_amount = _r4(pv_sum + pv_terminal)

    return DcfResult(
        discount_factors=discount_factors,
        present_values=present_values,
        pv_sum=pv_sum,
        terminal_value=terminal_value,
        pv_terminal=pv_terminal,
        recoverable_amount=recoverable_amount,
    )


def determine_impairment(carrying_amount: float, recoverable_amount: float) -> ImpairmentResult:
    """判定减值损失。

    减值损失 = max(0, 账面价值 - 可收回金额)
    """
    loss = _r4(max(0, carrying_amount - recoverable_amount))
    return ImpairmentResult(
        carrying_amount=_r4(carrying_amount),
        recoverable_amount=_r4(recoverable_amount),
        impairment_loss=loss,
        needs_impairment=loss > 0,
    )
