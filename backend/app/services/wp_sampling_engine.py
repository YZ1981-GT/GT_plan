"""统一抽样引擎

Sprint 8 Task 8.9: 统计抽样/非统计抽样/MUS 三种方法。
实现样本量计算公式 + 随机选样。
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SamplingParams:
    """抽样参数"""
    method: str  # statistical / non_statistical / mus
    population_size: int = 0
    population_value: float = 0.0
    confidence_level: float = 0.95  # 置信水平
    tolerable_misstatement: float = 0.0  # 可容忍错报
    expected_misstatement: float = 0.0  # 预期错报
    tolerable_rate: float = 0.05  # 可容忍偏差率（属性抽样）
    expected_rate: float = 0.01  # 预期偏差率
    materiality: float = 0.0  # 重要性水平


@dataclass
class SamplingResult:
    """抽样结果"""
    sample_size: int = 0
    sampling_interval: float = 0.0
    method: str = ""
    formula_used: str = ""
    selected_indices: list[int] = None  # type: ignore
    selected_items: list[dict] = None  # type: ignore

    def __post_init__(self):
        if self.selected_indices is None:
            self.selected_indices = []
        if self.selected_items is None:
            self.selected_items = []


# ─── Z 值表（置信水平→Z 值）───────────────────────────────────

Z_TABLE = {
    0.80: 1.28,
    0.85: 1.44,
    0.90: 1.645,
    0.95: 1.96,
    0.99: 2.576,
}


def calculate_sample_size(params: SamplingParams) -> SamplingResult:
    """计算样本量

    Args:
        params: 抽样参数

    Returns:
        SamplingResult 含 sample_size 和使用的公式
    """
    if params.method == "statistical":
        return _calc_statistical(params)
    elif params.method == "mus":
        return _calc_mus(params)
    else:
        return _calc_non_statistical(params)


def _calc_statistical(params: SamplingParams) -> SamplingResult:
    """统计抽样（属性抽样）

    公式：n = (Z² × p × (1-p)) / E²
    其中 Z=置信水平对应Z值, p=预期偏差率, E=可容忍偏差率-预期偏差率
    有限总体修正：n' = n / (1 + n/N)
    """
    z = Z_TABLE.get(params.confidence_level, 1.96)
    p = max(params.expected_rate, 0.005)  # 最低 0.5%
    e = params.tolerable_rate - params.expected_rate

    if e <= 0:
        return SamplingResult(
            sample_size=params.population_size,
            method="statistical",
            formula_used="E≤0, 全量检查",
        )

    # 无限总体样本量
    n_infinite = math.ceil((z ** 2 * p * (1 - p)) / (e ** 2))

    # 有限总体修正
    if params.population_size > 0:
        n = math.ceil(n_infinite / (1 + n_infinite / params.population_size))
    else:
        n = n_infinite

    n = max(n, 1)

    return SamplingResult(
        sample_size=n,
        method="statistical",
        formula_used=f"n = Z²×p×(1-p)/E² = {z}²×{p}×{1-p}/{e}² = {n_infinite}, 修正后={n}",
    )


def _calc_mus(params: SamplingParams) -> SamplingResult:
    """货币单位抽样 (MUS / PPS)

    公式：n = 总体金额 / 抽样间距
    抽样间距 = 可容忍错报 / 可靠性因子
    可靠性因子 R = -ln(1 - 置信水平)（预期错报为 0 时）
    调整：R = R + 预期错报数 × 扩展因子
    """
    if params.tolerable_misstatement <= 0:
        return SamplingResult(
            sample_size=0,
            method="mus",
            formula_used="可容忍错报为0，无法计算",
        )

    # 可靠性因子
    r_factor = -math.log(1 - params.confidence_level)

    # 如果有预期错报，调整可靠性因子
    if params.expected_misstatement > 0 and params.tolerable_misstatement > 0:
        expansion = 1.6  # 标准扩展因子
        expected_count = params.expected_misstatement / params.tolerable_misstatement
        r_factor += expected_count * expansion

    # 抽样间距
    interval = params.tolerable_misstatement / r_factor

    # 样本量
    if interval > 0 and params.population_value > 0:
        n = math.ceil(params.population_value / interval)
    else:
        n = 0

    n = max(n, 1)

    return SamplingResult(
        sample_size=n,
        sampling_interval=round(interval, 2),
        method="mus",
        formula_used=f"间距 = TM/R = {params.tolerable_misstatement}/{r_factor:.3f} = {interval:.2f}, n = PV/间距 = {n}",
    )


def _calc_non_statistical(params: SamplingParams) -> SamplingResult:
    """非统计抽样

    基于审计判断的经验公式：
    - 低风险：总体 × 5-10%
    - 中风险：总体 × 15-25%
    - 高风险：总体 × 30-50%

    简化：n = max(25, population_size × risk_factor)
    risk_factor 由 confidence_level 推导
    """
    if params.population_size <= 0:
        return SamplingResult(sample_size=0, method="non_statistical", formula_used="总体为空")

    # 置信水平→风险因子
    if params.confidence_level >= 0.95:
        factor = 0.30
    elif params.confidence_level >= 0.90:
        factor = 0.20
    elif params.confidence_level >= 0.85:
        factor = 0.15
    else:
        factor = 0.10

    n = max(25, math.ceil(params.population_size * factor))
    n = min(n, params.population_size)  # 不超过总体

    return SamplingResult(
        sample_size=n,
        method="non_statistical",
        formula_used=f"n = max(25, N×{factor}) = max(25, {params.population_size}×{factor}) = {n}",
    )


def random_select(
    population: list[dict],
    sample_size: int,
    method: str = "simple_random",
    value_field: Optional[str] = None,
    interval: Optional[float] = None,
    seed: Optional[int] = None,
) -> list[dict]:
    """执行随机选样

    Args:
        population: 总体数据列表
        sample_size: 样本量
        method: 选样方法 (simple_random / systematic / mus_cumulative)
        value_field: MUS 时的金额字段名
        interval: MUS 抽样间距
        seed: 随机种子（可复现）

    Returns:
        选中的样本列表
    """
    if not population or sample_size <= 0:
        return []

    rng = random.Random(seed)

    if method == "simple_random":
        # 简单随机抽样
        n = min(sample_size, len(population))
        indices = rng.sample(range(len(population)), n)
        return [population[i] for i in sorted(indices)]

    elif method == "systematic":
        # 系统抽样（等距）
        if len(population) <= sample_size:
            return population[:]
        step = len(population) / sample_size
        start = rng.uniform(0, step)
        indices = [int(start + i * step) for i in range(sample_size)]
        indices = [i for i in indices if i < len(population)]
        return [population[i] for i in indices]

    elif method == "mus_cumulative" and value_field and interval:
        # MUS 累计金额法
        selected = []
        cumulative = 0.0
        start = rng.uniform(0, interval)
        next_threshold = start

        for item in population:
            val = abs(float(item.get(value_field, 0)))
            cumulative += val
            while cumulative >= next_threshold and len(selected) < sample_size:
                selected.append(item)
                next_threshold += interval

        return selected

    return []


def evaluate_results(
    sample_errors: list[float],
    sample_size: int,
    population_value: float,
    method: str,
    tolerable_misstatement: float = 0.0,
) -> dict:
    """评价抽样结果

    Args:
        sample_errors: 样本中发现的错报金额列表
        sample_size: 样本量
        population_value: 总体金额
        method: 抽样方法
        tolerable_misstatement: 可容忍错报

    Returns:
        评价结果
    """
    total_error = sum(abs(e) for e in sample_errors)
    error_count = sum(1 for e in sample_errors if e != 0)

    if method == "mus" and population_value > 0 and sample_size > 0:
        # MUS 推断：错报推断到总体
        projected = total_error * (population_value / sample_size) if sample_size > 0 else 0
        conclusion = "accept" if projected <= tolerable_misstatement else "reject"
    else:
        # 非 MUS：简单比率推断
        error_rate = error_count / sample_size if sample_size > 0 else 0
        projected = total_error * (population_value / sample_size) if sample_size > 0 else 0
        conclusion = "accept" if projected <= tolerable_misstatement else "reject"

    return {
        "sample_errors_count": error_count,
        "sample_errors_total": round(total_error, 2),
        "projected_misstatement": round(projected, 2),
        "tolerable_misstatement": tolerable_misstatement,
        "conclusion": conclusion,
        "conclusion_label": "可接受" if conclusion == "accept" else "需扩大样本或追加程序",
    }
