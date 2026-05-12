"""Sprint 8 UX: add version column to import_jobs for optimistic locking.

Revision ID: sprint8_import_job_version_20260510
Revises: ledger_aux_balance_summary_20260509
"""
from alembic import op
import sqlalchemy as sa


revision = "sprint8_import_job_version_20260510"
down_revision = "ledger_aux_balance_summary_20260509"
branch_labels = None
depends_on = None


def upgrade():
    # 加 version 列，默认 0，历史行也会回填 0
    op.add_column(
        "import_jobs",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade():
    op.drop_column("import_jobs", "version")
