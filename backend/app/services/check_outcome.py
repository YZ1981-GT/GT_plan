"""S2 ADR-CCN-01：校对结果五态契约

XR、表间审核、附注校对类公式三个执行器的结果统一转为 CheckOutcome，
前端用同一组中文标签显示。

status 复用 phase14_enums.CheckStatus（与门禁五态同源）。
severity ∈ {blocking, warning, info}。
工厂函数：passed / failed / not_executed / not_applicable / error。

AST 约束：``passed(`` 不得在 ``except`` 块内调用（守卫同母 spec）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.phase14_enums import CheckStatus


# ── 中文标签 ──────────────────────────────────────────────────

STATUS_LABEL: dict[str, str] = {
    CheckStatus.passed: "通过",
    CheckStatus.failed: "未通过",
    CheckStatus.not_executed: "未执行（原因）",
    CheckStatus.not_applicable: "不适用",
    CheckStatus.error: "检查异常",
}


# ── 数据类 ────────────────────────────────────────────────────

@dataclass(frozen=True)
class CheckOutcome:
    """单条校对结果"""
    status: CheckStatus
    reason: str = ""
    left: float | None = None
    right: float | None = None
    diff: float | None = None
    severity: str = "info"  # blocking / warning / info
    rule_id: str = ""
    source: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "status": self.status,
            "label": self.label,
            "reason": self.reason,
            "severity": self.severity,
            "rule_id": self.rule_id,
            "source": self.source,
        }
        if self.left is not None:
            d["left"] = self.left
        if self.right is not None:
            d["right"] = self.right
        if self.diff is not None:
            d["diff"] = self.diff
        if self.extra:
            d["extra"] = self.extra
        return d


# ── 工厂函数 ──────────────────────────────────────────────────

def passed(
    rule_id: str = "",
    source: str = "",
    *,
    reason: str = "",
    severity: str = "info",
    **kw: Any,
) -> CheckOutcome:
    """构造「通过」结果。"""
    return CheckOutcome(
        status=CheckStatus.passed,
        reason=reason,
        severity=severity,
        rule_id=rule_id,
        source=source,
        **kw,
    )


def failed(
    rule_id: str = "",
    source: str = "",
    *,
    reason: str = "",
    left: float | None = None,
    right: float | None = None,
    diff: float | None = None,
    severity: str = "warning",
    **kw: Any,
) -> CheckOutcome:
    """构造「未通过」结果。"""
    return CheckOutcome(
        status=CheckStatus.failed,
        reason=reason,
        left=left,
        right=right,
        diff=diff,
        severity=severity,
        rule_id=rule_id,
        source=source,
        **kw,
    )


def not_executed(
    rule_id: str = "",
    source: str = "",
    *,
    reason: str = "",
    severity: str = "warning",
    **kw: Any,
) -> CheckOutcome:
    """构造「未执行」结果。"""
    return CheckOutcome(
        status=CheckStatus.not_executed,
        reason=reason,
        severity=severity,
        rule_id=rule_id,
        source=source,
        **kw,
    )


def not_applicable(
    rule_id: str = "",
    source: str = "",
    *,
    reason: str = "",
    severity: str = "info",
    **kw: Any,
) -> CheckOutcome:
    """构造「不适用」结果。"""
    return CheckOutcome(
        status=CheckStatus.not_applicable,
        reason=reason,
        severity=severity,
        rule_id=rule_id,
        source=source,
        **kw,
    )


def error(
    rule_id: str = "",
    source: str = "",
    *,
    reason: str = "",
    severity: str = "warning",
    **kw: Any,
) -> CheckOutcome:
    """构造「检查异常」结果。"""
    return CheckOutcome(
        status=CheckStatus.error,
        reason=reason,
        severity=severity,
        rule_id=rule_id,
        source=source,
        **kw,
    )
