"""核心模型扩展 Pydantic Schemas

扩展 User/Project schemas 以支持 Phase 8 新增字段：
- User: language 字段
- Project: accounting_standard_id 字段
- 扩展 audit_type 枚举

Validates: Requirements 2.4
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.base import ProjectStatus, UserRole


# ---------------------------------------------------------------------------
# 扩展审计类型枚举
# ---------------------------------------------------------------------------


class ExtendedAuditType(str, enum.Enum):
    """扩展审计类型（含 Phase 8 新增类型）"""

    annual = "annual"
    special = "special"
    ipo = "ipo"
    internal_control = "internal_control"
    special_audit = "special_audit"
    ipo_audit = "ipo_audit"
    internal_control_audit = "internal_control_audit"
    capital_verification = "capital_verification"
    tax_audit = "tax_audit"


# ---------------------------------------------------------------------------
# User Schemas
# ---------------------------------------------------------------------------


class UserCreateExtended(BaseModel):
    """创建用户（含 language 字段）"""

    username: str
    email: EmailStr
    password: str
    role: UserRole
    office_code: str | None = None
    language: str = Field(default="zh-CN", pattern=r"^(zh-CN|en-US)$")


class UserResponseExtended(BaseModel):
    """用户响应（含 language 字段）"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str
    role: UserRole
    office_code: str | None = None
    is_active: bool
    language: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Project Schemas
# ---------------------------------------------------------------------------


class ProjectCreateExtended(BaseModel):
    """创建项目（含 accounting_standard 字段）"""

    name: str = Field(..., max_length=255)
    client_name: str = Field(..., max_length=255)
    audit_period_start: date | None = None
    audit_period_end: date | None = None
    project_type: ExtendedAuditType | None = None
    materiality_level: float | None = None
    accounting_standard_id: UUID | None = None


class ProjectUpdateExtended(BaseModel):
    """更新项目（含 accounting_standard 字段）"""

    name: str | None = None
    client_name: str | None = None
    audit_period_start: date | None = None
    audit_period_end: date | None = None
    project_type: ExtendedAuditType | None = None
    materiality_level: float | None = None
    status: ProjectStatus | None = None
    accounting_standard_id: UUID | None = None


class ProjectResponseExtended(BaseModel):
    """项目响应（含 accounting_standard_id 字段）"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    client_name: str
    audit_period_start: date | None = None
    audit_period_end: date | None = None
    project_type: str | None = None
    materiality_level: float | None = None
    status: ProjectStatus
    accounting_standard_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
