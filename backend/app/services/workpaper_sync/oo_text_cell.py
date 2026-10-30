"""OO 在可编辑文本列里存成数值的输入，按文本读回（spec writeback-followup-issue-closure R13）。

常规格式的单元格里键入 ``231``，OnlyOffice 存成数值（openpyxl 读回 ``int 231``）。契约把这列
声明为 text，HTML 表单与物化都按字符串处理。读入时不转成文本，``merge.normalize_value`` 会拒
（text 必须是字符串，不把数字与其字符串形态判等）；base 与 current 都没有这个字段时三方合并
不比较值、直接采纳 incoming ⇒ 物化写盘时 ``EditableCellWriteError``，incoming 已 durable、
整次保存失败（10-24 和平药房 D2 实测，operation 813a2167）。

只转换能无歧义还原「用户键入的数字」的形态：

* ``int``（不含 ``bool``）→ 十进制字符串；
* 有限 ``float`` 且绝对值小于 2**53 → 最短十进制形态、不带多余零、不用科学计数
  （``231.0`` → ``"231"``，``1.5`` → ``"1.5"``，``1e-05`` → ``"0.00001"``）；
* 有限 ``Decimal`` → 去掉多余零后的定点形态。

其余（``bool``、NaN / Inf、超出双精度整数精度的数、日期、字符串）返回 ``None``，交原来的
类型规范化失败路径处理。只给 extract 用；比较口径（``normalize_value``）不变。
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Final

#: 双精度能精确表示的整数上限。超过它 OO 存的已不是用户键入的那串数字（尾数已丢），
#: 按文本读回只会得到另一串数字，所以不转换。
_EXACT_FLOAT_LIMIT: Final[float] = float(2**53)


def numeric_cell_as_text(value: Any) -> str | None:
    """数值 → 用户键入时的十进制文本；不是可无歧义还原的数值则返回 ``None``。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value) or abs(value) >= _EXACT_FLOAT_LIMIT:
            return None
        # repr 是能还原同一个 float 的最短十进制串（231.0 → '231.0'、1e-05 → '1e-05'），
        # 去掉多余零、改成定点即用户键入的形态。
        return _plain_decimal_text(Decimal(repr(value)))
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return _plain_decimal_text(value)
    return None


def _plain_decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "0") else text
