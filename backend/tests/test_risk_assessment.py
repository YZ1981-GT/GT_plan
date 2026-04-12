"""Unit tests for risk assessment service — combined risk matrix and coverage.

Validates: Requirements 11.6, 11.7, 11.10
"""

import pytest
from unittest.mock import MagicMock
from app.services.risk_service import (
    RiskAssessmentService,
    RISK_MATRIX,
)


# ---------------------------------------------------------------------------
# Combined risk matrix tests (all 9 combinations)
# ---------------------------------------------------------------------------

class TestCombinedRiskCalculation:
    """Test combined risk calculation for all 9 matrix combinations."""

    def test_high_x_high_equals_high(self):
        result = RiskAssessmentService.calculate_combined_risk("HIGH", "HIGH")
        assert result == "high"

    def test_high_x_medium_equals_medium(self):
        result = RiskAssessmentService.calculate_combined_risk("HIGH", "MEDIUM")
        assert result == "medium"

    def test_high_x_low_equals_medium(self):
        result = RiskAssessmentService.calculate_combined_risk("HIGH", "LOW")
        assert result == "medium"

    def test_medium_x_high_equals_medium(self):
        result = RiskAssessmentService.calculate_combined_risk("MEDIUM", "HIGH")
        assert result == "medium"

    def test_medium_x_medium_equals_medium(self):
        result = RiskAssessmentService.calculate_combined_risk("MEDIUM", "MEDIUM")
        assert result == "medium"

    def test_medium_x_low_equals_low(self):
        result = RiskAssessmentService.calculate_combined_risk("MEDIUM", "LOW")
        assert result == "low"

    def test_low_x_high_equals_low(self):
        result = RiskAssessmentService.calculate_combined_risk("LOW", "HIGH")
        assert result == "low"

    def test_low_x_medium_equals_low(self):
        result = RiskAssessmentService.calculate_combined_risk("LOW", "MEDIUM")
        assert result == "low"

    def test_low_x_low_equals_low(self):
        result = RiskAssessmentService.calculate_combined_risk("LOW", "LOW")
        assert result == "low"

    def test_case_insensitive(self):
        assert RiskAssessmentService.calculate_combined_risk("High", "high") == "high"
        assert RiskAssessmentService.calculate_combined_risk("medium", "Medium") == "medium"

    def test_risk_matrix_completeness(self):
        """Verify all 9 combinations are defined in the matrix."""
        expected_combinations = 9
        assert len(RISK_MATRIX) == expected_combinations


# ---------------------------------------------------------------------------
# Significant risk must have response strategy tests
# ---------------------------------------------------------------------------

class TestSignificantRiskValidation:
    """Test that significant risks must have a response strategy."""

    def test_significant_risk_requires_strategy(self):
        db = MagicMock()
        with pytest.raises(ValueError, match="Significant risks must have a response strategy"):
            RiskAssessmentService.create_assessment(
                db=db,
                project_id="proj-1",
                account_or_cycle="Revenue",
                assertion_level="existence",
                inherent_risk="high",
                control_risk="high",
                is_significant_risk=True,
                response_strategy=None,  # Missing strategy
            )

    def test_significant_risk_with_strategy_succeeds(self):
        db = MagicMock()
        result = RiskAssessmentService.create_assessment(
            db=db,
            project_id="proj-1",
            account_or_cycle="Revenue",
            assertion_level="existence",
            inherent_risk="high",
            control_risk="high",
            is_significant_risk=True,
            response_strategy="Perform detailed analytical procedures",
        )
        assert result["is_significant_risk"] is True
        assert result["response_strategy"] == "Perform detailed analytical procedures"

    def test_non_significant_risk_no_strategy_required(self):
        db = MagicMock()
        result = RiskAssessmentService.create_assessment(
            db=db,
            project_id="proj-1",
            account_or_cycle="Fixed Assets",
            assertion_level="existence",
            inherent_risk="low",
            control_risk="low",
            is_significant_risk=False,
            response_strategy=None,
        )
        assert result["is_significant_risk"] is False


# ---------------------------------------------------------------------------
# Risk-program coverage matrix tests
# ---------------------------------------------------------------------------

class TestRiskProgramCoverage:
    """Test risk-program coverage matrix completeness."""

    def test_all_risks_covered(self):
        db = MagicMock()
        assessments = [
            {"id": "risk-1", "combined_risk": "high"},
            {"id": "risk-2", "combined_risk": "medium"},
        ]
        procedures = [
            {"id": "proc-1", "related_risk_id": "risk-1"},
            {"id": "proc-2", "related_risk_id": "risk-2"},
        ]

        result = RiskAssessmentService.verify_risk_program_coverage(
            db=db,
            project_id="proj-1",
            assessments=assessments,
            procedures=procedures,
        )
        assert result["total_risks"] == 2
        assert result["covered_risks"] == 2
        assert result["uncovered_risks"] == 0
        assert result["is_complete"] is True

    def test_uncovered_risk(self):
        db = MagicMock()
        assessments = [
            {"id": "risk-1", "combined_risk": "high"},
            {"id": "risk-2", "combined_risk": "high"},
        ]
        procedures = [
            {"id": "proc-1", "related_risk_id": "risk-1"},
            # risk-2 has no procedure
        ]

        result = RiskAssessmentService.verify_risk_program_coverage(
            db=db,
            project_id="proj-1",
            assessments=assessments,
            procedures=procedures,
        )
        assert result["total_risks"] == 2
        assert result["covered_risks"] == 1
        assert result["uncovered_risks"] == 1
        assert result["is_complete"] is False
        assert "risk-2" in result["uncovered_risk_ids"]

    def test_multiple_procedures_per_risk(self):
        db = MagicMock()
        assessments = [
            {"id": "risk-1", "combined_risk": "high"},
        ]
        procedures = [
            {"id": "proc-1", "related_risk_id": "risk-1"},
            {"id": "proc-2", "related_risk_id": "risk-1"},
            {"id": "proc-3", "related_risk_id": "risk-1"},
        ]

        result = RiskAssessmentService.verify_risk_program_coverage(
            db=db,
            project_id="proj-1",
            assessments=assessments,
            procedures=procedures,
        )
        assert result["covered_risks"] == 1
        assert result["is_complete"] is True

    def test_empty_assessments(self):
        db = MagicMock()
        result = RiskAssessmentService.verify_risk_program_coverage(
            db=db,
            project_id="proj-1",
            assessments=[],
            procedures=[],
        )
        assert result["total_risks"] == 0
        assert result["is_complete"] is True


# ---------------------------------------------------------------------------
# Overall risk calculation tests
# ---------------------------------------------------------------------------

class TestOverallRiskCalculation:
    """Test aggregation of risk levels to overall project risk."""

    def test_all_high_risks_high_overall(self):
        db = MagicMock()
        assessments = [
            {"combined_risk": "high", "is_significant_risk": True},
            {"combined_risk": "high", "is_significant_risk": True},
            {"combined_risk": "high", "is_significant_risk": False},
        ]

        result = RiskAssessmentService.calculate_overall_risk(
            db=db,
            project_id="proj-1",
            assessments=assessments,
        )
        assert result["overall_risk"] == "high"
        assert result["significant_risks"] == 2
        assert result["total_risks"] == 3

    def test_all_low_risks_low_overall(self):
        db = MagicMock()
        assessments = [
            {"combined_risk": "low", "is_significant_risk": False},
            {"combined_risk": "low", "is_significant_risk": False},
        ]

        result = RiskAssessmentService.calculate_overall_risk(
            db=db,
            project_id="proj-1",
            assessments=assessments,
        )
        assert result["overall_risk"] == "low"

    def test_mixed_risks_medium_overall(self):
        db = MagicMock()
        assessments = [
            {"combined_risk": "high", "is_significant_risk": True},
            {"combined_risk": "low", "is_significant_risk": False},
            {"combined_risk": "low", "is_significant_risk": False},
        ]

        result = RiskAssessmentService.calculate_overall_risk(
            db=db,
            project_id="proj-1",
            assessments=assessments,
        )
        # (3+1+1)/3 = 1.67 → medium
        assert result["overall_risk"] == "medium"

    def test_empty_assessments_low_overall(self):
        db = MagicMock()
        result = RiskAssessmentService.calculate_overall_risk(
            db=db,
            project_id="proj-1",
            assessments=[],
        )
        assert result["overall_risk"] == "low"


# ---------------------------------------------------------------------------
# Risk matrix heatmap tests
# ---------------------------------------------------------------------------

class TestRiskMatrixHeatmap:
    """Test risk matrix heatmap generation."""

    def test_matrix_structure(self):
        assessments = [
            {"inherent_risk": "high", "control_risk": "high"},
            {"inherent_risk": "high", "control_risk": "medium"},
            {"inherent_risk": "low", "control_risk": "low"},
        ]

        result = RiskAssessmentService.get_risk_matrix("proj-1", assessments)
        assert "matrix" in result
        assert "colors" in result
        assert "legend" in result
        assert result["matrix"]["high"]["high"]  # Has entries
        assert result["colors"]["high"] == "#F56C6C"

    def test_matrix_counts(self):
        assessments = [
            {"inherent_risk": "high", "control_risk": "high"},
            {"inherent_risk": "high", "control_risk": "high"},
            {"inherent_risk": "medium", "control_risk": "low"},
        ]

        result = RiskAssessmentService.get_risk_matrix("proj-1", assessments)
        assert len(result["matrix"]["high"]["high"]) == 2
        assert len(result["matrix"]["medium"]["low"]) == 1
