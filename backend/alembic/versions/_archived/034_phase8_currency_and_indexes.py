"""Phase 8: Add currency_code to trial_balance + composite indexes

Revision ID: 034
Revises: 033
Create Date: 2026-04-19

Changes:
- trial_balance: add currency_code VARCHAR(3) DEFAULT 'CNY'
- 5 composite indexes for core query paths
"""

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # 1. trial_balance 添加 currency_code 字段
    op.add_column(
        "trial_balance",
        sa.Column(
            "currency_code",
            sa.String(3),
            server_default="CNY",
            nullable=False,
        ),
    )

    # 2. trial_balance currency_code 索引
    op.create_index(
        "idx_trial_balance_currency_code",
        "trial_balance",
        ["currency_code"],
    )

    # 3. 核心查询路径复合索引
    op.create_index(
        "idx_trial_balance_project_year_std_code",
        "trial_balance",
        ["project_id", "year", "standard_account_code"],
    )
    op.create_index(
        "idx_tb_balance_project_year_deleted",
        "tb_balance",
        ["project_id", "year", "is_deleted"],
    )
    op.create_index(
        "idx_adjustments_project_year_account_code",
        "adjustments",
        ["project_id", "year", "account_code"],
    )
    # import_batches 已在 ORM 模型中定义了该索引，此处用 IF NOT EXISTS 兜底
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_import_batches_project_year "
            "ON import_batches (project_id, year)"
        )
    )


def downgrade() -> None:
    op.drop_index("idx_import_batches_project_year", "import_batches")
    op.drop_index("idx_adjustments_project_year_account_code", "adjustments")
    op.drop_index("idx_tb_balance_project_year_deleted", "tb_balance")
    op.drop_index("idx_trial_balance_project_year_std_code", "trial_balance")
    op.drop_index("idx_trial_balance_currency_code", "trial_balance")
    op.drop_column("trial_balance", "currency_code")
