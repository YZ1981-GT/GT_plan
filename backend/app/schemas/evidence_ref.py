"""EvidenceRef 统一证据引用 schema (MVP DTO, 不立即入库)."""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class EvidenceType(str, Enum):
    attachment = "attachment"
    workpaper_cell = "workpaper_cell"
    report_paragraph = "report_paragraph"
    note_table = "note_table"
    ai_output = "ai_output"
    deliverable = "deliverable"


class EvidenceRef(BaseModel):
    evidence_type: EvidenceType
    evidence_id: str
    project_id: str
    year: Optional[int] = None
    label: Optional[str] = None
    route: Optional[str] = None
    hash: Optional[str] = None
    version: Optional[str] = None
