"""EvidenceRef 统一证据引用 schema (P0 DTO + 路由解析)."""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, model_validator


class EvidenceType(str, Enum):
    attachment = "attachment"
    workpaper_cell = "workpaper_cell"
    report_paragraph = "report_paragraph"
    note_table = "note_table"
    ai_output = "ai_output"
    deliverable = "deliverable"


# 各 evidence_type 对应的前端路由模板
_ROUTE_TEMPLATES: dict[str, str] = {
    "attachment": "/projects/{project_id}/attachments/{evidence_id}",
    "workpaper_cell": "/projects/{project_id}/workpapers/{evidence_id}",
    "report_paragraph": "/projects/{project_id}/report/{evidence_id}",
    "note_table": "/projects/{project_id}/notes/{evidence_id}",
    "ai_output": "/projects/{project_id}/ai-content/{evidence_id}",
    "deliverable": "/projects/{project_id}/deliverables/{evidence_id}",
}


class EvidenceRef(BaseModel):
    """统一证据引用结构。

    支持 6 种证据类型，可自动生成跳转路由。
    """

    evidence_type: EvidenceType
    evidence_id: str
    project_id: str
    year: Optional[int] = None
    label: Optional[str] = None
    route: Optional[str] = None
    hash: Optional[str] = None
    version: Optional[str] = None

    @model_validator(mode="after")
    def _auto_route(self) -> "EvidenceRef":
        """若 route 未显式指定，根据 evidence_type 自动生成。"""
        if not self.route:
            template = _ROUTE_TEMPLATES.get(self.evidence_type.value, "")
            if template:
                self.route = template.format(
                    project_id=self.project_id,
                    evidence_id=self.evidence_id,
                )
        return self

    def resolve_route(self) -> str:
        """解析并返回可跳转的前端路由。"""
        if self.route:
            return self.route
        template = _ROUTE_TEMPLATES.get(self.evidence_type.value, "")
        return template.format(
            project_id=self.project_id,
            evidence_id=self.evidence_id,
        )


def resolve_evidence_route(ref: EvidenceRef) -> str:
    """根据 EvidenceRef 解析前端跳转路由（独立工具函数）。"""
    return ref.resolve_route()
