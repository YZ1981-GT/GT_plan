"""Refinement Round 5: EQCR independent review tables + state machine extension

Revision ID: round5_eqcr_20260506
Revises: round3_qc_governance_20260506

本迁移落地 Round 5 EQCR 独立复核的数据模型变更：

1. ``eqcr_opinions`` — EQCR 5 判断域意见（需求 2）
2. ``eqcr_review_notes`` — EQCR 独立复核笔记（需求 3）
3. ``eqcr_shadow_computations`` — 影子计算留痕（需求 4）
4. ``eqcr_disagreement_resolutions`` — 意见不一致合议（需求 2）
5. ``related_party_registry`` — 关联方登记（需求 2）
6. ``related_party_transactions`` — 关联方交易（需求 2）
7. ``work_hours.purpose`` 新增列（需求 8）
8. ``report_status`` PG ENUM 追加 ``eqcr_approved``（需求 5, 6）；
   ``GateType`` 扩展 ``eqcr_approval`` 为 Python 枚举，不落 DB。

遵循 ``backend/alembic/MIGRATION_GUIDE.md`` 的幂等原则。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "round5_eqcr_20260506"
down_revision = "round3_qc_governance_20260506"
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
    # ============== 1. eqcr_opinions =======================================
    if not _has_table("eqcr_opinions"):
        op.create_table(
            "eqcr_opinions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column("domain", sa.String(30), nullable=False),
            sa.Column("verdict", sa.String(30), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            # SoftDeleteMixin
            sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            # TimestampMixin
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if _is_postgres():
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_eqcr_opinions_project "
            "ON eqcr_opinions (project_id) WHERE is_deleted = false"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_eqcr_opinions_project_domain "
            "ON eqcr_opinions (project_id, domain) WHERE is_deleted = false"
        )
    else:
        if not _has_index("eqcr_opinions", "idx_eqcr_opinions_project"):
            op.create_index(
                "idx_eqcr_opinions_project", "eqcr_opinions", ["project_id"]
            )
        if not _has_index("eqcr_opinions", "idx_eqcr_opinions_project_domain"):
            op.create_index(
                "idx_eqcr_opinions_project_domain",
                "eqcr_opinions",
                ["project_id", "domain"],
            )

    # ============== 2. eqcr_review_notes ===================================
    if not _has_table("eqcr_review_notes"):
        op.create_table(
            "eqcr_review_notes",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column(
                "shared_to_team",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("shared_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if _is_postgres():
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_eqcr_review_notes_project "
            "ON eqcr_review_notes (project_id) WHERE is_deleted = false"
        )
    else:
        if not _has_index("eqcr_review_notes", "idx_eqcr_review_notes_project"):
            op.create_index(
                "idx_eqcr_review_notes_project", "eqcr_review_notes", ["project_id"]
            )

    # ============== 3. eqcr_shadow_computations ============================
    if not _has_table("eqcr_shadow_computations"):
        op.create_table(
            "eqcr_shadow_computations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column("computation_type", sa.String(50), nullable=False),
            sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "team_result_snapshot",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "has_diff",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_index("eqcr_shadow_computations", "idx_eqcr_shadow_comp_project"):
        op.create_index(
            "idx_eqcr_shadow_comp_project", "eqcr_shadow_computations", ["project_id"]
        )
    if not _has_index(
        "eqcr_shadow_computations", "idx_eqcr_shadow_comp_project_type"
    ):
        op.create_index(
            "idx_eqcr_shadow_comp_project_type",
            "eqcr_shadow_computations",
            ["project_id", "computation_type"],
        )

    # ============== 4. eqcr_disagreement_resolutions =======================
    if not _has_table("eqcr_disagreement_resolutions"):
        op.create_table(
            "eqcr_disagreement_resolutions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column(
                "eqcr_opinion_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("eqcr_opinions.id"),
                nullable=False,
            ),
            sa.Column(
                "participants",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("resolution", sa.Text(), nullable=True),
            sa.Column("resolution_verdict", sa.String(30), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_index("eqcr_disagreement_resolutions", "idx_eqcr_disagreement_project"):
        op.create_index(
            "idx_eqcr_disagreement_project",
            "eqcr_disagreement_resolutions",
            ["project_id"],
        )
    if not _has_index("eqcr_disagreement_resolutions", "idx_eqcr_disagreement_opinion"):
        op.create_index(
            "idx_eqcr_disagreement_opinion",
            "eqcr_disagreement_resolutions",
            ["eqcr_opinion_id"],
        )

    # ============== 5. related_party_registry ==============================
    if not _has_table("related_party_registry"):
        op.create_table(
            "related_party_registry",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("relation_type", sa.String(50), nullable=False),
            sa.Column(
                "is_controlled_by_same_party",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if _is_postgres():
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_related_party_registry_project "
            "ON related_party_registry (project_id) WHERE is_deleted = false"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_related_party_registry_project_name "
            "ON related_party_registry (project_id, name) WHERE is_deleted = false"
        )
    else:
        if not _has_index("related_party_registry", "idx_related_party_registry_project"):
            op.create_index(
                "idx_related_party_registry_project",
                "related_party_registry",
                ["project_id"],
            )
        if not _has_index(
            "related_party_registry", "idx_related_party_registry_project_name"
        ):
            op.create_index(
                "idx_related_party_registry_project_name",
                "related_party_registry",
                ["project_id", "name"],
            )

    # ============== 6. related_party_transactions ==========================
    if not _has_table("related_party_transactions"):
        op.create_table(
            "related_party_transactions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column(
                "related_party_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("related_party_registry.id"),
                nullable=False,
            ),
            sa.Column("amount", sa.Numeric(20, 2), nullable=False),
            sa.Column("transaction_type", sa.String(50), nullable=False),
            sa.Column(
                "is_arms_length",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column(
                "evidence_refs",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if _is_postgres():
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_related_party_tx_project "
            "ON related_party_transactions (project_id) WHERE is_deleted = false"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_related_party_tx_party "
            "ON related_party_transactions (related_party_id) WHERE is_deleted = false"
        )
    else:
        if not _has_index("related_party_transactions", "idx_related_party_tx_project"):
            op.create_index(
                "idx_related_party_tx_project",
                "related_party_transactions",
                ["project_id"],
            )
        if not _has_index("related_party_transactions", "idx_related_party_tx_party"):
            op.create_index(
                "idx_related_party_tx_party",
                "related_party_transactions",
                ["related_party_id"],
            )

    # ============== 7. work_hours.purpose ==================================
    if _has_table("work_hours") and not _has_column("work_hours", "purpose"):
        op.add_column(
            "work_hours",
            sa.Column("purpose", sa.String(20), nullable=True),
        )

    # ============== 8. report_status ENUM: + eqcr_approved =================
    # PG ENUM 需显式 ALTER TYPE ... ADD VALUE。SQLite 无 ENUM，列是 TEXT，跳过。
    # eqcr_approved 必须插在 final 之前，以保证状态机顺序：
    #   draft → review → eqcr_approved → final
    if _is_postgres():
        op.execute(
            "ALTER TYPE report_status ADD VALUE IF NOT EXISTS 'eqcr_approved' "
            "BEFORE 'final'"
        )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # work_hours.purpose
    if _has_column("work_hours", "purpose"):
        op.drop_column("work_hours", "purpose")

    # Drop tables in reverse FK dependency order
    for table in [
        "related_party_transactions",
        "related_party_registry",
        "eqcr_disagreement_resolutions",
        "eqcr_shadow_computations",
        "eqcr_review_notes",
        "eqcr_opinions",
    ]:
        if _has_table(table):
            op.drop_table(table)

    # 注意：PG ENUM 不支持 DROP VALUE；``eqcr_approved`` 回滚时保留在类型中，
    # 仅 Python 枚举 ``ReportStatus`` 不再使用。这是 Alembic 对 PG ENUM 的
    # 固有限制，不属于本迁移的缺陷。
