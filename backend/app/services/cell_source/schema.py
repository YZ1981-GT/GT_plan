"""单元格来源（悬浮溯源卡片）的统一结构（spec citar-cell-source-hover design §2）。

一律用普通 dict，金额是字符串（Decimal 文本）。构造只经本模块的函数，保证各表同一形状：
- ``item``：构成明细一项；``sign`` 是系数（+1 / −1 / 常数），0 = 只列出、不参与合计（如「未计入本格的调整」）
- ``source``：一格的来源；``linear`` 时算 ``total = Σ sign × amount``，与 ``value`` 差额 ≥ 0.005 才给 ``diff``
- ``link``：跳转目标，只给语义（页 + 编码 / 格子），路由换算在前端 ``sourceLink``
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

MAX_ITEMS = 20
_CENT = Decimal("0.005")

#: 来源类型（前端按它显示标签）
KINDS = frozenset({
    "rule", "formula", "manual", "import", "derived", "synthetic", "preset", "param", "adjustment", "none",
})
#: 跳转目标页
PAGES = frozenset({
    "balance", "journal", "mapping", "trial_balance", "adjustments", "reports", "statement",
    "workpaper", "tax_return", "ledger_import",
})


def to_decimal(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def money(v: Any) -> str | None:
    """金额 → 字符串（去掉多余的尾零，保留到分以内的原值）；非数字原样转字符串，None 为 None。"""
    d = to_decimal(v)
    if d is None:
        return None if v is None else str(v)
    q = d.quantize(Decimal("0.0000000001")) if d.as_tuple().exponent < -10 else d
    text = format(q.normalize(), "f")
    return "0" if text in ("-0", "") else text


def link(page: str, **kw: Any) -> dict:
    if page not in PAGES:
        raise ValueError(f"未登记的跳转页 {page!r}")
    return {"page": page, **{k: v for k, v in kw.items() if v is not None}}


def item(label: str, amount: Any = None, *, sign: Any = 1, detail: str | None = None, link_to: dict | None = None) -> dict:
    return {"label": label, "detail": detail, "amount": money(amount), "sign": money(sign), "link": link_to}


def source(
    kind: str,
    title: str,
    value: Any = None,
    items: list[dict] | None = None,
    *,
    linear: bool = False,
    notes: list[str] | None = None,
    issue: str | None = None,
    manual: dict | None = None,
    rule_text: str | None = None,
) -> dict:
    """一格的来源。``linear`` 时按全部项（截断前）算合计与差额。"""
    if kind not in KINDS:
        raise ValueError(f"未登记的来源类型 {kind!r}")
    items = list(items or [])
    total = diff = None
    if linear:
        acc = Decimal(0)
        for it in items:
            amount, sign = to_decimal(it["amount"]), to_decimal(it["sign"])
            if amount is not None and sign:
                acc += amount * sign
        total = money(acc)
        v = to_decimal(value)
        gap = acc - (v if v is not None else Decimal(0))
        if abs(gap) >= _CENT:
            diff = money(gap)
    more = max(0, len(items) - MAX_ITEMS)
    if more:
        items = sorted(items, key=lambda it: abs(to_decimal(it["amount"]) or Decimal(0)), reverse=True)[:MAX_ITEMS]
    return {
        "kind": kind, "title": title, "value": money(value), "items": items, "more": more,
        "linear": linear, "total": total, "diff": diff, "notes": list(notes or []), "issue": issue,
        "manual": manual, "rule_text": rule_text,
    }
