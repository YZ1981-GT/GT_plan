"""第一阶段MVP核心：创建10张业务表、7个枚举类型及索引，projects表新增wizard_state列

Revision ID: 002
Revises: 001
Create Date: 2025-01-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. 创建 PostgreSQL 枚举类型
    # ------------------------------------------------------------------
    account_direction = postgresql.ENUM(
        "debit", "credit",
        name="account_direction",
        create_type=True,
    )
    account_direction.create(op.get_bind(), checkfirst=True)

    account_category = postgresql.ENUM(
        "asset", "liability", "equity", "revenue", "expense",
        name="account_category",
        create_type=True,
    )
    account_category.create(op.get_bind(), checkfirst=True)

    account_source = postgresql.ENUM(
        "standard", "client",
        name="account_source",
        create_type=True,
    )
    account_source.create(op.get_bind(), checkfirst=True)

    mapping_type = postgresql.ENUM(
        "auto_exact", "auto_fuzzy", "manual",
        name="mapping_type",
        create_type=True,
    )
    mapping_type.create(op.get_bind(), checkfirst=True)

    adjustment_type = postgresql.ENUM(
        "aje", "rje",
        name="adjustment_type",
        create_type=True,
    )
    adjustment_type.create(op.get_bind(), checkfirst=True)

    review_status = postgresql.ENUM(
        "draft", "pending_review", "approved", "rejected",
        name="review_status",
        create_type=True,
    )
    review_status.create(op.get_bind(), checkfirst=True)

    import_status = postgresql.ENUM(
        "pending", "processing", "completed", "failed", "rolled_back",
        name="import_status",
        create_type=True,
    )
    import_status.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # 2. ALTER projects 表：新增 wizard_state JSONB 列
    # ------------------------------------------------------------------
    op.add_column(
        "projects",
        sa.Column("wizard_state", postgresql.JSONB(), nullable=True),
    )

    # ------------------------------------------------------------------
    # 3. 创建 import_batches 表（先于四表数据表，因为它们有 FK 引用）
    # ------------------------------------------------------------------
    op.create_table(
        "import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("data_type", sa.String(), nullable=False),
        sa.Column("record_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="import_status", create_type=False),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("validation_summary", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


    # ------------------------------------------------------------------
    # 4. 创建 account_chart 表
    # ------------------------------------------------------------------
    op.create_table(
        "account_chart",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("account_code", sa.String(), nullable=False),
        sa.Column("account_name", sa.String(), nullable=False),
        sa.Column(
            "direction",
            postgresql.ENUM(name="account_direction", create_type=False),
            nullable=False,
        ),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column(
            "category",
            postgresql.ENUM(name="account_category", create_type=False),
            nullable=False,
        ),
        sa.Column("parent_code", sa.String(), nullable=True),
        sa.Column(
            "source",
            postgresql.ENUM(name="account_source", create_type=False),
            nullable=False,
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 5. 创建 account_mapping 表
    # ------------------------------------------------------------------
    op.create_table(
        "account_mapping",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("original_account_code", sa.String(), nullable=False),
        sa.Column("original_account_name", sa.String(), nullable=True),
        sa.Column("standard_account_code", sa.String(), nullable=False),
        sa.Column(
            "mapping_type",
            postgresql.ENUM(name="mapping_type", create_type=False),
            nullable=False,
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 6. 创建 tb_balance 表
    # ------------------------------------------------------------------
    op.create_table(
        "tb_balance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("company_code", sa.String(), nullable=False),
        sa.Column("account_code", sa.String(), nullable=False),
        sa.Column("account_name", sa.String(), nullable=True),
        sa.Column("opening_balance", sa.Numeric(20, 2), nullable=True),
        sa.Column("debit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("credit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("closing_balance", sa.Numeric(20, 2), nullable=True),
        sa.Column("currency_code", sa.String(3), server_default=sa.text("'CNY'"), nullable=False),
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_batches.id"),
            nullable=True,
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 7. 创建 tb_ledger 表
    # ------------------------------------------------------------------
    op.create_table(
        "tb_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("company_code", sa.String(), nullable=False),
        sa.Column("voucher_date", sa.Date(), nullable=False),
        sa.Column("voucher_no", sa.String(), nullable=False),
        sa.Column("account_code", sa.String(), nullable=False),
        sa.Column("account_name", sa.String(), nullable=True),
        sa.Column("debit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("credit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("counterpart_account", sa.String(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("preparer", sa.String(), nullable=True),
        sa.Column("currency_code", sa.String(3), server_default=sa.text("'CNY'"), nullable=False),
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_batches.id"),
            nullable=True,
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


    # ------------------------------------------------------------------
    # 8. 创建 tb_aux_balance 表
    # ------------------------------------------------------------------
    op.create_table(
        "tb_aux_balance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("company_code", sa.String(), nullable=False),
        sa.Column("account_code", sa.String(), nullable=False),
        sa.Column("aux_type", sa.String(), nullable=False),
        sa.Column("aux_code", sa.String(), nullable=True),
        sa.Column("aux_name", sa.String(), nullable=True),
        sa.Column("opening_balance", sa.Numeric(20, 2), nullable=True),
        sa.Column("debit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("credit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("closing_balance", sa.Numeric(20, 2), nullable=True),
        sa.Column("currency_code", sa.String(3), server_default=sa.text("'CNY'"), nullable=False),
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_batches.id"),
            nullable=True,
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 9. 创建 tb_aux_ledger 表
    # ------------------------------------------------------------------
    op.create_table(
        "tb_aux_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("company_code", sa.String(), nullable=False),
        sa.Column("voucher_date", sa.Date(), nullable=True),
        sa.Column("voucher_no", sa.String(), nullable=True),
        sa.Column("account_code", sa.String(), nullable=False),
        sa.Column("aux_type", sa.String(), nullable=True),
        sa.Column("aux_code", sa.String(), nullable=True),
        sa.Column("aux_name", sa.String(), nullable=True),
        sa.Column("debit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("credit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("preparer", sa.String(), nullable=True),
        sa.Column("currency_code", sa.String(3), server_default=sa.text("'CNY'"), nullable=False),
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_batches.id"),
            nullable=True,
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 10. 创建 adjustments 表
    # ------------------------------------------------------------------
    op.create_table(
        "adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("company_code", sa.String(), nullable=False),
        sa.Column("adjustment_no", sa.String(), nullable=False),
        sa.Column(
            "adjustment_type",
            postgresql.ENUM(name="adjustment_type", create_type=False),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("account_code", sa.String(), nullable=False),
        sa.Column("account_name", sa.String(), nullable=True),
        sa.Column("debit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("credit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("entry_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "review_status",
            postgresql.ENUM(name="review_status", create_type=False),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


    # ------------------------------------------------------------------
    # 11. 创建 trial_balance 表
    # ------------------------------------------------------------------
    op.create_table(
        "trial_balance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("company_code", sa.String(), nullable=False),
        sa.Column("standard_account_code", sa.String(), nullable=False),
        sa.Column("account_name", sa.String(), nullable=True),
        sa.Column(
            "account_category",
            postgresql.ENUM(name="account_category", create_type=False),
            nullable=False,
        ),
        sa.Column("unadjusted_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("rje_adjustment", sa.Numeric(20, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("aje_adjustment", sa.Numeric(20, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("audited_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("opening_balance", sa.Numeric(20, 2), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 12. 创建 materiality 表
    # ------------------------------------------------------------------
    op.create_table(
        "materiality",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("benchmark_type", sa.String(), nullable=False),
        sa.Column("benchmark_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("overall_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("overall_materiality", sa.Numeric(20, 2), nullable=False),
        sa.Column("performance_ratio", sa.Numeric(5, 2), nullable=False),
        sa.Column("performance_materiality", sa.Numeric(20, 2), nullable=False),
        sa.Column("trivial_ratio", sa.Numeric(5, 2), nullable=False),
        sa.Column("trivial_threshold", sa.Numeric(20, 2), nullable=False),
        sa.Column("is_override", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "calculated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("calculated_at", sa.DateTime(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 13. 创建索引
    # ------------------------------------------------------------------

    # account_chart: 复合唯一索引 (project_id, account_code, source)
    op.create_index(
        "uq_account_chart_project_code_source",
        "account_chart",
        ["project_id", "account_code", "source"],
        unique=True,
    )

    # account_mapping: 复合唯一索引 (project_id, original_account_code)
    op.create_index(
        "uq_account_mapping_project_original_code",
        "account_mapping",
        ["project_id", "original_account_code"],
        unique=True,
    )

    # tb_balance: 复合索引 (project_id, year, account_code)
    op.create_index(
        "idx_tb_balance_project_year_account",
        "tb_balance",
        ["project_id", "year", "account_code"],
    )

    # tb_ledger: 复合索引 (project_id, year, voucher_date, voucher_no)
    op.create_index(
        "idx_tb_ledger_project_year_date_no",
        "tb_ledger",
        ["project_id", "year", "voucher_date", "voucher_no"],
    )

    # tb_ledger: 复合索引 (project_id, year, account_code)
    op.create_index(
        "idx_tb_ledger_project_year_account",
        "tb_ledger",
        ["project_id", "year", "account_code"],
    )

    # tb_aux_balance: 复合索引 (project_id, year, account_code, aux_type)
    op.create_index(
        "idx_tb_aux_balance_project_year_account_aux",
        "tb_aux_balance",
        ["project_id", "year", "account_code", "aux_type"],
    )

    # tb_aux_ledger: 复合索引 (project_id, year, account_code, aux_type)
    op.create_index(
        "idx_tb_aux_ledger_project_year_account_aux",
        "tb_aux_ledger",
        ["project_id", "year", "account_code", "aux_type"],
    )

    # adjustments: 复合索引 (project_id, year, adjustment_type)
    op.create_index(
        "idx_adjustments_project_year_type",
        "adjustments",
        ["project_id", "year", "adjustment_type"],
    )

    # adjustments: 复合索引 (project_id, entry_group_id)
    op.create_index(
        "idx_adjustments_project_entry_group",
        "adjustments",
        ["project_id", "entry_group_id"],
    )

    # trial_balance: 复合唯一索引 (project_id, year, company_code, standard_account_code)
    op.create_index(
        "uq_trial_balance_project_year_company_account",
        "trial_balance",
        ["project_id", "year", "company_code", "standard_account_code"],
        unique=True,
    )

    # materiality: 复合唯一索引 (project_id, year)
    op.create_index(
        "uq_materiality_project_year",
        "materiality",
        ["project_id", "year"],
        unique=True,
    )

    # import_batches: 复合索引 (project_id, year)
    op.create_index(
        "idx_import_batches_project_year",
        "import_batches",
        ["project_id", "year"],
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 按创建的逆序删除索引
    # ------------------------------------------------------------------
    op.drop_index("idx_import_batches_project_year", table_name="import_batches")
    op.drop_index("uq_materiality_project_year", table_name="materiality")
    op.drop_index("uq_trial_balance_project_year_company_account", table_name="trial_balance")
    op.drop_index("idx_adjustments_project_entry_group", table_name="adjustments")
    op.drop_index("idx_adjustments_project_year_type", table_name="adjustments")
    op.drop_index("idx_tb_aux_ledger_project_year_account_aux", table_name="tb_aux_ledger")
    op.drop_index("idx_tb_aux_balance_project_year_account_aux", table_name="tb_aux_balance")
    op.drop_index("idx_tb_ledger_project_year_account", table_name="tb_ledger")
    op.drop_index("idx_tb_ledger_project_year_date_no", table_name="tb_ledger")
    op.drop_index("idx_tb_balance_project_year_account", table_name="tb_balance")
    op.drop_index("uq_account_mapping_project_original_code", table_name="account_mapping")
    op.drop_index("uq_account_chart_project_code_source", table_name="account_chart")

    # ------------------------------------------------------------------
    # 按创建的逆序删除表
    # ------------------------------------------------------------------
    op.drop_table("materiality")
    op.drop_table("trial_balance")
    op.drop_table("adjustments")
    op.drop_table("tb_aux_ledger")
    op.drop_table("tb_aux_balance")
    op.drop_table("tb_ledger")
    op.drop_table("tb_balance")
    op.drop_table("account_mapping")
    op.drop_table("account_chart")
    op.drop_table("import_batches")

    # ------------------------------------------------------------------
    # 删除 projects 表的 wizard_state 列
    # ------------------------------------------------------------------
    op.drop_column("projects", "wizard_state")

    # ------------------------------------------------------------------
    # 按创建的逆序删除枚举类型
    # ------------------------------------------------------------------
    postgresql.ENUM(name="import_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="review_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="adjustment_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="mapping_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="account_source").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="account_category").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="account_direction").drop(op.get_bind(), checkfirst=True)
