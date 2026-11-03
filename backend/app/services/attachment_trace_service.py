"""统一溯源中的附件子源。

底稿附件直接读取 ``EvidenceLink``、``AttachmentWorkingPaper`` 和兼容 reference 真源；
报表、附注、交付件等输出对象读取 ``AttachmentLineage``。底稿关系不再要求影子双写。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_lineage_model import AttachmentLineage
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.wp_optimization_models import EvidenceLink
from app.services.attachment_lineage_schema import (
    AttachmentLineageMigrationPending,
    lineage_project_column_ready,
)

TARGET_BY_OBJECT = {
    "wp_cell": "wp_cell",
    "report_row": "report_row",
    "note_cell": "note_section",
    "deliverable_section": "deliverable_section",
    "tb_row": "tb_row",
    "adjustment": "adjustment",
}


class AttachmentTraceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def for_object(
        self, project_id: UUID, object_type: str, object_id: str,
    ) -> list[dict[str, Any]]:
        if object_type == "wp_cell":
            direct = await self._workpaper_attachments(project_id, object_id)
            # 兼容历史手工 wp_cell lineage；迁移未就绪仍如实 partial，而不是静默漏数据。
            lineage = await self._lineage_attachments(project_id, object_type, object_id)
            return self._dedupe([*direct, *lineage])
        return await self._lineage_attachments(project_id, object_type, object_id)

    async def _resolve_workpaper(
        self, project_id: UUID, object_id: str,
    ) -> tuple[UUID, str, str | None, str | None] | None:
        from app.models.workpaper_models import WorkingPaper, WpIndex

        sheet_name: str | None = None
        cell_ref: str | None = None
        identifier = object_id
        if "!" in object_id:
            identifier, cell_ref = object_id.split("!", 1)
        elif object_id.count(":") >= 2:
            identifier, sheet_name, cell_ref = object_id.split(":", 2)
        try:
            wp_id = UUID(identifier)
        except (ValueError, TypeError):
            wp_id = None
        predicate = WorkingPaper.id == wp_id if wp_id else WpIndex.wp_code == identifier
        row = (await self.db.execute(
            sa.select(WorkingPaper.id, WpIndex.wp_code)
            .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == sa.false(),
                predicate,
            )
            .limit(1)
        )).first()
        if row is None:
            return None
        return row.id, str(row.wp_code or identifier), sheet_name, cell_ref

    async def _workpaper_attachments(
        self, project_id: UUID, object_id: str,
    ) -> list[dict[str, Any]]:
        resolved = await self._resolve_workpaper(project_id, object_id)
        if resolved is None:
            return []
        wp_id, wp_code, sheet_name, cell_ref = resolved
        target_ref = object_id
        rows: list[dict[str, Any]] = []

        evidence_stmt = (
            sa.select(EvidenceLink, Attachment)
            .join(Attachment, Attachment.id == EvidenceLink.attachment_id)
            .where(
                EvidenceLink.wp_id == wp_id,
                Attachment.project_id == project_id,
                Attachment.is_deleted == sa.false(),
            )
            .order_by(EvidenceLink.created_at.desc(), EvidenceLink.id)
        )
        if sheet_name is not None:
            evidence_stmt = evidence_stmt.where(EvidenceLink.sheet_name == sheet_name)
        if cell_ref is not None:
            evidence_stmt = evidence_stmt.where(EvidenceLink.cell_ref == cell_ref)
        for link, attachment in (await self.db.execute(evidence_stmt)).all():
            rows.append(self._row(
                relation_id=link.id, attachment=attachment, target_type="wp_cell",
                target_ref=target_ref, created_at=link.created_at, source="evidence_link",
            ))

        # 整稿关系对该底稿所有单元格均构成上位证据。
        whole = (await self.db.execute(
            sa.select(AttachmentWorkingPaper, Attachment)
            .join(Attachment, Attachment.id == AttachmentWorkingPaper.attachment_id)
            .where(
                AttachmentWorkingPaper.wp_id == wp_id,
                Attachment.project_id == project_id,
                Attachment.is_deleted == sa.false(),
            )
            .order_by(AttachmentWorkingPaper.created_at.desc(), AttachmentWorkingPaper.id)
        )).all()
        for link, attachment in whole:
            rows.append(self._row(
                relation_id=link.id, attachment=attachment, target_type="wp_cell",
                target_ref=wp_code, created_at=link.created_at, source="workpaper_link",
            ))

        references = (await self.db.execute(
            sa.select(Attachment).where(
                Attachment.project_id == project_id,
                Attachment.reference_type == "working_paper",
                Attachment.reference_id == wp_id,
                Attachment.is_deleted == sa.false(),
            ).order_by(Attachment.created_at.desc(), Attachment.id)
        )).scalars().all()
        for attachment in references:
            rows.append(self._row(
                relation_id=attachment.id, attachment=attachment, target_type="wp_cell",
                target_ref=wp_code, created_at=attachment.created_at, source="reference",
            ))
        return self._dedupe(rows)

    async def _lineage_attachments(
        self, project_id: UUID, object_type: str, object_id: str,
    ) -> list[dict[str, Any]]:
        if not await lineage_project_column_ready(self.db):
            raise AttachmentLineageMigrationPending()
        target_type = TARGET_BY_OBJECT.get(object_type, object_type)
        ref_match = AttachmentLineage.target_ref == object_id
        if "!" not in object_id:
            ref_match = sa.or_(
                ref_match,
                AttachmentLineage.target_ref.startswith(f"{object_id}!", autoescape=True),
            )
        query = (
            sa.select(AttachmentLineage, Attachment)
            .join(Attachment, Attachment.id == AttachmentLineage.attachment_id)
            .where(
                AttachmentLineage.project_id == project_id,
                AttachmentLineage.target_type == target_type,
                ref_match,
                Attachment.project_id == project_id,
                Attachment.is_deleted == sa.false(),
            )
            .order_by(AttachmentLineage.created_at.desc(), AttachmentLineage.id)
            .limit(20)
        )
        return [
            self._row(
                relation_id=lineage.id,
                attachment=attachment,
                target_type=lineage.target_type,
                target_ref=lineage.target_ref or object_id,
                created_at=lineage.created_at,
                source="attachment_lineage",
            )
            for lineage, attachment in (await self.db.execute(query)).all()
        ]

    @staticmethod
    def _row(*, relation_id, attachment, target_type, target_ref, created_at, source) -> dict[str, Any]:
        return {
            "id": str(relation_id),
            "attachment_id": str(attachment.id),
            "target_type": target_type,
            "target_ref": target_ref,
            "file_name": attachment.file_name,
            "file_type": attachment.file_type,
            "created_at": created_at.isoformat() if created_at else None,
            "source": source,
        }

    @staticmethod
    def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_attachment: dict[str, dict[str, Any]] = {}
        for row in rows:
            existing = by_attachment.get(row["attachment_id"])
            if existing is None:
                by_attachment[row["attachment_id"]] = row
                continue
            sources = existing.setdefault("sources", [existing.get("source")])
            if row.get("source") not in sources:
                sources.append(row.get("source"))
        return list(by_attachment.values())
