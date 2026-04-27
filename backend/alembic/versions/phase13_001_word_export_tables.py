"""Phase 13: Word 导出表 — word_export_task / word_export_task_versions / report_snapshot

Revision ID: phase13_001
Revises: 001_consolidated
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "phase13_001"
down_revision = "001_consolidated"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # word_export_task — Word导出主任务
    op.create_table(
        "word_export_task",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("doc_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), server_default="draft", nullable=False),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("template_type", sa.String(20), nullable=True),
        sa.Column("snapshot_id", UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_word_export_task_project", "word_export_task", ["project_id", "doc_type"])
    op.create_index("idx_word_export_task_status", "word_export_task", ["project_id", "status"])

    # word_export_task_versions — 版本快照
    op.create_table(
        "word_export_task_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("word_export_task_id", UUID(as_uuid=True), sa.ForeignKey("word_export_task.id"), nullable=False),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_word_export_versions_task", "word_export_task_versions", ["word_export_task_id", "version_no"])

    # report_snapshot — 报表数据快照
    op.create_table(
        "report_snapshot",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("report_type", sa.String(10), nullable=False),
        sa.Column("generated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("data", JSONB, nullable=True),
        sa.Column("source_trial_balance_hash", sa.String(64), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("idx_report_snapshot_project_year_type", "report_snapshot", ["project_id", "year", "report_type"])


def downgrade() -> None:
    op.drop_table("report_snapshot")
    op.drop_table("word_export_task_versions")
    op.drop_table("word_export_task")
