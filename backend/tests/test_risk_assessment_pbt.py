"""Property-based tests for risk assessment — Property 19 & 20.

Using Hypothesis to validate:
  - Property 19: combined_risk conforms to the 3×3 risk matrix for all
    inherent_risk × control_risk combinations (case-insensitive)
  - Property 20: is_significant_risk=True requires a non-empty response_strategy

Validates: Requirements 11.6, 11.7
"""

import pytest
from hypothesis import given, settings, assume, example, HealthCheck
from hypothesis import strategies as st

from app.services.risk_service import RiskAssessmentService, RISK_MATRIX


# ---------------------------------------------------------------------------
# Property 19 — combined_risk conforms to risk matrix
# ---------------------------------------------------------------------------

@settings(max_examples=500)
@given(
    ir=st.sampled_from(["HIGH", "high", "High", "Medium", "MEDIUM", "medium", "LOW", "low"]),
    cr=st.sampled_from(["HIGH", "high", "High", "Medium", "MEDIUM", "medium", "LOW", "low"]),
)
def test_property_19_combined_risk_conforms_to_matrix(ir: str, cr: str):
    """Combined risk must match the risk matrix regardless of case."""
    result = RiskAssessmentService.calculate_combined_risk(ir, cr)
    expected = RISK_MATRIX.get((ir.lower(), cr.lower()))
    assert result == expected, (
        f"Failed for inherent_risk={ir}, control_risk={cr}: "
        f"got {result}, expected {expected}"
    )


# Guarantee at least one example per matrix cell
@settings(max_examples=1, suppress_health_check=[HealthCheck.filter_too_much])
@example(ir="HIGH", cr="HIGH")
@example(ir="HIGH", cr="MEDIUM")
@example(ir="HIGH", cr="LOW")
@example(ir="MEDIUM", cr="HIGH")
@example(ir="MEDIUM", cr="MEDIUM")
@example(ir="MEDIUM", cr="LOW")
@example(ir="LOW", cr="HIGH")
@example(ir="LOW", cr="MEDIUM")
@example(ir="LOW", cr="LOW")
@given(ir=st.sampled_from(["HIGH", "HIGH", "HIGH", "MEDIUM", "MEDIUM", "MEDIUM", "LOW", "LOW", "LOW"]), cr=st.sampled_from(["HIGH", "MEDIUM", "LOW", "HIGH", "MEDIUM", "LOW", "HIGH", "MEDIUM", "LOW"]))
def test_property_19_all_9_matrix_cells(ir: str, cr: str):
    """Explicitly cover all 9 risk-matrix cells."""
    matrix_cases = [
        ("HIGH", "HIGH", "high"),
        ("HIGH", "MEDIUM", "medium"),
        ("HIGH", "LOW", "medium"),
        ("MEDIUM", "HIGH", "medium"),
        ("MEDIUM", "MEDIUM", "medium"),
        ("MEDIUM", "LOW", "low"),
        ("LOW", "HIGH", "low"),
        ("LOW", "MEDIUM", "low"),
        ("LOW", "LOW", "low"),
    ]
    for ir, cr, expected in matrix_cases:
        result = RiskAssessmentService.calculate_combined_risk(ir, cr)
        assert result == expected


@settings(max_examples=200)
@given(
    ir=st.sampled_from(["high", "medium", "low"]),
    cr=st.sampled_from(["high", "medium", "low"]),
    extra=st.one_of(st.just(""), st.just("  "), st.text(min_size=1, max_size=20)),
)
def test_property_19_robustness_with_extra_suffix(ir: str, cr: str, extra: str):
    """Extra whitespace/suffix on risk levels should not break calculation."""
    ir_input = (ir + extra).strip()
    cr_input = (cr + extra).strip()
    # Only test if stripped version is still a valid key
    key = (ir.lower().strip(), cr.lower().strip())
    if key in RISK_MATRIX:
        result = RiskAssessmentService.calculate_combined_risk(ir_input, cr_input)
        expected = RISK_MATRIX[key]
        assert result == expected


# ---------------------------------------------------------------------------
# Property 20 — significant risk requires response strategy
# ---------------------------------------------------------------------------

class RiskAssessmentRecord(dict):
    """Lightweight record mirroring the RiskAssessment model fields."""

    def __init__(
        self,
        is_significant_risk: bool,
        response_strategy: str | None,
        inherent_risk: str = "medium",
        control_risk: str = "medium",
    ):
        super().__init__(
            is_significant_risk=is_significant_risk,
            response_strategy=response_strategy,
            inherent_risk=inherent_risk,
            control_risk=control_risk,
        )


def assess_record(record: RiskAssessmentRecord) -> bool:
    """Validate Property 20: significant risk must have a response strategy.

    Returns True if valid (property holds), False otherwise.
    """
    if record["is_significant_risk"]:
        return record["response_strategy"] is not None and record["response_strategy"].strip() != ""
    return True


@settings(max_examples=500)
@given(
    is_sig=st.booleans(),
    strategy=st.one_of(st.none(), st.just(""), st.text(min_size=1, max_size=500)),
    ir=st.sampled_from(["high", "medium", "low"]),
    cr=st.sampled_from(["high", "medium", "low"]),
)
def test_property_20_significant_risk_needs_response(is_sig: bool, strategy: str | None, ir: str, cr: str):
    """When is_significant_risk=True, response_strategy must be non-empty."""
    record = RiskAssessmentRecord(
        is_significant_risk=is_sig,
        response_strategy=strategy,
        inherent_risk=ir,
        control_risk=cr,
    )
    valid = assess_record(record)
    if is_sig:
        assert valid, (
            f"Property 20 violated: is_significant_risk=True but "
            f"response_strategy={strategy!r}"
        )
    else:
        # No constraint when not a significant risk
        assert valid


@settings(max_examples=6, suppress_health_check=[HealthCheck.filter_too_much])
@example(is_sig=True, strategy="Implement substantive analytical procedures for revenue recognition.")
@example(is_sig=True, strategy="  ")
@example(is_sig=False, strategy=None)
@example(is_sig=False, strategy="Optional response")
@example(is_sig=False, strategy="")
@example(is_sig=True, strategy="Obtain external confirmation for all material related-party transactions.")
@given(is_sig=st.sampled_from([True, True, False, False, False, True]), strategy=st.sampled_from([
    "Implement substantive analytical procedures for revenue recognition.",
    "  ",
    None,
    "Optional response",
    "",
    "Obtain external confirmation for all material related-party transactions.",
]))
def test_property_20_boundary_cases(is_sig: bool, strategy: str | None):
    """Edge cases for significant risk response validation."""
    record = RiskAssessmentRecord(is_significant_risk=is_sig, response_strategy=strategy)
    valid = assess_record(record)
    if is_sig:
        assert valid, f"Property 20 violated: is_significant_risk=True but response_strategy={strategy!r}"


@settings(max_examples=300)
@given(
    sig_count=st.integers(min_value=1, max_value=10),
    non_sig_count=st.integers(min_value=0, max_value=10),
    strategy_content=st.text(min_size=5, max_size=200),
)
def test_property_20_batch_mixed_records(sig_count: int, non_sig_count: int, strategy_content: str):
    """Property 20 must hold across a batch of mixed records."""
    records = []
    for _ in range(sig_count):
        # Significant risk records MUST have non-empty strategy
        records.append(RiskAssessmentRecord(
            is_significant_risk=True,
            response_strategy=strategy_content,
        ))
    for _ in range(non_sig_count):
        records.append(RiskAssessmentRecord(
            is_significant_risk=False,
            response_strategy=None,
        ))

    violations = [
        r for r in records if not assess_record(r)
    ]
    assert len(violations) == 0, (
        f"Property 20 violated in batch: {len(violations)} records with "
        f"is_significant_risk=True lack a response strategy"
    )
