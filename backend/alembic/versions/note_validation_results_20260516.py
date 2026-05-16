"""创建 note_validation_results 表 — 附注校验结果

Requirements: 22.7

Revision ID: note_validation_results_20260516
Revises: audit_chain_executions_20260515
Create Date: 2026-05-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "note_validation_results_20260516"
down_revision = "audit_chain_executions_20260515"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note_validation_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("section_code", sa.String(100), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("rule_expression", sa.Text, nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("expected_value", sa.Numeric(20, 4), nullable=True),
        sa.Column("actual_value", sa.Numeric(20, 4), nullable=True),
        sa.Column("diff_amount", sa.Numeric(20, 4), nullable=True),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_note_validation_results_project_year",
        "note_validation_results",
        ["project_id", "year"],
    )


def downgrade() -> None:
    op.drop_index("ix_note_validation_results_project_year")
    op.drop_table("note_validation_results")
