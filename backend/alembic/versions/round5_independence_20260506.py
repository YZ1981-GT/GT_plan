"""Round 5 followup: annual_independence_declarations table

Revision ID: round5_independence_20260506
Revises: round5_eqcr_20260505

R5 任务 23 需求 12 — 年度独立性声明。

**架构决策**：
- R1 需求 10 规划了通用 ``independence_declarations`` 表
  （含 ``declaration_scope ∈ {'project','annual'}``），但 R1 尚未落库。
- 本轮先用独立表 ``annual_independence_declarations`` 承载年度声明，
  避免依赖 R1 未完成的表，也不在 ``users`` 表上加 ``metadata_`` JSONB
  （污染 User 表职责）。
- 当 R1 通用表建成后，执行一次性数据迁移脚本合并。

表结构：
- ``declarant_id`` FK → users.id
- ``declaration_year`` INT
- ``(declarant_id, declaration_year)`` 唯一约束
- ``answers`` JSONB 存 30+ 题答案
- ``risk_flagged_count`` 缓存有风险回答数（方便抽查排序）
- ``submitted_at`` TIMESTAMP
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "round5_independence_20260506"
down_revision = "round5_eqcr_20260505"
branch_labels = None
depends_on = None


def _inspector():
    bind = op.get_bind()
    return sa.inspect(bind)


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def upgrade() -> None:
    if not _has_table("annual_independence_declarations"):
        op.create_table(
            "annual_independence_declarations",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "declarant_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column("declaration_year", sa.Integer(), nullable=False),
            sa.Column("answers", sa.dialects.postgresql.JSONB(), nullable=False),
            sa.Column(
                "risk_flagged_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("submitted_at", sa.DateTime(), nullable=False),
            # --- mixins ---
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "declarant_id",
                "declaration_year",
                name="uq_annual_independence_declarant_year",
            ),
        )
        op.create_index(
            "idx_annual_independence_year",
            "annual_independence_declarations",
            ["declaration_year"],
            postgresql_where=sa.text("is_deleted = false"),
        )


def downgrade() -> None:
    if _has_table("annual_independence_declarations"):
        op.drop_index(
            "idx_annual_independence_year",
            table_name="annual_independence_declarations",
        )
        op.drop_table("annual_independence_declarations")
