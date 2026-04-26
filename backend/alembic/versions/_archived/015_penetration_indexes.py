"""011 penetration indexes — 穿透查询性能优化索引

补充四表联查的核心查询路径索引，提升26万+行凭证表的查询性能。
分区表策略暂缓（需要重建表，风险大），先用索引+缓存优化。

Revision ID: 011
Revises: 010
Create Date: 2026-04-13 00:00:00.000000
"""

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tb_ledger 补充索引：按凭证号查询（点击凭证穿透到分录明细）
    op.create_index(
        "idx_tb_ledger_project_year_voucher",
        "tb_ledger",
        ["project_id", "year", "voucher_no"],
    )

    # tb_aux_ledger 补充索引：按辅助维度查询
    op.create_index(
        "idx_tb_aux_ledger_project_year_aux_type_code",
        "tb_aux_ledger",
        ["project_id", "year", "aux_type", "aux_code"],
    )

    # tb_aux_balance 补充索引：按辅助维度查询
    op.create_index(
        "idx_tb_aux_balance_project_year_aux_type",
        "tb_aux_balance",
        ["project_id", "year", "aux_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_tb_aux_balance_project_year_aux_type", table_name="tb_aux_balance")
    op.drop_index("idx_tb_aux_ledger_project_year_aux_type_code", table_name="tb_aux_ledger")
    op.drop_index("idx_tb_ledger_project_year_voucher", table_name="tb_ledger")
