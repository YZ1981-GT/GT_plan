"""Phase 13: 审计报告·报表·附注生成与导出 — Pydantic Schemas

覆盖：
- WordExportTask 创建/响应/历史
- ReportSnapshot 创建/响应
- PlaceholderMap 占位符映射
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ===================================================================
# Word 导出任务
# ===================================================================

class WordExportTaskCreate(BaseModel):
    """创建 Word 导出任务"""
    project_id: UUID
    doc_type: str  # audit_report / financial_report / disclosure_notes / full_package
    template_type: str | None = None  # soe / listed / custom


class WordExportTaskResponse(BaseModel):
    """Word 导出任务响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    doc_type: str
    status: str
    file_path: str | None = None
    template_type: str | None = None
    snapshot_id: UUID | None = None
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None
    created_by: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WordExportHistoryResponse(BaseModel):
    """Word 导出历史列表"""
    tasks: list[WordExportTaskResponse] = []


# ===================================================================
# 报表数据快照
# ===================================================================

class ReportSnapshotCreate(BaseModel):
    """创建报表快照"""
    project_id: UUID
    year: int


class ReportSnapshotResponse(BaseModel):
    """报表快照响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    year: int
    report_type: str
    generated_at: datetime | None = None
    is_stale: bool = False
    data: dict | None = None


# ===================================================================
# 占位符映射
# ===================================================================

class PlaceholderMap(BaseModel):
    """审计报告正文占位符映射"""
    entity_name: str = ""
    entity_short_name: str = ""
    report_scope: str = ""
    audit_period: str = ""
    audit_year: str = ""
    signing_partner: str = ""
    report_date: str = ""
    firm_name: str = "致同会计师事务所（特殊普通合伙）"
    cpa_name_1: str = ""
    cpa_name_2: str = ""


class ScopeReplacementRequest(BaseModel):
    """报表口径替换请求"""
    project_id: UUID
    report_scope: str  # "consolidated" | "standalone"


class WordExportTaskConfirm(BaseModel):
    """确认导出任务（可附带备注）"""
    notes: str | None = None


class StaleCheckResponse(BaseModel):
    """快照过期检测响应"""
    is_stale: bool = False
    stale_reason: str | None = None


# ===================================================================
# 后台导出任务 (Stage 2.5)
# ===================================================================

class ExportJobCreate(BaseModel):
    """创建后台导出任务"""
    project_id: UUID
    job_type: str  # generate / full_package / retry
    payload: dict | None = None


class ExportJobItemResponse(BaseModel):
    """后台导出任务明细响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    word_export_task_id: UUID | None = None
    status: str
    error_message: str | None = None
    finished_at: datetime | None = None


class ExportJobResponse(BaseModel):
    """后台导出任务响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    job_type: str
    status: str
    payload: dict | None = None
    progress_total: int = 0
    progress_done: int = 0
    failed_count: int = 0
    initiated_by: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None
    items: list[ExportJobItemResponse] = []


class FullPackageRequest(BaseModel):
    """全套导出请求"""
    year: int
    template_type: str | None = None


# ===================================================================
# 交付件管理中心 (deliverable-center)
# ===================================================================

class DeliverableDTOSchema(BaseModel):
    """交付物列表 DTO"""
    task_id: UUID
    project_id: UUID
    doc_type: str
    status: str
    file_name: str | None = None
    version_no: int
    file_size: int | None = None
    exporter_name: str | None = None
    exported_at: datetime | None = None
    template_type: str | None = None
    selected_sections: list | None = None


class DeliverableListResponse(BaseModel):
    items: list[DeliverableDTOSchema] = []
    grouped: dict[str, list[DeliverableDTOSchema]] = {}


class DeliverableVersionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    word_export_task_id: UUID
    version_no: int
    file_path: str | None = None
    html_path: str | None = None
    file_size: int | None = None
    created_by: UUID
    created_at: datetime | None = None
    selected_sections: list | None = None
    created_via: str | None = None


class VersionCompareRequest(BaseModel):
    version_a: int
    version_b: int


class VersionCompareResponse(BaseModel):
    version_a: int
    version_b: int
    exported_at_diff: dict | None = None
    file_size_diff: dict | None = None
    selected_sections_diff: dict | None = None


class ReportBodyLoadTemplateRequest(BaseModel):
    opinion_type: str
    company_type: str = "non_listed"
    include_emphasis: bool = False


class ReportBodyRenderRequest(BaseModel):
    year: int
    opinion_type: str
    company_type: str = "non_listed"
    is_pie: bool = False
    include_emphasis: bool = False
    selected_sections: list[str] | None = None
    prior_period_info: str | None = None


class ReportBodyRenderResponse(BaseModel):
    task_id: UUID
    version_no: int
    download_url: str
    html_preview: str
    platform_persist_failed: bool = False
    report_body_json: dict | None = None
    validation_warning: str | None = None


class DeliverableExportRequest(BaseModel):
    year: int
    template_type: str = "soe"
    selected_sections: list[str] | None = None
    report_types: list[str] | None = None


class DeliverableExportResponse(BaseModel):
    task_id: UUID
    version_no: int
    download_url: str
    platform_persist_failed: bool = False
    file_name: str | None = None


class CompletenessResponse(BaseModel):
    passed: bool
    missing_doc_types: list[str] = []
    missing_financial_reports: list[str] = []
    has_confirmed: bool = False
    trio_consistent: bool = True
    trio_message: str | None = None
    warnings: list[str] = []


class SnapshotStaleResponse(BaseModel):
    stale: bool
    bound_tb_hash: str | None = None
    current_tb_hash: str | None = None
    message: str | None = None


class DeliverableSignRequest(BaseModel):
    sign_type: str = Field(..., description="项目合伙人 / 复核合伙人")
    year: int


class DeliverableSignResponse(BaseModel):
    task_id: UUID
    status: str
    signed_by: UUID
    signed_at: datetime | None = None
    sign_type: str | None = None


class ReportDateComplianceRequest(BaseModel):
    year: int
    report_date: date


class ReportDateComplianceResponse(BaseModel):
    compliant: bool
    requires_confirmation: bool = False
    warnings: list[str] = []
    floor_date: str | None = None


class OnlyOfficeHealthResponse(BaseModel):
    available: bool
    enabled: bool
    message: str | None = None


class DeliverableApprovalRejectRequest(BaseModel):
    reason: str


class DeliverableApprovalResponse(BaseModel):
    task_id: UUID
    status: str
    approval_by: UUID | None = None
    approval_at: datetime | None = None
    reject_reason: str | None = None


class DeliverableArchiveRequest(BaseModel):
    year: int
    force: bool = False


class DeliverableArchiveResponse(BaseModel):
    archived_count: int


class DeliverableUnarchiveRequest(BaseModel):
    reason: str


class IntegrityVerifyResponse(BaseModel):
    valid: bool
    tampered_versions: list[int] = []
    checked_count: int = 0
    message: str | None = None


class DeliverablePackageRequest(BaseModel):
    year: int
    ignore_incomplete: bool = False


class DeliverablePackageResponse(BaseModel):
    job_id: UUID
    warnings: list[str] = []


class OnlyOfficeConfigResponse(BaseModel):
    config: dict
    token: str
    mode: str
    documentType: str
