"""Phase 12: 底稿深度开发 — Pydantic Schemas"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 审计说明生成
# ---------------------------------------------------------------------------

class GenerateDraftRequest(BaseModel):
    wp_id: UUID


class GenerateDraftResponse(BaseModel):
    generation_id: UUID
    prompt_version: str
    draft_text: str
    structured: dict | None = None
    data_sources: list[str] = []
    confidence: str = "medium"
    suggestions: list[str] = []


class ConfirmDraftRequest(BaseModel):
    generation_id: UUID
    final_text: str


class ConfirmDraftResponse(BaseModel):
    explanation_status: str
    last_parsed_sync_at: datetime | None = None


class RefineDraftRequest(BaseModel):
    generation_id: UUID
    user_edits: str
    feedback: str | None = None


class AiGenerationRecord(BaseModel):
    id: UUID
    wp_id: UUID
    prompt_version: str
    model: str
    status: str
    output_text: str | None = None
    created_at: datetime
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# 后台任务
# ---------------------------------------------------------------------------

class JobCreateResponse(BaseModel):
    job_id: UUID
    status: str = "queued"


class JobItemResponse(BaseModel):
    id: UUID
    wp_id: UUID
    status: str
    error_message: str | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class JobStatusResponse(BaseModel):
    id: UUID
    job_type: str
    status: str
    progress_total: int = 0
    progress_done: int = 0
    failed_count: int = 0
    items: list[JobItemResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class JobRetryResponse(BaseModel):
    job_id: UUID
    retried_count: int


# ---------------------------------------------------------------------------
# AI预审
# ---------------------------------------------------------------------------

class ReviewIssue(BaseModel):
    description: str
    severity: str = "warning"  # warning | blocking
    suggested_action: str | None = None


class ReviewContentResponse(BaseModel):
    issues: list[ReviewIssue] = []


# ---------------------------------------------------------------------------
# 签字前检查
# ---------------------------------------------------------------------------

class ReadinessCheckItem(BaseModel):
    check_name: str
    passed: bool
    detail: str | None = None
    failed_wp_ids: list[UUID] = []


class WorkpaperReadinessResponse(BaseModel):
    all_passed: bool
    checks: list[ReadinessCheckItem] = []
    total_workpapers: int = 0
    check_duration_ms: int = 0


# ---------------------------------------------------------------------------
# 推荐反馈
# ---------------------------------------------------------------------------

class RecommendFeedbackRequest(BaseModel):
    wp_code: str
    action: str  # accepted | skipped | manually_added


class RecommendStatsResponse(BaseModel):
    adoption_rate: float = 0.0
    omission_rate: float = 0.0
    total_recommendations: int = 0
    by_category: list[dict] = []
