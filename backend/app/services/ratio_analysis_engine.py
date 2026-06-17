"""比率分析计算引擎 — 46 个财务比率公式（6 大类）

从 financial_report 数据（BS/IS/CFS）按 row_code 取分子/分母计算指标值，
支持年化处理和年末年初算术平均。

Requirements: 3.1~3.9
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReport, FinancialReportType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据类型定义
# ---------------------------------------------------------------------------

# 6 大类分组常量
CATEGORY_PROFITABILITY = "profitability"  # 盈利能力
CATEGORY_SHORT_TERM_SOLVENCY = "short_term_solvency"  # 短期偿债能力
CATEGORY_LONG_TERM_SOLVENCY = "long_term_solvency"  # 长期偿债能力
CATEGORY_ASSET_EFFICIENCY = "asset_efficiency"  # 资产管理效率
CATEGORY_CAPITAL_MANAGEMENT = "capital_management"  # 资本管理效果
CATEGORY_CASH_FLOW = "cash_flow"  # 现金流量

CATEGORY_LABELS = {
    CATEGORY_PROFITABILITY: "一、盈利能力分析",
    CATEGORY_SHORT_TERM_SOLVENCY: "二、短期偿债能力分析",
    CATEGORY_LONG_TERM_SOLVENCY: "三、长期偿债能力分析",
    CATEGORY_ASSET_EFFICIENCY: "四、资产管理效率分析",
    CATEGORY_CAPITAL_MANAGEMENT: "五、资本管理效果分析",
    CATEGORY_CASH_FLOW: "六、现金流量分析",
}

CATEGORY_ORDER = [
    CATEGORY_PROFITABILITY,
    CATEGORY_SHORT_TERM_SOLVENCY,
    CATEGORY_LONG_TERM_SOLVENCY,
    CATEGORY_ASSET_EFFICIENCY,
    CATEGORY_CAPITAL_MANAGEMENT,
    CATEGORY_CASH_FLOW,
]


@dataclass
class RatioFormula:
    """单个比率公式定义"""
    seq: int
    name: str
    formula: str
    # row_code 列表，前缀 "-" 表示减去该行
    numerator_codes: list[str]
    denominator_codes: list[str]
    category: str
    # 是否需要年化分子（IS/CFS 时期数据）
    annualize_numerator: bool = False
    # 是否需要分母取平均（BS 时点数据）
    average_denominator: bool = False
    # 正常值参考（可选）
    normal_value: float | None = None
    # 特殊计算标记
    special: str | None = None


@dataclass
class RatioResult:
    """单个比率计算结果"""
    seq: int
    name: str
    formula: str
    category: str
    prior_numerator: float | None = None
    prior_denominator: float | None = None
    prior_value: float | None = None
    current_numerator: float | None = None
    current_denominator: float | None = None
    current_value: float | None = None
    change: float | None = None
    direction: Literal["up", "down", "flat"] | None = None
    normal_value: float | None = None


# ---------------------------------------------------------------------------
# 35 个比率公式定义（6 大类）— 可自动计算
# 剩余 11 个因缺乏数据来源标记 special="no_data"
# ---------------------------------------------------------------------------
# Row code 速查 (soe_standalone):
# BS-001=货币资金, BS-002=交易性金融资产, BS-008=应收账款
# BS-018=存货, BS-020=流动资产合计
# BS-021~BS-038=非流动资产明细, BS-027=固定资产(净值)
# BS-039=资产合计(资产总计)
# BS-040~BS-057=流动负债明细
# BS-058=流动负债合计
# BS-059~BS-075=非流动负债明细
# BS-076=非流动负债合计
# BS-077=负债合计
# BS-078~BS-098=股东权益明细
# BS-078=实收资本(股本), BS-098=所有者权益合计
# BS-099=负债和股东权益合计
# BS-025=无形资产, BS-028=商誉
# IS-001=营业收入, IS-002=营业成本
# IS-007=营业成本(含税金及附加)
# IS-011=销售费用, IS-012=管理费用, IS-013=研发费用
# IS-014=财务费用, IS-015=利息费用(IS-014明细)
# IS-021=营业利润, IS-024=利润总额, IS-027=净利润
# CFS-001=经营活动现金流入, CFS-009=经营活动现金流量净额

RATIO_FORMULAS: list[RatioFormula] = [
    # ===== 一、盈利能力分析 (9) =====
    RatioFormula(
        seq=1, name="长期资本报酬率",
        formula="(利润总额+利息费用)/(非流动负债平均+所有者权益平均)×100%",
        numerator_codes=["IS-024", "IS-015"],
        denominator_codes=["BS-076", "BS-098"],
        category=CATEGORY_PROFITABILITY,
        annualize_numerator=True,
        average_denominator=True,
    ),
    RatioFormula(
        seq=2, name="资本金收益率",
        formula="净利润(年化)/实收资本平均值×100%",
        numerator_codes=["IS-027"],
        denominator_codes=["BS-078"],
        category=CATEGORY_PROFITABILITY,
        annualize_numerator=True,
        average_denominator=True,
    ),
    RatioFormula(
        seq=3, name="股本权益报酬率",
        formula="净利润(年化)/所有者权益平均值×100%",
        numerator_codes=["IS-027"],
        denominator_codes=["BS-098"],
        category=CATEGORY_PROFITABILITY,
        annualize_numerator=True,
        average_denominator=True,
    ),
    RatioFormula(
        seq=4, name="总资产报酬率",
        formula="(利润总额+利息费用)(年化)/资产总计平均值×100%",
        numerator_codes=["IS-024", "IS-015"],
        denominator_codes=["BS-039"],
        category=CATEGORY_PROFITABILITY,
        annualize_numerator=True,
        average_denominator=True,
    ),
    RatioFormula(
        seq=5, name="毛利率",
        formula="(营业收入-营业成本)/营业收入×100%",
        numerator_codes=["IS-001", "-IS-002"],
        denominator_codes=["IS-001"],
        category=CATEGORY_PROFITABILITY,
    ),
    RatioFormula(
        seq=6, name="营业利润率",
        formula="营业利润/营业收入×100%",
        numerator_codes=["IS-021"],
        denominator_codes=["IS-001"],
        category=CATEGORY_PROFITABILITY,
    ),
    RatioFormula(
        seq=7, name="销售净利率",
        formula="净利润/营业收入×100%",
        numerator_codes=["IS-027"],
        denominator_codes=["IS-001"],
        category=CATEGORY_PROFITABILITY,
    ),
    RatioFormula(
        seq=8, name="成本费用利润率",
        formula="利润总额/(营业成本+销售费用+管理费用+研发费用)×100%",
        numerator_codes=["IS-024"],
        denominator_codes=["IS-002", "IS-011", "IS-012", "IS-013"],
        category=CATEGORY_PROFITABILITY,
    ),
    RatioFormula(
        seq=9, name="研究开发费用比例",
        formula="研发费用/营业收入×100%",
        numerator_codes=["IS-013"],
        denominator_codes=["IS-001"],
        category=CATEGORY_PROFITABILITY,
    ),
    # ===== 二、短期偿债能力分析 (3) =====
    RatioFormula(
        seq=10, name="流动比率",
        formula="流动资产合计/流动负债合计",
        numerator_codes=["BS-020"],
        denominator_codes=["BS-058"],
        category=CATEGORY_SHORT_TERM_SOLVENCY,
        normal_value=2.0,
    ),
    RatioFormula(
        seq=11, name="速动比率",
        formula="(流动资产合计-存货)/流动负债合计",
        numerator_codes=["BS-020", "-BS-018"],
        denominator_codes=["BS-058"],
        category=CATEGORY_SHORT_TERM_SOLVENCY,
        normal_value=1.0,
    ),
    RatioFormula(
        seq=12, name="现金比率",
        formula="(货币资金+交易性金融资产)/流动负债合计",
        numerator_codes=["BS-001", "BS-002"],
        denominator_codes=["BS-058"],
        category=CATEGORY_SHORT_TERM_SOLVENCY,
        normal_value=0.3,
    ),
    # ===== 三、长期偿债能力分析 (7) =====
    RatioFormula(
        seq=13, name="资产负债比率",
        formula="负债合计/资产总计×100%",
        numerator_codes=["BS-077"],
        denominator_codes=["BS-039"],
        category=CATEGORY_LONG_TERM_SOLVENCY,
    ),
    RatioFormula(
        seq=14, name="产权比率",
        formula="负债合计/所有者权益合计×100%",
        numerator_codes=["BS-077"],
        denominator_codes=["BS-098"],
        category=CATEGORY_LONG_TERM_SOLVENCY,
    ),
    RatioFormula(
        seq=15, name="有形净值债务比率",
        formula="负债合计/(所有者权益-无形资产-商誉)×100%",
        numerator_codes=["BS-077"],
        denominator_codes=["BS-098", "-BS-025", "-BS-028"],
        category=CATEGORY_LONG_TERM_SOLVENCY,
    ),
    RatioFormula(
        seq=16, name="利息保障倍数",
        formula="(利润总额+利息费用)/利息费用",
        numerator_codes=["IS-024", "IS-015"],
        denominator_codes=["IS-015"],
        category=CATEGORY_LONG_TERM_SOLVENCY,
    ),
    RatioFormula(
        seq=17, name="营运资金长期负债比率",
        formula="(流动资产合计-流动负债合计)/非流动负债合计",
        numerator_codes=["BS-020", "-BS-058"],
        denominator_codes=["BS-076"],
        category=CATEGORY_LONG_TERM_SOLVENCY,
    ),
    RatioFormula(
        seq=18, name="长期负债比率",
        formula="非流动负债合计/负债合计×100%",
        numerator_codes=["BS-076"],
        denominator_codes=["BS-077"],
        category=CATEGORY_LONG_TERM_SOLVENCY,
    ),
    RatioFormula(
        seq=19, name="融资结构弹性比率",
        formula="流动负债合计/负债合计×100%",
        numerator_codes=["BS-058"],
        denominator_codes=["BS-077"],
        category=CATEGORY_LONG_TERM_SOLVENCY,
    ),
    # ===== 四、资产管理效率分析 (6) =====
    RatioFormula(
        seq=20, name="总资产周转率",
        formula="营业收入(年化)/资产总计平均值",
        numerator_codes=["IS-001"],
        denominator_codes=["BS-039"],
        category=CATEGORY_ASSET_EFFICIENCY,
        annualize_numerator=True,
        average_denominator=True,
    ),
    RatioFormula(
        seq=21, name="固定资产周转率",
        formula="营业收入(年化)/固定资产净值平均",
        numerator_codes=["IS-001"],
        denominator_codes=["BS-027"],
        category=CATEGORY_ASSET_EFFICIENCY,
        annualize_numerator=True,
        average_denominator=True,
    ),
    RatioFormula(
        seq=22, name="流动资产周转率",
        formula="营业收入(年化)/流动资产合计平均",
        numerator_codes=["IS-001"],
        denominator_codes=["BS-020"],
        category=CATEGORY_ASSET_EFFICIENCY,
        annualize_numerator=True,
        average_denominator=True,
    ),
    RatioFormula(
        seq=23, name="应收账款周转率",
        formula="营业收入(年化)/应收账款平均值",
        numerator_codes=["IS-001"],
        denominator_codes=["BS-008"],
        category=CATEGORY_ASSET_EFFICIENCY,
        annualize_numerator=True,
        average_denominator=True,
    ),
    RatioFormula(
        seq=24, name="存货周转率",
        formula="营业成本(年化)/存货平均值",
        numerator_codes=["IS-002"],
        denominator_codes=["BS-018"],
        category=CATEGORY_ASSET_EFFICIENCY,
        annualize_numerator=True,
        average_denominator=True,
    ),
    RatioFormula(
        seq=25, name="营业周期",
        formula="应收账款周转天数+存货周转天数(天)",
        numerator_codes=[],  # 特殊计算，依赖 seq 23 和 24
        denominator_codes=[],
        category=CATEGORY_ASSET_EFFICIENCY,
        special="operating_cycle",
    ),
    # ===== 五、资本管理效果分析 (6) =====
    RatioFormula(
        seq=26, name="资本保值增值率",
        formula="期末所有者权益/期初所有者权益×100%",
        numerator_codes=["BS-098"],  # 本期末
        denominator_codes=["BS-098"],  # 上期末(期初)
        category=CATEGORY_CAPITAL_MANAGEMENT,
        special="capital_preservation",
    ),
    RatioFormula(
        seq=27, name="社会贡献率",
        formula="企业社会贡献总额(年化)/资产总计平均值×100%",
        numerator_codes=[],  # 需工资+利息+税金+净利润，缺工资数据
        denominator_codes=["BS-039"],
        category=CATEGORY_CAPITAL_MANAGEMENT,
        special="no_data",
        average_denominator=True,
    ),
    RatioFormula(
        seq=28, name="社会积累率",
        formula="上交财政总额/企业社会贡献总额×100%",
        numerator_codes=[],
        denominator_codes=[],
        category=CATEGORY_CAPITAL_MANAGEMENT,
        special="no_data",
    ),
    RatioFormula(
        seq=29, name="不良资产比率",
        formula="不良资产总额/资产总计×100%",
        numerator_codes=[],  # 需不良资产明细
        denominator_codes=["BS-039"],
        category=CATEGORY_CAPITAL_MANAGEMENT,
        special="no_data",
    ),
    RatioFormula(
        seq=30, name="资产损失率",
        formula="资产损失总额/资产总计×100%",
        numerator_codes=[],
        denominator_codes=["BS-039"],
        category=CATEGORY_CAPITAL_MANAGEMENT,
        special="no_data",
    ),
    RatioFormula(
        seq=31, name="固定资产成新率",
        formula="固定资产净值平均/固定资产原价平均×100%",
        numerator_codes=["BS-027"],
        denominator_codes=["BS-027"],  # 需固定资产原价行，暂用净值占位
        category=CATEGORY_CAPITAL_MANAGEMENT,
        special="no_data",  # 缺固定资产原价行
    ),
    # ===== 六、现金流量分析 (4) =====
    RatioFormula(
        seq=32, name="经营活动净现金比率(一)",
        formula="经营活动现金流量净额/流动负债合计×100%",
        numerator_codes=["CFS-009"],
        denominator_codes=["BS-058"],
        category=CATEGORY_CASH_FLOW,
        annualize_numerator=True,
    ),
    RatioFormula(
        seq=33, name="经营活动净现金比率(二)",
        formula="经营活动现金流量净额/负债合计×100%",
        numerator_codes=["CFS-009"],
        denominator_codes=["BS-077"],
        category=CATEGORY_CASH_FLOW,
        annualize_numerator=True,
    ),
    RatioFormula(
        seq=34, name="净利润现金保证比率",
        formula="经营活动现金流量净额/净利润×100%",
        numerator_codes=["CFS-009"],
        denominator_codes=["IS-027"],
        category=CATEGORY_CASH_FLOW,
    ),
    RatioFormula(
        seq=35, name="销售收入现金回收比率",
        formula="经营活动现金流量净额/营业收入×100%",
        numerator_codes=["CFS-009"],
        denominator_codes=["IS-001"],
        category=CATEGORY_CASH_FLOW,
    ),
]


# ---------------------------------------------------------------------------
# 计算引擎
# ---------------------------------------------------------------------------


def _sum_codes(
    data: dict[str, Decimal],
    codes: list[str],
) -> Decimal | None:
    """按 row_code 列表求和，前缀 "-" 表示减去。

    如果所有涉及的 row_code 在 data 中都不存在，返回 None（无数据）。
    """
    if not codes:
        return None
    total = Decimal("0")
    any_found = False
    for code in codes:
        negate = code.startswith("-")
        actual_code = code[1:] if negate else code
        val = data.get(actual_code)
        if val is not None:
            any_found = True
            if negate:
                total -= val
            else:
                total += val
    return total if any_found else None


def _annualize(value: Decimal, month_count: int) -> Decimal:
    """年化处理：value * 12 / month_count。

    对于年报(12个月)，不做调整。
    """
    if month_count >= 12:
        return value
    if month_count <= 0:
        return value
    return value * Decimal("12") / Decimal(str(month_count))


def _average(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
    """年末年初算术平均: (current + prior) / 2。

    如果任一值为 None，尝试用另一值代替（单期数据仍可计算）。
    """
    if current is None and prior is None:
        return None
    c = current or Decimal("0")
    p = prior or Decimal("0")
    return (c + p) / Decimal("2")


def _safe_divide(
    numerator: Decimal | None,
    denominator: Decimal | None,
) -> Decimal | None:
    """安全除法，分母为 0 或 None 时返回 None。"""
    if numerator is None or denominator is None:
        return None
    if denominator == Decimal("0"):
        return None
    try:
        return numerator / denominator
    except (InvalidOperation, ZeroDivisionError):
        return None


def _to_float(val: Decimal | None, precision: int = 4) -> float | None:
    """Decimal → float，保留指定精度。"""
    if val is None:
        return None
    return round(float(val), precision)


def compute_single_ratio(
    formula: RatioFormula,
    current_data: dict[str, Decimal],
    prior_data: dict[str, Decimal],
    month_count: int = 12,
    all_results: dict[int, RatioResult] | None = None,
) -> RatioResult:
    """计算单个比率的本年和上年值。

    Args:
        formula: 公式定义
        current_data: 本年 row_code → amount 映射
        prior_data: 上年 row_code → amount 映射
        month_count: 本期包含月份数（用于年化）
        all_results: 已计算的其他比率结果（用于特殊依赖计算如营业周期）

    Returns:
        RatioResult 含本年/上年值及变动方向
    """
    result = RatioResult(
        seq=formula.seq,
        name=formula.name,
        formula=formula.formula,
        category=formula.category,
        normal_value=formula.normal_value,
    )

    # 特殊标记：无数据可计算的比率
    if formula.special == "no_data":
        return result

    # 特殊计算：营业周期 = 360/应收账款周转率 + 360/存货周转率
    if formula.special == "operating_cycle":
        if all_results:
            ar_turnover = all_results.get(23)
            inv_turnover = all_results.get(24)
            if ar_turnover and ar_turnover.current_value and ar_turnover.current_value != 0:
                ar_days = 360.0 / ar_turnover.current_value
            else:
                ar_days = None
            if inv_turnover and inv_turnover.current_value and inv_turnover.current_value != 0:
                inv_days = 360.0 / inv_turnover.current_value
            else:
                inv_days = None
            if ar_days is not None and inv_days is not None:
                result.current_value = round(ar_days + inv_days, 2)
                result.current_numerator = round(ar_days, 2)
                result.current_denominator = round(inv_days, 2)

            # 上年
            if ar_turnover and ar_turnover.prior_value and ar_turnover.prior_value != 0:
                ar_days_p = 360.0 / ar_turnover.prior_value
            else:
                ar_days_p = None
            if inv_turnover and inv_turnover.prior_value and inv_turnover.prior_value != 0:
                inv_days_p = 360.0 / inv_turnover.prior_value
            else:
                inv_days_p = None
            if ar_days_p is not None and inv_days_p is not None:
                result.prior_value = round(ar_days_p + inv_days_p, 2)
                result.prior_numerator = round(ar_days_p, 2)
                result.prior_denominator = round(inv_days_p, 2)
        _set_direction(result)
        return result

    # 特殊计算：资本保值增值率 = 期末权益 / 期初权益
    if formula.special == "capital_preservation":
        cur_equity = current_data.get("BS-098")
        pri_equity = prior_data.get("BS-098")
        if cur_equity is not None and pri_equity is not None and pri_equity != 0:
            result.current_numerator = _to_float(cur_equity)
            result.current_denominator = _to_float(pri_equity)
            result.current_value = _to_float(_safe_divide(cur_equity, pri_equity))
        # 上年资本保值增值率无法计算（需要更早一年的数据）
        _set_direction(result)
        return result

    # --- 通用计算 ---
    # 本年分子
    cur_numerator = _sum_codes(current_data, formula.numerator_codes)
    if formula.annualize_numerator and cur_numerator is not None:
        cur_numerator = _annualize(cur_numerator, month_count)

    # 本年分母
    if formula.average_denominator:
        cur_denom_end = _sum_codes(current_data, formula.denominator_codes)
        pri_denom_end = _sum_codes(prior_data, formula.denominator_codes)
        cur_denominator = _average(cur_denom_end, pri_denom_end)
    else:
        cur_denominator = _sum_codes(current_data, formula.denominator_codes)

    # 本年指标值
    cur_value = _safe_divide(cur_numerator, cur_denominator)

    result.current_numerator = _to_float(cur_numerator)
    result.current_denominator = _to_float(cur_denominator)
    result.current_value = _to_float(cur_value)

    # 上年分子（对于年化，上年假设也是全年数据，month_count=12）
    pri_numerator = _sum_codes(prior_data, formula.numerator_codes)
    # 上年不做年化（假设上年是全年数据）

    # 上年分母
    if formula.average_denominator:
        # 上年平均需要再之前一年（不可得），用上年期末值代替
        pri_denominator = _sum_codes(prior_data, formula.denominator_codes)
    else:
        pri_denominator = _sum_codes(prior_data, formula.denominator_codes)

    # 上年指标值
    pri_value = _safe_divide(pri_numerator, pri_denominator)

    result.prior_numerator = _to_float(pri_numerator)
    result.prior_denominator = _to_float(pri_denominator)
    result.prior_value = _to_float(pri_value)

    # 变动和方向
    _set_direction(result)
    return result


def _set_direction(result: RatioResult) -> None:
    """设置增减方向标记。"""
    if result.current_value is not None and result.prior_value is not None:
        diff = result.current_value - result.prior_value
        result.change = round(diff, 4)
        if diff > 0.0001:
            result.direction = "up"
        elif diff < -0.0001:
            result.direction = "down"
        else:
            result.direction = "flat"


def compute_all_ratios(
    current_data: dict[str, Decimal],
    prior_data: dict[str, Decimal],
    month_count: int = 12,
) -> list[RatioResult]:
    """计算全部比率。

    Args:
        current_data: 本年 row_code → amount (Decimal)
        prior_data: 上年 row_code → amount (Decimal)
        month_count: 本期月份数（年报=12）

    Returns:
        按 seq 排序的 RatioResult 列表
    """
    results: dict[int, RatioResult] = {}
    # 先计算非依赖型比率
    for formula in RATIO_FORMULAS:
        if formula.special != "operating_cycle":
            r = compute_single_ratio(formula, current_data, prior_data, month_count)
            results[r.seq] = r

    # 再计算依赖型比率（营业周期）
    for formula in RATIO_FORMULAS:
        if formula.special == "operating_cycle":
            r = compute_single_ratio(
                formula, current_data, prior_data, month_count, all_results=results
            )
            results[r.seq] = r

    return [results[k] for k in sorted(results.keys())]


# ---------------------------------------------------------------------------
# 输出格式化
# ---------------------------------------------------------------------------


def format_ratio_analysis_sheet(
    results: list[RatioResult],
    wp_code: str = "A1-13",
) -> dict:
    """将计算结果格式化为前端 ratio_analysis sheet 数据结构。"""
    categories = []
    for cat_key in CATEGORY_ORDER:
        cat_items = [r for r in results if r.category == cat_key]
        if not cat_items:
            continue
        items = []
        for r in cat_items:
            items.append({
                "seq": r.seq,
                "name": r.name,
                "formula": r.formula,
                "prior_numerator": r.prior_numerator,
                "prior_denominator": r.prior_denominator,
                "prior_value": r.prior_value,
                "current_numerator": r.current_numerator,
                "current_denominator": r.current_denominator,
                "current_value": r.current_value,
                "change": r.change,
                "direction": r.direction,
                "normal_value": r.normal_value,
            })
        categories.append({
            "name": CATEGORY_LABELS[cat_key],
            "items": items,
        })

    return {
        "title": "已审报表财务比率分析",
        "index": f"{wp_code}-5",
        "categories": categories,
        "notes": [
            "凡涉及平均数的比率按年末年初算术平均计算",
            "时期数据年化处理(annualized)=本期数据÷本期月份数×12",
            "流动比率正常值为2，速动比率正常值为1，现金比率正常值为0.3",
        ],
    }


# ---------------------------------------------------------------------------
# DB 取数入口
# ---------------------------------------------------------------------------


async def _get_report_data_for_ratio(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> dict[str, Decimal]:
    """从 financial_report 取指定年度的所有行金额。

    合并 BS/IS/CFS 三类报表数据到一个 dict。
    """
    stmt = (
        sa.select(
            FinancialReport.row_code,
            FinancialReport.current_period_amount,
        )
        .where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.is_deleted == sa.false(),
        )
    )
    result = await db.execute(stmt)
    data: dict[str, Decimal] = {}
    for row in result.fetchall():
        if row.current_period_amount is not None:
            data[row.row_code] = row.current_period_amount
    return data


async def get_ratio_analysis_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    wp_code: str = "A1-13",
    month_count: int = 12,
) -> dict:
    """获取比率分析完整数据（DB 取数 + 计算 + 格式化）。

    Args:
        db: 数据库会话
        project_id: 项目 ID
        year: 审计年度
        wp_code: 底稿编号
        month_count: 本期月份数（用于年化，年报=12）

    Returns:
        格式化后的 ratio_analysis sheet 数据
    """
    current_data = await _get_report_data_for_ratio(db, project_id, year)
    prior_data = await _get_report_data_for_ratio(db, project_id, year - 1)

    results = compute_all_ratios(current_data, prior_data, month_count)
    return format_ratio_analysis_sheet(results, wp_code)
