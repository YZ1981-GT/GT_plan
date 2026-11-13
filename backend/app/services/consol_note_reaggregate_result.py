"""合并附注重新汇总的结果模型与状态辅助。"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.services.consol_group_tree import KIND_AGGREGATE, KIND_ELIM

ACTION_PULL, ACTION_ELIM, ACTION_AGGREGATE = "pull", "elim", "aggregate"
_PERSISTED, _SKIPPED, _FAILED, _KEPT_MANUAL = "persisted", "skipped", "failed", "kept_manual"
_CENT = Decimal("0.01")


def _amount_key(value: Any) -> tuple[str, Any]:
    """按分比较金额；非金额文字保留规范化字符串。"""
    if value is None:
        return "text", ""
    text = str(value).strip()
    if not text:
        return "text", ""
    try:
        return "amount", Decimal(text.replace(",", "")).quantize(_CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return "text", text


@dataclass
class _Outcome:
    section_id: str
    node: Any
    action: str
    status: str
    reason: str | None = None
    pending: bool = False
    detail: dict[str, Any] = field(default_factory=dict)
    incomplete: bool = False

    def to_dict(self) -> dict[str, Any]:
        out = {
            "section_id": self.section_id,
            "node_key": self.node.node_key,
            "action": self.action,
            "status": self.status,
            "reason": self.reason,
        }
        out.update(self.detail)
        return out


@dataclass
class _NodeTally:
    node: Any
    action: str
    written: int = 0
    skipped: int = 0
    failed: int = 0
    reasons: Counter = field(default_factory=Counter)

    def add(self, outcome: _Outcome) -> None:
        if outcome.status == _PERSISTED:
            self.written += 1
        elif outcome.status == _FAILED:
            self.failed += 1
        else:
            self.skipped += 1
        if outcome.reason and outcome.status != _PERSISTED:
            self.reasons[outcome.reason] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_key": self.node.node_key,
            "kind": self.node.kind,
            "action": self.action,
            "label": _label(self.node),
            "written": self.written,
            "skipped": self.skipped,
            "failed": self.failed,
            "reasons": [{"reason": r, "count": n} for r, n in self.reasons.most_common()],
        }


def _label(node: Any) -> str:
    return node.display_name or node.company_name or node.node_key


def _action(node: Any) -> str:
    if node.kind == KIND_ELIM:
        return ACTION_ELIM
    if node.kind == KIND_AGGREGATE or node.children:
        return ACTION_AGGREGATE
    return ACTION_PULL
