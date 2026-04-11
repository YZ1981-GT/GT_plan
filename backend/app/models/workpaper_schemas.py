"""第一阶段MVP底稿：Pydantic Schema 定义

覆盖底稿模块 API 请求/响应模型：
- 模板管理 (TemplateUpload, TemplateResponse, TemplateSetResponse)
- 底稿管理 (WPFilter, WPResponse, WPIndexResponse)
- 取数公式 (FormulaRequest, FormulaResult)
- 质量自检 (QCFinding, QCResult, QCSummary)
- 复核批注 (ReviewCommentCreate, ReviewReply, ReviewRecordResponse)
- WOPI (WOPIFileInfo)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.workpaper_models import (
    RegionType,
    ReviewCommentStatus,
    WpFileStatus,
    WpSourceType,
    WpStatus,
    WpTemplateStatus,
)


# ===================================================================
# 1. 模板管理 (Template)
# ===================================================================


class TemplateMetadata(BaseModel):
    """模板上传元数据"""
    template_code: str
    template_name: str
    audit_cycle: str | None = None
    applicable_standard: str | None = None
    description: str | None = None


class TemplateUpload(BaseModel):
    """模板上传请求（元数据部分，文件通过 multipart 上传）"""
    template_code: str
    template_name: str
    audit_cycle: str | None = None
    applicable_standard: str | None = None
    description: str | None = None
    change_type: str = "minor"  # "major" or "minor"


class TemplateRegionResponse(BaseModel):
    """模板区域响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    range_name: str
    region_type: RegionType
    description: str | None = None


class TemplateResponse(BaseModel):
    """模板响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_code: str
    template_name: str
    audit_cycle: str | None = None
    applicable_standard: str | None = None
    version_major: int = 1
    version_minor: int = 0
    status: WpTemplateStatus = WpTemplateStatus.draft
    file_path: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TemplateSetResponse(BaseModel):
    """模板集响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    set_name: str
    template_codes: list[str] | None = None
    applicable_audit_type: str | None = None
    applicable_standard: str | None = None
    description: str | None = None


# ===================================================================
# 2. 底稿管理 (Working Paper)
# ===================================================================


class WPFilter(BaseModel):
    """底稿列表筛选"""
    audit_cycle: str | None = None
    status: WpStatus | None = None
    assigned_to: UUID | None = None


class WPIndexResponse(BaseModel):
    """底稿索引响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    wp_code: str
    wp_name: str
    audit_cycle: str | None = None
    assigned_to: UUID | None = None
    reviewer: UUID | None = None
    status: WpStatus = WpStatus.not_started
    cross_ref_codes: list[str] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WPResponse(BaseModel):
    """底稿文件响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    wp_index_id: UUID
    file_path: str
    source_type: WpSourceType
    status: WpFileStatus = WpFileStatus.draft
    assigned_to: UUID | None = None
    reviewer: UUID | None = None
    file_version: int = 1
    last_parsed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ===================================================================
# 3. 取数公式 (Formula)
# ===================================================================


class FormulaRequest(BaseModel):
    """取数公式执行请求"""
    project_id: UUID
    year: int
    formula_type: str  # TB / WP / AUX / PREV / SUM_TB
    params: dict[str, Any] = {}


class FormulaResult(BaseModel):
    """取数公式执行结果"""
    value: Any = None
    cached: bool = False
    error: str | None = None


# ===================================================================
# 4. 质量自检 (QC)
# ===================================================================


class QCFinding(BaseModel):
    """质量自检发现"""
    rule_id: str
    severity: str  # blocking / warning / info
    message: str
    cell_reference: str | None = None
    expected_value: Any = None
    actual_value: Any = None


class QCResult(BaseModel):
    """质量自检结果"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    working_paper_id: UUID
    check_timestamp: datetime
    findings: list[dict] = []
    passed: bool
    blocking_count: int = 0
    warning_count: int = 0
    info_count: int = 0


class QCSummary(BaseModel):
    """项目级QC汇总"""
    total_workpapers: int = 0
    passed_qc: int = 0
    has_blocking: int = 0
    not_started: int = 0
    not_checked: int = 0
    pass_rate: float = 0.0


# ===================================================================
# 5. 复核批注 (Review)
# ===================================================================


class ReviewCommentCreate(BaseModel):
    """创建复核意见"""
    working_paper_id: UUID
    cell_reference: str | None = None
    comment_text: str


class ReviewReply(BaseModel):
    """回复复核意见"""
    reply_text: str


class ReviewRecordResponse(BaseModel):
    """复核意见响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    working_paper_id: UUID
    cell_reference: str | None = None
    comment_text: str
    commenter_id: UUID
    status: ReviewCommentStatus = ReviewCommentStatus.open
    reply_text: str | None = None
    replier_id: UUID | None = None
    replied_at: datetime | None = None
    resolved_by: UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ===================================================================
# 6. WOPI
# ===================================================================


class WOPIFileInfo(BaseModel):
    """WOPI CheckFileInfo 响应"""
    BaseFileName: str
    Size: int
    OwnerId: str
    Version: str
    UserCanWrite: bool = True
    UserCanNotWriteRelative: bool = True
    SupportsLocks: bool = True
    UserFriendlyName: str | None = None



# ===================================================================
# 7. 抽样管理 (Sampling)
# ===================================================================


class SamplingConfigCreate(BaseModel):
    """创建抽样配置"""
    config_name: str
    sampling_type: str  # statistical / non_statistical
    sampling_method: str  # mus / attribute / random / systematic / stratified
    applicable_scenario: str  # control_test / substantive_test
    confidence_level: Decimal | None = None
    expected_deviation_rate: Decimal | None = None
    tolerable_deviation_rate: Decimal | None = None
    tolerable_misstatement: Decimal | None = None
    population_amount: Decimal | None = None
    population_count: int | None = None


class SamplingConfigResponse(BaseModel):
    """抽样配置响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    config_name: str
    sampling_type: str
    sampling_method: str
    applicable_scenario: str
    confidence_level: Decimal | None = None
    expected_deviation_rate: Decimal | None = None
    tolerable_deviation_rate: Decimal | None = None
    tolerable_misstatement: Decimal | None = None
    population_amount: Decimal | None = None
    population_count: int | None = None
    calculated_sample_size: int | None = None
    is_deleted: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SamplingRecordCreate(BaseModel):
    """创建抽样记录"""
    working_paper_id: UUID | None = None
    sampling_config_id: UUID | None = None
    sampling_purpose: str
    population_description: str
    population_total_amount: Decimal | None = None
    population_total_count: int | None = None
    sample_size: int
    sampling_method_description: str | None = None
    deviations_found: int | None = None
    misstatements_found: Decimal | None = None
    projected_misstatement: Decimal | None = None
    upper_misstatement_limit: Decimal | None = None
    conclusion: str | None = None


class SamplingRecordResponse(BaseModel):
    """抽样记录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    working_paper_id: UUID | None = None
    sampling_config_id: UUID | None = None
    sampling_purpose: str
    population_description: str
    population_total_amount: Decimal | None = None
    population_total_count: int | None = None
    sample_size: int
    sampling_method_description: str | None = None
    deviations_found: int | None = None
    misstatements_found: Decimal | None = None
    projected_misstatement: Decimal | None = None
    upper_misstatement_limit: Decimal | None = None
    conclusion: str | None = None
    is_deleted: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MUSEvaluation(BaseModel):
    """MUS评价结果"""
    projected_misstatement: Decimal
    upper_misstatement_limit: Decimal
    details: list[dict] = []


class SampleSizeCalculation(BaseModel):
    """样本量计算结果"""
    method: str
    params: dict = {}
    calculated_size: int
