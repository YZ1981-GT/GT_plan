"""通用 Pydantic 字段类型 — V3 收官增强 Req 2

提供金额相关的可复用 Annotated Decimal 字段：

- ``AmountDecimal``: 必填金额字段，自动 ``to_decimal`` + 拒绝 NaN/Infinity
- ``OptionalAmountDecimal``: 可空金额字段，None 直接放行，其余转 Decimal

用法示例::

    from app.schemas._common import AmountDecimal, OptionalAmountDecimal

    class AdjustmentLineItem(BaseModel):
        debit_amount: AmountDecimal = Decimal("0")
        credit_amount: AmountDecimal = Decimal("0")

    class MisstatementUpdate(BaseModel):
        misstatement_amount: OptionalAmountDecimal = None

校验规则（透传 ``app.services._decimal_helpers.to_decimal``）:
    - str / int / float / Decimal 统一转 ``Decimal``
    - NaN / Infinity / -Infinity 抛 ``AmountConversionError``（中文消息）
    - 空字符串、无法解析的字符串抛错
    - 科学计数法字符串支持（如 ``"1.5e3"``）
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator


def _validate_amount(v):
    """必填金额字段 BeforeValidator —— 委派给 ``to_decimal``。"""
    # 延迟导入以避免循环依赖（_decimal_helpers 内部目前未引用 schemas）
    from app.services._decimal_helpers import to_decimal

    return to_decimal(v, field="金额")


def _validate_optional_amount(v):
    """可空金额字段 BeforeValidator —— None 放行，否则委派给 ``to_decimal``。"""
    if v is None:
        return None
    from app.services._decimal_helpers import to_decimal

    return to_decimal(v, field="金额")


# ---------------------------------------------------------------------------
# 公开类型别名
# ---------------------------------------------------------------------------

AmountDecimal = Annotated[Decimal, BeforeValidator(_validate_amount)]
"""必填金额字段：自动转 Decimal + 拒绝 NaN/Infinity。"""

OptionalAmountDecimal = Annotated[Decimal | None, BeforeValidator(_validate_optional_amount)]
"""可空金额字段：None 直接放行，其余统一转 Decimal + 拒绝 NaN/Infinity。"""


__all__ = ["AmountDecimal", "OptionalAmountDecimal"]
