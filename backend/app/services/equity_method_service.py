"""
模拟权益法服务 — 6 项改进 [R11.1]

改进内容：
1. 投资收益确认：按持股比例确认被投资单位净利润中归属于母公司的份额
2. 其他综合收益调整：被投资单位其他综合收益变动的母公司份额
3. 内部交易未实现利润抵消：顺流/逆流交易的未实现利润调整
4. 投资减值测试：长期股权投资减值迹象判断与计提
5. 超额亏损处理：被投资单位亏损超过投资账面价值时的处理
6. 投资成本与享有份额差额处理：初始投资成本与应享有份额的差额（商誉/营业外收入）
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class EquityMethodInput:
    """权益法计算输入参数"""
    # 基本信息
    subsidiary_code: str
    subsidiary_name: str
    parent_share_ratio: Decimal  # 母公司持股比例（如 0.80 表示 80%）

    # 投资成本
    initial_investment_cost: Decimal  # 初始投资成本
    opening_book_value: Decimal  # 期初账面价值

    # 被投资单位财务数据
    sub_net_profit: Decimal = Decimal("0")  # 被投资单位本期净利润
    sub_other_comprehensive_income: Decimal = Decimal("0")  # 其他综合收益变动
    sub_net_assets_at_acquisition: Decimal = Decimal("0")  # 取得投资时被投资单位可辨认净资产公允价值
    sub_current_net_assets: Decimal = Decimal("0")  # 被投资单位期末净资产
    sub_dividend_declared: Decimal = Decimal("0")  # 被投资单位宣告分配的利润

    # 内部交易
    unrealized_upstream_profit: Decimal = Decimal("0")  # 逆流交易未实现利润（子→母）
    unrealized_downstream_profit: Decimal = Decimal("0")  # 顺流交易未实现利润（母→子）

    # 减值
    recoverable_amount: Optional[Decimal] = None  # 可收回金额（用于减值测试）
    accumulated_impairment: Decimal = Decimal("0")  # 累计已计提减值


@dataclass
class EquityMethodResult:
    """权益法计算结果"""
    subsidiary_code: str
    subsidiary_name: str

    # 1. 投资收益确认
    investment_income: Decimal = Decimal("0")  # 确认的投资收益
    adjusted_net_profit: Decimal = Decimal("0")  # 调整后的净利润（扣除内部交易）

    # 2. 其他综合收益调整
    oci_adjustment: Decimal = Decimal("0")  # 其他综合收益调整额

    # 3. 内部交易未实现利润
    upstream_profit_elimination: Decimal = Decimal("0")  # 逆流交易抵消额
    downstream_profit_elimination: Decimal = Decimal("0")  # 顺流交易抵消额

    # 4. 投资减值
    impairment_loss: Decimal = Decimal("0")  # 本期减值损失
    accumulated_impairment: Decimal = Decimal("0")  # 累计减值

    # 5. 超额亏损
    excess_loss: Decimal = Decimal("0")  # 超额亏损（未确认的投资损失）
    is_excess_loss: bool = False  # 是否存在超额亏损

    # 6. 投资成本差额
    goodwill: Decimal = Decimal("0")  # 商誉（投资成本 > 享有份额）
    bargain_purchase_gain: Decimal = Decimal("0")  # 营业外收入（投资成本 < 享有份额）

    # 汇总
    closing_book_value: Decimal = Decimal("0")  # 期末账面价值
    total_adjustment: Decimal = Decimal("0")  # 本期调整合计

    # 生成的抵消分录
    journal_entries: list = field(default_factory=list)


def _round2(val: Decimal) -> Decimal:
    """四舍五入到2位小数"""
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_equity_method(inp: EquityMethodInput) -> EquityMethodResult:
    """
    执行模拟权益法完整计算

    按照 CAS 2 长期股权投资准则，依次处理 6 项调整。
    """
    result = EquityMethodResult(
        subsidiary_code=inp.subsidiary_code,
        subsidiary_name=inp.subsidiary_name,
    )
    ratio = inp.parent_share_ratio
    entries: list[dict] = []

    # ── 6. 投资成本与享有份额差额（首先计算，影响后续账面价值） ──
    if inp.sub_net_assets_at_acquisition > 0:
        fair_value_share = _round2(inp.sub_net_assets_at_acquisition * ratio)
        diff = inp.initial_investment_cost - fair_value_share
        if diff > 0:
            result.goodwill = _round2(diff)
            # 商誉不单独确认，体现在长期股权投资账面价值中
        elif diff < 0:
            result.bargain_purchase_gain = _round2(abs(diff))
            entries.append({
                "description": "投资成本小于享有份额差额 → 营业外收入",
                "debit_account": "1511 长期股权投资",
                "debit_amount": str(result.bargain_purchase_gain),
                "credit_account": "6301 营业外收入",
                "credit_amount": str(result.bargain_purchase_gain),
            })

    # ── 3. 内部交易未实现利润抵消 ──
    # 逆流交易（子→母）：调整被投资单位净利润
    result.upstream_profit_elimination = _round2(inp.unrealized_upstream_profit)
    # 顺流交易（母→子）：调整被投资单位净利润
    result.downstream_profit_elimination = _round2(inp.unrealized_downstream_profit)

    # 调整后净利润 = 净利润 - 逆流未实现利润 - 顺流未实现利润
    result.adjusted_net_profit = _round2(
        inp.sub_net_profit
        - inp.unrealized_upstream_profit
        - inp.unrealized_downstream_profit
    )

    if inp.unrealized_upstream_profit > 0:
        elim_amount = _round2(inp.unrealized_upstream_profit * ratio)
        entries.append({
            "description": "逆流交易未实现利润抵消",
            "debit_account": "6001 营业收入",
            "debit_amount": str(elim_amount),
            "credit_account": "1511 长期股权投资",
            "credit_amount": str(elim_amount),
        })

    if inp.unrealized_downstream_profit > 0:
        elim_amount = _round2(inp.unrealized_downstream_profit * ratio)
        entries.append({
            "description": "顺流交易未实现利润抵消",
            "debit_account": "6001 营业收入",
            "debit_amount": str(elim_amount),
            "credit_account": "1405 库存商品",
            "credit_amount": str(elim_amount),
        })

    # ── 1. 投资收益确认 ──
    raw_income = _round2(result.adjusted_net_profit * ratio)

    # ── 5. 超额亏损处理 ──
    # 如果投资收益为负（亏损），检查是否超过账面价值
    book_before_income = inp.opening_book_value
    if raw_income < 0:
        max_loss = book_before_income  # 最多亏到账面价值为零
        if abs(raw_income) > max_loss:
            result.is_excess_loss = True
            result.excess_loss = _round2(abs(raw_income) - max_loss)
            result.investment_income = _round2(-max_loss)  # 只确认到账面价值为零
        else:
            result.investment_income = raw_income
    else:
        result.investment_income = raw_income

    if result.investment_income != 0:
        if result.investment_income > 0:
            entries.append({
                "description": "确认投资收益",
                "debit_account": "1511 长期股权投资—损益调整",
                "debit_amount": str(result.investment_income),
                "credit_account": "6111 投资收益",
                "credit_amount": str(result.investment_income),
            })
        else:
            entries.append({
                "description": "确认投资损失",
                "debit_account": "6111 投资收益",
                "debit_amount": str(abs(result.investment_income)),
                "credit_account": "1511 长期股权投资—损益调整",
                "credit_amount": str(abs(result.investment_income)),
            })

    # ── 2. 其他综合收益调整 ──
    if inp.sub_other_comprehensive_income != 0:
        result.oci_adjustment = _round2(inp.sub_other_comprehensive_income * ratio)
        if result.oci_adjustment > 0:
            entries.append({
                "description": "其他综合收益调整",
                "debit_account": "1511 长期股权投资—其他综合收益",
                "debit_amount": str(result.oci_adjustment),
                "credit_account": "4002 其他综合收益",
                "credit_amount": str(result.oci_adjustment),
            })
        else:
            entries.append({
                "description": "其他综合收益调整（减少）",
                "debit_account": "4002 其他综合收益",
                "debit_amount": str(abs(result.oci_adjustment)),
                "credit_account": "1511 长期股权投资—其他综合收益",
                "credit_amount": str(abs(result.oci_adjustment)),
            })

    # 被投资单位宣告分配利润
    dividend_share = Decimal("0")
    if inp.sub_dividend_declared > 0:
        dividend_share = _round2(inp.sub_dividend_declared * ratio)
        entries.append({
            "description": "被投资单位宣告分配利润",
            "debit_account": "1131 应收股利",
            "debit_amount": str(dividend_share),
            "credit_account": "1511 长期股权投资—损益调整",
            "credit_amount": str(dividend_share),
        })

    # ── 4. 投资减值测试 ──
    # 计算减值前的账面价值
    pre_impairment_bv = (
        inp.opening_book_value
        + result.investment_income
        + result.oci_adjustment
        - dividend_share
    )

    if inp.recoverable_amount is not None and pre_impairment_bv > inp.recoverable_amount:
        new_impairment = _round2(pre_impairment_bv - inp.recoverable_amount)
        result.impairment_loss = new_impairment
        result.accumulated_impairment = _round2(inp.accumulated_impairment + new_impairment)
        entries.append({
            "description": "长期股权投资减值",
            "debit_account": "6701 资产减值损失",
            "debit_amount": str(new_impairment),
            "credit_account": "1512 长期股权投资减值准备",
            "credit_amount": str(new_impairment),
        })
    else:
        result.accumulated_impairment = inp.accumulated_impairment

    # ── 汇总 ──
    result.total_adjustment = _round2(
        result.investment_income
        + result.oci_adjustment
        - dividend_share
        - result.impairment_loss
    )

    result.closing_book_value = _round2(
        inp.opening_book_value + result.total_adjustment
    )

    result.journal_entries = entries
    return result


def generate_equity_elimination_entries(result: EquityMethodResult) -> list[dict]:
    """
    从权益法计算结果生成合并抵消分录

    返回可直接用于 elimination_service.create_entry 的分录行列表。
    """
    return result.journal_entries
