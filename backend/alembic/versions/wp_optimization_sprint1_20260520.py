"""底稿深度优化 Sprint 1：数据模型与基础设施

新增 6 张表 + 修改 1 张表：
- wp_template_metadata: 底稿模板元数据
- workpaper_procedures: 审计程序清单
- cross_check_results: 跨科目校验结果
- evidence_links: 证据链
- workpaper_snapshots: 底稿快照
- cell_annotations: 单元格批注
- working_paper: 新增 quality_score / consistency_status / procedure_completion_rate / wp_status 列

Revision ID: wp_optimization_sprint1_20260520
Revises: view_refactor_creator_chain_20260520
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "wp_optimization_sprint1_20260520"
down_revision = "view_refactor_creator_chain_20260520"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. wp_template_metadata
    # ------------------------------------------------------------------
    op.create_table(
        "wp_template_metadata",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("wp_template.id"), nullable=True),
        sa.Column("wp_code", sa.String(20), nullable=False),
        sa.Column("component_type", sa.String(20), nullable=False, server_default="univer"),
        sa.Column("audit_stage", sa.String(30), nullable=False),
        sa.Column("cycle", sa.String(10), nullable=True),
        sa.Column("file_format", sa.String(10), nullable=True),
        sa.Column("procedure_steps", JSONB, server_default="[]"),
        sa.Column("guidance_text", sa.Text, nullable=True),
        sa.Column("formula_cells", JSONB, server_default="[]"),
        sa.Column("required_regions", JSONB, server_default="[]"),
        sa.Column("linked_accounts", JSONB, server_default="[]"),
        sa.Column("note_section", sa.String(20), nullable=True),
        sa.Column("conclusion_cell", JSONB, nullable=True),
        sa.Column("audit_objective", sa.Text, nullable=True),
        sa.Column("related_assertions", JSONB, server_default="[]"),
        sa.Column("procedure_flow_config", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_wp_tmpl_meta_code", "wp_template_metadata", ["wp_code"])
    op.create_index("idx_wp_tmpl_meta_stage", "wp_template_metadata", ["audit_stage"])

    # ------------------------------------------------------------------
    # 2. workpaper_procedures
    # ------------------------------------------------------------------
    op.create_table(
        "workpaper_procedures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("wp_id", UUID(as_uuid=True), sa.ForeignKey("working_paper.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("procedure_id", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category", sa.String(30), nullable=False, server_default="routine"),
        sa.Column("is_mandatory", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("applicable_project_types", JSONB, server_default='["all"]'),
        sa.Column("depends_on", JSONB, server_default="[]"),
        sa.Column("evidence_type", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("completed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trimmed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("trimmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trim_reason", sa.Text, nullable=True),
        sa.Column("sort_order", sa.Integer, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_wp_proc_wp", "workpaper_procedures", ["wp_id"])
    op.create_index("idx_wp_proc_status", "workpaper_procedures", ["wp_id", "status"])

    # ------------------------------------------------------------------
    # 3. cross_check_results
    # ------------------------------------------------------------------
    op.create_table(
        "cross_check_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("rule_id", sa.String(30), nullable=False),
        sa.Column("left_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("right_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("difference", sa.Numeric(20, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_cross_check_project",
        "cross_check_results",
        ["project_id", "year", sa.text("checked_at DESC")],
    )

    # ------------------------------------------------------------------
    # 4. evidence_links
    # ------------------------------------------------------------------
    op.create_table(
        "evidence_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("wp_id", UUID(as_uuid=True), sa.ForeignKey("working_paper.id"), nullable=False),
        sa.Column("sheet_name", sa.String(100), nullable=True),
        sa.Column("cell_ref", sa.String(20), nullable=True),
        sa.Column("attachment_id", UUID(as_uuid=True), sa.ForeignKey("attachments.id"), nullable=False),
        sa.Column("page_ref", sa.String(50), nullable=True),
        sa.Column("evidence_type", sa.String(30), nullable=True),
        sa.Column("check_conclusion", sa.String(200), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_evidence_wp", "evidence_links", ["wp_id"])
    op.create_index("idx_evidence_attachment", "evidence_links", ["attachment_id"])

    # ------------------------------------------------------------------
    # 5. workpaper_snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "workpaper_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("wp_id", UUID(as_uuid=True), sa.ForeignKey("working_paper.id"), nullable=False),
        sa.Column("trigger_event", sa.String(50), nullable=False),
        sa.Column("snapshot_data", JSONB, nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_locked", sa.Boolean, server_default=sa.text("false")),
        sa.Column("bound_dataset_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("idx_wp_snapshot", "workpaper_snapshots", ["wp_id", sa.text("created_at DESC")])

    # ------------------------------------------------------------------
    # 6. working_paper 表新增列
    # ------------------------------------------------------------------
    op.add_column("working_paper", sa.Column("quality_score", sa.Integer, server_default=sa.text("0")))
    op.add_column("working_paper", sa.Column("procedure_completion_rate", sa.Numeric(5, 2), server_default=sa.text("0")))
    op.add_column("working_paper", sa.Column("wp_status", sa.String(30), server_default="created"))
    # NOTE: consistency_status 列已存在（Phase 12 添加），跳过

    # ------------------------------------------------------------------
    # 7. cell_annotations
    # ------------------------------------------------------------------
    op.create_table(
        "cell_annotations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("wp_id", UUID(as_uuid=True), sa.ForeignKey("working_paper.id"), nullable=False),
        sa.Column("sheet_name", sa.String(100), nullable=False),
        sa.Column("row_idx", sa.Integer, nullable=False),
        sa.Column("col_idx", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("replied_by", UUID(as_uuid=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_content", sa.Text, nullable=True),
        sa.Column("resolved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_cell_anno_wp", "cell_annotations", ["wp_id"])
    op.create_index("idx_cell_anno_status", "cell_annotations", ["wp_id", "status"])


def downgrade() -> None:
    op.drop_table("cell_annotations")
    op.drop_column("working_paper", "wp_status")
    op.drop_column("working_paper", "procedure_completion_rate")
    op.drop_column("working_paper", "quality_score")
    op.drop_table("workpaper_snapshots")
    op.drop_table("evidence_links")
    op.drop_table("cross_check_results")
    op.drop_table("workpaper_procedures")
    op.drop_table("wp_template_metadata")
