"""单张报表内的求值顺序：被 ``ROW`` / ``SUM_ROW`` 引用的行先算。

报表引擎逐行求值、行值存进 ``row_cache`` 供后续行的 ``ROW()`` 读取。原先按 ``row_number`` 顺序算 ⇒
合计行排在明细之前时读到的是空缓存，静默得 0：国企利润表「一、营业总收入 = ROW('IS-002')+…」排在
「其中：营业收入」前面，营业收入 3,859 万、营业总收入 0（两版国企模板各 2 行，上市模板无此形态）。

``SUM_ROW('起','止')`` 与求值内核同口径：同表内行次按字符串落在 [起, 止] 区间的行。
循环引用不报错：在环上的那一跳按原顺序算（与改前行为一致），不影响其余行。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeVar

from app.services.formula_grammar import ROW_PATTERN, SUM_ROW_PATTERN


class _Row(Protocol):
    row_code: str
    row_number: int
    formula: str | None


R = TypeVar("R", bound=_Row)


def _refs(formula: str | None, codes: Sequence[str]) -> list[str]:
    if not formula:
        return []
    refs = [m.group(1) for m in ROW_PATTERN.finditer(formula)]
    for m in SUM_ROW_PATTERN.finditer(formula):
        start, end = m.group(1), m.group(2)
        refs.extend(c for c in codes if start <= c <= end)
    return refs


def evaluation_order(configs: Sequence[R]) -> list[R]:
    """依赖在前的求值顺序；没有前向引用时与按 ``row_number`` 排序完全相同。"""
    by_number = sorted(configs, key=lambda r: r.row_number)
    by_code: dict[str, R] = {}
    for r in by_number:
        by_code.setdefault(r.row_code, r)
    codes = list(by_code)
    out: list[R] = []
    state: dict[int, int] = {}  # id(row) → 1 访问中 / 2 已输出

    def visit(r: R) -> None:
        if state.get(id(r)):
            return
        state[id(r)] = 1
        for code in _refs(r.formula, codes):
            dep = by_code.get(code)
            if dep is not None and dep is not r and state.get(id(dep)) != 1:
                visit(dep)
        state[id(r)] = 2
        out.append(r)

    for r in by_number:
        visit(r)
    return out
