"""知识库数据模型 — 树形目录 + 文档 + 项目组权限

支持：
- 自定义文件夹嵌套（树形目录）
- 文档级别权限控制（public / 指定项目组）
- 预制分类文件夹 + 用户自定义文件夹
"""

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeAccessLevel(str, enum.Enum):
    """知识库访问级别"""
    public = "public"              # 全所公开
    project_group = "project_group"  # 指定项目组可见
    private = "private"            # 仅创建者可见


class KnowledgeFolder(Base):
    """知识库文件夹（树形目录）"""

    __tablename__ = "knowledge_folders"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_folders.id"), nullable=True
    )  # None = 顶级文件夹
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # 预制分类（如 accounting_standards），自定义文件夹为 None
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 权限
    access_level: Mapped[KnowledgeAccessLevel] = mapped_column(
        sa.Enum(KnowledgeAccessLevel, name="knowledge_access_level", create_type=False),
        server_default=text("'public'"),
        nullable=False,
    )
    project_ids: Mapped[list | None] = mapped_column(
        JSONB, nullable=True
    )  # access_level=project_group 时，允许访问的项目 ID 列表

    # 元数据
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )

    __table_args__ = (
        Index("idx_knowledge_folders_parent", "parent_id"),
        Index("idx_knowledge_folders_category", "category"),
    )


class KnowledgeDocument(Base):
    """知识库文档"""

    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    folder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_folders.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # pdf/docx/md/xlsx
    file_size: Mapped[int] = mapped_column(
        sa.BigInteger, server_default=text("0"), nullable=False
    )
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # 文件存储路径

    # 内容（小文件直接存文本，大文件存路径）
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 文本内容（供 RAG 检索）
    content_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # 摘要

    # 权限（继承文件夹权限，或单独设置）
    access_level: Mapped[KnowledgeAccessLevel | None] = mapped_column(
        sa.Enum(KnowledgeAccessLevel, name="knowledge_access_level", create_type=False),
        nullable=True,
    )  # None = 继承文件夹权限
    project_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # 元数据
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # 标签
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )

    __table_args__ = (
        Index("idx_knowledge_documents_folder", "folder_id"),
        Index("idx_knowledge_documents_name", "name"),
    )
