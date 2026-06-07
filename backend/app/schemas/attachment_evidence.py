"""附件证据属性 Pydantic schema (P0-3, ADR-029: metadata JSON)."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


class AttachmentEvidenceMetadata(BaseModel):
    """附件证据属性元数据（存储在 ocr_fields_cache.evidence 子键中）。"""

    source: Optional[str] = None  # 来源：客户提供 / 第三方获取 / 自行编制
    obtained_date: Optional[date] = None  # 取得日期
    provider: Optional[str] = None  # 提供方
    is_key_evidence: bool = False  # 是否关键证据
    linked_workpapers: list[str] = []  # 关联底稿 ID 列表
    reference_count: int = 0  # 被引用次数


class AttachmentImpactItem(BaseModel):
    """单条引用影响记录。"""

    module: str  # 引用模块：workpaper / report / note / review
    module_id: str  # 模块记录 ID
    module_label: str  # 展示名称
    route: Optional[str] = None  # 前端可跳转路由


class AttachmentImpactResult(BaseModel):
    """附件影响范围查询结果。"""

    project_id: str
    attachment_id: str
    file_name: Optional[str] = None
    is_key_evidence: bool = False
    references_count: int = 0
    referenced_by: list[AttachmentImpactItem] = []
    requires_confirmation: bool = False  # 是否需要用户确认才能删除
