"""Risk Assessment Service — risk identification, evaluation, and response strategy.

Validates: Requirements 11.1, 11.6, 11.7, 11.10
"""

from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import uuid


# ---------------------------------------------------------------------------
# Risk matrix: inherent_risk × control_risk → combined_risk
# ---------------------------------------------------------------------------
# HIGH × HIGH = HIGH
# HIGH × MEDIUM = MEDIUM
# HIGH × LOW = MEDIUM
# MEDIUM × HIGH = MEDIUM
# MEDIUM × MEDIUM = MEDIUM
# MEDIUM × LOW = LOW
# LOW × HIGH = LOW
# LOW × MEDIUM = LOW
# LOW × LOW = LOW

RISK_MATRIX: Dict[tuple[str, str], str] = {
    ("high", "high"): "high",
    ("high", "medium"): "medium",
    ("high", "low"): "medium",
    ("medium", "high"): "medium",
    ("medium", "medium"): "medium",
    ("medium", "low"): "low",
    ("low", "high"): "low",
    ("low", "medium"): "low",
    ("low", "low"): "low",
}


class RiskAssessmentService:
    @staticmethod
    def create_assessment(
        db: Session,
        project_id: str,
        account_or_cycle: str,
        assertion_level: str,
        inherent_risk: str,
        control_risk: str,
        risk_description: str = "",
        is_significant_risk: bool = False,
        response_strategy: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> dict:
        """Create risk assessment record and calculate combined risk."""
        # Calculate combined risk using risk matrix
        combined_risk = RiskAssessmentService.calculate_combined_risk(inherent_risk, control_risk)

        # Validate significant risk has response strategy
        if is_significant_risk and not response_strategy:
            raise ValueError("Significant risks must have a response strategy")

        assessment = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "account_or_cycle": account_or_cycle,
            "assertion_level": assertion_level,
            "inherent_risk": inherent_risk.lower(),
            "control_risk": control_risk.lower(),
            "combined_risk": combined_risk,
            "is_significant_risk": is_significant_risk,
            "risk_description": risk_description,
            "response_strategy": response_strategy,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return assessment

    @staticmethod
    def calculate_combined_risk(inherent_risk: str, control_risk: str) -> str:
        """Apply risk matrix to compute combined risk level."""
        ir = inherent_risk.lower()
        cr = control_risk.lower()
        return RISK_MATRIX.get((ir, cr), "medium")

    @staticmethod
    def assign_response_strategy(
        db: Session,
        assessment_id: str,
        strategy: str,
    ) -> dict:
        """Assign audit response strategy to significant risk."""
        # In production, would update the database record
        return {
            "id": assessment_id,
            "response_strategy": strategy,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def verify_risk_program_coverage(
        db: Session,
        project_id: str,
        procedures: List[dict],
        assessments: List[dict],
    ) -> dict:
        """Verify each risk has at least one procedure mapped."""
        # Build coverage map: risk_id → list of procedure_ids
        coverage: Dict[str, List[str]] = {}
        for proc in procedures:
            related_risk_id = proc.get("related_risk_id")
            if related_risk_id:
                if related_risk_id not in coverage:
                    coverage[related_risk_id] = []
                coverage[related_risk_id].append(proc.get("id", ""))

        uncovered_risks: List[str] = []
        covered_risks: List[str] = []

        for assessment in assessments:
            risk_id = assessment.get("id", "")
            if risk_id in coverage and len(coverage[risk_id]) > 0:
                covered_risks.append(risk_id)
            else:
                uncovered_risks.append(risk_id)

        return {
            "total_risks": len(assessments),
            "covered_risks": len(covered_risks),
            "uncovered_risks": len(uncovered_risks),
            "is_complete": len(uncovered_risks) == 0,
            "uncovered_risk_ids": uncovered_risks,
        }

    @staticmethod
    def calculate_overall_risk(
        db: Session,
        project_id: str,
        assessments: List[dict],
    ) -> dict:
        """Aggregate risk levels to compute overall project risk."""
        if not assessments:
            return {"overall_risk": "low", "significant_risks": 0, "total_risks": 0}

        risk_weights = {"high": 3, "medium": 2, "low": 1}
        total_score = sum(
            risk_weights.get(a.get("combined_risk", "low"), 2)
            for a in assessments
        )
        avg_score = total_score / len(assessments)

        if avg_score >= 2.5:
            overall = "high"
        elif avg_score >= 1.5:
            overall = "medium"
        else:
            overall = "low"

        significant_count = sum(1 for a in assessments if a.get("is_significant_risk", False))

        return {
            "overall_risk": overall,
            "significant_risks": significant_count,
            "total_risks": len(assessments),
            "average_risk_score": round(avg_score, 2),
        }

    @staticmethod
    def get_risk_matrix(project_id: str, assessments: List[dict]) -> dict:
        """Build risk matrix view: rows=inherent_risk, cols=control_risk."""
        matrix: Dict[str, Dict[str, List[dict]]] = {
            "high": {"high": [], "medium": [], "low": []},
            "medium": {"high": [], "medium": [], "low": []},
            "low": {"high": [], "medium": [], "low": []},
        }

        for a in assessments:
            ir = a.get("inherent_risk", "medium").lower()
            cr = a.get("control_risk", "medium").lower()
            if ir in matrix and cr in matrix[ir]:
                matrix[ir][cr].append(a)

        # Color coding for heatmap
        risk_colors = {
            "high": "#F56C6C",   # Red
            "medium": "#E6A23C",  # Orange
            "low": "#67C23A",    # Green
        }

        return {
            "matrix": matrix,
            "colors": risk_colors,
            "legend": {
                "high": "High risk — requires immediate attention",
                "medium": "Medium risk — requires monitoring",
                "low": "Low risk — routine audit procedures sufficient",
            },
        }
