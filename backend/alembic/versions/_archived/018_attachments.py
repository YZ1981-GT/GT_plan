"""013 attachments — 附件管理表 + 附件底稿关联表

Revision ID: 013
Revises: 012
Create Date: 2026-04-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("paperless_document_id", sa.Integer, nullable=True),
        sa.Column("ocr_status", sa.String(20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("ocr_text", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_attachments_project", "attachments", ["project_id"])
    op.create_index("idx_attachments_ocr_status", "attachments", ["project_id", "ocr_status"])
    op.create_index("idx_attachments_paperless", "attachments", ["paperless_document_id"])

    op.create_table(
        "attachment_working_paper",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("attachment_id", UUID(as_uuid=True), sa.ForeignKey("attachments.id"), nullable=False),
        sa.Column("wp_id", UUID(as_uuid=True), sa.ForeignKey("working_paper.id"), nullable=False),
        sa.Column("association_type", sa.String(50), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_attachment_wp_attachment", "attachment_working_paper", ["attachment_id"])
    op.create_index("idx_attachment_wp_wp", "attachment_working_paper", ["wp_id"])


def downgrade() -> None:
    op.drop_index("idx_attachment_wp_wp", table_name="attachment_working_paper")
    op.drop_index("idx_attachment_wp_attachment", table_name="attachment_working_paper")
    op.drop_table("attachment_working_paper")
    op.drop_index("idx_attachments_paperless", table_name="attachments")
    op.drop_index("idx_attachments_ocr_status", table_name="attachments")
    op.drop_index("idx_attachments_project", table_name="attachments")
    op.drop_table("attachments")
