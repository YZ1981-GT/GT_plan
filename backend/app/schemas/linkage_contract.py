"""LinkageContract 统一数据联动契约 schema (MVP)."""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class SourceType(str, Enum):
    trial_balance = "trial_balance"
    ledger = "ledger"
    audit_sheet = "audit_sheet"
    workpaper = "workpaper"
    adjustment = "adjustment"
    report = "report"
    note = "note"
    attachment = "attachment"
    ai = "ai"


class TargetType(str, Enum):
    trial_balance = "trial_balance"
    ledger = "ledger"
    audit_sheet = "audit_sheet"
    workpaper = "workpaper"
    adjustment = "adjustment"
    report = "report"
    note = "note"
    attachment = "attachment"
    ai = "ai"


class LinkageStatus(str, Enum):
    current = "current"
    stale = "stale"
    conflict = "conflict"
    manual_override = "manual_override"


class LinkageConfidence(str, Enum):
    system = "system"
    manual = "manual"
    ai_suggested = "ai_suggested"
    ai_confirmed = "ai_confirmed"


class LinkageContract(BaseModel):
    source_type: SourceType
    source_id: str
    source_cell: Optional[str] = None
    target_type: TargetType
    target_id: str
    target_cell: Optional[str] = None
    amount: Optional[str] = None  # Decimal as string
    basis: Optional[str] = None
    status: LinkageStatus = LinkageStatus.current
    confidence: LinkageConfidence = LinkageConfidence.system
    route: Optional[str] = None
    audit_log_id: Optional[str] = None
