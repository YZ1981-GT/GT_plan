"""Tests for migration 002: MVP core tables structure validation.

Validates: Requirements 9.1-9.10
"""

import pytest


class TestMigration002Metadata:
    """Verify migration revision chain and basic metadata via source inspection."""

    @pytest.fixture(scope="class")
    def source(self) -> str:
        with open("alembic/versions/002_mvp_core_tables.py", encoding="utf-8") as f:
            return f.read()

    def test_revision_id(self, source):
        assert 'revision = "002"' in source

    def test_down_revision(self, source):
        assert 'down_revision = "001"' in source

    def test_has_upgrade(self, source):
        assert "def upgrade()" in source

    def test_has_downgrade(self, source):
        assert "def downgrade()" in source


class TestMigration002SourceContent:
    """Verify the migration source contains all required tables, enums, and indexes."""

    @pytest.fixture(scope="class")
    def source(self) -> str:
        with open("alembic/versions/002_mvp_core_tables.py", encoding="utf-8") as f:
            return f.read()

    # --- Enum types ---
    @pytest.mark.parametrize(
        "enum_name",
        [
            "account_direction",
            "account_category",
            "account_source",
            "mapping_type",
            "adjustment_type",
            "review_status",
            "import_status",
        ],
    )
    def test_enum_created(self, source, enum_name):
        assert f'name="{enum_name}"' in source

    # --- Tables ---
    @pytest.mark.parametrize(
        "table_name",
        [
            "import_batches",
            "account_chart",
            "account_mapping",
            "tb_balance",
            "tb_ledger",
            "tb_aux_balance",
            "tb_aux_ledger",
            "adjustments",
            "trial_balance",
            "materiality",
        ],
    )
    def test_table_created(self, source, table_name):
        assert f'"{table_name}"' in source

    # --- Indexes ---
    @pytest.mark.parametrize(
        "index_name",
        [
            "uq_account_chart_project_code_source",
            "uq_account_mapping_project_original_code",
            "idx_tb_balance_project_year_account",
            "idx_tb_ledger_project_year_date_no",
            "idx_tb_ledger_project_year_account",
            "idx_tb_aux_balance_project_year_account_aux",
            "idx_tb_aux_ledger_project_year_account_aux",
            "idx_adjustments_project_year_type",
            "idx_adjustments_project_entry_group",
            "uq_trial_balance_project_year_company_account",
            "uq_materiality_project_year",
            "idx_import_batches_project_year",
        ],
    )
    def test_index_created(self, source, index_name):
        assert f'"{index_name}"' in source

    # --- wizard_state column on projects ---
    def test_wizard_state_added(self, source):
        assert "wizard_state" in source
        assert "JSONB" in source

    # --- Downgrade drops all tables ---
    @pytest.mark.parametrize(
        "table_name",
        [
            "materiality",
            "trial_balance",
            "adjustments",
            "tb_aux_ledger",
            "tb_aux_balance",
            "tb_ledger",
            "tb_balance",
            "account_mapping",
            "account_chart",
            "import_batches",
        ],
    )
    def test_downgrade_drops_table(self, source, table_name):
        downgrade_section = source.split("def downgrade")[1]
        assert f'drop_table("{table_name}")' in downgrade_section

    # --- Monetary columns use Numeric(20, 2) ---
    def test_numeric_precision(self, source):
        assert "Numeric(20, 2)" in source

    # --- FK to import_batches ---
    def test_import_batch_fk(self, source):
        assert 'ForeignKey("import_batches.id")' in source

    # --- import_batches created before data tables ---
    def test_import_batches_before_data_tables(self, source):
        ib_pos = source.index('"import_batches"')
        for tbl in ["tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger"]:
            tbl_pos = source.index(f'"{tbl}"')
            assert ib_pos < tbl_pos, f"import_batches must be created before {tbl}"
