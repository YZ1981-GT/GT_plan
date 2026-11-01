"""AI 复核不能独立产生业务通过。"""

from types import SimpleNamespace

import pytest

from app.services.ai_review_verdict import AIReviewStatus, resolve_ai_review_verdict
from app.services.llm_response_parser import LlmResponseParser


def _finding(*, passed=True, risk="low"):
    return SimpleNamespace(pass_status=passed, risk_level=risk)


def test_schema_valid_empty_findings_means_no_new_findings_not_pass() -> None:
    parsed = LlmResponseParser.parse('{"findings": []}')
    assert parsed.parse_success is True
    verdict = resolve_ai_review_verdict(
        parse_success=parsed.parse_success, findings=parsed.findings
    )
    assert verdict.status is AIReviewStatus.ai_no_new_findings
    assert verdict.business_pass is False


@pytest.mark.parametrize(
    ("parse_success", "rows", "expected"),
    [
        (False, [_finding(passed=False, risk="unknown")], AIReviewStatus.manual_review_required),
        (True, [_finding(passed=False, risk="unknown")], AIReviewStatus.manual_review_required),
        (True, [_finding(passed=False, risk="medium")], AIReviewStatus.ai_findings_present),
        (True, [_finding(passed=True, risk="low")], AIReviewStatus.ai_no_new_findings),
    ],
)
def test_ai_verdict_statuses_never_create_business_pass(parse_success, rows, expected) -> None:
    verdict = resolve_ai_review_verdict(
        parse_success=parse_success, findings=rows
    )
    assert verdict.status is expected
    assert verdict.business_pass is False


def test_deterministic_failure_overrides_ai_clean_answer() -> None:
    verdict = resolve_ai_review_verdict(
        parse_success=True,
        findings=[],
        deterministic_blocking_failures=1,
        human_confirmed=True,
    )
    assert verdict.status is AIReviewStatus.deterministic_failure
    assert verdict.business_pass is False


def test_human_confirmation_only_applies_after_clean_machine_state() -> None:
    verdict = resolve_ai_review_verdict(
        parse_success=True, findings=[], human_confirmed=True
    )
    assert verdict.status is AIReviewStatus.ai_no_new_findings
    assert verdict.business_pass is True
