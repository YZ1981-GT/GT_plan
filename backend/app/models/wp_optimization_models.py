"""底稿深度优化 ORM 模型

Sprint 1 新增 6 个模型类：
- WpTemplateMetadata: 底稿模板元数据
- WorkpaperProcedure: 审计程序清单
- CrossCheckResult: 跨科目校验结果
- EvidenceLink: 证据链
- WorkpaperSnapshot: 底稿快照
- CellAnnotation: 单元格批注
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ---------------------------------------------------------------------------
# WpTemplateMetadata 模型（底稿模板元数据）
# ---------------------------------------------------------------------------


class WpTemplateMetadata(Base):
    """底稿模板元数据

    每个模板一行，含 component_type / procedure_steps / formula_cells 等 JSONB 字段。
    用于驱动编辑器组件选型、程序清单初始化、公式预填充等。
    """

    __tablename__ = "wp_template_metadata"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("wp_template.id"),
        nullable=True,
    )
    wp_code: Mapped[str] = mapped_column(String(20), nullable=False)
    component_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="univer"
    )
    audit_stage: Mapped[str] = mapped_column(String(30), nullable=False)
    cycle: Mapped[str | None] = mapped_column(String(10), nullable=True)
    file_format: Mapped[str | None] = mapped_column(String(10), nullable=True)
    procedure_steps: Mapped[dict | None] = mapped_column(JSONB, server_default="[]")
    guidance_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    formula_cells: Mapped[dict | None] = mapped_column(JSONB, server_default="[]")
    required_regions: Mapped[dict | None] = mapped_column(JSONB, server_default="[]")
    linked_accounts: Mapped[dict | None] = mapped_column(JSONB, server_default="[]")
    note_section: Mapped[str | None] = mapped_column(String(20), nullable=True)
    conclusion_cell: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    audit_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_assertions: Mapped[dict | None] = mapped_column(JSONB, server_default="[]")
    procedure_flow_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_wp_tmpl_meta_code", "wp_code"),
        Index("idx_wp_tmpl_meta_stage", "audit_stage"),
    )


# ---------------------------------------------------------------------------
# WorkpaperProcedure 模型（审计程序清单）
# ---------------------------------------------------------------------------


class WorkpaperProcedure(Base):
    """审计程序清单

    每个底稿实例一份，从模板 procedure_steps 复制。
    支持裁剪（status='not_applicable'）和完成标记。
    """

    __tablename__ = "workpaper_procedures"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("working_paper.id"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    procedure_id: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="routine"
    )
    is_mandatory: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("true")
    )
    applicable_project_types: Mapped[dict | None] = mapped_column(
        JSONB, server_default='["all"]'
    )
    depends_on: Mapped[dict | None] = mapped_column(JSONB, server_default="[]")
    evidence_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    trimmed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    trimmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    trim_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_wp_proc_wp", "wp_id"),
        Index("idx_wp_proc_status", "wp_id", "status"),
    )


# ---------------------------------------------------------------------------
# CrossCheckResult 模型（跨科目校验结果）
# ---------------------------------------------------------------------------


class CrossCheckResult(Base):
    """跨科目校验结果

    持久化校验结果，支持历史对比。
    """

    __tablename__ = "cross_check_results"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(30), nullable=False)
    left_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    right_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    difference: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_cross_check_project", "project_id", "year"),
    )


# ---------------------------------------------------------------------------
# EvidenceLink 模型（证据链）
# ---------------------------------------------------------------------------


class EvidenceLink(Base):
    """证据链

    底稿单元格→附件→具体页码的三级关联。
    """

    __tablename__ = "evidence_links"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("working_paper.id"),
        nullable=False,
    )
    sheet_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cell_ref: Mapped[str | None] = mapped_column(String(20), nullable=True)
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("attachments.id"),
        nullable=False,
    )
    page_ref: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evidence_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    check_conclusion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_evidence_wp", "wp_id"),
        Index("idx_evidence_attachment", "attachment_id"),
    )


# ---------------------------------------------------------------------------
# WorkpaperSnapshot 模型（底稿快照）
# ---------------------------------------------------------------------------


class WorkpaperSnapshot(Base):
    """底稿快照

    关键时点的数据冻结副本。snapshot_data 存储公式单元格当前值。
    签字时点快照绑定 bound_dataset_id，不可删除。
    """

    __tablename__ = "workpaper_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("working_paper.id"),
        nullable=False,
    )
    trigger_event: Mapped[str] = mapped_column(String(50), nullable=False)
    snapshot_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    is_locked: Mapped[bool] = mapped_column(server_default=text("false"))
    bound_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    __table_args__ = (
        Index("idx_wp_snapshot", "wp_id"),
    )


# ---------------------------------------------------------------------------
# CellAnnotation 模型（单元格批注）— 已在 phase10_models.py 中定义
# 此处不重复定义，避免 SQLAlchemy MetaData 冲突。
# 如需底稿级单元格批注，使用 phase10_models.CellAnnotation（通用批注模型）。
# ---------------------------------------------------------------------------
