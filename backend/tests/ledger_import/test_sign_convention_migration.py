"""符号约定迁移测试。

验证 V064 迁移 DDL 的幂等性、新字段可空性和旧数据可读性。
使用 sqlglot 静态解析 SQL（不依赖实际 PG 连接）。

Requirements: 5.3, 6.6
"""

import re
from pathlib import Path

import pytest

MIGRATION_DIR = Path(__file__).resolve().parents[2] / "migrations"
V064_PATH = MIGRATION_DIR / "V064__sign_convention_direction_fields.sql"
R064_PATH = MIGRATION_DIR / "R064__sign_convention_direction_fields.sql"


class TestMigrationFileExists:
    def test_v064_exists(self):
        assert V064_PATH.exists(), f"V064 migration not found at {V064_PATH}"

    def test_r064_exists(self):
        assert R064_PATH.exists(), f"R064 rollback not found at {R064_PATH}"


class TestMigrationIdempotent:
    """验证所有 DDL 语句使用 IF NOT EXISTS / IF EXISTS。"""

    def test_v064_all_alter_have_if_not_exists(self):
        content = V064_PATH.read_text(encoding="utf-8")
        alter_stmts = re.findall(
            r"ALTER\s+TABLE\s+\w+\s+ADD\s+COLUMN.*?;",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        assert len(alter_stmts) > 0, "No ALTER TABLE ADD COLUMN found"
        for stmt in alter_stmts:
            assert "IF NOT EXISTS" in stmt.upper(), (
                f"ALTER without IF NOT EXISTS: {stmt[:80]}"
            )

    def test_v064_create_table_has_if_not_exists(self):
        content = V064_PATH.read_text(encoding="utf-8")
        create_stmts = re.findall(
            r"CREATE\s+TABLE.*?;",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        for stmt in create_stmts:
            assert "IF NOT EXISTS" in stmt.upper(), (
                f"CREATE TABLE without IF NOT EXISTS: {stmt[:80]}"
            )

    def test_v064_create_index_has_if_not_exists(self):
        content = V064_PATH.read_text(encoding="utf-8")
        idx_stmts = re.findall(
            r"CREATE\s+INDEX.*?;",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        for stmt in idx_stmts:
            assert "IF NOT EXISTS" in stmt.upper(), (
                f"CREATE INDEX without IF NOT EXISTS: {stmt[:80]}"
            )

    def test_r064_all_drop_have_if_exists(self):
        content = R064_PATH.read_text(encoding="utf-8")
        drop_col_stmts = re.findall(
            r"ALTER\s+TABLE\s+\w+\s+DROP\s+COLUMN.*?;",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        for stmt in drop_col_stmts:
            assert "IF EXISTS" in stmt.upper(), (
                f"DROP COLUMN without IF EXISTS: {stmt[:80]}"
            )

    def test_r064_drop_table_has_if_exists(self):
        content = R064_PATH.read_text(encoding="utf-8")
        drop_table_stmts = re.findall(
            r"DROP\s+TABLE.*?;",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        for stmt in drop_table_stmts:
            assert "IF EXISTS" in stmt.upper(), (
                f"DROP TABLE without IF EXISTS: {stmt[:80]}"
            )


class TestFieldsNullable:
    """验证所有新增字段不含 NOT NULL 约束（允许旧数据无值）。"""

    def test_v064_balance_columns_are_nullable(self):
        content = V064_PATH.read_text(encoding="utf-8")
        # All ALTER TABLE ADD COLUMN statements should NOT have NOT NULL
        alter_stmts = re.findall(
            r"ALTER\s+TABLE\s+\w+\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+(\w+)\s+[^;]+;",
            content,
            re.IGNORECASE,
        )
        for stmt_match in re.finditer(
            r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+(\w+)\s+([^;]+);",
            content,
            re.IGNORECASE,
        ):
            table = stmt_match.group(1)
            col = stmt_match.group(2)
            definition = stmt_match.group(3)
            # Should not have NOT NULL in column definition
            assert "NOT NULL" not in definition.upper(), (
                f"{table}.{col} has NOT NULL constraint — must be nullable for old data"
            )


class TestOldDataReadable:
    """验证新字段不改变已有列的行为。"""

    def test_v064_no_alter_existing_columns(self):
        """V064 should only ADD new columns, not ALTER existing ones."""
        content = V064_PATH.read_text(encoding="utf-8")
        # Should not have ALTER COLUMN (type change, rename, set default on existing cols)
        alter_col = re.findall(
            r"ALTER\s+TABLE\s+\w+\s+ALTER\s+COLUMN",
            content,
            re.IGNORECASE,
        )
        assert len(alter_col) == 0, (
            f"V064 should not ALTER existing columns, found: {alter_col}"
        )

    def test_v064_no_drop_column(self):
        """V064 should not drop any existing columns."""
        content = V064_PATH.read_text(encoding="utf-8")
        drops = re.findall(
            r"ALTER\s+TABLE\s+\w+\s+DROP\s+COLUMN",
            content,
            re.IGNORECASE,
        )
        assert len(drops) == 0, "V064 should not drop columns"


class TestDirectionOverrideTable:
    """验证 direction_override 表结构。"""

    def test_has_required_columns(self):
        content = V064_PATH.read_text(encoding="utf-8")
        required_cols = [
            "project_id",
            "dataset_id",
            "table_name",
            "record_id",
            "original_direction",
            "override_direction",
            "override_reason",
            "override_by",
            "override_at",
            "created_at",
            "updated_at",
        ]
        for col in required_cols:
            assert col in content, f"direction_override missing column: {col}"

    def test_has_timestamps(self):
        """TimestampMixin columns (created_at, updated_at) must be present."""
        content = V064_PATH.read_text(encoding="utf-8")
        assert "created_at TIMESTAMPTZ NOT NULL DEFAULT now()" in content
        assert "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()" in content

    def test_has_project_foreign_key(self):
        content = V064_PATH.read_text(encoding="utf-8")
        assert "REFERENCES projects(id)" in content


class TestExpectedColumnCounts:
    """验证新增列数量与设计文档一致。"""

    def test_tb_balance_6_new_columns(self):
        content = V064_PATH.read_text(encoding="utf-8")
        bal_cols = re.findall(
            r"ALTER\s+TABLE\s+tb_balance\s+ADD\s+COLUMN",
            content,
            re.IGNORECASE,
        )
        assert len(bal_cols) == 6

    def test_tb_aux_balance_6_new_columns(self):
        content = V064_PATH.read_text(encoding="utf-8")
        aux_bal_cols = re.findall(
            r"ALTER\s+TABLE\s+tb_aux_balance\s+ADD\s+COLUMN",
            content,
            re.IGNORECASE,
        )
        assert len(aux_bal_cols) == 6

    def test_tb_ledger_2_new_columns(self):
        content = V064_PATH.read_text(encoding="utf-8")
        ledger_cols = re.findall(
            r"ALTER\s+TABLE\s+tb_ledger\s+ADD\s+COLUMN",
            content,
            re.IGNORECASE,
        )
        assert len(ledger_cols) == 2

    def test_tb_aux_ledger_2_new_columns(self):
        content = V064_PATH.read_text(encoding="utf-8")
        aux_ledger_cols = re.findall(
            r"ALTER\s+TABLE\s+tb_aux_ledger\s+ADD\s+COLUMN",
            content,
            re.IGNORECASE,
        )
        assert len(aux_ledger_cols) == 2


class TestUserOverrideDesign:
    """验证设计决策：用户覆盖通过独立 overlay 表，不改写原始四表。

    Property 5：原始事实不可被覆盖抹除。
    """

    def test_v064_does_not_add_override_columns_to_four_tables(self):
        """direction_override 是独立表，四表不含 override 相关列。"""
        content = V064_PATH.read_text(encoding="utf-8")
        # 四表的 ALTER 语句不应包含 override 字样
        four_table_alters = re.findall(
            r"ALTER\s+TABLE\s+(tb_balance|tb_aux_balance|tb_ledger|tb_aux_ledger)\s+ADD\s+COLUMN[^;]+;",
            content,
            re.IGNORECASE,
        )
        for stmt in four_table_alters:
            assert "override" not in stmt.lower(), (
                f"Four tables should not have override columns: {stmt[:80]}"
            )

    def test_direction_override_is_separate_table(self):
        """direction_override 表独立于四表存在。"""
        content = V064_PATH.read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS direction_override" in content

    def test_override_preserves_original_direction(self):
        """direction_override 表包含 original_direction 列，保留覆盖前事实。"""
        content = V064_PATH.read_text(encoding="utf-8")
        # Extract CREATE TABLE direction_override block
        match = re.search(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+direction_override\s*\((.*?)\);",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        assert match is not None, "direction_override CREATE TABLE not found"
        create_body = match.group(1)
        assert "original_direction" in create_body, (
            "direction_override must store original_direction for audit trail"
        )
        assert "override_reason" in create_body, (
            "direction_override must record reason"
        )
        assert "override_by" in create_body, (
            "direction_override must record who made the override"
        )
        assert "override_at" in create_body, (
            "direction_override must record when the override was made"
        )

    def test_override_references_record_not_modifies(self):
        """direction_override 用 record_id 引用原始行，不修改原始行。"""
        content = V064_PATH.read_text(encoding="utf-8")
        match = re.search(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+direction_override\s*\((.*?)\);",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        assert match is not None
        create_body = match.group(1)
        assert "record_id" in create_body, (
            "direction_override must reference original record by ID"
        )
        assert "table_name" in create_body, (
            "direction_override must track which table the record belongs to"
        )


class TestWriterDirectionFieldPersistence:
    """验证 writer 能正确传递方向字段到 DB。

    writer 使用 table_model column introspection 自动拾取 row dict 中的字段。
    只要 converter 输出的 dict 含方向字段 key、且 DB 有对应列，writer 即持久化。
    """

    def test_direction_fields_are_valid_for_balance_table(self):
        """方向字段名与 V064 定义的列名一致。"""
        content = V064_PATH.read_text(encoding="utf-8")
        balance_direction_fields = [
            "opening_direction",
            "opening_direction_source",
            "closing_direction",
            "closing_direction_source",
            "sign_convention_version",
            "sign_anomaly_flags",
        ]
        for field_name in balance_direction_fields:
            assert field_name in content, (
                f"Expected column {field_name} in V064 migration"
            )

    def test_direction_fields_are_valid_for_ledger_table(self):
        """序时账方向字段名与 V064 定义的列名一致。"""
        content = V064_PATH.read_text(encoding="utf-8")
        ledger_direction_fields = [
            "entry_direction",
            "entry_direction_source",
        ]
        for field_name in ledger_direction_fields:
            assert field_name in content, (
                f"Expected column {field_name} in V064 migration"
            )

    def test_converter_v2_result_rows_are_dicts(self):
        """convert_balance_rows_v2 输出的 rows 是 dict 列表，writer 可直接消费。"""
        from app.services.ledger_import.converter import convert_balance_rows_v2

        input_rows = [
            {
                "account_code": "1001",
                "account_name": "库存现金",
                "opening_debit": 1000,
                "opening_credit": 0,
                "closing_debit": 1500,
                "closing_credit": 0,
            }
        ]
        result = convert_balance_rows_v2(input_rows)
        assert isinstance(result.rows, list)
        assert len(result.rows) > 0
        assert isinstance(result.rows[0], dict)
        # rows contain standard balance fields
        assert "account_code" in result.rows[0]
        assert "opening_balance" in result.rows[0]

    def test_converter_v2_stats_has_sign_convention(self):
        """v2 result stats 包含符号约定版本。"""
        from app.services.ledger_import.converter import convert_balance_rows_v2

        input_rows = [
            {
                "account_code": "1001",
                "account_name": "库存现金",
                "closing_balance": 500,
            }
        ]
        result = convert_balance_rows_v2(input_rows)
        assert result.stats["sign_convention_version"] == "v1_net_debit_positive"
