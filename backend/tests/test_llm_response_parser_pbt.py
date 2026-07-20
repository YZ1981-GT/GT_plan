"""Property-Based Tests for LlmResponseParser

Property 5: Pass/fail determination correctness
Property 12: Parse degradation safety

Validates: Requirements 8.3, 8.4
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st

from app.services.llm_response_parser import (
    LlmResponseParser,
    ParseResult,
    ReviewFinding,
)


# ─── Strategies ─────────────────────────────────────────────────────────────

_RISK_LEVELS = st.sampled_from(["high", "medium", "low", "unknown"])

_finding_strategy = st.builds(
    ReviewFinding,
    id=st.uuids().map(str),
    description=st.text(min_size=1, max_size=100),
    risk_level=_RISK_LEVELS,
    pass_status=st.booleans(),
    category=st.sampled_from(
        ["认定检查", "程序执行", "数据完整性", "风险评估", "general"]
    ),
    sheet_location=st.none() | st.text(min_size=1, max_size=50),
    suggestion=st.none() | st.text(min_size=1, max_size=100),
)

_findings_list = st.lists(_finding_strategy, min_size=0, max_size=20)

# Strategy for raw text inputs to parse: empty, garbage, unicode, structured markdown
_raw_text_strategy = st.one_of(
    st.just(""),  # empty
    st.text(min_size=0, max_size=500),  # arbitrary text including unicode
    # Well-formed markdown with checklist items
    st.builds(
        lambda sections: "\n".join(sections),
        sections=st.lists(
            st.one_of(
                st.just("## 高风险检查项"),
                st.just("## 中风险检查项"),
                st.just("## 低风险检查项"),
                st.text(min_size=1, max_size=80).map(lambda t: f"- [ ] {t}"),
                st.text(min_size=1, max_size=80).map(lambda t: f"- [x] {t}"),
                st.text(min_size=0, max_size=100),
            ),
            min_size=0,
            max_size=20,
        ),
    ),
)


# ─── Property 5: Pass/fail determination correctness ────────────────────────


class TestPassFailDetermination:
    """**Validates: Requirements 8.3**

    For any set of ReviewFinding objects, pass_status = "pass" iff
    count(high-risk && not pass_status) == 0 AND
    count(medium-risk && not pass_status) < 3.
    """

    @given(findings=_findings_list)
    @settings(max_examples=5)
    def test_p5_pass_fail_determination_correctness(
        self, findings: list[ReviewFinding]
    ) -> None:
        """Property 5: Pass/fail determination correctness"""
        result = LlmResponseParser.determine_pass_status(findings)

        # Compute expected result from first principles
        high_count = sum(
            1
            for f in findings
            if f.risk_level == "high" and not f.pass_status
        )
        medium_count = sum(
            1
            for f in findings
            if f.risk_level == "medium" and not f.pass_status
        )

        expected = "pass" if (high_count == 0 and medium_count < 3) else "fail"

        assert result == expected, (
            f"determine_pass_status returned '{result}' but expected '{expected}' "
            f"(high_count={high_count}, medium_count={medium_count}, "
            f"findings_count={len(findings)})"
        )


# ─── Property 12: Parse degradation safety ──────────────────────────────────


class TestParseDegradationSafety:
    """**Validates: Requirements 8.4**

    For any raw string (including empty, garbage, or well-formed),
    LlmResponseParser.parse() returns a ParseResult with at least one finding,
    never raising an exception.
    """

    @given(raw_text=_raw_text_strategy)
    @settings(max_examples=5)
    def test_p12_parse_degradation_safety(self, raw_text: str) -> None:
        """Property 12: Parse degradation safety"""
        # Must never raise
        result = LlmResponseParser.parse(raw_text)

        # Must return a ParseResult
        assert isinstance(result, ParseResult), (
            f"Expected ParseResult, got {type(result)}"
        )

        # Must have at least one finding
        assert len(result.findings) >= 1, (
            f"ParseResult must have at least one finding, got 0 "
            f"for input: {repr(raw_text[:100])}"
        )

        # Each finding must be a ReviewFinding with valid risk_level
        for finding in result.findings:
            assert isinstance(finding, ReviewFinding)
            assert finding.risk_level in {"high", "medium", "low", "unknown"}
            assert isinstance(finding.pass_status, bool)
            assert isinstance(finding.description, str)
            assert len(finding.description) > 0
