"""第一阶段MVP底稿：8张底稿相关表 ORM 模型

对应 Alembic 迁移脚本 007_workpaper_tables.py，包含：
- 6 个 PostgreSQL 枚举类型
- 8 个 SQLAlchemy ORM 模型
"""

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ---------------------------------------------------------------------------
# PostgreSQL 枚举类型（与迁移 007 一致）
# ---------------------------------------------------------------------------


class WpTemplateStatus(str, enum.Enum):
    """底稿模板状态"""
    draft = "draft"
    published = "published"
    deprecated = "deprecated"


class RegionType(str, enum.Enum):
    """模板区域类型"""
    formula = "formula"
    manual = "manual"
    ai_fill = "ai_fill"
    conclusion = "conclusion"
    cross_ref = "cross_ref"


class WpStatus(str, enum.Enum):
    """底稿索引状态"""
    not_started = "not_started"
    in_progress = "in_progress"
    draft_complete = "draft_complete"
    review_passed = "review_passed"
    archived = "archived"


class WpSourceType(str, enum.Enum):
    """底稿来源类型"""
    template = "template"
    manual = "manual"
    imported = "imported"


class WpFileStatus(str, enum.Enum):
    """底稿文件状态"""
    draft = "draft"
    edit_complete = "edit_complete"
    review_level1_passed = "review_level1_passed"
    review_level2_passed = "review_level2_passed"
    archived = "archived"


class ReviewCommentStatus(str, enum.Enum):
    """复核批注状态"""
    open = "open"
    replied = "replied"
    resolved = "resolved"


# ---------------------------------------------------------------------------
# WpTemplate 模型（底稿模板）
# ---------------------------------------------------------------------------


class WpTemplate(Base):
    """底稿模板"""

    __tablename__ = "wp_template"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_code: Mapped[str] = mapped_column(String, nullable=False)
    template_name: Mapped[str] = mapped_column(String, nullable=False)
    audit_cycle: Mapped[str | None] = mapped_column(String, nullable=True)
    applicable_standard: Mapped[str | None] = mapped_column(String, nullable=True)
    version_major: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("1"), nullable=False
    )
    version_minor: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    status: Mapped[WpTemplateStatus] = mapped_column(
        sa.Enum(WpTemplateStatus, name="wp_template_status", create_type=False),
        server_default=text("'draft'"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "uq_wp_template_code_version",
            "template_code", "version_major", "version_minor",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# WpTemplateMeta 模型（模板元数据/命名区域）
# ---------------------------------------------------------------------------


class WpTemplateMeta(Base):
    """模板元数据（命名区域定义）"""

    __tablename__ = "wp_template_meta"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wp_template.id"), nullable=False
    )
    range_name: Mapped[str] = mapped_column(String, nullable=False)
    region_type: Mapped[RegionType] = mapped_column(
        sa.Enum(RegionType, name="region_type", create_type=False),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_wp_template_meta_template_id", "template_id"),
    )


# ---------------------------------------------------------------------------
# WpTemplateSet 模型（模板集）
# ---------------------------------------------------------------------------


class WpTemplateSet(Base):
    """底稿模板集"""

    __tablename__ = "wp_template_set"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    set_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    template_codes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    applicable_audit_type: Mapped[str | None] = mapped_column(String, nullable=True)
    applicable_standard: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------------------
# WpIndex 模型（底稿索引）
# ---------------------------------------------------------------------------


class WpIndex(Base):
    """底稿索引"""

    __tablename__ = "wp_index"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    wp_code: Mapped[str] = mapped_column(String, nullable=False)
    wp_name: Mapped[str] = mapped_column(String, nullable=False)
    audit_cycle: Mapped[str | None] = mapped_column(String, nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reviewer: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    status: Mapped[WpStatus] = mapped_column(
        sa.Enum(WpStatus, name="wp_status", create_type=False),
        server_default=text("'not_started'"),
        nullable=False,
    )
    cross_ref_codes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "uq_wp_index_project_code",
            "project_id", "wp_code",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# WorkingPaper 模型（底稿文件）
# ---------------------------------------------------------------------------


class WorkingPaper(Base):
    """底稿文件"""

    __tablename__ = "working_paper"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    wp_index_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wp_index.id"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[WpSourceType] = mapped_column(
        sa.Enum(WpSourceType, name="wp_source_type", create_type=False),
        nullable=False,
    )
    status: Mapped[WpFileStatus] = mapped_column(
        sa.Enum(WpFileStatus, name="wp_file_status", create_type=False),
        server_default=text("'draft'"),
        nullable=False,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reviewer: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    file_version: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("1"), nullable=False
    )
    last_parsed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "uq_working_paper_project_index",
            "project_id", "wp_index_id",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# WpCrossRef 模型（交叉引用）
# ---------------------------------------------------------------------------


class WpCrossRef(Base):
    """底稿交叉引用"""

    __tablename__ = "wp_cross_ref"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    source_wp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("working_paper.id"), nullable=False
    )
    target_wp_code: Mapped[str] = mapped_column(String, nullable=False)
    cell_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_wp_cross_ref_project_source",
            "project_id", "source_wp_id",
        ),
    )


# ---------------------------------------------------------------------------
# WpQcResult 模型（质量自检结果）
# ---------------------------------------------------------------------------


class WpQcResult(Base):
    """底稿质量自检结果"""

    __tablename__ = "wp_qc_results"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    working_paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("working_paper.id"), nullable=False
    )
    check_timestamp: Mapped[datetime] = mapped_column(nullable=False)
    findings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False)
    blocking_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    warning_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    info_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    checked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_wp_qc_results_working_paper_id", "working_paper_id"),
    )


# ---------------------------------------------------------------------------
# ReviewRecord 模型（复核批注）
# ---------------------------------------------------------------------------


class ReviewRecord(Base):
    """复核批注"""

    __tablename__ = "review_records"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    working_paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("working_paper.id"), nullable=False
    )
    cell_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    commenter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    status: Mapped[ReviewCommentStatus] = mapped_column(
        sa.Enum(ReviewCommentStatus, name="review_comment_status", create_type=False),
        server_default=text("'open'"),
        nullable=False,
    )
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    replier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    replied_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "idx_review_records_wp_status",
            "working_paper_id", "status",
        ),
    )


# ---------------------------------------------------------------------------
# 抽样相关枚举类型（与迁移 008 一致）
# ---------------------------------------------------------------------------


class SamplingType(str, enum.Enum):
    """抽样类型"""
    statistical = "statistical"
    non_statistical = "non_statistical"


class SamplingMethod(str, enum.Enum):
    """抽样方法"""
    mus = "mus"
    attribute = "attribute"
    random = "random"
    systematic = "systematic"
    stratified = "stratified"


class ApplicableScenario(str, enum.Enum):
    """适用场景"""
    control_test = "control_test"
    substantive_test = "substantive_test"


# ---------------------------------------------------------------------------
# SamplingConfig 模型（抽样配置）
# ---------------------------------------------------------------------------


class SamplingConfig(Base):
    """抽样配置"""

    __tablename__ = "sampling_config"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    config_name: Mapped[str] = mapped_column(String, nullable=False)
    sampling_type: Mapped[SamplingType] = mapped_column(
        sa.Enum(SamplingType, name="sampling_type", create_type=False),
        nullable=False,
    )
    sampling_method: Mapped[SamplingMethod] = mapped_column(
        sa.Enum(SamplingMethod, name="sampling_method", create_type=False),
        nullable=False,
    )
    applicable_scenario: Mapped[ApplicableScenario] = mapped_column(
        sa.Enum(ApplicableScenario, name="applicable_scenario", create_type=False),
        nullable=False,
    )
    confidence_level: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(5, 4), nullable=True
    )
    expected_deviation_rate: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(5, 4), nullable=True
    )
    tolerable_deviation_rate: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(5, 4), nullable=True
    )
    tolerable_misstatement: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    population_amount: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    population_count: Mapped[int | None] = mapped_column(
        sa.Integer, nullable=True
    )
    calculated_sample_size: Mapped[int | None] = mapped_column(
        sa.Integer, nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_sampling_config_project_method", "project_id", "sampling_method"),
    )


# ---------------------------------------------------------------------------
# SamplingRecord 模型（抽样记录）
# ---------------------------------------------------------------------------


class SamplingRecord(Base):
    """抽样记录"""

    __tablename__ = "sampling_records"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    working_paper_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("working_paper.id"), nullable=True
    )
    sampling_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sampling_config.id"), nullable=True
    )
    sampling_purpose: Mapped[str] = mapped_column(Text, nullable=False)
    population_description: Mapped[str] = mapped_column(Text, nullable=False)
    population_total_amount: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    population_total_count: Mapped[int | None] = mapped_column(
        sa.Integer, nullable=True
    )
    sample_size: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    sampling_method_description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    deviations_found: Mapped[int | None] = mapped_column(
        sa.Integer, nullable=True
    )
    misstatements_found: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    projected_misstatement: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    upper_misstatement_limit: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_sampling_records_project_wp", "project_id", "working_paper_id"),
    )
