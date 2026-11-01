"""调整分录对通用 EvidenceRef 的只读投影与批准前置门。"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence_governance_models import EvidenceRef
from app.services.evidence_governance.typed_adapters import get_adapter


class AdjustmentEvidenceError(ValueError):
    def __init__(self, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


async def active_adjustment_evidence(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    entry_group_id: UUID,
) -> list[dict[str, Any]]:
    """返回当前仍能按 typed adapter 解析的活动证据引用。"""
    rows = list((await db.execute(sa.select(EvidenceRef).where(
        EvidenceRef.project_id == project_id,
        EvidenceRef.audit_year == year,
        EvidenceRef.source_type == "adjustment",
        EvidenceRef.source_id == str(entry_group_id),
        EvidenceRef.status == "active",
    ).order_by(EvidenceRef.created_at, EvidenceRef.id))).scalars().all())
    result: list[dict[str, Any]] = []
    allowed_types = {"attachment_version", "voucher", "workpaper_cell", "confirmation", "review_opinion"}
    for row in rows:
        if row.evidence_type not in allowed_types:
            continue
        if row.evidence_type == "attachment_version":
            from app.models.evidence_governance_models import AttachmentVersion
            version_id = row.attachment_version_id
            if version_id is None:
                try:
                    version_id = UUID(row.evidence_id)
                except (TypeError, ValueError):
                    continue
            target = (await db.execute(sa.select(AttachmentVersion.id).where(
                AttachmentVersion.id == version_id,
                AttachmentVersion.project_id == project_id,
                AttachmentVersion.audit_year == year,
                AttachmentVersion.availability.in_(("staged", "available")),
            ))).first()
        else:
            target = await get_adapter(row.evidence_type).resolve(
                row.evidence_id, project_id=project_id, audit_year=year, db=db,
            )
        if target is None:
            continue
        result.append({
            "id": str(row.id),
            "evidence_type": row.evidence_type,
            "evidence_id": row.evidence_id,
            "attachment_version_id": str(row.attachment_version_id) if row.attachment_version_id else None,
            "target_version": row.target_version,
            "target_hash": row.target_hash,
            "label": row.label or getattr(target, "display_label", None),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return result


async def require_adjustment_evidence(
    db: AsyncSession, *, project_id: UUID, year: int, entry_group_id: UUID,
) -> list[dict[str, Any]]:
    evidence = await active_adjustment_evidence(
        db, project_id=project_id, year=year, entry_group_id=entry_group_id,
    )
    if not evidence:
        raise AdjustmentEvidenceError(
            "ADJUSTMENT_EVIDENCE_REQUIRED",
            "重大或高风险调整必须先关联有效附件版本或凭证证据",
        )
    return evidence
