"""014 extension tables — Phase 8 扩展表结构

包含：
- accounting_standards 会计准则表 (Task 1.1)
- users 表扩展 language 字段 (Task 1.2)
- projects 表扩展 audit_type 枚举 + accounting_standard FK (Task 1.3, 1.8)
- signature_records 签名记录表 (Task 1.4)
- wp_template_custom 自定义模板表 (Task 1.5)
- regulatory_filing 监管备案表 (Task 1.6)
- ai_plugins AI插件表 (补充)

Revision ID: 014
Revises: 013
Create Date: 2026-04-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ================================================================
    # 1.1 accounting_standards
    # ================================================================
    op.create_table(
        "accounting_standards",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("standard_code", sa.String(20), unique=True, nullable=False),
        sa.Column("standard_name", sa.String(100), nullable=False),
        sa.Column("standard_description", sa.Text, nullable=True),
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_accounting_standards_code", "accounting_standards", ["standard_code"])
    op.create_index("idx_accounting_standards_active", "accounting_standards", ["is_active"])

    # ================================================================
    # 1.2 users 表扩展 language 字段
    # ================================================================
    op.add_column("users", sa.Column("language", sa.String(10), server_default=sa.text("'zh-CN'"), nullable=False))

    # ================================================================
    # 1.3 projects 表扩展 audit_type（新增枚举值通过 ALTER TYPE）
    # 1.8 projects 表添加 accounting_standard FK
    # ================================================================
    # 注意：PostgreSQL ALTER TYPE ADD VALUE 不能在事务中执行
    # 使用 op.execute 直接执行
    try:
        op.execute("ALTER TYPE projecttype ADD VALUE IF NOT EXISTS 'special_audit'")
        op.execute("ALTER TYPE projecttype ADD VALUE IF NOT EXISTS 'ipo_audit'")
        op.execute("ALTER TYPE projecttype ADD VALUE IF NOT EXISTS 'internal_control_audit'")
        op.execute("ALTER TYPE projecttype ADD VALUE IF NOT EXISTS 'capital_verification'")
        op.execute("ALTER TYPE projecttype ADD VALUE IF NOT EXISTS 'tax_audit'")
    except Exception:
        pass  # SQLite 不支持 ALTER TYPE

    op.add_column("projects", sa.Column(
        "accounting_standard_id", UUID(as_uuid=True),
        sa.ForeignKey("accounting_standards.id"), nullable=True,
    ))

    # ================================================================
    # 1.4 signature_records
    # ================================================================
    op.create_table(
        "signature_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("object_type", sa.String(50), nullable=False),
        sa.Column("object_id", UUID(as_uuid=True), nullable=False),
        sa.Column("signer_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signature_level", sa.String(20), nullable=False),
        sa.Column("signature_data", JSONB, nullable=True),
        sa.Column("signature_timestamp", sa.DateTime, nullable=False),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_signature_records_object", "signature_records", ["object_type", "object_id"])
    op.create_index("idx_signature_records_signer", "signature_records", ["signer_id"])

    # ================================================================
    # 1.5 wp_template_custom
    # ================================================================
    op.create_table(
        "wp_template_custom",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("template_name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("template_file_path", sa.String(500), nullable=False),
        sa.Column("is_published", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_wp_template_custom_user", "wp_template_custom", ["user_id"])
    op.create_index("idx_wp_template_custom_category", "wp_template_custom", ["category"])
    op.create_index("idx_wp_template_custom_published", "wp_template_custom", ["is_published"])

    # ================================================================
    # 1.6 regulatory_filing
    # ================================================================
    op.create_table(
        "regulatory_filing",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("filing_type", sa.String(50), nullable=False),
        sa.Column("filing_status", sa.String(50), nullable=False),
        sa.Column("submission_data", JSONB, nullable=True),
        sa.Column("response_data", JSONB, nullable=True),
        sa.Column("submitted_at", sa.DateTime, nullable=True),
        sa.Column("responded_at", sa.DateTime, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_regulatory_filing_project", "regulatory_filing", ["project_id"])
    op.create_index("idx_regulatory_filing_type", "regulatory_filing", ["filing_type"])
    op.create_index("idx_regulatory_filing_status", "regulatory_filing", ["filing_status"])

    # ================================================================
    # 补充：ai_plugins
    # ================================================================
    op.create_table(
        "ai_plugins",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("plugin_id", sa.String(100), unique=True, nullable=False),
        sa.Column("plugin_name", sa.String(200), nullable=False),
        sa.Column("plugin_version", sa.String(20), nullable=False),
        sa.Column("plugin_description", sa.Text, nullable=True),
        sa.Column("is_enabled", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_ai_plugins_id", "ai_plugins", ["plugin_id"])
    op.create_index("idx_ai_plugins_enabled", "ai_plugins", ["is_enabled"])


def downgrade() -> None:
    op.drop_index("idx_ai_plugins_enabled", table_name="ai_plugins")
    op.drop_index("idx_ai_plugins_id", table_name="ai_plugins")
    op.drop_table("ai_plugins")

    op.drop_index("idx_regulatory_filing_status", table_name="regulatory_filing")
    op.drop_index("idx_regulatory_filing_type", table_name="regulatory_filing")
    op.drop_index("idx_regulatory_filing_project", table_name="regulatory_filing")
    op.drop_table("regulatory_filing")

    op.drop_index("idx_wp_template_custom_published", table_name="wp_template_custom")
    op.drop_index("idx_wp_template_custom_category", table_name="wp_template_custom")
    op.drop_index("idx_wp_template_custom_user", table_name="wp_template_custom")
    op.drop_table("wp_template_custom")

    op.drop_index("idx_signature_records_signer", table_name="signature_records")
    op.drop_index("idx_signature_records_object", table_name="signature_records")
    op.drop_table("signature_records")

    op.drop_column("projects", "accounting_standard_id")
    op.drop_column("users", "language")

    op.drop_index("idx_accounting_standards_active", table_name="accounting_standards")
    op.drop_index("idx_accounting_standards_code", table_name="accounting_standards")
    op.drop_table("accounting_standards")
