"""创建 export_logs 表 — 导出日志

Requirements: 9.5

Revision ID: export_logs_20260516
Revises: note_account_mappings_20260516
Create Date: 2026-05-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "export_logs_20260516"
down_revision = "note_account_mappings_20260516"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("export_type", sa.String(20), nullable=False, comment="excel/word/package"),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("exported_by", sa.String(36), nullable=False),
        sa.Column("consistency_result", sa.JSON, nullable=True),
        sa.Column("data_hash", sa.String(64), nullable=True, comment="SHA-256 of exported data"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_export_logs_project_year", "export_logs", ["project_id", "year"])


def downgrade() -> None:
    op.drop_index("idx_export_logs_project_year")
    op.drop_table("export_logs")
