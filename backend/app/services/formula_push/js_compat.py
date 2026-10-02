"""与前端 JS 数值语义逐位一致的解析 / 格式化（纯函数）。

公式推送引擎在后端复刻前端 composable 的算式（spec chain-closure-phase2-formula-push-engine
design §一「前后端同式」），两侧对「什么算数」「数怎么变成字符串」必须完全相同，否则
双侧夹具会因格式差异打红、或同一行数据两侧算出不同结果：

* :func:`js_number` —— ``Number(str)``：去首尾空白；空串为 0；十进制 / 指数 / 十六进制 /
  二进制 / 八进制字面量；``Infinity``；其余 NaN。（Python ``float`` 另接受 ``1_000`` / ``nan``
  / ``inf``，JS 不接受。）
* :func:`parse_num` —— ``useE1FormulaEngine.parseNum``：null / undefined / 空串 / NaN / ±∞ → 0。
* :func:`js_number_to_string` —— ``String(number)``（ECMAScript Number::toString），前端写入
  ``checklist_responses.remark`` 的数值字符串形态（``100`` 而非 ``100.0``，``1e-7`` 而非 ``1e-07``）。
* :func:`js_json_number` —— 行 JSON 里的数值：整数值落为 int，与 ``JSON.stringify`` 输出一致。
"""
from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any

_DECIMAL_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_RADIX_RE = {
    16: re.compile(r"^0[xX][0-9a-fA-F]+$"),
    2: re.compile(r"^0[bB][01]+$"),
    8: re.compile(r"^0[oO][0-7]+$"),
}
_INFINITY = {"Infinity": math.inf, "+Infinity": math.inf, "-Infinity": -math.inf}


def js_number(value: Any) -> float:
    """``Number(value)`` 的子集：str / int / float / Decimal / bool / None。其余 → NaN。"""
    if value is None:
        return 0.0  # Number(null) === 0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, list):
        # Number([]) === 0；Number([x]) === Number(String(x))；多元素 NaN
        if not value:
            return 0.0
        if len(value) == 1 and isinstance(value[0], (str, int, float)) and not isinstance(value[0], bool):
            inner = value[0]
            return js_number(inner if isinstance(inner, str) else js_number_to_string(inner))
        return math.nan
    if not isinstance(value, str):
        return math.nan
    text = value.strip()
    if text == "":
        return 0.0
    if _DECIMAL_RE.match(text):
        return float(text)
    for radix, pattern in _RADIX_RE.items():
        if pattern.match(text):
            return float(int(text[2:], radix))
    return _INFINITY.get(text, math.nan)


def parse_num(value: Any) -> float:
    """``parseNum``：null / undefined / 空串 / NaN / ±∞ / 非数值 → 0。"""
    if value is None or (isinstance(value, str) and value == ""):
        return 0.0
    number = js_number(value)
    return number if math.isfinite(number) else 0.0


def read_number(value: Any) -> float | None:
    """``e1MainRowPrefill.readNumber``：null / undefined / 空串 → None；非有限数 → None。"""
    if value is None or (isinstance(value, str) and value == ""):
        return None
    number = js_number(value)
    return number if math.isfinite(number) else None


def js_or_zero(value: Any) -> float:
    """``Number(value) || 0``（NaN 与 ±0 都落 0）。"""
    number = js_number(value)
    return number if (math.isfinite(number) and number != 0) else 0.0


def js_number_to_string(value: float | int | Decimal) -> str:
    """ECMAScript ``Number::toString(10)``。"""
    x = float(value)
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    if x < 0:
        return "-" + js_number_to_string(-x)
    mantissa, _, exp_text = repr(x).partition("e")
    exponent = int(exp_text) if exp_text else 0
    int_part, _, frac_part = mantissa.partition(".")
    digits = (int_part + frac_part).lstrip("0")
    stripped = digits.rstrip("0")
    trailing = len(digits) - len(stripped)
    k = len(stripped)
    n = exponent - len(frac_part) + trailing + k  # 数值 = stripped × 10^(n−k)
    if k <= n <= 21:
        return stripped + "0" * (n - k)
    if 0 < n <= 21:
        return stripped[:n] + "." + stripped[n:]
    if -6 < n <= 0:
        return "0." + "0" * (-n) + stripped
    e = n - 1
    sign = "+" if e >= 0 else "-"
    head = stripped if k == 1 else stripped[0] + "." + stripped[1:]
    return f"{head}e{sign}{abs(e)}"


def js_json_number(value: float | int | Decimal) -> float | int:
    """行 JSON 数值：整数值落 int（``JSON.stringify(100)`` 是 ``100`` 不是 ``100.0``）。"""
    x = float(value)
    if math.isfinite(x) and x.is_integer() and abs(x) < 2**53:
        return int(x)
    return x
