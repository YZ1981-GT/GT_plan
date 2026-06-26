"""Tests for migration V092: A13 misstatement aggregation columns.

Validates: Requirements 4.1 - prior_year_status + source_wp_code columns
"""

from pathlib import Path

import pytest

_MIGRATION_FILE = (
    Path(__file__).resolve().parent.parent / "migrations" / "V092__a13_misstatement_aggregation.sql"
)


class TestV092MigrationSource:
    """Verify migration SQL contains required DDL statements."""

    @pytest.fixture(scope="class")
    def source(self) -> str:
        return _MIGRATION_FILE.read_text(encoding="utf-8")

    def test_migration_file_exists(self):
        assert _MIGRATION_FILE.exists()

    def test_adds_prior_year_status_column(self, source):
        assert "prior_year_status" in source

    def test_prior_year_status_default_new(self, source):
        assert "DEFAULT 'new'" in source

    def test_prior_year_status_check_constraint(self, source):
        assert "'new'" in source
        assert "'continuing'" in source
        assert "'reversed'" in source
        assert "CHECK" in source

    def test_adds_source_wp_code_column(self, source):
        assert "source_wp_code" in source

    def test_source_wp_code_varchar20(self, source):
        assert "VARCHAR(20)" in source

    def test_has_column_comments(self, source):
        assert "COMMENT ON COLUMN" in source
        assert "prior_year_status" in source
        assert "source_wp_code" in source

    def test_uses_if_not_exists(self, source):
        assert "IF NOT EXISTS" in source
