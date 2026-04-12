"""007 workpaper tables — 8张底稿相关表

Revision ID: 007
Revises: 006
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- 枚举类型 ----
    wp_template_status_enum = sa.Enum(
        "draft", "published", "deprecated",
        name="wp_template_status",
    )
    wp_template_status_enum.create(op.get_bind(), checkfirst=True)

    region_type_enum = sa.Enum(
        "formula", "manual", "ai_fill", "conclusion", "cross_ref",
        name="region_type",
    )
    region_type_enum.create(op.get_bind(), checkfirst=True)

    wp_status_enum = sa.Enum(
        "not_started", "in_progress", "draft_complete", "review_passed", "archived",
        name="wp_status",
    )
    wp_status_enum.create(op.get_bind(), checkfirst=True)

    wp_source_type_enum = sa.Enum(
        "template", "manual", "imported",
        name="wp_source_type",
    )
    wp_source_type_enum.create(op.get_bind(), checkfirst=True)

    wp_file_status_enum = sa.Enum(
        "draft", "edit_complete", "review_level1_passed", "review_level2_passed", "archived",
        name="wp_file_status",
    )
    wp_file_status_enum.create(op.get_bind(), checkfirst=True)

    review_comment_status_enum = sa.Enum(
        "open", "replied", "resolved",
        name="review_comment_status",
    )
    review_comment_status_enum.create(op.get_bind(), checkfirst=True)

    # ---- 1.1 wp_template ----
    op.create_table(
        "wp_template",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("template_code", sa.String, nullable=False),
        sa.Column("template_name", sa.String, nullable=False),
        sa.Column("audit_cycle", sa.String, nullable=True),
        sa.Column("applicable_standard", sa.String, nullable=True),
        sa.Column("version_major", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.Column("version_minor", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "published", "deprecated",
                    name="wp_template_status", create_type=False),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_wp_template_code_version",
        "wp_template",
        ["template_code", "version_major", "version_minor"],
        unique=True,
    )

    # ---- 1.2 wp_template_meta ----
    op.create_table(
        "wp_template_meta",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("wp_template.id"), nullable=False),
        sa.Column("range_name", sa.String, nullable=False),
        sa.Column(
            "region_type",
            sa.Enum("formula", "manual", "ai_fill", "conclusion", "cross_ref",
                    name="region_type", create_type=False),
            nullable=False,
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_wp_template_meta_template_id",
        "wp_template_meta",
        ["template_id"],
    )

    # ---- 1.3 wp_template_set ----
    op.create_table(
        "wp_template_set",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("set_name", sa.String, nullable=False, unique=True),
        sa.Column("template_codes", sa.JSON, nullable=True),
        sa.Column("applicable_audit_type", sa.String, nullable=True),
        sa.Column("applicable_standard", sa.String, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ---- 1.4 wp_index ----
    op.create_table(
        "wp_index",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("wp_code", sa.String, nullable=False),
        sa.Column("wp_name", sa.String, nullable=False),
        sa.Column("audit_cycle", sa.String, nullable=True),
        sa.Column("assigned_to", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewer", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("not_started", "in_progress", "draft_complete", "review_passed", "archived",
                    name="wp_status", create_type=False),
            server_default=sa.text("'not_started'"),
            nullable=False,
        ),
        sa.Column("cross_ref_codes", sa.JSON, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_wp_index_project_code",
        "wp_index",
        ["project_id", "wp_code"],
        unique=True,
    )

    # ---- 1.5 working_paper ----
    op.create_table(
        "working_paper",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("wp_index_id", UUID(as_uuid=True), sa.ForeignKey("wp_index.id"), nullable=False),
        sa.Column("file_path", sa.String, nullable=False),
        sa.Column(
            "source_type",
            sa.Enum("template", "manual", "imported",
                    name="wp_source_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("draft", "edit_complete", "review_level1_passed",
                    "review_level2_passed", "archived",
                    name="wp_file_status", create_type=False),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column("assigned_to", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewer", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("file_version", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.Column("last_parsed_at", sa.DateTime, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_working_paper_project_index",
        "working_paper",
        ["project_id", "wp_index_id"],
        unique=True,
    )

    # ---- 1.6 wp_cross_ref ----
    op.create_table(
        "wp_cross_ref",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("source_wp_id", UUID(as_uuid=True), sa.ForeignKey("working_paper.id"), nullable=False),
        sa.Column("target_wp_code", sa.String, nullable=False),
        sa.Column("cell_reference", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_wp_cross_ref_project_source",
        "wp_cross_ref",
        ["project_id", "source_wp_id"],
    )

    # ---- 1.7 wp_qc_results ----
    op.create_table(
        "wp_qc_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("working_paper_id", UUID(as_uuid=True), sa.ForeignKey("working_paper.id"), nullable=False),
        sa.Column("check_timestamp", sa.DateTime, nullable=False),
        sa.Column("findings", sa.JSON, nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("blocking_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("warning_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("info_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("checked_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_wp_qc_results_working_paper_id",
        "wp_qc_results",
        ["working_paper_id"],
    )

    # ---- 1.8 review_records ----
    op.create_table(
        "review_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("working_paper_id", UUID(as_uuid=True), sa.ForeignKey("working_paper.id"), nullable=False),
        sa.Column("cell_reference", sa.String, nullable=True),
        sa.Column("comment_text", sa.Text, nullable=False),
        sa.Column("commenter_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "replied", "resolved",
                    name="review_comment_status", create_type=False),
            server_default=sa.text("'open'"),
            nullable=False,
        ),
        sa.Column("reply_text", sa.Text, nullable=True),
        sa.Column("replier_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("replied_at", sa.DateTime, nullable=True),
        sa.Column("resolved_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_review_records_wp_status",
        "review_records",
        ["working_paper_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_review_records_wp_status", table_name="review_records")
    op.drop_table("review_records")

    op.drop_index("idx_wp_qc_results_working_paper_id", table_name="wp_qc_results")
    op.drop_table("wp_qc_results")

    op.drop_index("idx_wp_cross_ref_project_source", table_name="wp_cross_ref")
    op.drop_table("wp_cross_ref")

    op.drop_index("uq_working_paper_project_index", table_name="working_paper")
    op.drop_table("working_paper")

    op.drop_index("uq_wp_index_project_code", table_name="wp_index")
    op.drop_table("wp_index")

    op.drop_table("wp_template_set")

    op.drop_index("idx_wp_template_meta_template_id", table_name="wp_template_meta")
    op.drop_table("wp_template_meta")

    op.drop_index("uq_wp_template_code_version", table_name="wp_template")
    op.drop_table("wp_template")

    # Drop enums
    sa.Enum(name="review_comment_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="wp_file_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="wp_source_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="wp_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="region_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="wp_template_status").drop(op.get_bind(), checkfirst=True)
