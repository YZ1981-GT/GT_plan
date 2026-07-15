"""API contract tests for draft-refresh Pydantic models (design §11).

Tests model validation, serialization, field presence and types.
Does NOT test actual HTTP requests — only model validation.

Validates: Requirements 10, 12, 13 | P13, P15
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.formula_runtime import (
    DraftRefreshRequest,
    DraftRefreshResponse,
    PresetApplication,
    RollbackResponse,
)


# ---------------------------------------------------------------------------
# DraftRefreshRequest
# ---------------------------------------------------------------------------


class TestDraftRefreshRequest:
    """Request model validation."""

    def test_valid_minimal_request(self):
        """Minimal valid request with required fields."""
        req = DraftRefreshRequest(
            project_id=uuid.uuid4(),
            year=2025,
            scopes=["report"],
        )
        assert req.transaction_mode == "all_or_nothing"
        assert req.idempotency_key is None
        assert req.confirm_overwrite is False

    def test_valid_full_request(self):
        """Full request with all optional fields."""
        pid = uuid.uuid4()
        req = DraftRefreshRequest(
            project_id=pid,
            year=2025,
            scopes=["report", "note", "workpaper"],
            transaction_mode="partial_success",
            idempotency_key="abc-123",
            confirm_overwrite=True,
        )
        assert req.project_id == pid
        assert req.transaction_mode == "partial_success"
        assert req.idempotency_key == "abc-123"
        assert req.confirm_overwrite is True

    def test_empty_scopes_rejected(self):
        """Empty scopes → validation error (422 at API level)."""
        with pytest.raises(ValidationError) as exc_info:
            DraftRefreshRequest(
                project_id=uuid.uuid4(),
                year=2025,
                scopes=[],
            )
        errors = exc_info.value.errors()
        assert any("scopes" in str(e.get("loc", "")) for e in errors)

    def test_missing_scopes_rejected(self):
        """Missing scopes field → validation error."""
        with pytest.raises(ValidationError):
            DraftRefreshRequest(
                project_id=uuid.uuid4(),
                year=2025,
            )

    def test_invalid_transaction_mode_rejected(self):
        """Invalid transaction_mode literal → validation error."""
        with pytest.raises(ValidationError):
            DraftRefreshRequest(
                project_id=uuid.uuid4(),
                year=2025,
                scopes=["report"],
                transaction_mode="invalid_mode",
            )

    def test_transaction_mode_all_or_nothing(self):
        """all_or_nothing is valid."""
        req = DraftRefreshRequest(
            project_id=uuid.uuid4(),
            year=2025,
            scopes=["workpaper"],
            transaction_mode="all_or_nothing",
        )
        assert req.transaction_mode == "all_or_nothing"

    def test_transaction_mode_partial_success(self):
        """partial_success is valid."""
        req = DraftRefreshRequest(
            project_id=uuid.uuid4(),
            year=2025,
            scopes=["note"],
            transaction_mode="partial_success",
        )
        assert req.transaction_mode == "partial_success"


# ---------------------------------------------------------------------------
# DraftRefreshResponse
# ---------------------------------------------------------------------------


class TestDraftRefreshResponse:
    """Response model serialization and field completeness."""

    def _make_response(self, **overrides) -> DraftRefreshResponse:
        defaults = {
            "status": "success",
            "run_id": uuid.uuid4(),
            "transaction_mode": "all_or_nothing",
            "affected_count": 12,
            "applied_count": 12,
            "failed_count": 0,
            "skipped_count": 0,
            "scopes": ["report"],
            "idempotent": False,
            "rollback_available": True,
            "warnings": [],
            "failures": [],
            "preset_application": PresetApplication(
                preset_count=3,
                presetted_pages=["report:*"],
                pending_pages=[],
            ),
        }
        defaults.update(overrides)
        return DraftRefreshResponse(**defaults)

    def test_all_design_fields_present(self):
        """All fields from design §11 are present in serialized output."""
        resp = self._make_response()
        data = resp.model_dump()
        expected_fields = {
            "status",
            "run_id",
            "transaction_mode",
            "affected_count",
            "applied_count",
            "failed_count",
            "skipped_count",
            "scopes",
            "idempotent",
            "rollback_available",
            "warnings",
            "failures",
            "preset_application",
        }
        assert expected_fields == set(data.keys())

    def test_preset_application_fields(self):
        """preset_application sub-model has correct fields."""
        resp = self._make_response()
        pa = resp.model_dump()["preset_application"]
        assert set(pa.keys()) == {"preset_count", "presetted_pages", "pending_pages"}

    def test_status_success(self):
        """status='success' serializes correctly."""
        resp = self._make_response(status="success")
        assert resp.status == "success"

    def test_status_partial_success(self):
        """status='partial_success' serializes correctly."""
        resp = self._make_response(status="partial_success", failed_count=2)
        assert resp.status == "partial_success"
        assert resp.failed_count == 2

    def test_status_idempotent_hit(self):
        """status='idempotent_hit' serializes correctly."""
        resp = self._make_response(status="idempotent_hit", idempotent=True)
        assert resp.status == "idempotent_hit"
        assert resp.idempotent is True

    def test_status_failed(self):
        """status='failed' serializes correctly."""
        resp = self._make_response(
            status="failed",
            applied_count=0,
            failed_count=5,
            failures=["adapter error"],
        )
        assert resp.status == "failed"
        assert resp.failures == ["adapter error"]

    def test_invalid_status_rejected(self):
        """Invalid status literal → validation error."""
        with pytest.raises(ValidationError):
            self._make_response(status="unknown_status")

    def test_run_id_is_uuid(self):
        """run_id must be a valid UUID."""
        rid = uuid.uuid4()
        resp = self._make_response(run_id=rid)
        assert resp.run_id == rid

    def test_json_roundtrip(self):
        """Model can be serialized to JSON and back."""
        resp = self._make_response()
        json_str = resp.model_dump_json()
        restored = DraftRefreshResponse.model_validate_json(json_str)
        assert restored.status == resp.status
        assert restored.run_id == resp.run_id
        assert restored.affected_count == resp.affected_count


# ---------------------------------------------------------------------------
# RollbackResponse
# ---------------------------------------------------------------------------


class TestRollbackResponse:
    """Rollback response model validation."""

    def test_rolled_back_success(self):
        """Successful rollback response."""
        rid = uuid.uuid4()
        resp = RollbackResponse(
            status="rolled_back",
            run_id=rid,
            restored_count=5,
            conflicts=[],
            error=None,
        )
        assert resp.status == "rolled_back"
        assert resp.restored_count == 5
        assert resp.error is None

    def test_rollback_failed(self):
        """Failed rollback response with error."""
        rid = uuid.uuid4()
        resp = RollbackResponse(
            status="failed",
            run_id=rid,
            restored_count=0,
            conflicts=["version mismatch on target X"],
            error="CAS conflict detected",
        )
        assert resp.status == "failed"
        assert resp.error == "CAS conflict detected"
        assert len(resp.conflicts) == 1

    def test_all_rollback_fields_present(self):
        """All fields from design §11 rollback are present."""
        resp = RollbackResponse(
            status="rolled_back",
            run_id=uuid.uuid4(),
            restored_count=3,
            conflicts=[],
            error=None,
        )
        data = resp.model_dump()
        expected_fields = {"status", "run_id", "restored_count", "conflicts", "error"}
        assert expected_fields == set(data.keys())

    def test_invalid_rollback_status_rejected(self):
        """Invalid rollback status → validation error."""
        with pytest.raises(ValidationError):
            RollbackResponse(
                status="partial",
                run_id=uuid.uuid4(),
                restored_count=0,
                conflicts=[],
                error=None,
            )

    def test_json_roundtrip(self):
        """Rollback model JSON roundtrip."""
        resp = RollbackResponse(
            status="rolled_back",
            run_id=uuid.uuid4(),
            restored_count=7,
            conflicts=["conflict_a"],
            error=None,
        )
        json_str = resp.model_dump_json()
        restored = RollbackResponse.model_validate_json(json_str)
        assert restored.restored_count == 7
        assert restored.conflicts == ["conflict_a"]


# ---------------------------------------------------------------------------
# PresetApplication
# ---------------------------------------------------------------------------


class TestPresetApplication:
    """PresetApplication sub-model validation."""

    def test_defaults(self):
        """Default values are zeros/empty."""
        pa = PresetApplication()
        assert pa.preset_count == 0
        assert pa.presetted_pages == []
        assert pa.pending_pages == []

    def test_with_values(self):
        """Can set all fields."""
        pa = PresetApplication(
            preset_count=5,
            presetted_pages=["report:*", "note:*"],
            pending_pages=["workpaper:D"],
        )
        assert pa.preset_count == 5
        assert len(pa.presetted_pages) == 2
        assert pa.pending_pages == ["workpaper:D"]
