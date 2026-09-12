"""行名对齐映射存储 ORM 模型

对应迁移 V160__workpaper_row_name_mapping.sql。
名称对齐层的 N:M 映射：底稿行名 ↔ 账套明细名（aux_name / account_name）。

版本模型：每次确认写**新行**（mapping_version+1，is_active=true），旧行置
is_active=false 并被新行 superseded_from 指向 → 覆盖历史天然留痕。

spec: .kiro/specs/formula-row-name-alignment-confirmation/ Requirement 3
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WorkpaperRowNameMapping(Base, TimestampMixin):
    """一行的行名对齐映射（版本行）。

    作用域 (project_id, year, wp_code, sheet_code, row_key) 的 active 版本唯一
    （部分唯一索引 `uq_row_name_mapping_active_scope`，仅约束 is_active 行）。
    """

    __tablename__ = "workpaper_row_name_mapping"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 作用域键（Requirement 3.2）
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    wp_code: Mapped[str] = mapped_column(String(64), nullable=False)
    sheet_code: Mapped[str] = mapped_column(String(128), nullable=False)
    row_key: Mapped[str] = mapped_column(String(256), nullable=False)

    # 目标身份数组（展示 + 快照）；可查询明细见 WorkpaperRowNameMappingTarget
    targets: Mapped[list | None] = mapped_column(JSONB, nullable=False, default=list)

    match_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="user_confirmed"
    )

    # stale 指纹（Requirement 1.4 / Property 2）
    dataset_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 版本 / 幂等 / 乐观锁（Requirement 3.6）
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    base_mapping_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 版本链与留痕（Requirement 3.5）
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    superseded_from: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workpaper_row_name_mapping.id"),
        nullable=True,
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_row_name_mapping_scope",
            "project_id",
            "year",
            "wp_code",
            "sheet_code",
        ),
    )


class WorkpaperRowNameMappingTarget(Base):
    """映射目标身份明细（让身份可 SQL 查询：判 stale / 多对一交集）。

    名称仅作展示；身份判定用
    (source_kind, account_code, aux_type, dimension_key, dataset_id)。
    """

    __tablename__ = "workpaper_row_name_mapping_target"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mapping_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workpaper_row_name_mapping.id", ondelete="CASCADE"),
        nullable=False,
    )

    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    account_code: Mapped[str] = mapped_column(String(64), nullable=False)
    aux_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    aux_name: Mapped[str] = mapped_column(String(256), nullable=False)
    dimension_key: Mapped[str] = mapped_column(String(512), nullable=False)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_row_name_mapping_target_identity", "dimension_key", "dataset_id"
        ),
        Index("ix_row_name_mapping_target_mapping", "mapping_id"),
    )
