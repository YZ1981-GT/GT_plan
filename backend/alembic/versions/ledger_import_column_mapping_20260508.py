"""Ledger Import: import_column_mapping_history table [Sprint 2 Task 30]

Revision ID: ledger_import_column_mapping_20260508
Revises: round7_clients_20260508
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'ledger_import_column_mapping_20260508'
down_revision = 'round7_clients_20260508'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'import_column_mapping_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('software_fingerprint', sa.String(100), nullable=False),
        sa.Column('table_type', sa.String(30), nullable=False),
        sa.Column('column_mapping', JSONB, nullable=False),
        sa.Column('used_count', sa.Integer, nullable=False, server_default='1'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index(
        'idx_icmh_project_fingerprint',
        'import_column_mapping_history',
        ['project_id', 'software_fingerprint'],
    )


def downgrade():
    op.drop_table('import_column_mapping_history')
