"""知识库数据模型 — 树形目录 + 文档 + 项目组权限

支持：
- 自定义文件夹嵌套（树形目录）
- 文档级别权限控制（public / 指定项目组）
- 预制分类文件夹 + 用户自定义文件夹
"""

import enum
import re
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.models.base import Base

#: 列宽常量（列定义直接引用，改列宽只有一处）
DOCUMENT_NAME_MAX_LEN = 500
FILE_TYPE_MAX_LEN = 20

_FILE_TYPE_RE = re.compile(r"^[a-z0-9_+\-]+$")


def strip_nul(value: Any) -> Any:
    """剔除 NUL（``\\x00``）：PostgreSQL 的 text / varchar / jsonb 都不能存它。

    2026-09-30 真库实测：UTF-16 文本或含 NUL 的文本正文写库报
    ``CharacterNotInRepertoireError``，把整批上传拖成 500。字符串与字符串列表逐项处理，
    其它类型原样返回。
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [v.replace("\x00", "") if isinstance(v, str) else v for v in value]
    return value


def normalize_file_type(value: str | None) -> str | None:
    """文档类型规范化：去首点与空白、小写；超列宽或含非法字符时返回 ``None``。

    ``file_type`` 只是展示与预览分流用的提示字段，取不到合法值宁可留空，也不能让
    「扩展名」过长的文件名（如 ``报告.final-reviewed-by-partner-v2``）撞 ``VARCHAR(20)``
    让整个上传请求 500（2026-09-30 真库实测）。
    """
    if value is None:
        return None
    t = str(value).replace("\x00", "").strip().lstrip(".").strip().lower()
    if not t or len(t) > FILE_TYPE_MAX_LEN or not _FILE_TYPE_RE.match(t):
        return None
    return t


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
    # V170：系统文件夹定位键（project:{pid} / project:{pid}:{slot}），用户文件夹为 None。
    # 部分唯一索引 uq_knowledge_folders_system_key 只约束未删除行。
    system_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
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

    @validates("name", "description")
    def _strip_nul(self, _key: str, value: Any) -> Any:
        return strip_nul(value)


class KnowledgeDocument(Base):
    """知识库文档"""

    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    folder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_folders.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(DOCUMENT_NAME_MAX_LEN), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(FILE_TYPE_MAX_LEN), nullable=True)  # pdf/docx/md/xlsx
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

    # AT-3 KB 接入：版本管理（V016）
    version: Mapped[int] = mapped_column(sa.Integer, server_default=text("1"), nullable=False)
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    # V116: 索引状态追踪
    index_status: Mapped[str | None] = mapped_column(
        String(30), server_default=text("'pending'"), nullable=True
    )
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_knowledge_documents_folder", "folder_id"),
        Index("idx_knowledge_documents_name", "name"),
    )

    # 写入清洗放在 ORM 层而非上传入口：写本表的路径有 7 条（文件夹上传、项目上传、
    # POST /documents、AI 笔记转存、版本回滚、批量建文档、索引流水线回填正文），
    # 全部经实例构造或属性赋值，validates 一处兜住（spec knowledge-upload-robustness-and-consumer-wiring R2）。
    @validates("name", "content_text", "content_summary", "tags", "index_error")
    def _strip_nul(self, _key: str, value: Any) -> Any:
        return strip_nul(value)

    @validates("file_type")
    def _normalize_file_type(self, _key: str, value: str | None) -> str | None:
        return normalize_file_type(value)
