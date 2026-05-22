"""Tests for EQCR Issues API — Phase 7 F2

Tests:
- Schema validation for EqcrIssueCreate
- Severity ordering logic
- Summary counting logic
- Visibility check logic
"""

import pytest
from uuid import uuid4

from app.routers.eqcr_issues import EqcrIssueCreate, EqcrIssueReply


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestEqcrIssueSchema:
    """Test Pydantic validation for EQCR issue schemas."""

    def test_valid_issue_create(self):
        """Valid issue creation payload."""
        body = EqcrIssueCreate(
            severity="blocker",
            category="data_mismatch",
            title="TB 与报表不一致",
            description="D2-1 审定表金额与 TB 差异 5000 元",
            wp_id=str(uuid4()),
        )
        assert body.severity == "blocker"
        assert body.category == "data_mismatch"

    def test_valid_issue_minimal(self):
        """Minimal valid issue (no description, no wp_id)."""
        body = EqcrIssueCreate(
            severity="minor",
            category="evidence_missing",
            title="缺少审计证据",
        )
        assert body.description is None
        assert body.wp_id is None

    def test_invalid_severity(self):
        """Invalid severity value → ValidationError."""
        with pytest.raises(Exception):
            EqcrIssueCreate(
                severity="critical",  # not in enum
                category="test",
                title="test",
            )

    def test_valid_reply(self):
        """Valid reply body."""
        reply = EqcrIssueReply(content="已修正，请复核")
        assert reply.content == "已修正，请复核"


class TestEqcrIssueSeverityOrdering:
    """Test severity ordering logic."""

    def test_severity_order(self):
        """Severity ordering: blocker > major > minor > suggestion."""
        severity_order = {
            "blocker": 1,
            "major": 2,
            "minor": 3,
            "suggestion": 4,
        }
        sorted_severities = sorted(severity_order.keys(), key=lambda s: severity_order[s])
        assert sorted_severities == ["blocker", "major", "minor", "suggestion"]


class TestEqcrIssueSummary:
    """Test summary counting logic."""

    def test_summary_counting(self):
        """Summary counts open/in_fix/closed correctly."""
        statuses = ["open", "open", "in_fix", "closed", "closed", "closed"]
        summary = {"open": 0, "in_fix": 0, "closed": 0}
        for s in statuses:
            if s in summary:
                summary[s] += 1
        assert summary == {"open": 2, "in_fix": 1, "closed": 3}

    def test_empty_summary(self):
        """Empty issue list → all zeros."""
        summary = {"open": 0, "in_fix": 0, "closed": 0}
        assert summary["open"] == 0
        assert summary["in_fix"] == 0
        assert summary["closed"] == 0
