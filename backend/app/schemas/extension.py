"""Phase 8 扩展模型 Pydantic Schemas

包含：AccountingStandard、SignatureRecord、CustomTemplate、RegulatoryFiling、
      GTWPCoding、AIPlugin 的 Create/Update/Response schemas

Validates: Requirements 2.3
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class FilingTypeEnum(str, enum.Enum):
    cicpa_report = "cicpa_report"
    archival_standard = "archival_standard"


class FilingStatusEnum(str, enum.Enum):
    submitted = "submitted"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class SignatureLevelEnum(str, enum.Enum):
    level1 = "level1"
    level2 = "level2"
    level3 = "level3"


class ObjectTypeEnum(str, enum.Enum):
    working_paper = "working_paper"
    adjustment = "adjustment"
    audit_report = "audit_report"


class TemplateCategoryEnum(str, enum.Enum):
    industry = "industry"
    client = "client"
    personal = "personal"


# ---------------------------------------------------------------------------
# AccountingStandard
# ---------------------------------------------------------------------------


class AccountingStandardCreate(BaseModel):
    standard_code: str = Field(..., max_length=20)
    standard_name: str = Field(..., max_length=100)
    standard_description: str | None = None
    effective_date: date | None = None
    is_active: bool = True


class AccountingStandardUpdate(BaseModel):
    standard_name: str | None = None
    standard_description: str | None = None
    effective_date: date | None = None
    is_active: bool | None = None


class AccountingStandardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    standard_code: str
    standard_name: str
    standard_description: str | None = None
    effective_date: date | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# SignatureRecord
# ---------------------------------------------------------------------------


class SignatureRecordCreate(BaseModel):
    object_type: str
    object_id: UUID
    signer_id: UUID
    signature_level: str
    signature_data: dict | None = None
    ip_address: str | None = None


class SignatureRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_type: str
    object_id: UUID
    signer_id: UUID
    signature_level: str
    signature_data: dict | None = None
    signature_timestamp: datetime
    ip_address: str | None = None
    is_deleted: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# CustomTemplate (WpTemplateCustom)
# ---------------------------------------------------------------------------


class CustomTemplateCreate(BaseModel):
    template_name: str = Field(..., max_length=200)
    category: TemplateCategoryEnum
    template_file_path: str = Field(..., max_length=500)
    version: str = Field(default="1.0.0", max_length=20)
    description: str | None = None
    is_published: bool = False


class CustomTemplateUpdate(BaseModel):
    template_name: str | None = None
    category: TemplateCategoryEnum | None = None
    template_file_path: str | None = None
    version: str | None = None
    description: str | None = None
    is_published: bool | None = None


class CustomTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    template_name: str
    category: str
    template_file_path: str
    is_published: bool
    version: str
    description: str | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# RegulatoryFiling
# ---------------------------------------------------------------------------


class RegulatoryFilingCreate(BaseModel):
    project_id: UUID
    filing_type: FilingTypeEnum
    submission_data: dict | None = None


class RegulatoryFilingUpdate(BaseModel):
    filing_status: FilingStatusEnum | None = None
    response_data: dict | None = None
    error_message: str | None = None


class RegulatoryFilingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    filing_type: str
    filing_status: str
    submission_data: dict | None = None
    response_data: dict | None = None
    submitted_at: datetime | None = None
    responded_at: datetime | None = None
    error_message: str | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# GTWPCoding
# ---------------------------------------------------------------------------


class GTWPCodingCreate(BaseModel):
    code_prefix: str
    code_range: str
    cycle_name: str
    wp_type: str
    description: str | None = None
    parent_cycle: str | None = None
    sort_order: int | None = None
    is_active: bool = True


class GTWPCodingUpdate(BaseModel):
    code_range: str | None = None
    cycle_name: str | None = None
    description: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class GTWPCodingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code_prefix: str
    code_range: str
    cycle_name: str
    wp_type: str
    description: str | None = None
    parent_cycle: str | None = None
    sort_order: int | None = None
    is_active: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AIPlugin
# ---------------------------------------------------------------------------


class AIPluginCreate(BaseModel):
    plugin_id: str = Field(..., max_length=100)
    plugin_name: str = Field(..., max_length=200)
    plugin_version: str = Field(..., max_length=20)
    plugin_description: str | None = None
    config: dict | None = None


class AIPluginUpdate(BaseModel):
    plugin_name: str | None = None
    plugin_version: str | None = None
    plugin_description: str | None = None
    is_enabled: bool | None = None
    config: dict | None = None


class AIPluginResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plugin_id: str
    plugin_name: str
    plugin_version: str
    plugin_description: str | None = None
    is_enabled: bool
    config: dict | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
