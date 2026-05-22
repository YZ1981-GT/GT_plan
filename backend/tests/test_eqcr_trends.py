"""Tests for EQCR Trends API — Phase 7 F3

Tests:
- Response schema validation
- Pass rate calculation logic
- Top 5 sorting logic
- Empty data returns empty lists
"""

import pytest

from app.routers.eqcr_trends import (
    YearTrend,
    TopIssueCategory,
    EqcrTrendResponse,
)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestEqcrTrendSchema:
    """Test Pydantic schemas for EQCR trends."""

    def test_year_trend_schema(self):
        """YearTrend schema validation."""
        trend = YearTrend(
            year=2025,
            pass_rate=85.5,
            avg_review_days=7.2,
            total_projects=20,
        )
        assert trend.year == 2025
        assert trend.pass_rate == 85.5
        assert trend.avg_review_days == 7.2
        assert trend.total_projects == 20

    def test_top_issue_category_schema(self):
        """TopIssueCategory schema validation."""
        issue = TopIssueCategory(category="data_mismatch", count=15)
        assert issue.category == "data_mismatch"
        assert issue.count == 15

    def test_trend_response_with_warnings(self):
        """EqcrTrendResponse with warnings."""
        response = EqcrTrendResponse(
            yearly_trends=[],
            top_issues=[],
            warnings=["查询超时"],
        )
        assert response.warnings == ["查询超时"]

    def test_trend_response_empty(self):
        """Empty data returns empty lists."""
        response = EqcrTrendResponse(
            yearly_trends=[],
            top_issues=[],
        )
        assert response.yearly_trends == []
        assert response.top_issues == []
        assert response.warnings == []


class TestPassRateCalculation:
    """Test pass rate calculation logic."""

    def test_all_passed(self):
        """All projects passed → 100%."""
        total = 10
        passed = 10
        rate = round((passed / total) * 100, 1)
        assert rate == 100.0

    def test_none_passed(self):
        """No projects passed → 0%."""
        total = 10
        passed = 0
        rate = round((passed / total) * 100, 1)
        assert rate == 0.0

    def test_partial_pass(self):
        """Partial pass → correct percentage."""
        total = 20
        passed = 17
        rate = round((passed / total) * 100, 1)
        assert rate == 85.0

    def test_zero_total(self):
        """Zero total projects → 0% (no division by zero)."""
        total = 0
        passed = 0
        rate = round((passed / max(total, 1)) * 100, 1)
        assert rate == 0.0


class TestTopIssuesSorting:
    """Test Top 5 issues sorting logic."""

    def test_top_5_sorted_desc(self):
        """Top 5 sorted by count descending."""
        issues = [
            {"category": "a", "count": 5},
            {"category": "b", "count": 15},
            {"category": "c", "count": 10},
            {"category": "d", "count": 3},
            {"category": "e", "count": 20},
            {"category": "f", "count": 8},
        ]
        sorted_issues = sorted(issues, key=lambda x: x["count"], reverse=True)[:5]
        assert sorted_issues[0]["category"] == "e"
        assert sorted_issues[0]["count"] == 20
        assert sorted_issues[-1]["category"] == "a"
        assert len(sorted_issues) == 5

    def test_less_than_5_categories(self):
        """Less than 5 categories → return all."""
        issues = [
            {"category": "a", "count": 5},
            {"category": "b", "count": 3},
        ]
        sorted_issues = sorted(issues, key=lambda x: x["count"], reverse=True)[:5]
        assert len(sorted_issues) == 2
