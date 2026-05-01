"""共享配置模板 Pydantic Schemas"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SharedConfigCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: str = ""
    config_type: str  # report_mapping / account_mapping / formula_config / report_template / workpaper_template
    owner_type: str = "personal"  # system / group / personal
    owner_project_id: Optional[UUID] = None
    config_data: dict = Field(default_factory=dict)
    applicable_standard: Optional[str] = None  # soe / listed / both
    is_public: bool = False
    allowed_project_ids: list[UUID] = Field(default_factory=list)


class SharedConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config_data: Optional[dict] = None
    applicable_standard: Optional[str] = None
    is_public: Optional[bool] = None
    allowed_project_ids: Optional[list[UUID]] = None


class SharedConfigResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    config_type: str
    owner_type: str
    owner_user_id: Optional[UUID]
    owner_project_id: Optional[UUID]
    owner_project_name: Optional[str]
    config_version: int
    applicable_standard: Optional[str]
    is_public: bool
    reference_count: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SharedConfigDetail(SharedConfigResponse):
    config_data: dict
    allowed_project_ids: list


class ApplyTemplateRequest(BaseModel):
    template_id: UUID
    project_id: UUID


class ApplyTemplateResponse(BaseModel):
    success: bool
    message: str
    config_type: str
    items_applied: int = 0


class AvailableTemplatesRequest(BaseModel):
    config_type: str
    project_id: Optional[UUID] = None
