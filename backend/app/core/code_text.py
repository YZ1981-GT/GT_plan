"""编码类单元格（科目编码 / 凭证号 / 组织编码 / 辅助编码）→ 文本。

独立成模块、不依赖任何业务模块：账套导入 converter、旧导入引擎、客户科目表导入都要用，
放进 converter 会与 account_chart_service 互相 import（converter → direction_resolver →
account_chart_service → converter）。
"""

from __future__ import annotations

from decimal import Decimal


def code_text(val) -> str:
    """Excel 里存成数字的编码，calamine / openpyxl 读出来是 float：``str(1001.0)`` 得 ``"1001.0"``，
    科目上下级（``5101`` / ``510101``）就认不出来，父子重复汇总、凭证号也对不上。

    整数值的 float / Decimal 去掉小数部分；本来是文本（``"1002.01"`` 点号分级、``"001"`` 前导零）原样保留。
    """
    if val is None:
        return ""
    if isinstance(val, bool):
        return str(val).strip()
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    if isinstance(val, Decimal) and val.is_finite() and val == val.to_integral_value():
        return str(int(val))
    return str(val).strip()
