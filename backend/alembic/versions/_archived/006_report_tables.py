"""006 report tables — 8张报表相关表

Revision ID: 006
Revises: 005
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- 枚举类型 ----
    report_type_enum = sa.Enum(
        "balance_sheet", "income_statement", "cash_flow_statement", "equity_statement",
        name="financial_report_type",
    )
    report_type_enum.create(op.get_bind(), checkfirst=True)

    cash_flow_category_enum = sa.Enum(
        "operating", "investing", "financing", "supplementary",
        name="cash_flow_category",
    )
    cash_flow_category_enum.create(op.get_bind(), checkfirst=True)

    content_type_enum = sa.Enum(
        "table", "text", "mixed",
        name="content_type",
    )
    content_type_enum.create(op.get_bind(), checkfirst=True)

    source_template_enum = sa.Enum(
        "soe", "listed",
        name="source_template",
    )
    source_template_enum.create(op.get_bind(), checkfirst=True)

    note_status_enum = sa.Enum(
        "draft", "confirmed",
        name="note_status",
    )
    note_status_enum.create(op.get_bind(), checkfirst=True)

    opinion_type_enum = sa.Enum(
        "unqualified", "qualified", "adverse", "disclaimer",
        name="opinion_type",
    )
    opinion_type_enum.create(op.get_bind(), checkfirst=True)

    company_type_enum = sa.Enum(
        "listed", "non_listed",
        name="company_type",
    )
    company_type_enum.create(op.get_bind(), checkfirst=True)

    report_status_enum = sa.Enum(
        "draft", "review", "final",
        name="report_status",
    )
    report_status_enum.create(op.get_bind(), checkfirst=True)

    export_task_type_enum = sa.Enum(
        "single_document", "full_archive",
        name="export_task_type",
    )
    export_task_type_enum.create(op.get_bind(), checkfirst=True)

    export_task_status_enum = sa.Enum(
        "queued", "processing", "completed", "failed",
        name="export_task_status",
    )
    export_task_status_enum.create(op.get_bind(), checkfirst=True)


    # ---- 1.1 report_config ----
    op.create_table(
        "report_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_type",
            sa.Enum("balance_sheet", "income_statement", "cash_flow_statement", "equity_statement",
                    name="financial_report_type", create_type=False),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("row_code", sa.String, nullable=False),
        sa.Column("row_name", sa.String, nullable=False),
        sa.Column("indent_level", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("formula", sa.Text, nullable=True),
        sa.Column("applicable_standard", sa.String, nullable=False),
        sa.Column("is_total_row", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("parent_row_code", sa.String, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_report_config_type_code_standard",
        "report_config",
        ["report_type", "row_code", "applicable_standard"],
        unique=True,
    )

    # ---- 1.2 financial_report ----
    op.create_table(
        "financial_report",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column(
            "report_type",
            sa.Enum("balance_sheet", "income_statement", "cash_flow_statement", "equity_statement",
                    name="financial_report_type", create_type=False),
            nullable=False,
        ),
        sa.Column("row_code", sa.String, nullable=False),
        sa.Column("row_name", sa.String, nullable=True),
        sa.Column("current_period_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("prior_period_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("formula_used", sa.Text, nullable=True),
        sa.Column("source_accounts", sa.JSON, nullable=True),
        sa.Column("generated_at", sa.DateTime, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_financial_report_project_year_type_code",
        "financial_report",
        ["project_id", "year", "report_type", "row_code"],
        unique=True,
    )

    # ---- 1.3 cfs_adjustments ----
    op.create_table(
        "cfs_adjustments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("adjustment_no", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("debit_account", sa.String, nullable=False),
        sa.Column("credit_account", sa.String, nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column(
            "cash_flow_category",
            sa.Enum("operating", "investing", "financing", "supplementary",
                    name="cash_flow_category", create_type=False),
            nullable=True,
        ),
        sa.Column("cash_flow_line_item", sa.String, nullable=True),
        sa.Column("entry_group_id", UUID(as_uuid=True), nullable=True),
        sa.Column("is_auto_generated", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(
        "idx_cfs_adjustments_project_year_category",
        "cfs_adjustments",
        ["project_id", "year", "cash_flow_category"],
    )

    # ---- 1.4 disclosure_notes ----
    op.create_table(
        "disclosure_notes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("note_section", sa.String, nullable=False),
        sa.Column("section_title", sa.String, nullable=False),
        sa.Column("account_name", sa.String, nullable=True),
        sa.Column(
            "content_type",
            sa.Enum("table", "text", "mixed", name="content_type", create_type=False),
            nullable=True,
        ),
        sa.Column("table_data", sa.JSON, nullable=True),
        sa.Column("text_content", sa.Text, nullable=True),
        sa.Column(
            "source_template",
            sa.Enum("soe", "listed", name="source_template", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum("draft", "confirmed", name="note_status", create_type=False),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(
        "uq_disclosure_notes_project_year_section",
        "disclosure_notes",
        ["project_id", "year", "note_section"],
        unique=True,
    )

    # ---- 1.5 audit_report ----
    op.create_table(
        "audit_report",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column(
            "opinion_type",
            sa.Enum("unqualified", "qualified", "adverse", "disclaimer",
                    name="opinion_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "company_type",
            sa.Enum("listed", "non_listed", name="company_type", create_type=False),
            server_default=sa.text("'non_listed'"),
            nullable=False,
        ),
        sa.Column("report_date", sa.Date, nullable=True),
        sa.Column("signing_partner", sa.String, nullable=True),
        sa.Column("paragraphs", sa.JSON, nullable=True),
        sa.Column("financial_data", sa.JSON, nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "review", "final", name="report_status", create_type=False),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(
        "uq_audit_report_project_year",
        "audit_report",
        ["project_id", "year"],
        unique=True,
    )

    # ---- 1.6 audit_report_template ----
    op.create_table(
        "audit_report_template",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opinion_type",
            sa.Enum("unqualified", "qualified", "adverse", "disclaimer",
                    name="opinion_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "company_type",
            sa.Enum("listed", "non_listed", name="company_type", create_type=False),
            nullable=False,
        ),
        sa.Column("section_name", sa.String, nullable=False),
        sa.Column("section_order", sa.Integer, nullable=False),
        sa.Column("template_text", sa.Text, nullable=False),
        sa.Column("is_required", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_audit_report_template_opinion_company_section",
        "audit_report_template",
        ["opinion_type", "company_type", "section_name"],
        unique=True,
    )

    # ---- 1.7 export_tasks ----
    op.create_table(
        "export_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "task_type",
            sa.Enum("single_document", "full_archive", name="export_task_type", create_type=False),
            nullable=False,
        ),
        sa.Column("document_type", sa.String, nullable=True),
        sa.Column(
            "status",
            sa.Enum("queued", "processing", "completed", "failed",
                    name="export_task_status", create_type=False),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("progress_percentage", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("file_path", sa.String, nullable=True),
        sa.Column("file_size", sa.BigInteger, nullable=True),
        sa.Column("password_protected", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_export_tasks_project_status",
        "export_tasks",
        ["project_id", "status"],
    )

    # ---- 1.8 note_validation_results ----
    op.create_table(
        "note_validation_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("validation_timestamp", sa.DateTime, nullable=False),
        sa.Column("findings", sa.JSON, nullable=False),
        sa.Column("error_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("warning_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("info_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("validated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_note_validation_results_project_year",
        "note_validation_results",
        ["project_id", "year"],
    )


def downgrade() -> None:
    op.drop_index("idx_note_validation_results_project_year", table_name="note_validation_results")
    op.drop_table("note_validation_results")

    op.drop_index("idx_export_tasks_project_status", table_name="export_tasks")
    op.drop_table("export_tasks")

    op.drop_index("uq_audit_report_template_opinion_company_section", table_name="audit_report_template")
    op.drop_table("audit_report_template")

    op.drop_index("uq_audit_report_project_year", table_name="audit_report")
    op.drop_table("audit_report")

    op.drop_index("uq_disclosure_notes_project_year_section", table_name="disclosure_notes")
    op.drop_table("disclosure_notes")

    op.drop_index("idx_cfs_adjustments_project_year_category", table_name="cfs_adjustments")
    op.drop_table("cfs_adjustments")

    op.drop_index("uq_financial_report_project_year_type_code", table_name="financial_report")
    op.drop_table("financial_report")

    op.drop_index("uq_report_config_type_code_standard", table_name="report_config")
    op.drop_table("report_config")

    # Drop enums
    sa.Enum(name="export_task_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="export_task_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="report_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="company_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="opinion_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="note_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="source_template").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="content_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="cash_flow_category").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="financial_report_type").drop(op.get_bind(), checkfirst=True)
