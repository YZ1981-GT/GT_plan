"""附件溯源关联 Pydantic Schema — wp-traceability-panel Task 2.2

Requirements: 3.1, 3.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AttachmentLineageCreate(BaseModel):
    """创建附件关联请求"""

    target_type: Literal["wp_cell", "report_row", "note_section"] = Field(
        ..., description="关联目标类型"
    )
    target_id: UUID | None = Field(default=None, description="关联目标 UUID")
    target_ref: str | None = Field(
        default=None, max_length=200, description="精确位置引用，如 D2-3!B5"
    )


class AttachmentLineageResponse(BaseModel):
    """附件关联响应"""

    model_config = {"from_attributes": True}

    id: UUID
    attachment_id: UUID
    target_type: str
    target_id: UUID | None = None
    target_ref: str | None = None
    created_at: datetime | None = None


class AttachmentRef(BaseModel):
    """溯源图中的附件引用（轻量）"""

    id: UUID
    attachment_id: UUID
    target_type: str
    target_ref: str | None = None
    file_name: str | None = None
    file_type: str | None = None
    created_at: datetime | None = None
