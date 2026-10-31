"""formula_runtime schemas — Pydantic response models for draft-refresh API.

Strict types matching design.md §11 API contract.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PresetApplication(BaseModel):
    """预设套用结果（design §11）。"""

    preset_count: int = 0
    presetted_pages: list[str] = Field(default_factory=list)
    pending_pages: list[str] = Field(default_factory=list)


class DraftRefreshRequest(BaseModel):
    """POST /api/workpapers/draft-refresh 请求体（design §11 + Req 10/12/13）。

    - scopes: 必需非空列表，空 scopes 返回 422。
    - transaction_mode: 事务模式，默认 all_or_nothing。
    - idempotency_key: 可选幂等键。
    """

    project_id: UUID
    year: int
    scopes: list[str] = Field(..., min_length=1)
    transaction_mode: Literal["all_or_nothing", "partial_success"] = "all_or_nothing"
    idempotency_key: str | None = None
    confirm_overwrite: bool = False


class DraftRefreshResponse(BaseModel):
    """POST /api/workpapers/draft-refresh 标准响应（design §11）。

    ``status`` / ``outcome`` 按需求 3.2 状态表派生（``formula_management.refresh_outcome`` 的 ``RESPONSE_STATUSES`` /
    ``OUTCOMES`` 与这里的 Literal 相等，有测试守着）；幂等命中 ``status = idempotent_hit``、``outcome`` = 首次运行的
    outcome。计数（需求 3.3）：``affected_count = applied_count + recomputed_count``，``draft_marked_count`` 单列。
    """

    status: Literal[
        "success", "recomputed", "draft_marked", "no_effect", "partial_success", "failed", "idempotent_hit",
    ]
    outcome: Literal["applied", "recomputed", "draft_marked", "no_effect", "partial", "failed"] | None = None
    run_id: UUID
    transaction_mode: Literal["all_or_nothing", "partial_success"]
    affected_count: int = 0
    applied_count: int = 0
    recomputed_count: int = 0
    draft_marked_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    scopes: list[str] = Field(default_factory=list)
    idempotent: bool = False
    rollback_available: bool = True
    warnings: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    preset_application: PresetApplication = Field(default_factory=PresetApplication)


class RollbackResponse(BaseModel):
    """POST /api/workpapers/draft-refresh/{run_id}/rollback 响应（design §11）。"""

    status: Literal["rolled_back", "failed"]
    run_id: UUID
    restored_count: int = 0
    conflicts: list[str] = Field(default_factory=list)
    error: str | None = None
