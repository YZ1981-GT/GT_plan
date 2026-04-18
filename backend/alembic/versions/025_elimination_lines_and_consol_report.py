"""018 添加 elimination_entries.lines 列及合并报表相关表

Revision ID: 018
Revises: 017_ai_chat
Create Date: 2025-04-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加 lines 列到 elimination_entries 表
    op.add_column(
        'elimination_entries',
        sa.Column('lines', JSONB, nullable=True)
    )
    op.alter_column('elimination_entries', 'debit_amount', server_default=None)
    op.alter_column('elimination_entries', 'credit_amount', server_default=None)


def downgrade() -> None:
    op.drop_column('elimination_entries', 'lines')
