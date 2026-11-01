"""AI 复核建议与业务复核状态的边界。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


class AIReviewStatus(str, Enum):
    ai_no_new_findings = "ai_no_new_findings"
    ai_findings_present = "ai_findings_present"
    manual_review_required = "manual_review_required"
    deterministic_failure = "deterministic_failure"


@dataclass(frozen=True)
class AIReviewVerdict:
    status: AIReviewStatus
    business_pass: bool
    reason: str


def resolve_ai_review_verdict(
    *,
    parse_success: bool,
    findings: Iterable[Any],
    deterministic_blocking_failures: int = 0,
    human_confirmed: bool = False,
) -> AIReviewVerdict:
    """AI 只能增加疑点；没有人工确认时不能产生业务 ``pass``。"""
    rows = list(findings)
    if deterministic_blocking_failures > 0:
        return AIReviewVerdict(
            AIReviewStatus.deterministic_failure,
            False,
            "系统确定性检查存在阻断差异",
        )
    if not parse_success or any(
        str(getattr(row, "risk_level", "unknown")) == "unknown" for row in rows
    ):
        return AIReviewVerdict(
            AIReviewStatus.manual_review_required,
            False,
            "AI 输出无法可靠解析或包含未知风险项",
        )
    if any(not bool(getattr(row, "pass_status", False)) for row in rows):
        return AIReviewVerdict(
            AIReviewStatus.ai_findings_present,
            False,
            "AI 提出了待人工核实的疑点",
        )
    return AIReviewVerdict(
        AIReviewStatus.ai_no_new_findings,
        bool(human_confirmed),
        "AI 未发现新增疑点；仍需审计人员完成复核",
    )
