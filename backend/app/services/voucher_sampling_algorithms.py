"""通用抽凭引擎 — 5种审计抽样算法实现

纯算法模块，无数据库交互。被 voucher_sampling router 调用。
支持：随机抽样、金额分层抽样、特定项目选取、系统抽样（等距）、MUS货币单元抽样。

核心规范：
- 金额使用 Decimal 精度
- GREATEST = max(COALESCE(debit_amount, 0), COALESCE(credit_amount, 0))
- 随机种子保证可复现性
- 结果超 500 条时截断并标记 truncated=True
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

# ─── 类型定义 ──────────────────────────────────────────────────────────────────

SamplingMethod = Literal["random", "stratified", "specific_item", "systematic", "mus"]

MAX_RESULT_ITEMS = 500


@dataclass
class StratumConfig:
    """金额分层配置"""

    lower_bound: Decimal
    upper_bound: Decimal
    sample_size: int


@dataclass
class SamplingParams:
    """抽样参数（各方法特有字段按需填入）"""

    # random
    sample_size: int | None = None
    # stratified
    strata: list[StratumConfig] | None = None
    # specific_item
    materiality_threshold: Decimal | None = None
    # systematic
    start_point: int | None = None
    interval: int | None = None
    # mus
    mus_sample_size: int | None = None


@dataclass
class SamplingResult:
    """抽样结果"""

    items: list[dict]
    seed_used: int
    population_count: int
    population_debit_total: Decimal
    population_credit_total: Decimal
    sample_count: int
    sample_debit_total: Decimal
    sample_credit_total: Decimal
    count_coverage_rate: Decimal  # 笔数覆盖率 (%)
    amount_coverage_rate: Decimal  # 金额覆盖率 (%)
    truncated: bool = False


# ─── 辅助函数 ──────────────────────────────────────────────────────────────────


def _greatest(item: dict) -> Decimal:
    """计算单条凭证的 GREATEST(COALESCE(debit_amount,0), COALESCE(credit_amount,0))"""
    debit = item.get("debit_amount")
    credit = item.get("credit_amount")
    debit_val = Decimal(str(debit)) if debit is not None else Decimal("0")
    credit_val = Decimal(str(credit)) if credit is not None else Decimal("0")
    return max(debit_val, credit_val)


def _compute_coverage(
    population: list[dict], sample: list[dict]
) -> tuple[Decimal, Decimal]:
    """计算笔数覆盖率和金额覆盖率

    Returns:
        (count_coverage_rate, amount_coverage_rate) — 百分比，保留两位小数
    """
    pop_count = len(population)
    sample_count = len(sample)

    if pop_count == 0:
        return Decimal("0"), Decimal("0")

    # 笔数覆盖率
    count_rate = round(Decimal(sample_count) / Decimal(pop_count) * 100, 2)

    # 金额覆盖率：使用 GREATEST 的绝对值之和
    pop_amount = sum(_greatest(item) for item in population)
    sample_amount = sum(_greatest(item) for item in sample)

    if pop_amount == 0:
        amount_rate = Decimal("0")
    else:
        amount_rate = round(sample_amount / pop_amount * 100, 2)

    return count_rate, amount_rate


def _sum_debit(items: list[dict]) -> Decimal:
    """计算借方金额合计"""
    total = Decimal("0")
    for item in items:
        val = item.get("debit_amount")
        if val is not None:
            total += Decimal(str(val))
    return total


def _sum_credit(items: list[dict]) -> Decimal:
    """计算贷方金额合计"""
    total = Decimal("0")
    for item in items:
        val = item.get("credit_amount")
        if val is not None:
            total += Decimal(str(val))
    return total


# ─── 抽样算法实现 ──────────────────────────────────────────────────────────────


def _random_sampling(population: list[dict], n: int, rng: random.Random) -> list[dict]:
    """随机抽样：rng.sample(population, min(n, len(population)))"""
    actual_n = min(n, len(population))
    return rng.sample(population, actual_n)


def _stratified_sampling(
    population: list[dict], strata: list[StratumConfig], rng: random.Random
) -> list[dict]:
    """金额分层抽样：按 GREATEST(debit,credit) 分层 + 每层 rng.sample

    每个 item 根据其 GREATEST 值分配到对应层（lower_bound <= amount <= upper_bound）。
    每层取 min(configured_sample_size, actual_stratum_count) 笔。
    """
    result: list[dict] = []

    for stratum in strata:
        # 筛选落入当前层的凭证
        stratum_items = [
            item
            for item in population
            if stratum.lower_bound <= _greatest(item) <= stratum.upper_bound
        ]
        # 每层抽取配置的样本量（不超过实际层内笔数）
        actual_size = min(stratum.sample_size, len(stratum_items))
        if actual_size > 0:
            sampled = rng.sample(stratum_items, actual_size)
            result.extend(sampled)

    return result


def _specific_item_sampling(
    population: list[dict], threshold: Decimal
) -> list[dict]:
    """特定项目选取：筛选 GREATEST(debit, credit) >= threshold 的全部凭证"""
    return [item for item in population if _greatest(item) >= threshold]


def _systematic_sampling(
    population: list[dict], start: int, interval: int
) -> list[dict]:
    """系统抽样：按 voucher_date + voucher_no 排序后，从 start 起每隔 interval 取 1 笔

    start: 1-based 起始点
    interval: 间隔 K
    选取的 0-based 索引为 {start-1, start-1+interval, start-1+2*interval, ...} ∩ [0, len)
    """
    # 排序：按 voucher_date + voucher_no
    sorted_pop = sorted(
        population,
        key=lambda x: (x.get("voucher_date") or "", x.get("voucher_no") or ""),
    )

    result: list[dict] = []
    n = len(sorted_pop)
    # start 是 1-based，转为 0-based index
    idx = start - 1
    while 0 <= idx < n:
        result.append(sorted_pop[idx])
        idx += interval

    return result


def _mus_sampling(
    population: list[dict], sample_size: int, rng: random.Random
) -> list[dict]:
    """MUS 货币单元抽样：累积金额法 PPS

    interval = total_amount / sample_size
    random_start = rng.uniform(0, interval)
    遍历凭证累积金额，每跨越一个间隔点选中当前凭证。
    负数金额取绝对值参与权重计算。
    """
    if sample_size <= 0:
        return []

    # 计算总体金额（使用 GREATEST 的绝对值）
    total_amount = sum(abs(_greatest(item)) for item in population)

    if total_amount == 0:
        return []

    # 计算间隔
    interval = total_amount / Decimal(sample_size)

    if interval <= 0:
        return []

    # 随机起始点
    random_start = Decimal(str(rng.uniform(0, float(interval))))

    # 遍历累积选取
    result: list[dict] = []
    cumulative = Decimal("0")
    next_threshold = random_start

    for item in population:
        amount = abs(_greatest(item))
        cumulative += amount

        # 当累积金额跨越一个或多个间隔点时，选中当前凭证
        if cumulative >= next_threshold:
            result.append(item)
            # 推进到下一个间隔点（可能跨越多个间隔）
            while next_threshold <= cumulative:
                next_threshold += interval

    return result


# ─── 分发函数 ──────────────────────────────────────────────────────────────────


def execute_sampling(
    method: SamplingMethod,
    population: list[dict],
    params: SamplingParams,
    seed: int | None = None,
) -> SamplingResult:
    """执行抽样算法

    根据 method 分发到具体算法实现。
    若 seed 为 None，自动生成随机种子并记录到结果。

    Args:
        method: 抽样方法（5种之一）
        population: 总体凭证列表（dict 列表）
        params: 抽样参数
        seed: 随机种子（可选）

    Returns:
        SamplingResult 包含抽样结果和统计信息
    """
    # 生成或使用种子
    if seed is None:
        seed = random.randint(0, 2**31)

    rng = random.Random(seed)

    # 根据方法分发
    if method == "random":
        n = params.sample_size or 30
        sample = _random_sampling(population, n, rng)
    elif method == "stratified":
        strata = params.strata or []
        sample = _stratified_sampling(population, strata, rng)
    elif method == "specific_item":
        threshold = params.materiality_threshold or Decimal("0")
        sample = _specific_item_sampling(population, threshold)
    elif method == "systematic":
        start = params.start_point or 1
        interval = params.interval or 2
        sample = _systematic_sampling(population, start, interval)
    elif method == "mus":
        mus_size = params.mus_sample_size or 10
        sample = _mus_sampling(population, mus_size, rng)
    else:
        sample = []

    # 截断处理
    truncated = len(sample) > MAX_RESULT_ITEMS
    if truncated:
        sample = sample[:MAX_RESULT_ITEMS]

    # 计算覆盖率
    count_rate, amount_rate = _compute_coverage(population, sample)

    # 构建结果
    return SamplingResult(
        items=sample,
        seed_used=seed,
        population_count=len(population),
        population_debit_total=_sum_debit(population),
        population_credit_total=_sum_credit(population),
        sample_count=len(sample),
        sample_debit_total=_sum_debit(sample),
        sample_credit_total=_sum_credit(sample),
        count_coverage_rate=count_rate,
        amount_coverage_rate=amount_rate,
        truncated=truncated,
    )
