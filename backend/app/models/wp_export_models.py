"""底稿导出快照与版本归档 ORM 模型

对应迁移 V071__wp_export_import_tables.sql。
- WpExportSnapshot: 记录每次导出时的快照哈希，用于导入时冲突检测
- WpVersionArchive: 记录版本归档元数据（文件可能已清理但元数据保留）

Requirements: 1.5, 4.1, 6.1, 6.2
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WpExportSnapshot(Base):
    """底稿导出快照 — 记录每次导出时的内容哈希，用于导入冲突检测"""

    __tablename__ = "wp_export_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    working_paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("working_paper.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    file_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    exported_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    exported_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    file_format: Mapped[str] = mapped_column(
        String(10), server_default=text("'xlsx'"), nullable=False
    )
    file_size_bytes: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    metadata_bundle: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        Index(
            "idx_wp_export_snapshot_wp_version",
            "working_paper_id", "file_version",
            postgresql_ops={"file_version": "DESC"},
        ),
    )


class WpVersionArchive(Base):
    """底稿版本归档 — 记录版本元数据（文件可能已清理但元数据保留）"""

    __tablename__ = "wp_version_archive"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    working_paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("working_paper.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), server_default=text("'import'"), nullable=False
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    archive_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_retained: Mapped[bool] = mapped_column(
        server_default=text("true"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "working_paper_id", "version_no",
            name="uq_wp_version_archive_wp_ver",
        ),
    )
