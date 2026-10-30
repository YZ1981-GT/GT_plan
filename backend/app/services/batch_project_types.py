"""批量建项跨模块 DTO 与无副作用身份辅助。"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.models.core import Project
from app.services import batch_project_workbook as workbook_io


class BatchImportFailure(BaseModel):
    row_number: int
    errors: list[str]


class BatchActionSummary(BaseModel):
    create: int = 0
    update: int = 0
    unchanged: int = 0
    skip: int = 0
    auto_root: int = 0
    error: int = 0


class BatchImportResult(BaseModel):
    success_count: int
    fail_count: int
    failures: list[BatchImportFailure] = Field(default_factory=list)
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    skipped_count: int = 0
    auto_root_count: int = 0
    project_ids: list[str] = Field(default_factory=list)
    root_project_ids: list[str] = Field(default_factory=list)
    idempotent: bool = False


class RowError(BaseModel):
    row_number: int
    errors: list[str]


class RowWarning(BaseModel):
    row_number: int
    messages: list[str]


class BatchValidateResponse(BaseModel):
    valid: bool
    total_rows: int
    tree_preview: list[dict]
    errors: list[RowError]
    warnings: list[RowWarning] = Field(default_factory=list)
    summary: BatchActionSummary = Field(default_factory=BatchActionSummary)
    file_sha256: str | None = None
    template_version: str | None = None
    validation_id: UUID | None = None
    expires_at: str | None = None


class BatchAnalysis(BaseModel):
    loaded_sha256: str
    template_version: str | None
    parsed_rows: list[workbook_io.ParsedRow]
    response: BatchValidateResponse
    # 仅持久化在计划 summary 中的私有依赖快照；绝不回传给浏览器。
    dependencies: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


def role_value(user: Any | None) -> str | None:
    role = getattr(user, "role", None)
    return getattr(role, "value", role)


def row_key(row: workbook_io.ParsedRow) -> tuple[str, int | None, str]:
    return row.company_code, row.audit_year, row.report_scope


def project_key(project: Project) -> tuple[str, int | None, str]:
    return (project.company_code or "").strip(), project.audit_year, project.report_scope or "standalone"


def project_year(project: Project) -> int | None:
    if project.audit_year is not None:
        return project.audit_year
    from app.services.project_audit_year import resolve_project_audit_year
    return resolve_project_audit_year(project)


def accounting_standard(project: Project | None) -> str:
    if project is None:
        return "enterprise"
    state = project.wizard_state or {}
    return str(
        state.get("steps", {}).get("basic_info", {}).get("data", {}).get("accounting_standard")
        or "enterprise"
    )


def public_error(exc: BaseException) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            return str(detail.get("message") or detail.get("detail") or "批量建项失败")
        return str(detail)
    text = str(exc).upper()
    if "UNIQUE" in text or "UQ_PROJECT_COMPANY_YEAR_SCOPE" in text:
        return "项目已被其他操作创建，请重新预校验"
    return "批量建项执行失败，已全部回滚，请重新预校验后重试"


__all__ = [
    "BatchActionSummary", "BatchAnalysis", "BatchImportFailure", "BatchImportResult",
    "BatchValidateResponse", "RowError", "RowWarning", "accounting_standard",
    "project_key", "project_year", "public_error", "role_value", "row_key",
]
