"""Add 'interrupted' value to job_status_enum (PG only).

Revision ID: view_refactor_interrupted_status_20260511
Revises: view_refactor_creator_chain_20260520
Create Date: 2026-05-11

F44 / Sprint 7.14: ImportJob 新增 interrupted 状态，用于 worker 收到 SIGTERM
后主动标记中断的作业。重启后 recover_jobs 优先恢复这些作业。
"""

revision = "view_refactor_interrupted_status_20260511"
down_revision = "view_refactor_creator_chain_20260520"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    # PG 不允许在事务内 ALTER TYPE ADD VALUE，需要 autocommit_block
    # SQLite 无原生 enum 类型，此迁移对 SQLite 为 no-op
    try:
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'interrupted'")
    except Exception:
        # SQLite 或其他不支持 ALTER TYPE 的数据库静默跳过
        pass


def downgrade() -> None:
    # PG 不支持移除 enum 值，downgrade 为 no-op
    pass
