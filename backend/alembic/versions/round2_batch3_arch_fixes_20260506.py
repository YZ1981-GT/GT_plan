"""Round 2 Batch 3: Architecture fixes (4 schema changes)

Revision ID: round2_batch3_arch_fixes_20260506
Revises: round2_budget_handover_20260510

Schema changes:
1. staff_members.role_level (String(20), nullable) + data backfill
2. word_export_task.cache_key (String(64), nullable) + index
3. projects.risk_level (String(10), nullable)
4. projects.risk_level_updated_at (DateTime, nullable)

Follows idempotent pattern: check _has_column before adding.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "round2_batch3_arch_fixes_20260506"
down_revision = "round2_budget_handover_20260510"
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
    cols = {c["name"] for c in _inspector().get_columns(table_name)}
    return column_name in cols


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    indexes = {ix["name"] for ix in _inspector().get_indexes(table_name)}
    return index_name in indexes


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ============== Fix 1: staff_members.role_level ========================
    if _has_table("staff_members"):
        if not _has_column("staff_members", "role_level"):
            op.add_column(
                "staff_members",
                sa.Column("role_level", sa.String(20), nullable=True,
                          comment="费率等级: partner/manager/senior/auditor/intern"),
            )
            # Backfill existing rows based on title
            bind = op.get_bind()
            bind.execute(sa.text("""
                UPDATE staff_members SET role_level = CASE title
                    WHEN '合伙人' THEN 'partner'
                    WHEN '总监' THEN 'manager'
                    WHEN '高级经理' THEN 'manager'
                    WHEN '经理' THEN 'manager'
                    WHEN '高级审计员' THEN 'senior'
                    WHEN '审计员' THEN 'auditor'
                    WHEN '实习生' THEN 'intern'
                    ELSE NULL
                END
            """))

    # ============== Fix 2: word_export_task.cache_key ======================
    if _has_table("word_export_task"):
        if not _has_column("word_export_task", "cache_key"):
            op.add_column(
                "word_export_task",
                sa.Column("cache_key", sa.String(64), nullable=True,
                          comment="批量简报缓存键 MD5"),
            )
        if not _has_index("word_export_task", "idx_word_export_task_cache_key"):
            op.create_index(
                "idx_word_export_task_cache_key",
                "word_export_task",
                ["cache_key"],
            )

    # ============== Fix 4: projects.risk_level + risk_level_updated_at =====
    if _has_table("projects"):
        if not _has_column("projects", "risk_level"):
            op.add_column(
                "projects",
                sa.Column("risk_level", sa.String(10), nullable=True,
                          comment="风险等级: high/medium/low"),
            )
        if not _has_column("projects", "risk_level_updated_at"):
            op.add_column(
                "projects",
                sa.Column("risk_level_updated_at", sa.DateTime(), nullable=True),
            )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # projects
    if _has_column("projects", "risk_level_updated_at"):
        op.drop_column("projects", "risk_level_updated_at")
    if _has_column("projects", "risk_level"):
        op.drop_column("projects", "risk_level")

    # word_export_task
    if _has_index("word_export_task", "idx_word_export_task_cache_key"):
        op.drop_index("idx_word_export_task_cache_key", table_name="word_export_task")
    if _has_column("word_export_task", "cache_key"):
        op.drop_column("word_export_task", "cache_key")

    # staff_members
    if _has_column("staff_members", "role_level"):
        op.drop_column("staff_members", "role_level")
