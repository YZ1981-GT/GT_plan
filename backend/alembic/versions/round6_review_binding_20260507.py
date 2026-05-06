"""Refinement Round 6: ReviewRecord conversation_id binding

Revision ID: round6_review_binding_20260507
Revises: round6_qc_rule_definitions_20260507

为 ``review_records`` 表新增 ``conversation_id`` 列（UUID, nullable），
外键指向 ``review_conversations.id``，用于将复核批注关联到多轮讨论链。

遵循 ``backend/alembic/MIGRATION_GUIDE.md`` 的幂等原则：使用 inspector 检查
列是否已存在后再添加。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "round6_review_binding_20260507"
down_revision = "round6_qc_rule_definitions_20260507"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _inspector():
    bind = op.get_bind()
    return sa.inspect(bind)


def _has_column(table_name: str, column_name: str) -> bool:
    if table_name not in _inspector().get_table_names():
        return False
    columns = {col["name"] for col in _inspector().get_columns(table_name)}
    return column_name in columns


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    if not _has_column("review_records", "conversation_id"):
        op.add_column(
            "review_records",
            sa.Column(
                "conversation_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                comment="关联的多轮讨论链（可选）",
            ),
        )
        op.create_foreign_key(
            "fk_review_records_conversation_id",
            "review_records",
            "review_conversations",
            ["conversation_id"],
            ["id"],
        )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    if _has_column("review_records", "conversation_id"):
        op.drop_constraint(
            "fk_review_records_conversation_id",
            "review_records",
            type_="foreignkey",
        )
        op.drop_column("review_records", "conversation_id")
