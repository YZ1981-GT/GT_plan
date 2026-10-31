"""一致性门控 — 试算平衡口径识别（ADR-FHIC-15）。

纯函数 :func:`balance_diff`：五类叶子合计 → 口径判定 → 差额计算。
被 ``_impl.py::check_tb_balance`` 调用。

口径：
- 负债合计 < 0 → ``debit_positive``（借正贷负）
- 负债合计 > 0 → ``v2_positive``（v2 正数口径）
- 负债 = 0 按权益同规则判
- 两者都 = 0 → 口径无法识别

差额：
- ``debit_positive`` → 五类之和（附告警）
- ``v2_positive`` → asset − liability − equity − (revenue − expense)

资不抵债（v2 下权益 < 0、负债 > 0）按负债符号仍判 v2。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

_CENT = Decimal("0.01")

Convention = Literal["debit_positive", "v2_positive"]

#: 五类叶子合计必须恰好是这五个键
EXPECTED_CATEGORIES: frozenset[str] = frozenset({
    "asset", "liability", "equity", "revenue", "expense",
})


@dataclass(frozen=True, slots=True)
class BalanceVerdict:
    """试算平衡判定结果"""
    diff: Decimal
    convention: Convention | None
    warning: str  # 非空 = 口径告警


def _fmt(v: Decimal) -> str:
    return format(v.quantize(_CENT, rounding=ROUND_HALF_UP), ",.2f")


def balance_diff(sums: dict[str, Decimal]) -> BalanceVerdict:
    """五类叶子合计 → BalanceVerdict。

    Parameters
    ----------
    sums : dict
        键 = ``asset / liability / equity / revenue / expense``，
        值 = 该类所有叶子行的 ``audited_amount`` 合计。

    Returns
    -------
    BalanceVerdict
        ``convention=None`` 表示口径无法识别（两者都为 0）。
    """
    asset = sums.get("asset", Decimal("0"))
    liability = sums.get("liability", Decimal("0"))
    equity = sums.get("equity", Decimal("0"))
    revenue = sums.get("revenue", Decimal("0"))
    expense = sums.get("expense", Decimal("0"))

    # ---------- 口径识别 ----------
    convention = _detect_convention(liability, equity)
    if convention is None:
        return BalanceVerdict(
            diff=Decimal("0"),
            convention=None,
            warning="负债与权益合计均为 0，无法识别试算表口径",
        )

    # ---------- 差额计算 ----------
    if convention == "debit_positive":
        diff = asset + liability + equity + revenue + expense
        warning = "试算表为借正贷负口径"
    else:
        # v2 正数口径：asset − liability − equity − (revenue − expense)
        diff = asset - liability - equity - (revenue - expense)
        warning = ""

    return BalanceVerdict(diff=diff, convention=convention, warning=warning)


def _detect_convention(
    liability: Decimal, equity: Decimal,
) -> Convention | None:
    """按负债 → 权益顺序推断口径。"""
    if liability < 0:
        return "debit_positive"
    if liability > 0:
        return "v2_positive"
    # liability == 0 → 按权益判
    if equity < 0:
        return "debit_positive"
    if equity > 0:
        return "v2_positive"
    return None
