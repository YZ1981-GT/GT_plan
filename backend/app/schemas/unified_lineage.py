"""统一溯源端点响应契约（formula-hub-integrity-closure 需求 9.1~9.3）。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.locate_target import LocateTargetSchema


class LineageSourceError(BaseModel):
    """单个溯源子源的可见错误；主响应仍可携带其他子源结果。"""

    source: str = Field(..., description="失败的子源")
    message: str = Field(..., description="中文错误说明")
    status: int = Field(default=500, description="子源错误状态")
    error_code: str = Field(default="LINEAGE_SOURCE_FAILED", description="稳定错误码")


class LineageAttachmentRef(BaseModel):
    """与当前对象关联的附件。"""

    id: str
    attachment_id: str
    target_type: str
    target_ref: str
    file_name: str | None = None
    file_type: str | None = None
    created_at: str | None = None


class UnifiedLineageResponse(BaseModel):
    """统一溯源响应；``partial`` 只表示至少一个实际执行的子源失败。"""

    current: LocateTargetSchema
    upstream: list[LocateTargetSchema]
    downstream: list[LocateTargetSchema]
    attachments: list[LineageAttachmentRef]
    partial: bool = False
    errors: list[LineageSourceError] = Field(default_factory=list)
