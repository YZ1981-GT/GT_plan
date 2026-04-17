"""Phase 10 Pydantic Schemas"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── 底稿下载/导入 ─────────────────────────────────────────

class DownloadPackRequest(BaseModel):
    wp_ids: list[UUID]
    include_prefill: bool = True


class UploadWorkpaperRequest(BaseModel):
    uploaded_version: int
    force_overwrite: bool = False


class VersionConflictResponse(BaseModel):
    has_conflict: bool
    uploaded_version: int
    server_version: int
    wp_id: str


# ── 连续审计 ──────────────────────────────────────────────

class CreateNextYearRequest(BaseModel):
    copy_team: bool = True
    copy_mapping: bool = True
    copy_procedures: bool = True


class CreateNextYearResponse(BaseModel):
    new_project_id: str
    prior_year_project_id: str
    items_copied: dict[str, int]


# ── 复核对话 ──────────────────────────────────────────────

class CreateConversationRequest(BaseModel):
    target_id: UUID
    related_object_type: str
    related_object_id: UUID | None = None
    cell_ref: str | None = None
    title: str


class SendMessageRequest(BaseModel):
    content: str
    message_type: str = "text"
    attachment_path: str | None = None
    finding_id: UUID | None = None


class ConversationResponse(BaseModel):
    id: str
    project_id: str
    initiator_id: str
    target_id: str
    related_object_type: str
    related_object_id: str | None
    cell_ref: str | None
    status: str
    title: str
    message_count: int = 0
    created_at: datetime | None = None
    closed_at: datetime | None = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    content: str
    message_type: str
    attachment_path: str | None
    finding_id: str | None
    created_at: datetime | None = None


# ── 单元格批注 ────────────────────────────────────────────

class CreateAnnotationRequest(BaseModel):
    object_type: str
    object_id: UUID
    cell_ref: str | None = None
    content: str
    priority: str = "medium"
    mentioned_user_ids: list[UUID] | None = None


class UpdateAnnotationRequest(BaseModel):
    status: str | None = None
    content: str | None = None


class AnnotationResponse(BaseModel):
    id: str
    project_id: str
    object_type: str
    object_id: str
    cell_ref: str | None
    content: str
    priority: str
    status: str
    author_id: str
    mentioned_user_ids: list[str] | None
    linked_annotation_id: str | None
    conversation_id: str | None
    created_at: datetime | None = None


# ── 私人库 ────────────────────────────────────────────────

class QuotaResponse(BaseModel):
    used: int
    limit: int
    usage_pct: float
    warning: bool


class PrivateFileResponse(BaseModel):
    name: str
    size: int
    modified_at: str
    path: str


# ── 论坛 ──────────────────────────────────────────────────

class CreatePostRequest(BaseModel):
    title: str
    content: str
    category: str = "share"
    is_anonymous: bool = False


class CreateCommentRequest(BaseModel):
    content: str


class PostResponse(BaseModel):
    id: str
    author_id: str | None
    author_name: str | None = None
    is_anonymous: bool
    category: str
    title: str
    content: str
    like_count: int
    comment_count: int = 0
    created_at: datetime | None = None


# ── 报告排版模板 ──────────────────────────────────────────

class ReportFormatTemplateCreate(BaseModel):
    template_name: str
    template_type: str
    config: dict[str, Any]


class ReportFormatTemplateUpdate(BaseModel):
    template_name: str | None = None
    config: dict[str, Any] | None = None


class ReportFormatTemplateResponse(BaseModel):
    id: str
    template_name: str
    template_type: str
    config: dict[str, Any]
    version: int
    is_default: bool
    created_at: datetime | None = None
