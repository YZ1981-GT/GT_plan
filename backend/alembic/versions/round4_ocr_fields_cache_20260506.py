"""Refinement Round 4: add ocr_fields_cache JSONB to attachments

Revision ID: round4_ocr_fields_cache_20260506
Revises: round4_editing_lock_20260506

本迁移落地 Round 4 需求 12 的 OCR 字段缓存：

在 ``attachments`` 表新增 ``ocr_fields_cache`` JSONB 列，
用于缓存 OCR 字段提取结果，避免重复调用 OCR 引擎。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "round4_ocr_fields_cache_20260506"
down_revision = "round4_editing_lock_20260506"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _inspector():
    bind = op.get_bind()
    return sa.inspect(bind)


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    columns = {col["name"] for col in _inspector().get_columns(table_name)}
    return column_name in columns


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    if not _has_column("attachments", "ocr_fields_cache"):
        op.add_column(
            "attachments",
            sa.Column("ocr_fields_cache", sa.JSON(), nullable=True),
        )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    if _has_column("attachments", "ocr_fields_cache"):
        op.drop_column("attachments", "ocr_fields_cache")
