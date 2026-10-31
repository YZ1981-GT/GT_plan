"""试算表取数的叶子口径（spec formula-hub-integrity-closure 需求 4.1~4.3，ADR-FHIC-03）。

取数点（报表 ``TB`` / ``SUM_TB``、``TrialBalanceResolver``、预载 ``_load_tb``、推送 ``load_tb_audited``、底稿严格轨）
先按前缀 / 区间取宽集合，再经 :func:`select_leaves` 只累加叶子行：集合内存在「以本码为前缀且更长的其他码」的行是
父行，不计入。原先按前缀全部相加，父子并存时父行金额（通常 = 下级之和）被算两遍（F8 / F9：医疗器械 2025 的
``1231`` 坏账准备双计 102,358,291.13）。

父行金额与其叶子合计差 > 0.005 时生成告警 ``{"code", "parent", "leaf_sum", "diff", "message"}``（``diff`` =
父行 − 叶子合计，金额为 ``Decimal``），经 :mod:`app.services.formula_warnings` 送到结果合并点。

判下级用标准科目码的**字符串前缀**（``1231`` → ``1231-01`` / ``123101``），与取数 SQL ``LIKE 'code%'`` 同一判据；
不复用 ``four_table/leaf_aggregation.select_leaves``：那边按 ``code + '.'`` 判子级，是 ``tb_balance`` 的口径。
同码多行（如多个 ``company_code``）互不为父子，全部计入；父行金额按同码合计比较。
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from operator import attrgetter
from typing import Any, Generic, TypeVar

from app.services.formula_warnings import emit

R = TypeVar("R")

#: 父行金额与叶子合计的容差（元）：差额绝对值 > 0.005 才告警
LEAF_DIFF_TOLERANCE = Decimal("0.005")
_CENT = Decimal("0.01")

#: ``trial_balance`` 行（ORM 对象或 Row）的标准科目码
standard_code_of: Callable[[Any], Any] = attrgetter("standard_account_code")


@dataclass(frozen=True)
class LeafSelection(Generic[R]):
    """叶子筛选结果：``rows`` = 叶子行（保持输入顺序），``total`` = 叶子金额合计，``warnings`` = 父子不符告警。"""

    rows: list[R]
    total: Decimal
    warnings: list[dict[str, Any]] = field(default_factory=list)


def _code(value: Any) -> str:
    return "" if value is None else str(value)


def _amount(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def leaf_code_set(codes: Iterable[Any]) -> frozenset[str]:
    """集合内不存在「以本码为前缀且更长的其他码」的码（同码重复只算一个）。

    字典序排序后，以 ``c`` 为前缀的码紧跟在 ``c`` 之后连续出现 ⇒ 只需看后继是否以 ``c`` 开头。
    """
    ordered = sorted({_code(c) for c in codes})
    successors = [*ordered[1:], None]
    return frozenset(c for c, nxt in zip(ordered, successors) if nxt is None or not nxt.startswith(c))


def format_amount(value: Decimal) -> str:
    """告警文案里的金额：四舍五入到分、千分位（``Decimal('10')`` → ``10.00``）。"""
    return format(value.quantize(_CENT, rounding=ROUND_HALF_UP), ",.2f")


def scope_for_year(year: Any) -> str:
    """告警文案的取数范围前缀；各取数点统一用它，同一父子不符在不同取数点得到同一文案（合并时去重）。"""
    return f"{year} 年度试算表"


def _message(scope: str, code: str, column: str | None, parent: Decimal, leaf_sum: Decimal, diff: Decimal) -> str:
    col = f"（{column}）" if column else ""
    return (
        f"{scope}科目 {code}{col}本级金额 {format_amount(parent)} 与下级科目合计 {format_amount(leaf_sum)} 不一致，"
        f"相差 {format_amount(diff)}；已按下级科目合计取数，本级金额未计入"
    )


def select_leaves(
    rows: Iterable[R],
    code_of: Callable[[R], Any],
    amount_of: Callable[[R], Any],
    *,
    column: str | None = None,
    scope: str = "试算表",
) -> LeafSelection[R]:
    """只保留叶子行并合计；父行金额与其叶子合计差 > 0.005 的给告警。

    ``code_of`` / ``amount_of`` 取每行的科目码 / 金额（``None`` 金额按 0）；``column``、``scope`` 只用于告警文案。
    """
    items = list(rows)
    codes = [_code(code_of(r)) for r in items]
    amounts = [_amount(amount_of(r)) for r in items]
    leaves = leaf_code_set(codes)
    picked = [r for r, c in zip(items, codes) if c in leaves]
    total = sum((a for a, c in zip(amounts, codes) if c in leaves), Decimal("0"))

    by_code: dict[str, Decimal] = {}
    for c, a in zip(codes, amounts):
        by_code[c] = by_code.get(c, Decimal("0")) + a
    leaf_amounts = [(c, by_code[c]) for c in sorted(leaves)]
    warnings: list[dict[str, Any]] = []
    for parent in sorted(set(by_code) - leaves):
        leaf_sum = sum((a for c, a in leaf_amounts if c.startswith(parent)), Decimal("0"))
        diff = by_code[parent] - leaf_sum
        if abs(diff) > LEAF_DIFF_TOLERANCE:
            warnings.append({
                "code": parent,
                "parent": by_code[parent],
                "leaf_sum": leaf_sum,
                "diff": diff,
                "message": _message(scope, parent, column, by_code[parent], leaf_sum, diff),
            })
    return LeafSelection(rows=picked, total=total, warnings=warnings)


def leaf_total(
    rows: Iterable[R],
    amount_of: Callable[[R], Any],
    *,
    column: str | None = None,
    scope: str = "试算表",
    code_of: Callable[[R], Any] = standard_code_of,
) -> Decimal:
    """取数点共用：叶子合计，并把父子不符告警 ``emit`` 给当前收集器（没有收集器时只记日志）。"""
    selection = select_leaves(rows, code_of, amount_of, column=column, scope=scope)
    emit(selection.warnings)
    return selection.total
