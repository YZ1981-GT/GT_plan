"""Ledger: create tb_aux_balance_summary materialized table.

Sprint 7: rebuild_aux_balance_summary 会填充此表，前端辅助余额树形视图
直接查汇总表渲染（避免加载 12 万行原始数据）；早期 archived 迁移中曾有
这张表，但被清理后未回落到 baseline，PG 重建环境中缺失。

Revision ID: ledger_aux_balance_summary_20260509
Revises: ledger_import_raw_extra_gin_20260509
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'ledger_aux_balance_summary_20260509'
down_revision = 'ledger_import_raw_extra_gin_20260509'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tb_aux_balance_summary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("dim_type", sa.String(length=100), nullable=True),
        sa.Column("account_code", sa.String(length=64), nullable=False),
        sa.Column("account_name", sa.String(length=255), nullable=True),
        sa.Column("aux_code", sa.String(length=255), nullable=True),
        sa.Column("aux_name", sa.String(length=255), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opening_balance", sa.Numeric(20, 2), nullable=True),
        sa.Column("debit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("credit_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("closing_balance", sa.Numeric(20, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "idx_tb_aux_balance_summary_project_year_dim",
        "tb_aux_balance_summary",
        ["project_id", "year", "dim_type"],
    )
    op.create_index(
        "idx_tb_aux_balance_summary_project_year_account",
        "tb_aux_balance_summary",
        ["project_id", "year", "account_code"],
    )


def downgrade():
    op.drop_index("idx_tb_aux_balance_summary_project_year_account",
                  table_name="tb_aux_balance_summary")
    op.drop_index("idx_tb_aux_balance_summary_project_year_dim",
                  table_name="tb_aux_balance_summary")
    op.drop_table("tb_aux_balance_summary")
