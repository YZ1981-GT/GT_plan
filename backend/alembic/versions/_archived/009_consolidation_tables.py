"""009 consolidation_tables 集团合并相关表

Revision ID: 009
Revises: 008
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ========== 1. companies 表 ==========
    op.execute("CREATE TYPE consol_method AS ENUM ('full', 'equity', 'proportional')")
    op.create_table(
        "companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("company_code", sa.String, nullable=False),
        sa.Column("company_name", sa.String, nullable=False),
        sa.Column("parent_code", sa.String, nullable=True),
        sa.Column("ultimate_code", sa.String, nullable=False),
        sa.Column("consol_level", sa.Integer, server_default="0", nullable=False),
        sa.Column("shareholding", sa.Numeric(5, 2), nullable=True),
        sa.Column("consol_method", sa.Enum("full", "equity", "proportional", name="consol_method", create_type=False), nullable=True),
        sa.Column("acquisition_date", sa.Date, nullable=True),
        sa.Column("disposal_date", sa.Date, nullable=True),
        sa.Column("functional_currency", sa.String(3), server_default="'CNY'", nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_companies_project_code", "companies", ["project_id", "company_code"], unique=True)
    op.create_index("idx_companies_parent", "companies", ["parent_code"])

    # ========== 2. consol_scope 表 ==========
    op.execute("CREATE TYPE inclusion_reason AS ENUM ('subsidiary', 'associate', 'joint_venture', 'special_purpose')")
    op.execute("CREATE TYPE scope_change_type AS ENUM ('none', 'new_inclusion', 'exclusion', 'method_change')")
    op.create_table(
        "consol_scope",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("company_code", sa.String, nullable=False),
        sa.Column("is_included", sa.Boolean, server_default="true", nullable=False),
        sa.Column("inclusion_reason", sa.Enum("subsidiary", "associate", "joint_venture", "special_purpose", name="inclusion_reason", create_type=False), nullable=True),
        sa.Column("exclusion_reason", sa.Text, nullable=True),
        sa.Column("scope_change_type", sa.Enum("none", "new_inclusion", "exclusion", "method_change", name="scope_change_type", create_type=False), server_default="'none'", nullable=False),
        sa.Column("scope_change_description", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_consol_scope_unique", "consol_scope", ["project_id", "year", "company_code"], unique=True)

    # ========== 3. consol_trial 表 ==========
    op.execute("CREATE TYPE account_category AS ENUM ('asset', 'liability', 'equity', 'revenue', 'expense')")
    op.create_table(
        "consol_trial",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("standard_account_code", sa.String, nullable=False),
        sa.Column("account_name", sa.String, nullable=True),
        sa.Column("account_category", sa.Enum("asset", "liability", "equity", "revenue", "expense", name="account_category", create_type=False), nullable=True),
        sa.Column("individual_sum", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("consol_adjustment", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("consol_elimination", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("consol_amount", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_consol_trial_unique", "consol_trial", ["project_id", "year", "standard_account_code"], unique=True)

    # ========== 4. elimination_entries 表 ==========
    op.execute("CREATE TYPE elimination_entry_type AS ENUM ('equity', 'internal_trade', 'internal_ar_ap', 'unrealized_profit', 'other')")
    op.execute("CREATE TYPE review_status_enum AS ENUM ('draft', 'pending_review', 'approved', 'rejected')")
    op.create_table(
        "elimination_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("entry_no", sa.String, nullable=False),
        sa.Column("entry_type", sa.Enum("equity", "internal_trade", "internal_ar_ap", "unrealized_profit", "other", name="elimination_entry_type", create_type=False), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("account_code", sa.String, nullable=False),
        sa.Column("account_name", sa.String, nullable=True),
        sa.Column("debit_amount", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("credit_amount", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("entry_group_id", UUID(as_uuid=True), nullable=False),
        sa.Column("related_company_codes", JSONB, nullable=True),
        sa.Column("is_continuous", sa.Boolean, server_default="false", nullable=False),
        sa.Column("prior_year_entry_id", UUID(as_uuid=True), nullable=True),
        sa.Column("review_status", sa.Enum("draft", "pending_review", "approved", "rejected", name="review_status_enum", create_type=False), server_default="'draft'", nullable=False),
        sa.Column("reviewer_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("idx_elimination_project_year_type", "elimination_entries", ["project_id", "year", "entry_type"])
    op.create_index("idx_elimination_entry_group", "elimination_entries", ["entry_group_id"])
    op.create_index("idx_elimination_entry_no", "elimination_entries", ["entry_no"])

    # ========== 5. internal_trade 表 ==========
    op.execute("CREATE TYPE trade_type AS ENUM ('goods', 'services', 'assets', 'other')")
    op.create_table(
        "internal_trade",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("seller_company_code", sa.String, nullable=False),
        sa.Column("buyer_company_code", sa.String, nullable=False),
        sa.Column("trade_type", sa.Enum("goods", "services", "assets", "other", name="trade_type", create_type=False), nullable=True),
        sa.Column("trade_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("cost_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("unrealized_profit", sa.Numeric(20, 2), nullable=True),
        sa.Column("inventory_remaining_ratio", sa.Numeric(5, 4), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_internal_trade_project_year", "internal_trade", ["project_id", "year"])

    # ========== 6. internal_ar_ap 表 ==========
    op.execute("CREATE TYPE reconciliation_status AS ENUM ('matched', 'unmatched', 'adjusted')")
    op.create_table(
        "internal_ar_ap",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("debtor_company_code", sa.String, nullable=False),
        sa.Column("creditor_company_code", sa.String, nullable=False),
        sa.Column("debtor_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("creditor_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("difference_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("difference_reason", sa.Text, nullable=True),
        sa.Column("reconciliation_status", sa.Enum("matched", "unmatched", "adjusted", name="reconciliation_status", create_type=False), server_default="'unmatched'", nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_internal_ar_ap_project_year", "internal_ar_ap", ["project_id", "year"])

    # ========== 7. goodwill_calc 表 ==========
    op.create_table(
        "goodwill_calc",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("subsidiary_company_code", sa.String, nullable=False),
        sa.Column("acquisition_date", sa.Date, nullable=True),
        sa.Column("acquisition_cost", sa.Numeric(20, 2), nullable=True),
        sa.Column("identifiable_net_assets_fv", sa.Numeric(20, 2), nullable=True),
        sa.Column("parent_share_ratio", sa.Numeric(5, 4), nullable=True),
        sa.Column("goodwill_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("accumulated_impairment", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("current_year_impairment", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("carrying_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("is_negative_goodwill", sa.Boolean, server_default="false", nullable=False),
        sa.Column("negative_goodwill_treatment", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_goodwill_unique", "goodwill_calc", ["project_id", "year", "subsidiary_company_code"], unique=True)

    # ========== 8. minority_interest 表 ==========
    op.create_table(
        "minority_interest",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("subsidiary_company_code", sa.String, nullable=False),
        sa.Column("subsidiary_net_assets", sa.Numeric(20, 2), nullable=True),
        sa.Column("minority_share_ratio", sa.Numeric(5, 4), nullable=True),
        sa.Column("minority_equity", sa.Numeric(20, 2), nullable=True),
        sa.Column("subsidiary_net_profit", sa.Numeric(20, 2), nullable=True),
        sa.Column("minority_profit", sa.Numeric(20, 2), nullable=True),
        sa.Column("minority_equity_opening", sa.Numeric(20, 2), nullable=True),
        sa.Column("minority_equity_movement", JSONB, nullable=True),
        sa.Column("is_excess_loss", sa.Boolean, server_default="false", nullable=False),
        sa.Column("excess_loss_amount", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_minority_interest_unique", "minority_interest", ["project_id", "year", "subsidiary_company_code"], unique=True)

    # ========== 9. forex_translation 表 ==========
    op.create_table(
        "forex_translation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("company_code", sa.String, nullable=False),
        sa.Column("functional_currency", sa.String(3), nullable=False),
        sa.Column("reporting_currency", sa.String(3), server_default="'CNY'", nullable=True),
        sa.Column("bs_closing_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("pl_average_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("equity_historical_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("opening_retained_earnings_translated", sa.Numeric(20, 2), nullable=True),
        sa.Column("translation_difference", sa.Numeric(20, 2), nullable=True),
        sa.Column("translation_difference_oci", sa.Numeric(20, 2), nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_forex_translation_unique", "forex_translation", ["project_id", "year", "company_code"], unique=True)

    # ========== 10. component_auditors 表 ==========
    op.execute("CREATE TYPE competence_rating AS ENUM ('reliable', 'additional_procedures_needed', 'unreliable')")
    op.create_table(
        "component_auditors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("company_code", sa.String, nullable=False),
        sa.Column("firm_name", sa.String, nullable=False),
        sa.Column("contact_person", sa.String, nullable=True),
        sa.Column("contact_info", sa.String, nullable=True),
        sa.Column("competence_rating", sa.Enum("reliable", "additional_procedures_needed", "unreliable", name="competence_rating", create_type=False), nullable=True),
        sa.Column("rating_basis", sa.Text, nullable=True),
        sa.Column("independence_confirmed", sa.Boolean, server_default="false", nullable=False),
        sa.Column("independence_date", sa.Date, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_component_auditors_unique", "component_auditors", ["project_id", "company_code"], unique=True)

    # ========== 11. component_instructions 表 ==========
    op.execute("CREATE TYPE instruction_status AS ENUM ('draft', 'sent', 'acknowledged')")
    op.create_table(
        "component_instructions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("component_auditor_id", UUID(as_uuid=True), sa.ForeignKey("component_auditors.id"), nullable=False),
        sa.Column("instruction_date", sa.Date, nullable=True),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("materiality_level", sa.Numeric(20, 2), nullable=True),
        sa.Column("audit_scope_description", sa.Text, nullable=True),
        sa.Column("reporting_format", sa.Text, nullable=True),
        sa.Column("special_attention_items", sa.Text, nullable=True),
        sa.Column("instruction_file_path", sa.String, nullable=True),
        sa.Column("status", sa.Enum("draft", "sent", "acknowledged", name="instruction_status", create_type=False), server_default="'draft'", nullable=False),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("idx_component_instructions_project_auditor", "component_instructions", ["project_id", "component_auditor_id"])

    # ========== 12. component_results 表 ==========
    op.execute("CREATE TYPE opinion_type_enum AS ENUM ('unqualified', 'qualified', 'adverse', 'disclaimer')")
    op.execute("CREATE TYPE evaluation_status AS ENUM ('pending', 'accepted', 'requires_followup')")
    op.create_table(
        "component_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("component_auditor_id", UUID(as_uuid=True), sa.ForeignKey("component_auditors.id"), nullable=False),
        sa.Column("received_date", sa.Date, nullable=True),
        sa.Column("opinion_type", sa.Enum("unqualified", "qualified", "adverse", "disclaimer", name="opinion_type_enum", create_type=False), nullable=True),
        sa.Column("identified_misstatements", JSONB, nullable=True),
        sa.Column("significant_findings", sa.Text, nullable=True),
        sa.Column("result_file_path", sa.String, nullable=True),
        sa.Column("group_team_evaluation", sa.Text, nullable=True),
        sa.Column("needs_additional_procedures", sa.Boolean, server_default="false", nullable=False),
        sa.Column("evaluation_status", sa.Enum("pending", "accepted", "requires_followup", name="evaluation_status", create_type=False), server_default="'pending'", nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_component_results_project_auditor", "component_results", ["project_id", "component_auditor_id"])


def downgrade() -> None:
    # 删除 tables
    op.drop_table("component_results")
    op.drop_table("component_instructions")
    op.drop_table("component_auditors")
    op.drop_table("forex_translation")
    op.drop_table("minority_interest")
    op.drop_table("goodwill_calc")
    op.drop_table("internal_ar_ap")
    op.drop_table("internal_trade")
    op.drop_table("elimination_entries")
    op.drop_table("consol_trial")
    op.drop_table("consol_scope")
    op.drop_table("companies")

    # 删除枚举类型
    sa.Enum(name="evaluation_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="opinion_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="instruction_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="competence_rating").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reconciliation_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="trade_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="review_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="elimination_entry_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="account_category").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="scope_change_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="inclusion_reason").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="consol_method").drop(op.get_bind(), checkfirst=True)
