"""Ledger Import: add raw_extra JSONB to four ledger tables [Sprint 2 Task 32a]

Revision ID: ledger_import_raw_extra_20260508
Revises: ledger_import_column_mapping_20260508
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'ledger_import_raw_extra_20260508'
down_revision = 'ledger_import_column_mapping_20260508'
branch_labels = None
depends_on = None

_TABLES = ('tb_balance', 'tb_ledger', 'tb_aux_balance', 'tb_aux_ledger')


def upgrade():
    for table in _TABLES:
        op.add_column(table, sa.Column('raw_extra', JSONB, nullable=True))


def downgrade():
    for table in _TABLES:
        op.drop_column(table, 'raw_extra')
