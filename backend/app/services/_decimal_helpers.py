"""金额 Decimal 化公共转换器 — V3 收官增强 Req 2

提供 3 个核心函数：
- to_decimal: 统一将 str/int/float/Decimal 转为 Decimal，处理边界 case
- quantize: 按业务场景四舍五入（元/千分位/整元）
- amount_tolerance: 按金额规模动态容差

调用方：所有金额相关 service / Pydantic schema / 前端传入校验
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

# 精度上下文：28 位（Python decimal 默认），覆盖 10^15 量级金额 + 0.0001 分位
getcontext().prec = 28


class AmountConversionError(ValueError):
    """金额转换异常，继承 ValueError 便于 Pydantic 捕获。"""

    pass


def to_decimal(
    value,
    *,
    allow_none: bool = False,
    field: str = "金额",
) -> Decimal | None:
    """str/int/float/Decimal -> Decimal，统一边界处理。

    参数:
        value: 待转换值（支持 str/int/float/Decimal/None）
        allow_none: 是否允许 None 输入（True 时返回 None，False 时抛异常）
        field: 字段名称，用于错误消息

    返回:
        转换后的 Decimal 值，或 None（仅当 allow_none=True 且 value=None）

    异常:
        AmountConversionError:
            - None + allow_none=False
            - NaN / Infinity
            - 无法解析的格式（空字符串等）
    """
    if value is None:
        if allow_none:
            return None
        raise AmountConversionError(f"{field} 不能为空")

    try:
        d = Decimal(str(value)) if not isinstance(value, Decimal) else value
    except InvalidOperation:
        raise AmountConversionError(f"{field} 格式非法: {value!r}")

    if d.is_nan() or d.is_infinite():
        raise AmountConversionError(f"{field} 不能为 NaN 或 Infinity")

    return d


def quantize(value: Decimal, *, scale: int = 2) -> Decimal:
    """按业务场景四舍五入。

    参数:
        value: 待量化的 Decimal 值
        scale: 小数位数
            - scale=2: 元（0.01）— 默认
            - scale=4: 千分位（0.0001）— 汇率/比率
            - scale=0: 整元（部分汇总场景）

    返回:
        四舍五入后的 Decimal 值
    """
    quant = Decimal(10) ** -scale
    return value.quantize(quant, rounding=ROUND_HALF_UP)


def amount_tolerance(
    amount: Decimal | None,
    *,
    ratio: Decimal = Decimal("0.001"),
) -> Decimal:
    """按金额规模动态容差。

    规则:
        - amount 为 None 或 0: tolerance = 0.01（绝对值最小容差）
        - |amount| < 1万: tolerance = 0.01（绝对值）
        - |amount| ∈ [1万, 100万): tolerance = |amount| * 0.0001
        - |amount| ≥ 100万: tolerance = |amount| * ratio（默认 0.001）

    参数:
        amount: 金额值（可为 None）
        ratio: 大金额容差比率（默认 0.001）

    返回:
        动态容差值（始终为正 Decimal）
    """
    if amount is None:
        return Decimal("0.01")

    abs_amount = abs(amount)

    # < 1万：绝对容差
    if abs_amount < Decimal("10000"):
        return Decimal("0.01")

    # [1万, 100万)：万分之一
    if abs_amount < Decimal("1000000"):
        return abs_amount * Decimal("0.0001")

    # ≥ 100万：按 ratio（默认千分之一）
    return abs_amount * ratio
