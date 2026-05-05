"""Refinement Round 1: long-term compliance models

Revision ID: round1_long_term_compliance_20260508
Revises: round1_review_closure_20260508

本迁移落地 Round 1 Sprint 3（长期运营合规）的数据模型变更：

1. 新建 ``audit_log_entries`` 表 — 不可变追加式哈希链审计日志（需求 9）
2. 新建 ``independence_declarations`` 表 — 独立性声明结构化（需求 10）
3. 新建 ``partner_rotation_overrides`` 表 — 合伙人轮换 override（需求 11）
4. ``projects`` 表新增 ``archived_at`` / ``retention_until`` 两列（需求 11）

遵循 ``backend/alembic/MIGRATION_GUIDE.md`` 的幂等原则：使用
``IF [NOT] EXISTS`` + inspector 防重。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "round1_long_term_compliance_20260508"
down_revision = "round1_review_closure_20260508"
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

def upgrade() -> None:  # noqa: C901
    # ============== 1. audit_log_entries ===================================
    if not _has_table("audit_log_entries"):
        op.create_table(
            "audit_log_entries",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "ts",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("session_id", sa.String(length=128), nullable=True),
            sa.Column("action_type", sa.String(length=64), nullable=False),
            sa.Column("object_type", sa.String(length=64), nullable=False),
            sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "payload",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("ip", sa.String(length=45), nullable=True),
            sa.Column("ua", sa.Text(), nullable=True),
            sa.Column("trace_id", sa.String(length=64), nullable=True),
            sa.Column("prev_hash", sa.String(length=64), nullable=False),
            sa.Column("entry_hash", sa.String(length=64), nullable=False),
        )

    # Indexes for audit_log_entries
    if not _has_index("audit_log_entries", "idx_audit_log_entries_ts"):
        op.create_index(
            "idx_audit_log_entries_ts", "audit_log_entries", ["ts"]
        )
    if not _has_index("audit_log_entries", "idx_audit_log_entries_user_id"):
        op.create_index(
            "idx_audit_log_entries_user_id", "audit_log_entries", ["user_id"]
        )
    if not _has_index("audit_log_entries", "idx_audit_log_entries_action_type"):
        op.create_index(
            "idx_audit_log_entries_action_type",
            "audit_log_entries",
            ["action_type"],
        )
    if not _has_index("audit_log_entries", "idx_audit_log_entries_object"):
        op.create_index(
            "idx_audit_log_entries_object",
            "audit_log_entries",
            ["object_type", "object_id"],
        )
    if not _has_index("audit_log_entries", "idx_audit_log_entries_entry_hash"):
        op.create_index(
            "idx_audit_log_entries_entry_hash",
            "audit_log_entries",
            ["entry_hash"],
            unique=True,
        )

    # ============== 2. independence_declarations ==========================
    if not _has_table("independence_declarations"):
        op.create_table(
            "independence_declarations",
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
                "declarant_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column("declaration_year", sa.Integer(), nullable=False),
            sa.Column(
                "answers",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "attachments",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("signed_at", sa.DateTime(), nullable=True),
            sa.Column(
                "signature_record_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("signature_records.id"),
                nullable=True,
            ),
            sa.Column(
                "reviewed_by_qc_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=30),
                server_default=sa.text("'draft'"),
                nullable=False,
            ),
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

    # Indexes for independence_declarations
    if not _has_index("independence_declarations", "idx_independence_declarations_project"):
        op.create_index(
            "idx_independence_declarations_project",
            "independence_declarations",
            ["project_id", "declaration_year"],
        )
    if not _has_index("independence_declarations", "idx_independence_declarations_declarant"):
        op.create_index(
            "idx_independence_declarations_declarant",
            "independence_declarations",
            ["declarant_id", "project_id"],
        )
    if not _has_index("independence_declarations", "idx_independence_declarations_status"):
        op.create_index(
            "idx_independence_declarations_status",
            "independence_declarations",
            ["status"],
        )

    # ============== 3. partner_rotation_overrides ==========================
    if not _has_table("partner_rotation_overrides"):
        op.create_table(
            "partner_rotation_overrides",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "staff_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column("client_name", sa.String(length=255), nullable=False),
            sa.Column("original_years", sa.Integer(), nullable=False),
            sa.Column("override_reason", sa.Text(), nullable=False),
            sa.Column(
                "approved_by_compliance_partner",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column(
                "approved_by_chief_risk_partner",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column("override_expires_at", sa.DateTime(), nullable=True),
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

    # Indexes for partner_rotation_overrides
    if not _has_index("partner_rotation_overrides", "idx_rotation_overrides_staff_client"):
        op.create_index(
            "idx_rotation_overrides_staff_client",
            "partner_rotation_overrides",
            ["staff_id", "client_name"],
        )

    # ============== 4. projects: archived_at + retention_until =============
    if _has_table("projects"):
        if not _has_column("projects", "archived_at"):
            op.add_column(
                "projects",
                sa.Column("archived_at", sa.DateTime(), nullable=True),
            )
        if not _has_column("projects", "retention_until"):
            op.add_column(
                "projects",
                sa.Column("retention_until", sa.DateTime(), nullable=True),
            )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # projects columns
    if _has_column("projects", "retention_until"):
        op.drop_column("projects", "retention_until")
    if _has_column("projects", "archived_at"):
        op.drop_column("projects", "archived_at")

    # partner_rotation_overrides
    if _has_index("partner_rotation_overrides", "idx_rotation_overrides_staff_client"):
        op.drop_index(
            "idx_rotation_overrides_staff_client",
            table_name="partner_rotation_overrides",
        )
    if _has_table("partner_rotation_overrides"):
        op.drop_table("partner_rotation_overrides")

    # independence_declarations
    if _has_index("independence_declarations", "idx_independence_declarations_status"):
        op.drop_index(
            "idx_independence_declarations_status",
            table_name="independence_declarations",
        )
    if _has_index("independence_declarations", "idx_independence_declarations_declarant"):
        op.drop_index(
            "idx_independence_declarations_declarant",
            table_name="independence_declarations",
        )
    if _has_index("independence_declarations", "idx_independence_declarations_project"):
        op.drop_index(
            "idx_independence_declarations_project",
            table_name="independence_declarations",
        )
    if _has_table("independence_declarations"):
        op.drop_table("independence_declarations")

    # audit_log_entries
    if _has_index("audit_log_entries", "idx_audit_log_entries_entry_hash"):
        op.drop_index(
            "idx_audit_log_entries_entry_hash",
            table_name="audit_log_entries",
        )
    if _has_index("audit_log_entries", "idx_audit_log_entries_object"):
        op.drop_index(
            "idx_audit_log_entries_object",
            table_name="audit_log_entries",
        )
    if _has_index("audit_log_entries", "idx_audit_log_entries_action_type"):
        op.drop_index(
            "idx_audit_log_entries_action_type",
            table_name="audit_log_entries",
        )
    if _has_index("audit_log_entries", "idx_audit_log_entries_user_id"):
        op.drop_index(
            "idx_audit_log_entries_user_id",
            table_name="audit_log_entries",
        )
    if _has_index("audit_log_entries", "idx_audit_log_entries_ts"):
        op.drop_index(
            "idx_audit_log_entries_ts",
            table_name="audit_log_entries",
        )
    if _has_table("audit_log_entries"):
        op.drop_table("audit_log_entries")
