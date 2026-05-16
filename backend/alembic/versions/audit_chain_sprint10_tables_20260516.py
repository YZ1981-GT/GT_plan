"""Sprint 10: 新增 4 张表 (group_note_templates / note_section_locks / data_snapshots / note_section_templates)

Revision ID: audit_chain_sprint10_tables_20260516
Revises: export_logs_20260516
Create Date: 2026-05-16

Requirements: 44.1-44.6, 49.1-49.8, 52.1-52.7, 53.1-53.7
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = "audit_chain_sprint10_tables_20260516"
down_revision = "export_logs_20260516"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 集团附注模板表 (Requirements: 52.1-52.7)
    op.create_table(
        "group_note_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("template_data", JSONB, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. 附注章节编辑锁表 (Requirements: 44.1-44.6)
    op.create_table(
        "note_section_locks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("section_code", sa.String(100), nullable=False),
        sa.Column("locked_by", UUID(as_uuid=True), nullable=False),
        sa.Column("locked_by_name", sa.String(100), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_note_section_locks_active",
        "note_section_locks",
        ["project_id", "year", "section_code"],
        postgresql_where=sa.text("released_at IS NULL"),
    )

    # 3. 数据快照表 (Requirements: 53.1-53.7)
    op.create_table(
        "data_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("snapshot_data", JSONB, nullable=True),
        sa.Column("data_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_data_snapshots_project_year",
        "data_snapshots",
        ["project_id", "year"],
    )

    # 4. 附注章节模板库表 (Requirements: 49.1-49.8)
    op.create_table(
        "note_section_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("template_data", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("note_section_templates")
    op.drop_table("data_snapshots")
    op.drop_table("note_section_locks")
    op.drop_table("group_note_templates")
