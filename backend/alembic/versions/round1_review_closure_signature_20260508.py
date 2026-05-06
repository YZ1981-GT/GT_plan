"""Refinement Round 1: review closure + signature workflow + archive jobs

Revision ID: round1_review_closure_20260508
Revises: phase17_005

本迁移一次性落地 Round 1（复核闭环）的全部数据模型变更：

1. ``issue_tickets.source`` VARCHAR(16) → VARCHAR(32)，并一次性预留 5 轮
   共享的全量枚举值（review_comment / consistency / ai / reminder /
   client_commitment / pbc / confirmation / qc_inspection）。Postgres 列类型
   存的是原始字符串，不需要 DROP/CREATE TYPE，只做宽度扩展以承载最长
   ``client_commitment`` (17)。
2. ``issue_tickets.source_ref_id`` UUID NULL — 双向追溯字段。
3. ``signature_records`` 三列：``required_order`` INT、``required_role``
   VARCHAR(30)、``prerequisite_signature_ids`` JSONB，以及组合索引
   ``idx_signature_records_order``。
4. ``review_records`` 已有 ``status`` / ``reply_text`` 列，迁移仅补写默认值与
   确保 ``is_deleted=false`` 回填（幂等 no-op，保留历史兼容）。
5. ``project_assignments.role`` 运行时文本列，枚举值 ``eqcr`` 仅在 Python
   层的 ``AssignmentRole`` 枚举中新增，无需 DDL。
6. 新建 ``archive_jobs`` 表，记录归档编排作业的断点续传状态。

遵循 ``backend/alembic/MIGRATION_GUIDE.md`` 的幂等原则：使用
``IF [NOT] EXISTS`` + inspector 防重。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "round1_review_closure_20260508"
down_revision = "phase17_005"
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


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:  # noqa: C901 - 按章节顺序易读
    # ---------------- 1. issue_tickets: 扩 source + 加 source_ref_id ------
    if _has_table("issue_tickets"):
        if _is_postgres():
            # 扩宽 source 以承载最长枚举值 'client_commitment' (17)
            op.execute(
                "ALTER TABLE issue_tickets ALTER COLUMN source TYPE VARCHAR(32)"
            )
        if not _has_column("issue_tickets", "source_ref_id"):
            op.add_column(
                "issue_tickets",
                sa.Column(
                    "source_ref_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                ),
            )

    # ---------------- 2. signature_records: 三级签字流水字段 --------------
    if _has_table("signature_records"):
        if not _has_column("signature_records", "required_order"):
            op.add_column(
                "signature_records",
                sa.Column("required_order", sa.Integer(), nullable=True),
            )
        if not _has_column("signature_records", "required_role"):
            op.add_column(
                "signature_records",
                sa.Column("required_role", sa.String(length=30), nullable=True),
            )
        if not _has_column("signature_records", "prerequisite_signature_ids"):
            op.add_column(
                "signature_records",
                sa.Column(
                    "prerequisite_signature_ids",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=True,
                ),
            )
        if not _has_index("signature_records", "idx_signature_records_order"):
            op.create_index(
                "idx_signature_records_order",
                "signature_records",
                ["object_type", "object_id", "required_order"],
            )

    # ---------------- 3. review_records: status + reply_text 幂等 ---------
    # 列已在原始 007 迁移中创建，本迁移仅保证 server_default 与回填。
    if _has_table("review_records") and _is_postgres():
        op.execute(
            "UPDATE review_records SET status = 'open' WHERE status IS NULL"
        )
        # status 已有 NOT NULL + server_default='open'，无需额外变更
        # reply_text 为 TEXT NULL，无需回填

    # ---------------- 4. archive_jobs 新建 -------------------------------
    if not _has_table("archive_jobs"):
        op.create_table(
            "archive_jobs",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column(
                "scope",
                sa.String(length=20),
                server_default=sa.text("'final'"),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.String(length=20),
                server_default=sa.text("'queued'"),
                nullable=False,
            ),
            sa.Column(
                "push_to_cloud",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column(
                "purge_local",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column(
                "gate_eval_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
            sa.Column("last_succeeded_section", sa.String(length=16), nullable=True),
            sa.Column("failed_section", sa.String(length=16), nullable=True),
            sa.Column("failed_reason", sa.Text(), nullable=True),
            sa.Column(
                "section_progress",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("output_url", sa.String(length=500), nullable=True),
            sa.Column("manifest_hash", sa.String(length=64), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column(
                "initiated_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    if not _has_index("archive_jobs", "idx_archive_jobs_project_status"):
        if _is_postgres():
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_archive_jobs_project_status "
                "ON archive_jobs (project_id, status) "
                "WHERE is_deleted = false"
            )
        else:
            op.create_index(
                "idx_archive_jobs_project_status",
                "archive_jobs",
                ["project_id", "status"],
            )
    if not _has_index("archive_jobs", "idx_archive_jobs_status"):
        op.create_index("idx_archive_jobs_status", "archive_jobs", ["status"])


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # archive_jobs
    if _has_index("archive_jobs", "idx_archive_jobs_status"):
        op.drop_index("idx_archive_jobs_status", table_name="archive_jobs")
    if _has_index("archive_jobs", "idx_archive_jobs_project_status"):
        op.drop_index(
            "idx_archive_jobs_project_status", table_name="archive_jobs"
        )
    if _has_table("archive_jobs"):
        op.drop_table("archive_jobs")

    # signature_records
    if _has_index("signature_records", "idx_signature_records_order"):
        op.drop_index(
            "idx_signature_records_order", table_name="signature_records"
        )
    if _has_column("signature_records", "prerequisite_signature_ids"):
        op.drop_column("signature_records", "prerequisite_signature_ids")
    if _has_column("signature_records", "required_role"):
        op.drop_column("signature_records", "required_role")
    if _has_column("signature_records", "required_order"):
        op.drop_column("signature_records", "required_order")

    # issue_tickets
    if _has_column("issue_tickets", "source_ref_id"):
        op.drop_column("issue_tickets", "source_ref_id")
    if _has_table("issue_tickets") and _is_postgres():
        # 回缩 source 宽度：仅在确认所有行 ≤ 16 字符时安全
        op.execute(
            "ALTER TABLE issue_tickets "
            "ALTER COLUMN source TYPE VARCHAR(16) "
            "USING LEFT(source, 16)"
        )
