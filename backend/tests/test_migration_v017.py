"""Tests for migration V017: v3_refinement_tables.

Validates: V017 creates 3 tables (ai_content_log, cross_module_conflicts,
time_machine_snapshots) with correct columns, constraints, and indexes.
Also validates R017 rollback drops all 3 tables.
"""

from pathlib import Path

import pytest

# Resolve migrations dir relative to this test file, so the test passes
# regardless of cwd (workspace root vs backend/).
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class TestV017MigrationSource:
    """Verify V017 migration SQL contains all required DDL."""

    @pytest.fixture(scope="class")
    def source(self) -> str:
        with open(
            _MIGRATIONS_DIR / "V017__v3_refinement_tables.sql", encoding="utf-8"
        ) as f:
            return f.read()

    # --- Tables ---
    @pytest.mark.parametrize(
        "table_name",
        [
            "ai_content_log",
            "cross_module_conflicts",
            "time_machine_snapshots",
        ],
    )
    def test_table_created(self, source, table_name):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in source

    # --- ai_content_log columns ---
    @pytest.mark.parametrize(
        "column",
        [
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid()",
            "project_id UUID NOT NULL REFERENCES projects(id)",
            "wp_id UUID",
            "user_id UUID NOT NULL REFERENCES users(id)",
            "content_hash VARCHAR(64) NOT NULL",
            "target_cell VARCHAR(255)",
            "prompt_hash VARCHAR(64)",
            "model VARCHAR(100) NOT NULL",
            "confidence NUMERIC(5,4)",
            "generated_content TEXT NOT NULL",
            "revised_content TEXT",
            "confirmed_by UUID REFERENCES users(id)",
            "confirmed_at TIMESTAMPTZ",
            "generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        ],
    )
    def test_ai_content_log_columns(self, source, column):
        assert column in source

    def test_ai_content_log_confirm_action_check(self, source):
        assert "confirm_action IN ('pending', 'confirmed', 'revised', 'rejected')" in source

    # --- cross_module_conflicts columns ---
    @pytest.mark.parametrize(
        "column",
        [
            "source_module VARCHAR(50) NOT NULL",
            "source_id UUID NOT NULL",
            "target_module VARCHAR(50) NOT NULL",
            "target_id UUID NOT NULL",
            "target_field VARCHAR(100) NOT NULL",
            "upstream_value TEXT",
            "manual_value TEXT",
            "final_value TEXT",
            "resolved_by UUID REFERENCES users(id)",
            "resolved_at TIMESTAMPTZ",
        ],
    )
    def test_cross_module_conflicts_columns(self, source, column):
        assert column in source

    def test_cross_module_conflicts_resolution_check(self, source):
        assert "resolution IN ('keep_manual', 'accept_new', 'merge')" in source

    def test_cross_module_conflicts_status_check(self, source):
        assert "status IN ('pending', 'resolved', 'auto_skipped')" in source

    # --- time_machine_snapshots columns ---
    @pytest.mark.parametrize(
        "column",
        [
            "instance_id UUID NOT NULL",
            "instance_type VARCHAR(50) NOT NULL",
            "diff_json JSONB NOT NULL",
            "parent_snapshot_id UUID REFERENCES time_machine_snapshots(id)",
        ],
    )
    def test_time_machine_snapshots_columns(self, source, column):
        assert column in source

    # --- Indexes ---
    @pytest.mark.parametrize(
        "index_name",
        [
            "idx_ai_content_log_project",
            "idx_ai_content_log_project_action",
            "idx_ai_content_log_wp",
            "idx_cross_module_conflicts_project_status",
            "idx_cross_module_conflicts_target",
            "idx_time_machine_snapshots_instance",
            "idx_time_machine_snapshots_project",
        ],
    )
    def test_index_created(self, source, index_name):
        assert f"CREATE INDEX IF NOT EXISTS {index_name}" in source

    # --- Idempotency ---
    def test_all_creates_are_idempotent(self, source):
        """All CREATE TABLE and CREATE INDEX use IF NOT EXISTS."""
        import re

        tables = re.findall(r"CREATE TABLE\b", source)
        tables_ine = re.findall(r"CREATE TABLE IF NOT EXISTS", source)
        assert len(tables) == len(tables_ine), "All CREATE TABLE must use IF NOT EXISTS"

        indexes = re.findall(r"CREATE INDEX\b", source)
        indexes_ine = re.findall(r"CREATE INDEX IF NOT EXISTS", source)
        assert len(indexes) == len(indexes_ine), "All CREATE INDEX must use IF NOT EXISTS"

    # --- SQL syntax basic validation ---
    def test_no_trailing_comma_before_closing_paren(self, source):
        """Basic syntax check: no trailing comma before closing paren in CREATE TABLE."""
        import re

        # Match comma followed by optional whitespace/newline then closing paren
        bad_pattern = re.findall(r",\s*\)", source)
        assert len(bad_pattern) == 0, f"Trailing comma before ')' found: {bad_pattern}"


class TestR017RollbackSource:
    """Verify R017 rollback SQL drops all 3 tables and indexes."""

    @pytest.fixture(scope="class")
    def source(self) -> str:
        with open(
            _MIGRATIONS_DIR / "R017__v3_refinement_tables_rollback.sql",
            encoding="utf-8",
        ) as f:
            return f.read()

    @pytest.mark.parametrize(
        "table_name",
        [
            "ai_content_log",
            "cross_module_conflicts",
            "time_machine_snapshots",
        ],
    )
    def test_table_dropped(self, source, table_name):
        assert f"DROP TABLE IF EXISTS {table_name}" in source

    @pytest.mark.parametrize(
        "index_name",
        [
            "idx_ai_content_log_project",
            "idx_ai_content_log_project_action",
            "idx_ai_content_log_wp",
            "idx_cross_module_conflicts_project_status",
            "idx_cross_module_conflicts_target",
            "idx_time_machine_snapshots_instance",
            "idx_time_machine_snapshots_project",
        ],
    )
    def test_index_dropped(self, source, index_name):
        assert f"DROP INDEX IF EXISTS {index_name}" in source

    def test_rollback_drops_tables_after_indexes(self, source):
        """Tables should be dropped after their indexes for clarity."""
        # ai_content_log indexes before table
        idx_pos = source.index("idx_ai_content_log_project")
        tbl_pos = source.index("DROP TABLE IF EXISTS ai_content_log")
        assert idx_pos < tbl_pos

        # cross_module_conflicts indexes before table
        idx_pos = source.index("idx_cross_module_conflicts_target")
        tbl_pos = source.index("DROP TABLE IF EXISTS cross_module_conflicts")
        assert idx_pos < tbl_pos

        # time_machine_snapshots indexes before table
        idx_pos = source.index("idx_time_machine_snapshots_instance")
        tbl_pos = source.index("DROP TABLE IF EXISTS time_machine_snapshots")
        assert idx_pos < tbl_pos
