"""度量类型枚举与显示规则

七类 measure kind 的枚举定义和 RatioScale 枚举，用于跨层格式化统一。
"""
from enum import Enum
from typing import Optional


class MeasureKind(str, Enum):
    """度量类型（七类）

    用于统一前后端的数值格式化规则。各类型的显示规则见 GtMeasureCell 组件。
    """
    AMOUNT = "amount"           # 金额：按项目金额单位和账号小数位格式化
    RATIO = "ratio"             # 比例：固定2位小数 + %，根据 RatioScale 确定是否需要 ×100
    COUNT = "count"             # 计数：0位小数，整数
    QUANTITY = "quantity"       # 数量：原值有效小数位（最多6位）
    EXCHANGE_RATE = "exchange_rate"  # 汇率：原值有效小数位（最多6位）
    UNIT_PRICE = "unit_price"   # 单价：原值有效小数位（最多6位）
    TEXT = "text"               # 文本：原样输出，不做数值格式化


class RatioScale(str, Enum):
    """比例刻度类型

    仅用于 ratio kind，决定原值如何转换为百分比显示：
    - fraction: 原值是小数（如 0.2 表示 20%），显示时 ×100
    - percent_points: 原值已是百分点（如 20 表示 20%），显示时不变

    两种情况的除数（divisor）均为 1。
    """
    FRACTION = "fraction"               # 小数形式：0.2 → 20.00%
    PERCENT_POINTS = "percent_points"   # 百分点形式：20 → 20.00%


def validate_ratio_scale(
    kind: Optional[MeasureKind],
    ratio_scale: Optional[RatioScale]
) -> None:
    """校验 ratio_scale 仅在 kind=ratio 时出现

    Args:
        kind: 度量类型
        ratio_scale: 比例刻度（可选）

    Raises:
        ValueError: 当 kind=ratio 时缺少 ratio_scale，或其他 kind 带有 ratio_scale
    """
    if kind == MeasureKind.RATIO and ratio_scale is None:
        raise ValueError("ratio kind 必须传递 ratio_scale")
    if kind != MeasureKind.RATIO and ratio_scale is not None:
        raise ValueError(f"{kind} kind 禁止传递 ratio_scale")
