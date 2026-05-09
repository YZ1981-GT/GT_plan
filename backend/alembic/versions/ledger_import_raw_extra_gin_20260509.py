"""Ledger Import: add GIN index on raw_extra JSONB for fast key lookup.

Sprint 7: 用户需要查询 raw_extra 里的非关键列（如"来源系统"/"部门"），
无索引时全表扫 JSONB 性能差。GIN 索引支持 @> / ? / ?| 等 JSONB 操作符。

Revision ID: ledger_import_raw_extra_gin_20260509
Revises: ledger_import_aux_triplet_idx_20260508
"""
from alembic import op

revision = 'ledger_import_raw_extra_gin_20260509'
down_revision = 'ledger_import_aux_triplet_idx_20260508'
branch_labels = None
depends_on = None

_TABLES = ('tb_balance', 'tb_ledger', 'tb_aux_balance', 'tb_aux_ledger')


def upgrade():
    for table in _TABLES:
        op.create_index(
            f'idx_{table}_raw_extra_gin',
            table,
            ['raw_extra'],
            postgresql_using='gin',
            postgresql_where='raw_extra IS NOT NULL',
        )


def downgrade():
    for table in _TABLES:
        op.drop_index(f'idx_{table}_raw_extra_gin', table_name=table)
