"""Tests for V3 refinement ORM models.

Validates: Task 0.3 — AiContentLog / CrossModuleConflict / TimeMachineSnapshot
can be imported and have correct __tablename__ matching V017 migration DDL.
"""

import uuid

import pytest

from app.models.v3_refinement_models import (
    AiContentLog,
    CrossModuleConflict,
    TimeMachineSnapshot,
)
from app.models.base import Base


class TestV3RefinementModelsImport:
    """Verify V3 refinement models can be imported and have correct table names."""

    def test_ai_content_log_tablename(self):
        assert AiContentLog.__tablename__ == "ai_content_log"

    def test_cross_module_conflict_tablename(self):
        assert CrossModuleConflict.__tablename__ == "cross_module_conflicts"

    def test_time_machine_snapshot_tablename(self):
        assert TimeMachineSnapshot.__tablename__ == "time_machine_snapshots"

    def test_models_registered_in_metadata(self):
        """All 3 tables should be registered in Base.metadata."""
        registered = set(Base.metadata.tables.keys())
        assert "ai_content_log" in registered
        assert "cross_module_conflicts" in registered
        assert "time_machine_snapshots" in registered

    def test_ai_content_log_columns(self):
        """AiContentLog should have all columns from V017 DDL."""
        cols = {c.name for c in AiContentLog.__table__.columns}
        expected = {
            "id", "project_id", "wp_id", "user_id", "content_hash",
            "target_cell", "prompt_hash", "model", "confidence",
            "generated_content", "revised_content", "confirm_action",
            "confirmed_by", "confirmed_at", "generated_at",
            "created_at", "updated_at",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_cross_module_conflict_columns(self):
        """CrossModuleConflict should have all columns from V017 DDL."""
        cols = {c.name for c in CrossModuleConflict.__table__.columns}
        expected = {
            "id", "project_id", "source_module", "source_id",
            "target_module", "target_id", "target_field",
            "upstream_value", "manual_value", "final_value",
            "resolution", "resolved_by", "resolved_at", "status",
            "created_at", "updated_at",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_time_machine_snapshot_columns(self):
        """TimeMachineSnapshot should have all columns from V017 DDL."""
        cols = {c.name for c in TimeMachineSnapshot.__table__.columns}
        expected = {
            "id", "instance_id", "instance_type", "user_id",
            "project_id", "diff_json", "parent_snapshot_id", "created_at",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_ai_content_log_uuid_pk(self):
        """AiContentLog PK should be UUID type."""
        pk_col = AiContentLog.__table__.c.id
        assert pk_col.primary_key

    def test_cross_module_conflict_uuid_pk(self):
        """CrossModuleConflict PK should be UUID type."""
        pk_col = CrossModuleConflict.__table__.c.id
        assert pk_col.primary_key

    def test_time_machine_snapshot_uuid_pk(self):
        """TimeMachineSnapshot PK should be UUID type."""
        pk_col = TimeMachineSnapshot.__table__.c.id
        assert pk_col.primary_key

    def test_models_importable_from_init(self):
        """Models should be importable from app.models package."""
        from app.models import AiContentLog as ACL
        from app.models import CrossModuleConflict as CMC
        from app.models import TimeMachineSnapshot as TMS

        assert ACL.__tablename__ == "ai_content_log"
        assert CMC.__tablename__ == "cross_module_conflicts"
        assert TMS.__tablename__ == "time_machine_snapshots"
