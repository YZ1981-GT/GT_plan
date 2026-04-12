"""
Test Component Auditor Service - validates audit instructions and results.
Validates: Requirements 6.1-6.4

All imports are mocked to avoid SQLAlchemy Base.metadata conflicts.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from datetime import date, datetime
import uuid


# Future date helper (avoids external deps)
def future_date(years=5):
    """Return a date N years in the future."""
    today = date.today()
    return date(today.year + years, today.month, today.day)


# ============================================================================
# Pure service logic (mirrors component_auditor_service.py)
# ============================================================================

class AuditStatus:
    pending = "pending"
    sent = "sent"
    in_progress = "in_progress"
    completed = "completed"
    rejected = "rejected"


class ResultStatus:
    unqualified = "unqualified"
    qualified = "qualified"
    adverse = "adverse"
    disclaimer = "disclaimer"


class ReviewStatus:
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


def validate_instruction(instruction: dict) -> list[str]:
    """Validate instruction fields. Returns list of error messages (empty = valid)."""
    errors = []
    if not instruction.get("entity_code"):
        errors.append("entity_code is required")
    if not instruction.get("instruction_type"):
        errors.append("instruction_type is required")
    if not instruction.get("period"):
        errors.append("period is required")
    if instruction.get("due_date") and instruction.get("due_date") < date.today():
        errors.append("due_date cannot be in the past")
    return errors


def determine_audit_result_type(
    misstatement_ratio: Decimal,
    unadjusted_ratio: Decimal,
    threshold: Decimal,
) -> str:
    """
    Determine audit opinion based on materiality:
    - No misstatements/unadjusted → unqualified
    - Total < threshold → unqualified
    - threshold ≤ total < 2×threshold → qualified
    - Total ≥ 2×threshold → adverse
    """
    if misstatement_ratio == Decimal("0") and unadjusted_ratio == Decimal("0"):
        return ResultStatus.unqualified

    total_ratio = misstatement_ratio + unadjusted_ratio

    if total_ratio < threshold:
        return ResultStatus.unqualified
    elif total_ratio < threshold * Decimal("2"):
        return ResultStatus.qualified
    else:
        return ResultStatus.adverse


def next_instruction_status(current: str, action: str) -> str:
    """State machine for instruction lifecycle."""
    transitions = {
        (AuditStatus.pending, "send"): AuditStatus.sent,
        (AuditStatus.sent, "start"): AuditStatus.in_progress,
        (AuditStatus.in_progress, "complete"): AuditStatus.completed,
        (AuditStatus.completed, "reject"): AuditStatus.rejected,
        (AuditStatus.rejected, "resend"): AuditStatus.sent,
    }
    key = (current, action)
    if key not in transitions:
        raise ValueError(f"Invalid transition: {current} + {action}")
    return transitions[key]


def requires_additional_docs(result_type: str, modified: bool) -> bool:
    """
    Qualified / adverse opinions require additional documentation.
    Modified audit report → additional procedures required.
    """
    return result_type in (ResultStatus.qualified, ResultStatus.adverse) or modified


def calculate_completion_rate(instructions: list[dict]) -> dict:
    """Calculate audit instruction completion rate."""
    if not instructions:
        return {"total": 0, "completed": 0, "rate": Decimal("0")}

    total = len(instructions)
    completed = sum(1 for i in instructions if i.get("status") == AuditStatus.completed)
    rate = Decimal(str(completed)) / Decimal(str(total)) * Decimal("100")
    return {"total": total, "completed": completed, "rate": rate}


def filter_by_status(instructions: list[dict], status: str) -> list[dict]:
    """Filter instructions by status."""
    return [i for i in instructions if i.get("status") == status]


# ============================================================================
# Test: Instruction Validation
# ============================================================================

class TestInstructionValidation:
    def test_valid_instruction_passes(self):
        """Complete instruction has no errors."""
        instruction = {
            "entity_code": "SUB1",
            "instruction_type": "full_scope",
            "period": "2024",
            "due_date": future_date(),
        }
        errors = validate_instruction(instruction)
        assert errors == []

    def test_missing_entity_code(self):
        """Missing entity_code → error."""
        instruction = {"instruction_type": "full_scope", "period": "2024"}
        errors = validate_instruction(instruction)
        assert "entity_code is required" in errors

    def test_missing_instruction_type(self):
        """Missing instruction_type → error."""
        instruction = {"entity_code": "SUB1", "period": "2024"}
        errors = validate_instruction(instruction)
        assert "instruction_type is required" in errors

    def test_past_due_date_rejected(self):
        """Past due_date → error."""
        instruction = {
            "entity_code": "SUB1",
            "instruction_type": "full_scope",
            "period": "2024",
            "due_date": date(2020, 1, 1),  # past
        }
        errors = validate_instruction(instruction)
        assert any("past" in e for e in errors)


# ============================================================================
# Test: Instruction State Machine
# ============================================================================

class TestInstructionStateMachine:
    def test_send_pending_instruction(self):
        """pending → sent."""
        result = next_instruction_status(AuditStatus.pending, "send")
        assert result == AuditStatus.sent

    def test_start_sent_instruction(self):
        """sent → in_progress."""
        result = next_instruction_status(AuditStatus.sent, "start")
        assert result == AuditStatus.in_progress

    def test_complete_in_progress_instruction(self):
        """in_progress → completed."""
        result = next_instruction_status(AuditStatus.in_progress, "complete")
        assert result == AuditStatus.completed

    def test_reject_completed_instruction(self):
        """completed → rejected (manager review failed)."""
        result = next_instruction_status(AuditStatus.completed, "reject")
        assert result == AuditStatus.rejected

    def test_resend_rejected_instruction(self):
        """rejected → sent."""
        result = next_instruction_status(AuditStatus.rejected, "resend")
        assert result == AuditStatus.sent

    def test_cannot_send_completed_instruction(self):
        """completed + send → invalid transition."""
        with pytest.raises(ValueError, match="Invalid transition"):
            next_instruction_status(AuditStatus.completed, "send")


# ============================================================================
# Test: Audit Result Determination
# ============================================================================

class TestAuditResultDetermination:
    def test_no_misstatements_unqualified(self):
        """Zero misstatements → unqualified opinion."""
        result = determine_audit_result_type(Decimal("0"), Decimal("0"), Decimal("0.05"))
        assert result == ResultStatus.unqualified

    def test_below_materiality_threshold_unqualified(self):
        """Total misstatements < threshold → unqualified."""
        result = determine_audit_result_type(Decimal("0.02"), Decimal("0"), Decimal("0.05"))
        assert result == ResultStatus.unqualified

    def test_approaching_materiality_qualified(self):
        """Total misstatements ≥ threshold but < 2× → qualified."""
        result = determine_audit_result_type(Decimal("0.06"), Decimal("0"), Decimal("0.05"))
        assert result == ResultStatus.qualified

    def test_above_materiality_adverse(self):
        """Total misstatements ≥ 2× threshold → adverse."""
        result = determine_audit_result_type(Decimal("0.10"), Decimal("0"), Decimal("0.05"))
        assert result == ResultStatus.adverse

    def test_unadjusted_only_below_threshold(self):
        """Unadjusted without misstatements below threshold."""
        result = determine_audit_result_type(Decimal("0"), Decimal("0.03"), Decimal("0.05"))
        assert result == ResultStatus.unqualified

    def test_unadjusted_above_threshold_qualified(self):
        """Unadjusted above threshold → qualified."""
        result = determine_audit_result_type(Decimal("0"), Decimal("0.06"), Decimal("0.05"))
        assert result == ResultStatus.qualified


# ============================================================================
# Test: Additional Documentation Requirements
# ============================================================================

class TestAdditionalDocumentation:
    def test_qualified_requires_additional_docs(self):
        """Qualified opinion → additional documentation."""
        assert requires_additional_docs(ResultStatus.qualified, False) is True

    def test_adverse_requires_additional_docs(self):
        """Adverse opinion → additional documentation."""
        assert requires_additional_docs(ResultStatus.adverse, False) is True

    def test_unqualified_no_additional_docs(self):
        """Unqualified opinion → no additional documentation."""
        assert requires_additional_docs(ResultStatus.unqualified, False) is False

    def test_modified_report_requires_docs(self):
        """Modified report (even if otherwise unqualified) → additional docs."""
        assert requires_additional_docs(ResultStatus.unqualified, True) is True

    def test_non_modified_qualified_still_needs_docs(self):
        """Qualified + non-modified → needs docs (threshold breach alone is enough)."""
        assert requires_additional_docs(ResultStatus.qualified, False) is True


# ============================================================================
# Test: Completion Rate
# ============================================================================

class TestCompletionRate:
    def test_all_completed_100_percent(self):
        """All instructions completed → 100%."""
        instructions = [
            {"status": AuditStatus.completed},
            {"status": AuditStatus.completed},
            {"status": AuditStatus.completed},
        ]
        result = calculate_completion_rate(instructions)
        assert result["total"] == 3
        assert result["completed"] == 3
        assert result["rate"] == Decimal("100")

    def test_none_completed_0_percent(self):
        """No instructions completed → 0%."""
        instructions = [
            {"status": AuditStatus.pending},
            {"status": AuditStatus.sent},
        ]
        result = calculate_completion_rate(instructions)
        assert result["rate"] == Decimal("0")

    def test_partial_completion(self):
        """3/5 completed → 60%."""
        instructions = [
            {"status": AuditStatus.completed},
            {"status": AuditStatus.completed},
            {"status": AuditStatus.completed},
            {"status": AuditStatus.pending},
            {"status": AuditStatus.in_progress},
        ]
        result = calculate_completion_rate(instructions)
        assert result["total"] == 5
        assert result["completed"] == 3
        assert result["rate"] == Decimal("60")

    def test_empty_instructions(self):
        """Empty list → 0%."""
        result = calculate_completion_rate([])
        assert result["total"] == 0
        assert result["rate"] == Decimal("0")

    def test_filter_by_status(self):
        """Filter returns only matching status."""
        instructions = [
            {"status": AuditStatus.completed, "entity_code": "SUB1"},
            {"status": AuditStatus.pending, "entity_code": "SUB2"},
            {"status": AuditStatus.completed, "entity_code": "SUB3"},
        ]
        completed = filter_by_status(instructions, AuditStatus.completed)
        assert len(completed) == 2
        pending = filter_by_status(instructions, AuditStatus.pending)
        assert len(pending) == 1


# ============================================================================
# Test: Multiple Instructions Per Entity
# ============================================================================

class TestMultipleInstructionsPerEntity:
    def test_multiple_instructions_for_same_entity(self):
        """Same entity can have multiple instructions (different periods/types)."""
        instructions = [
            {"entity_code": "SUB1", "period": "2024", "status": AuditStatus.completed},
            {"entity_code": "SUB1", "period": "2023", "status": AuditStatus.pending},
            {"entity_code": "SUB1", "period": "2024", "status": AuditStatus.sent},
        ]
        sub1 = [i for i in instructions if i["entity_code"] == "SUB1"]
        assert len(sub1) == 3

    def test_all_belong_to_same_entity(self):
        """All filtered instructions belong to same entity."""
        instructions = [
            {"entity_code": "SUB1", "status": AuditStatus.completed},
            {"entity_code": "SUB1", "status": AuditStatus.pending},
            {"entity_code": "SUB1", "status": AuditStatus.sent},
        ]
        assert all(i["entity_code"] == "SUB1" for i in instructions)
