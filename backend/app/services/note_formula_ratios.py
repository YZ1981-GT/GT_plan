"""附注表格比例 / 损失率派生列 —— 单体预设公式与合并拉数后派生共用的唯一判定。

spec note-table-structure-formula-pull-closure R2。按标题行库逐列语义（``column_keys``）认列：

* 占比（share）：叶子是「比例(%)」「占比」「比重」、上一层是金额分组（「账面余额」）⇒ 本行同组金额 ÷ 本表合计行同组金额 × 100。
  分母不在本表的占比（前五名「占应收账款合计的比例」）不派生。
* 损失率（rate）：叶子含「损失率」「计提比例」「计提率」「坏账率」「减值率」⇒ 同期间准备列（坏账 / 减值 / 跌价准备）÷ 同期间
  账面余额列 × 100（账面余额 = 同期间唯一一列既不是准备、也不是账面价值的金额列）。

认不准（同期间 / 同组多列、没有唯一合计行）不派生、回原因。分子格为空不算（不写 0）、分母为 0 不写，由调用方按计划执行：
单体 ``note_formula_tables.table_preset_formulas`` 生成 ``ratio`` 类预设公式，合并 ``consol_note_table_totals.build_note_rows``
汇总后直接按计划算。列下标都是 ``values`` 下标（不含标签列）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

__all__ = ["RatioPlan", "derive_ratio", "expression", "ratio_plans", "ratio_rows"]

_SHARE_RE = re.compile(r"^(?:比例|占比|比重)(?:\(%\)|%)?$")
_RATE_RE = re.compile(r"损失率|计提比例|计提率|坏账率|减值率")
_PROVISION_WORDS = ("坏账准备", "减值准备", "跌价准备")
_HUNDRED = Decimal(100)


@dataclass(frozen=True)
class RatioPlan:
    column: int  # 比例列（values 下标）
    kind: str  # share / rate
    numerator: int  # share：同组金额列；rate：准备列
    denominator: int | None  # rate：账面余额列；share：None（分母 = 合计行同列）
    total_row: int | None  # share：分母所在的合计行
    label: str  # 比例列表头（说明用）


def _keys(table: dict) -> list[Any]:
    from app.services.note_table_header_library import column_keys

    try:
        return column_keys(table)
    except Exception:  # noqa: BLE001 —— 表头坏了不派生
        return []


def _is_provision(key: Any) -> bool:
    return any(w in "".join(key.measure) for w in _PROVISION_WORDS)


def _single_total_row(rows: list[Any]) -> int | None:
    from app.services.note_total_terms import row_kind

    totals = [i for i, r in enumerate(rows) if row_kind(r) == "total"]
    return totals[0] if len(totals) == 1 else None


def ratio_plans(table: dict, rows: list[Any] | None = None) -> tuple[list[RatioPlan], list[str]]:
    """一张表的比例列派生计划 + 没派生的说明（``["列名：原因"]``）。``rows`` 缺省取 ``table["rows"]``。"""
    from app.services.note_table_header_library import load_vocabulary, norm

    vocab = load_vocabulary()
    keys = _keys(table)[1:]
    rows = rows if rows is not None else (table.get("rows") if isinstance(table.get("rows"), list) else [])
    amounts = [k for k in keys if k.kind == "amount"]
    plans: list[RatioPlan] = []
    notes: list[str] = []
    for k in keys:
        if k.kind != "ratio" or not k.path:
            continue
        leaf = norm(k.path[-1])
        label = "/".join(k.path)
        if _SHARE_RE.fullmatch(leaf):
            group = tuple(k.path[:-1])
            same = [a for a in amounts if a.period == k.period and tuple(a.path[:-1]) == group]
            total = _single_total_row(rows)
            if len(same) != 1:
                notes.append(f"{label}：同组同期间有 {len(same)} 列金额，分不出比例的分子")
            elif total is None:
                notes.append(f"{label}：表里没有唯一的合计行，比例没有分母")
            else:
                plans.append(RatioPlan(k.index - 1, "share", same[0].index - 1, None, total, label))
        elif _RATE_RE.search(leaf):
            period = [a for a in amounts if a.period == k.period]
            provisions = [a for a in period if _is_provision(a)]
            gross = [a for a in period if not _is_provision(a) and a.measure not in vocab.net_measures]
            if len(provisions) != 1 or len(gross) != 1:
                notes.append(f"{label}：同期间准备列 {len(provisions)} 列、账面余额列 {len(gross)} 列，认不准分子 / 分母")
            else:
                plans.append(RatioPlan(k.index - 1, "rate", provisions[0].index - 1, gross[0].index - 1, None, label))
        elif "占" in leaf:
            notes.append(f"{label}：分母不在本表（占某科目合计的比例），不自动计算")
    return plans, notes


def ratio_rows(rows: list[Any]) -> list[int]:
    """参与比例派生的行：明细 / 「其中：X」/ 合计 / 小计（标题、标记、减项、占位行不算）。"""
    from app.services.note_total_terms import row_kind

    return [i for i, r in enumerate(rows) if row_kind(r) in ("data", "sub", "total", "subtotal")]


def derive_ratio(plan: RatioPlan, row: int, read: Callable[[int, int], Decimal | None]) -> Decimal | None:
    """按计划算一格：``read(行, values 列)``；分子空 / 分母空或为 0 ⇒ None（不写）。"""
    numerator = read(row, plan.numerator)
    if numerator is None:
        return None
    denominator = read(plan.total_row, plan.numerator) if plan.kind == "share" else read(row, plan.denominator)
    if denominator is None or denominator == 0:
        return None
    return numerator / denominator * _HUNDRED


def expression(plan: RatioPlan, row: int) -> str:
    """单体预设公式的表达式（``note_formula_tables.evaluate`` 语法）。"""
    if plan.kind == "share":
        return f"cell({row},{plan.numerator}) / cell({plan.total_row},{plan.numerator}) * 100"
    return f"cell({row},{plan.numerator}) / cell({row},{plan.denominator}) * 100"
