"""临时授权 Pydantic Schema

请求/响应模型，供 router 层使用。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TemporaryGrantCreate(BaseModel):
    """创建临时授权请求"""

    operation_code: str = Field(
        ...,
        description="授权的操作代码，如 wp:edit、report:sign",
        max_length=64,
    )
    grantee: UUID = Field(..., description="被授权人 ID")
    reason: str = Field(
        ...,
        description="授权原因",
        min_length=2,
        max_length=500,
    )
    expires_at: datetime = Field(..., description="过期时间（UTC）")


class TemporaryGrantResponse(BaseModel):
    """临时授权响应"""

    id: UUID
    project_id: UUID
    operation_code: str
    grantee: UUID
    approver: UUID
    reason: str
    expires_at: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemporaryGrantListResponse(BaseModel):
    """临时授权列表响应"""

    grants: list[TemporaryGrantResponse]
    total: int
