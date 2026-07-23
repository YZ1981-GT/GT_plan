"""抽样方法学单一真源（voucher-sampling-hardening Task 9）

Python 精确移植前端 `useSamplingAlgorithms.ts` 的 CAS 1314 泊松可信赖度系数表与 MUS
抽样间隔/样本量推导，使后端成为方法学权威口径，消除前后端双算漂移。

前端保留即时预览计算，正式抽样以本模块返回值为准（algo_version 留痕）。

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 10.1, 10.8
Properties: Property 13, Property 22
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

# 算法版本：方法学口径变更时递增，用于回填留痕与漂移追溯。
ALGO_VERSION = "cas1314-mus-v1"

# CAS 1314 泊松可信赖度系数表（与前端 CAS1314_RELIABILITY_TABLE 逐行一致）
# (confidence, base, increment)
CAS1314_RELIABILITY_TABLE: list[tuple[float, float, float]] = [
    (0.50, 0.70, 1.14),
    (0.63, 1.00, 1.21),
    (0.70, 1.21, 1.27),
    (0.75, 1.39, 1.32),
    (0.80, 1.61, 1.38),
    (0.85, 1.90, 1.47),
    (0.90, 2.31, 1.58),
    (0.95, 3.00, 1.75),
    (0.99, 4.61, 2.03),
]


def _to_decimal(v) -> Decimal:
    try:
        d = Decimal(str(v if v is not None else 0))
        return d if d.is_finite() else Decimal("0")
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _nearest_row(confidence_level: float) -> tuple[float, float, float]:
    best = CAS1314_RELIABILITY_TABLE[0]
    best_dist = abs(best[0] - confidence_level)
    for row in CAS1314_RELIABILITY_TABLE:
        dist = abs(row[0] - confidence_level)
        if dist < best_dist:
            best = row
            best_dist = dist
    return best


def reliability_factor(confidence_level: float, expected_errors: float) -> float:
    """可信赖度系数 R(置信度, 预期错报数) = base + max(0,errors)*increment。

    与前端 reliabilityFactor 一致：取最近邻表行，结果保留 6 位小数（JS Math.round 语义）。
    """
    _, base, increment = _nearest_row(confidence_level)
    errors = expected_errors if (math.isfinite(expected_errors) and expected_errors > 0) else 0.0
    factor = base + errors * increment
    # JS Math.round(x*1e6)/1e6（四舍五入）
    return math.floor(factor * 1e6 + 0.5) / 1e6


def compute_mus_interval(tolerable: str, confidence_level: float, expected: str) -> str:
    """MUS 抽样间隔 = 可容忍错报 / 可信赖度系数，2 位小数 ROUND_HALF_EVEN。

    与前端 computeMusInterval 逐位一致。可容忍错报 ≤ 0 → "0.00"。
    """
    tol = _to_decimal(tolerable)
    if tol <= 0:
        return "0.00"
    exp = _to_decimal(expected)
    load = float(exp / tol) if exp > 0 else 0.0
    rf = reliability_factor(confidence_level, load)
    if rf <= 0:
        return "0.00"
    return (tol / Decimal(str(rf))).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN).__str__()


def compute_sample_size(
    population_amount: str, tolerable: str, expected: str, confidence_level: float
) -> int:
    """科学样本量 = ceil(总体金额 / 抽样间隔)。与前端 computeSampleSize 一致。"""
    interval = _to_decimal(compute_mus_interval(tolerable, confidence_level, expected))
    if interval <= 0:
        return 0
    pop = _to_decimal(population_amount)
    if pop <= 0:
        return 0
    return int((pop / interval).to_integral_value(rounding="ROUND_CEILING"))


def build_methodology_snapshot(
    *,
    sampling_method: str,
    population_amount: str,
    confidence_level: float | None,
    tolerable_misstatement: str | None,
    expected_misstatement: str | None,
) -> dict:
    """构建方法学快照（权威口径）。

    仅 MUS 且提供置信度 + 可容忍错报时推导 CAS1314 间隔与建议样本量；否则相应字段为 None。
    """
    snapshot: dict = {
        "algo_version": ALGO_VERSION,
        "sampling_method": sampling_method,
        "confidence_level": confidence_level,
        "tolerable_misstatement": tolerable_misstatement,
        "expected_misstatement": expected_misstatement,
        "reliability_factor": None,
        "sampling_interval": None,
        "suggested_sample_size": None,
    }
    has_tol = tolerable_misstatement not in (None, "") and _to_decimal(tolerable_misstatement) > 0
    valid_cl = confidence_level is not None and 0 < confidence_level < 1
    if sampling_method == "mus" and has_tol and valid_cl:
        exp = expected_misstatement if expected_misstatement not in (None, "") else "0"
        snapshot["reliability_factor"] = reliability_factor(
            confidence_level,
            float(_to_decimal(exp) / _to_decimal(tolerable_misstatement))
            if _to_decimal(exp) > 0
            else 0.0,
        )
        snapshot["sampling_interval"] = compute_mus_interval(
            tolerable_misstatement, confidence_level, exp
        )
        snapshot["suggested_sample_size"] = compute_sample_size(
            population_amount, tolerable_misstatement, exp, confidence_level
        )
    return snapshot
