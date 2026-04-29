"""Phase 15: 任务树与事件编排 Pydantic Schemas"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Task Tree ──

class TaskTreeNodeSchema(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    node_level: str  # unit/account/workpaper/evidence
    parent_id: Optional[uuid.UUID] = None
    ref_id: uuid.UUID
    status: str  # pending/in_progress/blocked/done
    assignee_id: Optional[uuid.UUID] = None
    due_at: Optional[datetime] = None
    meta: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class TaskTreeTransitRequest(BaseModel):
    next_status: str
    operator_id: uuid.UUID


class TaskTreeReassignRequest(BaseModel):
    task_node_id: uuid.UUID
    assignee_id: uuid.UUID
    operator_id: uuid.UUID
    reason_code: str


class TaskTreeStatsResponse(BaseModel):
    total: int
    by_level: dict[str, dict[str, int]]  # {node_level: {status: count}}
    completion_rate: float


# ── Task Events ──

class TaskEventSchema(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    event_type: str
    task_node_id: Optional[uuid.UUID] = None
    payload: dict
    status: str  # queued/processing/succeeded/failed/dead_letter
    retry_count: int
    max_retries: int
    next_retry_at: Optional[datetime] = None
    error_message: Optional[str] = None
    trace_id: str
    created_at: datetime


class TaskEventReplayRequest(BaseModel):
    event_id: uuid.UUID
    operator_id: uuid.UUID
    reason_code: str


# ── Issue Tickets ──

class IssueFromConversationRequest(BaseModel):
    conversation_id: uuid.UUID
    task_node_id: Optional[uuid.UUID] = None
    operator_id: uuid.UUID
    sla_level: str = Field(..., description="P0/P1/P2")


class IssueStatusUpdateRequest(BaseModel):
    status: str
    operator_id: uuid.UUID
    reason_code: str
    evidence_refs: list[str] = Field(default_factory=list)


class IssueEscalateRequest(BaseModel):
    from_level: str  # L2/L3/Q
    to_level: str
    reason_code: str


class IssueTicketSchema(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    wp_id: Optional[uuid.UUID] = None
    task_node_id: Optional[uuid.UUID] = None
    conversation_id: Optional[uuid.UUID] = None
    source: str  # L2/L3/Q
    severity: str  # blocker/major/minor/suggestion
    category: str
    title: str
    description: Optional[str] = None
    owner_id: uuid.UUID
    due_at: Optional[datetime] = None
    status: str
    evidence_refs: list = Field(default_factory=list)
    reason_code: Optional[str] = None
    trace_id: str
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None


class IssueListResponse(BaseModel):
    items: list[IssueTicketSchema]
    total: int
    page: int
    page_size: int


# ── RC Enhanced ──

class RCExportEvidenceRequest(BaseModel):
    purpose: str
    receiver: str
    export_scope: str = "full_timeline"  # full_timeline/summary/attachments_only
    mask_policy: str = "standard"  # none/standard/strict
    include_hash_manifest: bool = False


class RCExportEvidenceResponse(BaseModel):
    export_id: str
    file_url: str
    hash: str
    trace_id: str


class RCParticipantRequest(BaseModel):
    user_id: uuid.UUID
    role: str = "viewer"
    is_required_ack: bool = False
