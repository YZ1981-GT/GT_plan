"""创建 chain_executions 表 — 全链路执行记录

Requirements: 1.10, 9.1, 9.2

Revision ID: audit_chain_executions_20260515
Revises: view_refactor_creator_chain_20260520
Create Date: 2026-05-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "audit_chain_executions_20260515"
down_revision = "view_refactor_creator_chain_20260520"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chain_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("steps", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("trigger_type", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("triggered_by", sa.String(36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_duration_ms", sa.Integer, nullable=True),
        sa.Column("snapshot_before", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_chain_executions_project_year",
        "chain_executions",
        ["project_id", "year"],
    )


def downgrade() -> None:
    op.drop_index("ix_chain_executions_project_year", table_name="chain_executions")
    op.drop_table("chain_executions")
