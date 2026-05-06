"""Refinement Round 7: section_progress GIN index

Revision ID: round7_section_progress_gin_20260507
Revises: round6_review_binding_20260507

为 ``archive_jobs.section_progress`` JSONB 列添加 GIN 索引，
加速按章节状态查询归档作业进度（如"查找所有 gate 步骤失败的作业"）。

遵循 ``backend/alembic/MIGRATION_GUIDE.md`` 的幂等原则：使用 inspector 检查
索引是否已存在后再创建。仅 PostgreSQL 支持 GIN 索引。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "round7_section_progress_gin_20260507"
down_revision = "round6_review_binding_20260507"
branch_labels = None
depends_on = None

INDEX_NAME = "idx_archive_jobs_section_progress_gin"
TABLE_NAME = "archive_jobs"
COLUMN_NAME = "section_progress"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _index_exists(index_name: str) -> bool:
    """检查索引是否已存在（兼容 PG 和 SQLite）。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE_NAME not in inspector.get_table_names():
        return False
    indexes = inspector.get_indexes(TABLE_NAME)
    return any(idx["name"] == index_name for idx in indexes)


def _is_postgresql() -> bool:
    """检查当前数据库是否为 PostgreSQL。"""
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    if not _is_postgresql():
        # GIN 索引仅 PostgreSQL 支持，SQLite 跳过
        return

    if not _index_exists(INDEX_NAME):
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            [COLUMN_NAME],
            postgresql_using="gin",
        )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    if not _is_postgresql():
        return

    if _index_exists(INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
