"""报表合计行公式生成器的两条约束（spec formula-hub-integrity-closure 任务 18，ADR-FHIC-23；需求 6.2、6.3）。

``report_formula_service._generate_sum_formula`` 按缩进 / 同级行给合计行自动生成 ``SUM_ROW``。2026-05-13 的首版同级扫描只在
「：」「:」「合计」「小计」处停，把四套利润表的归属行（国企 IS-074 / IS-075、上市 IS-051 / IS-052）写成了跨越「综合收益总额」
「利润总额」等合计行的区间（N1：真库 8 行原文与首版的输出逐字相同）。现行版本在「总计」「总额」处也停，但仍会把更深缩进的
合计行、名字里不带合计词的同级合计行收进区间。由生成器调用的两条约束：

① 本行已有显式定义（去空白后非空的字符串公式）⇒ 不生成，不覆盖；
② 候选 ``SUM_ROW`` 区间（同表、起 ≤ 行次 ≤ 止，与 ``report_row_compute`` 同口径）含本行以外的 ``is_total_row`` 行 ⇒ 不生成，
   向调用方给的列表追加一条 warning（``fill_all_formulas`` 放进返回值的 ``warnings`` 并记 ``logger.warning``）。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def has_explicit_formula(row: Any) -> bool:
    """约束①：本行公式是去空白后非空的字符串（``None`` / 空串 / 非字符串都不算显式定义）。"""
    formula = getattr(row, "formula", None)
    return isinstance(formula, str) and bool(formula.strip())


def total_rows_in_range(configs: Sequence[Any], current_idx: int, first: str, last: str) -> list[str]:
    """约束②：区间内（``first ≤ 行次 ≤ last``，字符串比较）除本行外 ``is_total_row`` 为真的行次，按表内顺序。"""
    me = configs[current_idx].row_code
    return [row.row_code for row in configs
            if first <= row.row_code <= last and row.row_code != me and getattr(row, "is_total_row", False) is True]


def range_blocked(configs: Sequence[Any], current_idx: int, first: str, last: str,
                  warnings: list[str] | None) -> bool:
    """约束②：候选区间含其他合计行 ⇒ 追加 warning（``warnings`` 不为 None 时）并返回 True。"""
    crossed = total_rows_in_range(configs, current_idx, first, last)
    if not crossed:
        return False
    if warnings is not None:
        row = configs[current_idx]
        warnings.append(f"合计行 {row.row_code}「{row.row_name}」未自动生成公式：候选 SUM_ROW('{first}','{last}') "
                        f"的区间含其他合计行 {'、'.join(crossed)}")
    return True
