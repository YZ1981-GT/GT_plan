"""Refinement Round 3: QC governance tables

Revision ID: round3_qc_governance_20260506
Revises: round2_batch3_arch_fixes_20260506

本迁移落地 Round 3 质控治理的数据模型变更：

1. ``qc_rule_definitions`` — QC 规则定义表（需求 1, 10）
2. ``qc_inspections`` — 质控抽查批次（需求 4）
3. ``qc_inspection_items`` — 抽查子项（需求 4）
4. ``qc_inspection_records`` — 质控独立复核记录（需求 4）
5. ``project_quality_ratings`` — 项目质量评级（需求 3）
6. ``reviewer_metrics_snapshots`` — 复核人深度指标快照（需求 6）
7. ``qc_case_library`` — 失败案例库（需求 8）

遵循 ``backend/alembic/MIGRATION_GUIDE.md`` 的幂等原则：使用
``IF [NOT] EXISTS`` + inspector 防重。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "round3_qc_governance_20260506"
down_revision = "round2_batch3_arch_fixes_20260506"
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
    # ============== 1. qc_rule_definitions =================================
    if not _has_table("qc_rule_definitions"):
        op.create_table(
            "qc_rule_definitions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("rule_code", sa.String(50), unique=True, nullable=False),
            sa.Column("severity", sa.String(20), nullable=False),
            sa.Column("scope", sa.String(30), nullable=False),
            sa.Column("category", sa.String(100), nullable=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("standard_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("expression_type", sa.String(20), nullable=False),
            sa.Column("expression", sa.Text(), nullable=False),
            sa.Column("parameters_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            # SoftDeleteMixin
            sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            # TimestampMixin
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_index("qc_rule_definitions", "idx_qc_rule_definitions_scope"):
        op.create_index("idx_qc_rule_definitions_scope", "qc_rule_definitions", ["scope"])
    if not _has_index("qc_rule_definitions", "idx_qc_rule_definitions_enabled"):
        op.create_index("idx_qc_rule_definitions_enabled", "qc_rule_definitions", ["enabled"])

    # ============== 2. qc_inspections ======================================
    if not _has_table("qc_inspections"):
        op.create_table(
            "qc_inspections",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("strategy", sa.String(30), nullable=False),
            sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("status", sa.String(20), server_default=sa.text("'created'"), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("report_url", sa.String(500), nullable=True),
            # SoftDeleteMixin
            sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            # TimestampMixin
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_index("qc_inspections", "idx_qc_inspections_project"):
        op.create_index("idx_qc_inspections_project", "qc_inspections", ["project_id"])
    if not _has_index("qc_inspections", "idx_qc_inspections_reviewer"):
        op.create_index("idx_qc_inspections_reviewer", "qc_inspections", ["reviewer_id"])
    if not _has_index("qc_inspections", "idx_qc_inspections_status"):
        op.create_index("idx_qc_inspections_status", "qc_inspections", ["status"])

    # ============== 3. qc_inspection_items =================================
    if not _has_table("qc_inspection_items"):
        op.create_table(
            "qc_inspection_items",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("inspection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("qc_inspections.id"), nullable=False),
            sa.Column("wp_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("status", sa.String(20), server_default=sa.text("'pending'"), nullable=False),
            sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("qc_verdict", sa.String(20), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            # TimestampMixin
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_index("qc_inspection_items", "idx_qc_inspection_items_inspection"):
        op.create_index("idx_qc_inspection_items_inspection", "qc_inspection_items", ["inspection_id"])
    if not _has_index("qc_inspection_items", "idx_qc_inspection_items_wp"):
        op.create_index("idx_qc_inspection_items_wp", "qc_inspection_items", ["wp_id"])
    if not _has_index("qc_inspection_items", "idx_qc_inspection_items_status"):
        op.create_index("idx_qc_inspection_items_status", "qc_inspection_items", ["status"])

    # ============== 4. qc_inspection_records ================================
    if not _has_table("qc_inspection_records"):
        op.create_table(
            "qc_inspection_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("inspection_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("qc_inspection_items.id"), nullable=False),
            sa.Column("comment", sa.Text(), nullable=False),
            sa.Column("severity", sa.String(20), nullable=False),
            sa.Column("cell_ref", sa.String(20), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
            # TimestampMixin
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_index("qc_inspection_records", "idx_qc_inspection_records_item"):
        op.create_index("idx_qc_inspection_records_item", "qc_inspection_records", ["inspection_item_id"])
    if not _has_index("qc_inspection_records", "idx_qc_inspection_records_created_by"):
        op.create_index("idx_qc_inspection_records_created_by", "qc_inspection_records", ["created_by"])

    # ============== 5. project_quality_ratings ==============================
    if not _has_table("project_quality_ratings"):
        op.create_table(
            "project_quality_ratings",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("rating", sa.String(1), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("computed_by_rule_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
            sa.Column("override_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("override_rating", sa.String(1), nullable=True),
            sa.Column("override_reason", sa.Text(), nullable=True),
            # TimestampMixin
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_index("project_quality_ratings", "idx_project_quality_ratings_project_year"):
        op.create_index("idx_project_quality_ratings_project_year", "project_quality_ratings", ["project_id", "year"])
    if not _has_index("project_quality_ratings", "idx_project_quality_ratings_year"):
        op.create_index("idx_project_quality_ratings_year", "project_quality_ratings", ["year"])
    if not _has_index("project_quality_ratings", "idx_project_quality_ratings_rating"):
        op.create_index("idx_project_quality_ratings_rating", "project_quality_ratings", ["rating"])

    # ============== 6. reviewer_metrics_snapshots ===========================
    if not _has_table("reviewer_metrics_snapshots"):
        op.create_table(
            "reviewer_metrics_snapshots",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("avg_review_time_min", sa.Float(), nullable=True),
            sa.Column("avg_comments_per_wp", sa.Float(), nullable=True),
            sa.Column("rejection_rate", sa.Float(), nullable=True),
            sa.Column("qc_rule_catch_rate", sa.Float(), nullable=True),
            sa.Column("sampled_rework_rate", sa.Float(), nullable=True),
            # TimestampMixin
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_index("reviewer_metrics_snapshots", "idx_reviewer_metrics_snapshots_reviewer_year"):
        op.create_index("idx_reviewer_metrics_snapshots_reviewer_year", "reviewer_metrics_snapshots", ["reviewer_id", "year"])
    if not _has_index("reviewer_metrics_snapshots", "idx_reviewer_metrics_snapshots_date"):
        op.create_index("idx_reviewer_metrics_snapshots_date", "reviewer_metrics_snapshots", ["snapshot_date"])

    # ============== 7. qc_case_library =====================================
    if not _has_table("qc_case_library"):
        op.create_table(
            "qc_case_library",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("category", sa.String(50), nullable=False),
            sa.Column("severity", sa.String(20), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("lessons_learned", sa.Text(), nullable=True),
            sa.Column("related_wp_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("related_standards", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("published_by", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("published_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("review_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
            # SoftDeleteMixin
            sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            # TimestampMixin
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if not _has_index("qc_case_library", "idx_qc_case_library_category"):
        op.create_index("idx_qc_case_library_category", "qc_case_library", ["category"])
    if not _has_index("qc_case_library", "idx_qc_case_library_severity"):
        op.create_index("idx_qc_case_library_severity", "qc_case_library", ["severity"])
    if not _has_index("qc_case_library", "idx_qc_case_library_published_at"):
        op.create_index("idx_qc_case_library_published_at", "qc_case_library", ["published_at"])


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Drop tables in reverse dependency order
    for table in [
        "qc_case_library",
        "reviewer_metrics_snapshots",
        "project_quality_ratings",
        "qc_inspection_records",
        "qc_inspection_items",
        "qc_inspections",
        "qc_rule_definitions",
    ]:
        if _has_table(table):
            op.drop_table(table)
