"""Add sync markers to disclosure_notes table for workpaper → module unidirectional sync.

按 design §12.1 推荐选项 A（底稿 → 模块单向同步）：
- last_sync_source: 'workpaper' / NULL（仅记录最近一次来源）
- last_sync_wp_id: FK → working_paper.id（最近一次同步的源底稿）
- last_sync_at: 同步时间
- last_sync_user_id: FK → users.id（触发同步的用户）

Index:
- idx_disclosure_notes_last_sync_wp (last_sync_wp_id) WHERE last_sync_wp_id IS NOT NULL

Revision ID: disclosure_note_sync_markers_20260526
Revises: workpaper_sheet_version_mapping_20260525
Create Date: 2026-05-26

Requirements: 3.11.5 §4.2（附注双源问题）+ design §12.1 推荐选项 A
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers
revision = "disclosure_note_sync_markers_20260526"
down_revision = "workpaper_sheet_version_mapping_20260525"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ─── 幂等性保护：检查列是否已存在 ──────────────────────────────────
    existing_cols = {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'disclosure_notes'"
            )
        ).fetchall()
    }

    if "last_sync_source" not in existing_cols:
        op.add_column(
            "disclosure_notes",
            sa.Column("last_sync_source", sa.String(50), nullable=True),
        )

    if "last_sync_wp_id" not in existing_cols:
        op.add_column(
            "disclosure_notes",
            sa.Column(
                "last_sync_wp_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("working_paper.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    if "last_sync_at" not in existing_cols:
        op.add_column(
            "disclosure_notes",
            sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "last_sync_user_id" not in existing_cols:
        op.add_column(
            "disclosure_notes",
            sa.Column(
                "last_sync_user_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    # ─── 部分索引：仅对已同步过的记录建索引（节省空间） ─────────────────
    existing_indexes = {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'disclosure_notes'"
            )
        ).fetchall()
    }
    if "idx_disclosure_notes_last_sync_wp" not in existing_indexes:
        op.create_index(
            "idx_disclosure_notes_last_sync_wp",
            "disclosure_notes",
            ["last_sync_wp_id"],
            postgresql_where=sa.text("last_sync_wp_id IS NOT NULL"),
        )


def downgrade() -> None:
    conn = op.get_bind()

    existing_indexes = {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'disclosure_notes'"
            )
        ).fetchall()
    }
    if "idx_disclosure_notes_last_sync_wp" in existing_indexes:
        op.drop_index(
            "idx_disclosure_notes_last_sync_wp",
            table_name="disclosure_notes",
        )

    # 删除列（逆序）
    existing_cols = {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'disclosure_notes'"
            )
        ).fetchall()
    }
    for col in ("last_sync_user_id", "last_sync_at", "last_sync_wp_id", "last_sync_source"):
        if col in existing_cols:
            op.drop_column("disclosure_notes", col)
