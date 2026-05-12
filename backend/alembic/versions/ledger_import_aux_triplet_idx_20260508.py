"""Ledger Import: add (project_id, year, account_code, aux_type, aux_code) composite index
to tb_aux_ledger and tb_aux_balance. [Sprint 6 Task S6-8]

原 idx_tb_aux_ledger_project_year_account_aux 只覆盖到 aux_type，
按三元组 (account_code, aux_type, aux_code) 精确查询时 aux_code 走字段扫描。
加 aux_code 到索引尾部可让跨维度类型（如"税率"同时出现在客户/项目下）的
精确穿透查询走索引。

Revision ID: ledger_import_aux_triplet_idx_20260508
Revises: ledger_import_raw_extra_20260508
"""
from alembic import op

revision = 'ledger_import_aux_triplet_idx_20260508'
down_revision = 'ledger_import_raw_extra_20260508'
branch_labels = None
depends_on = None


def upgrade():
    # tb_aux_ledger
    op.create_index(
        'idx_tb_aux_ledger_triplet',
        'tb_aux_ledger',
        ['project_id', 'year', 'account_code', 'aux_type', 'aux_code'],
        postgresql_where='is_deleted = false',
    )
    # tb_aux_balance
    op.create_index(
        'idx_tb_aux_balance_triplet',
        'tb_aux_balance',
        ['project_id', 'year', 'account_code', 'aux_type', 'aux_code'],
        postgresql_where='is_deleted = false',
    )


def downgrade():
    op.drop_index('idx_tb_aux_ledger_triplet', table_name='tb_aux_ledger')
    op.drop_index('idx_tb_aux_balance_triplet', table_name='tb_aux_balance')
