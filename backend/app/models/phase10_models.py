"""Phase 10 ORM 模型 — 复核对话 + 论坛 + 批注 + 快照 + 打卡 + 排版模板"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ── 复核对话 ──────────────────────────────────────────────

class ReviewConversation(Base):
    __tablename__ = "review_conversations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    initiator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    related_object_type: Mapped[str] = mapped_column(String(50), nullable=False)
    related_object_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    cell_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'open'"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReviewMessage(Base):
    __tablename__ = "review_messages"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_conversations.id"), nullable=False)
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), server_default=text("'text'"))
    attachment_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ── 论坛 ──────────────────────────────────────────────────

class ForumPost(Base):
    __tablename__ = "forum_posts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(server_default=text("false"))
    category: Mapped[str] = mapped_column(String(20), server_default=text("'share'"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    like_count: Mapped[int] = mapped_column(sa.Integer, server_default=text("0"))
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ForumComment(Base):
    __tablename__ = "forum_comments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("forum_posts.id"), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ── 单元格批注 ────────────────────────────────────────────

class CellAnnotation(Base):
    __tablename__ = "cell_annotations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    cell_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), server_default=text("'medium'"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    mentioned_user_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    linked_annotation_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ── 合并快照 ──────────────────────────────────────────────

class ConsolSnapshot(Base):
    __tablename__ = "consol_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    snapshot_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    trigger_reason: Mapped[str] = mapped_column(String(30), nullable=False)
    diff_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ── 打卡签到 ──────────────────────────────────────────────

class CheckIn(Base):
    __tablename__ = "check_ins"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_members.id"), nullable=False)
    check_time: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    latitude: Mapped[float | None] = mapped_column(sa.Numeric(10, 7), nullable=True)
    longitude: Mapped[float | None] = mapped_column(sa.Numeric(10, 7), nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    check_type: Mapped[str] = mapped_column(String(20), server_default=text("'morning'"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ── 报告排版模板 ──────────────────────────────────────────

class ReportFormatTemplate(Base):
    __tablename__ = "report_format_templates"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_name: Mapped[str] = mapped_column(String(200), nullable=False)
    template_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, server_default=text("1"))
    is_default: Mapped[bool] = mapped_column(server_default=text("false"))
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
