"""Draft Refresh 结果聚合合同（spec formula-hub-integrity-closure ADR-FHIC-08；需求 3.2 / 3.3）。

纯数据结构与纯函数：不连库、不发事件、不 import 业务服务（编排器与服务层引用本模块不会成环）。

- :class:`ScopeOutcome`：一个刷新范围的产出 —— 金额变化数、仅重算数、Draft 标记数、失败清单、提交后待发事件；
- :data:`OUTCOME_TABLE` / :func:`derive_outcome`：按需求 3.2 状态表派生整体 ``outcome`` 与响应 ``status``。每行把条件
  写全（不靠行序），任一组合计恰命中一行；幂等命中不经此表，由调用方返回首次运行记录的 outcome +
  :data:`IDEMPOTENT_HIT_STATUS`；
- :func:`normalize_value` / :func:`values_equal` / :func:`split_unchanged`：Runtime 范围 before 与 after 规范化后相等的
  mutation 移出写入集合、计入「仅重算」。

计数口径（需求 3.3）：``applied_count`` = 金额变化数，``affected_count = applied_count + recomputed_count``，Draft 标记数
单列 ``draft_marked_count``、不计入 ``affected_count``。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Literal, TypeVar

if TYPE_CHECKING:
    from app.models.audit_platform_schemas import EventPayload

Outcome = Literal["applied", "recomputed", "draft_marked", "no_effect", "partial", "failed"]
ResponseStatus = Literal[
    "success", "recomputed", "draft_marked", "no_effect", "partial_success", "failed", "idempotent_hit",
]

TRANSACTION_MODES: tuple[str, ...] = ("all_or_nothing", "partial_success")
IDEMPOTENT_HIT_STATUS = "idempotent_hit"
_CENT = Decimal("0.01")
T = TypeVar("T")


@dataclass
class ScopeOutcome:
    """一个刷新范围（scope）的产出。计数为非负整数；``failures`` 每条记一个失败。"""

    scope: str
    value_changes: int = 0
    recomputed: int = 0
    draft_marked: int = 0
    failures: list[dict] = field(default_factory=list)
    post_commit_events: list[EventPayload] = field(default_factory=list)


@dataclass(frozen=True)
class OutcomeTotals:
    """全部范围的合计；``effective``（需求 3.2 的「有效」）= 金额变化 + 仅重算 + Draft 标记。"""

    value_changes: int = 0
    recomputed: int = 0
    draft_marked: int = 0
    failures: int = 0

    @property
    def effective(self) -> int:
        return self.value_changes + self.recomputed + self.draft_marked


def summarize(outcomes: Iterable[ScopeOutcome]) -> OutcomeTotals:
    """合计各范围计数。计数为负 ⇒ ValueError（计数都来自 ``len()``，负数只可能是调用方写错）。"""
    value_changes = recomputed = draft_marked = failures = 0
    for item in outcomes:
        counts = (item.value_changes, item.recomputed, item.draft_marked)
        if min(counts) < 0:
            raise ValueError(f"范围 {item.scope!r} 的计数不能为负：{counts}")
        value_changes += item.value_changes
        recomputed += item.recomputed
        draft_marked += item.draft_marked
        failures += len(item.failures)
    return OutcomeTotals(value_changes, recomputed, draft_marked, failures)


def effective_count(outcomes: Iterable[ScopeOutcome]) -> int:
    """「有效」数 = Σ（金额变化 + 仅重算 + Draft 标记）。"""
    return summarize(outcomes).effective


@dataclass(frozen=True)
class OutcomeRule:
    """需求 3.2 状态表的一行：``when(合计, 事务模式)`` 为真即命中；``condition`` 是需求原文条件。"""

    outcome: Outcome
    status: ResponseStatus
    condition: str
    when: Callable[[OutcomeTotals, str], bool]


#: 需求 3.2 状态表（「幂等命中」一行除外）。条件逐行写全、两两互斥、合起来完备 —— 不依赖行序。
OUTCOME_TABLE: tuple[OutcomeRule, ...] = (
    OutcomeRule("applied", "success", "金额变化 > 0，无失败",
                lambda t, mode: t.failures == 0 and t.value_changes > 0),
    OutcomeRule("recomputed", "recomputed", "金额变化 = 0、仅重算 > 0，无失败",
                lambda t, mode: t.failures == 0 and t.value_changes == 0 and t.recomputed > 0),
    OutcomeRule("draft_marked", "draft_marked", "金额变化 = 仅重算 = 0、draft 标记 > 0，无失败",
                lambda t, mode: (t.failures == 0 and t.value_changes == 0 and t.recomputed == 0
                                 and t.draft_marked > 0)),
    OutcomeRule("no_effect", "no_effect", "三者均为 0，无失败",
                lambda t, mode: t.failures == 0 and t.effective == 0),
    OutcomeRule("partial", "partial_success", "有失败且有效 > 0（partial_success 事务模式）",
                lambda t, mode: t.failures > 0 and t.effective > 0 and mode == "partial_success"),
    OutcomeRule("failed", "failed", "有失败且有效 = 0，或 all_or_nothing 模式下任一失败",
                lambda t, mode: t.failures > 0 and (t.effective == 0 or mode == "all_or_nothing")),
)
OUTCOMES: tuple[str, ...] = tuple(rule.outcome for rule in OUTCOME_TABLE)
#: 响应 ``status`` 全部取值 = 表里 6 个 + 幂等命中（与 ``DraftRefreshResponse.status`` 的 Literal 相等，有测试守着）
RESPONSE_STATUSES: tuple[str, ...] = (*(rule.status for rule in OUTCOME_TABLE), IDEMPOTENT_HIT_STATUS)


def derive_outcome(outcomes: Iterable[ScopeOutcome], transaction_mode: str) -> tuple[Outcome, ResponseStatus]:
    """按 :data:`OUTCOME_TABLE` 派生 ``(outcome, status)``。

    ``transaction_mode`` 只认 ``all_or_nothing`` / ``partial_success``（否则 ValueError）；命中行数 ≠ 1 说明表本身
    写错，抛 RuntimeError（不静默取第一行）。
    """
    if transaction_mode not in TRANSACTION_MODES:
        raise ValueError(f"未知事务模式 {transaction_mode!r}（只认 {TRANSACTION_MODES}）")
    totals = summarize(outcomes)
    matched = [rule for rule in OUTCOME_TABLE if rule.when(totals, transaction_mode)]
    if len(matched) != 1:
        raise RuntimeError(f"需求 3.2 状态表应恰命中 1 行，实际 {[rule.outcome for rule in matched]}：{totals}")
    return matched[0].outcome, matched[0].status


def normalize_value(value: Any) -> Any:
    """before / after 的规范形态（需求 3.2「规范化后 before≠after」）。

    - ``None`` 与空白字符串 ⇒ ``None``：二者在各写入方都表示「无值」、界面都显示为空。``None`` 不等于 ``0`` / ``"0"``
      —— 空格写成 0 是一次真实写入（从无值变成有值），按金额变化处理；
    - 数值（``Decimal`` / ``int`` / ``float``，``bool`` 除外）与去首尾空白后能解析为有限 ``Decimal`` 的字符串 ⇒
      ``ROUND_HALF_UP`` 量化到 0.01 的 ``Decimal``（``"1.00"`` 与 ``Decimal("1")`` 相等）。``float`` 先取 ``str()`` 的
      最短十进制写法，免得二进制误差改变半分进位（``1.005`` ⇒ ``1.01``）；量化结果超出默认精度（28 位）的极大值不量化、
      按原值精确比较；非有限数值（NaN / Infinity）⇒ ``("nonfinite", str(value))``；
    - 其余字符串 ⇒ 去首尾空白；``bool`` ⇒ ``("bool", value)``（不与 1 / 0 相等）；
    - 其他（dict / list 等结构化值）原样参与 ``==`` 比较、不深入规范化 —— 只有逐项相等才算未变，宁可多写一次。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (Decimal, int, float)):
        number = Decimal(str(value)) if isinstance(value, float) else Decimal(value)
        return _to_cents(number) if number.is_finite() else ("nonfinite", str(value))
    if isinstance(value, str):
        text = value.strip()
        try:
            number = Decimal(text)
        except InvalidOperation:
            return text
        return _to_cents(number) if number.is_finite() else text
    return value


def _to_cents(number: Decimal) -> Decimal:
    try:
        return number.quantize(_CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:  # 量化结果超出当前精度：不量化，按原值精确比较
        return number


def values_equal(before: Any, after: Any) -> bool:
    """规范化后是否相等（相等 = 计算成功但金额未变，计入「仅重算」）。"""
    return normalize_value(before) == normalize_value(after)


def split_unchanged(
    items: Iterable[T],
    *,
    before_of: Callable[[T], Any] = attrgetter("before_value"),
    after_of: Callable[[T], Any] = attrgetter("after_value"),
) -> tuple[list[T], list[T]]:
    """把 mutation 分成 ``(待写入, 仅重算)``：before / after 规范化后相等的进后者，不下发写入方。

    默认取 ``FormulaMutation.before_value`` / ``after_value``；两组都保持输入顺序，合起来恰是输入（不丢不重）。
    """
    to_write: list[T] = []
    unchanged: list[T] = []
    for item in items:
        (unchanged if values_equal(before_of(item), after_of(item)) else to_write).append(item)
    return to_write, unchanged
