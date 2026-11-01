"""合并报表正式 run、preview/published 与不可变 artifact API 契约。"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReportRunStatus = Literal["building", "succeeded", "failed", "stale"]
ArtifactKind = Literal["report_excel", "consol_workpaper"]
ArtifactStatus = Literal["generating", "ready", "failed"]
ReportMode = Literal["published", "preview"]


class ReportRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    year: int
    operation_id: UUID | None = None
    operation_revision: int | None = None
    node_key: str | None = None
    applicable_standard: str | None = None
    trigger: str
    status: ReportRunStatus
    calc_version: int
    input_digest: str | None = None
    row_digest: str | None = None
    row_count: int
    report_types: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None


class ConsolReportEnvelope(BaseModel):
    mode: ReportMode
    published: bool
    project_id: UUID
    year: int
    node_key: str
    report_type: str
    operation_id: UUID | None = None
    operation_revision: int | None = None
    report_run_id: UUID | None = None
    input_digest: str | None = None
    row_digest: str | None = None
    applicable_standard: str | None = None
    download_allowed: bool = False
    rows: list[dict[str, Any]] = Field(default_factory=list)
    notice: str | None = None


class ConsolArtifactCreate(BaseModel):
    report_run_id: UUID
    kind: ArtifactKind = "consol_workpaper"
    node_key: str | None = None

    @field_validator("node_key")
    @classmethod
    def reject_blank_node(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("node_key 不能为空字符串")
        return value


class ConsolArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    year: int
    operation_id: UUID | None = None
    operation_revision: int | None = None
    report_run_id: UUID
    node_key: str
    kind: ArtifactKind
    status: ArtifactStatus
    file_name: str
    content_type: str
    size_bytes: int | None = None
    sha256: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str | None = None
    ready_at: str | None = None
