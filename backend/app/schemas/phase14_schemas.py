"""Phase 14: 门禁引擎 Pydantic Schemas"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Gate Engine ──

class GateEvaluateRequest(BaseModel):
    gate_type: str = Field(..., description="门禁类型: submit_review/sign_off/export_package")
    project_id: uuid.UUID
    wp_id: Optional[uuid.UUID] = None
    actor_id: uuid.UUID
    context: dict = Field(default_factory=dict)


class GateRuleHitSchema(BaseModel):
    rule_code: str
    error_code: str
    severity: str  # blocking/warning/info
    message: str
    location: Optional[dict] = None
    suggested_action: Optional[str] = None


class GateEvaluateResponse(BaseModel):
    decision: str  # allow/block/warn
    hit_rules: list[GateRuleHitSchema] = []
    trace_id: str


# ── SoD ──

class SoDCheckRequest(BaseModel):
    project_id: uuid.UUID
    wp_id: uuid.UUID
    actor_id: uuid.UUID
    target_role: str


class SoDCheckResponse(BaseModel):
    allowed: bool
    conflict_type: Optional[str] = None
    policy_code: Optional[str] = None
    trace_id: str


# ── Trace ──

class TraceEventSchema(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    event_type: str
    object_type: str
    object_id: uuid.UUID
    actor_id: uuid.UUID
    actor_role: Optional[str] = None
    action: str
    decision: Optional[str] = None
    reason_code: Optional[str] = None
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    content_hash: Optional[str] = None
    version_no: Optional[int] = None
    trace_id: str
    created_at: datetime


class TraceReplayResponse(BaseModel):
    trace_id: str
    level: str  # L1/L2/L3
    events: list[dict]


class TraceQueryRequest(BaseModel):
    project_id: uuid.UUID
    event_type: Optional[str] = None
    object_type: Optional[str] = None
    object_id: Optional[uuid.UUID] = None
    page: int = 1
    page_size: int = 50


class TraceQueryResponse(BaseModel):
    items: list[TraceEventSchema]
    total: int
    page: int
    page_size: int


# ── Gate Rule Config ──

class GateRuleConfigSchema(BaseModel):
    rule_code: str
    config_level: str  # platform/tenant
    threshold_key: Optional[str] = None
    threshold_value: Optional[str] = None
    tenant_id: Optional[uuid.UUID] = None
    updated_by: Optional[uuid.UUID] = None
    updated_at: Optional[datetime] = None


class GateRuleConfigUpdateRequest(BaseModel):
    threshold_key: str
    threshold_value: str
